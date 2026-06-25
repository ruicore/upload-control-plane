from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.api.auth import get_db_session
from upload_control_plane.api.request_context import REQUEST_ID_HEADER
from upload_control_plane.api.upload_tasks import get_object_storage
from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompletedObject,
    CompleteMultipartUploadRequest,
    CreateMultipartUploadRequest,
    CreateMultipartUploadResult,
    HeadObjectRequest,
    HeadObjectResult,
    ListedPartsPage,
    ListPartsRequest,
    PresignedPartUrl,
    PresignUploadPartRequest,
    StorageCapabilities,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    Device,
    DeviceCredential,
    IdempotencyRecord,
    PermissionGrant,
    UploadEvent,
    UploadObject,
    UploadPart,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import (
    DEV_API_KEY_VALUE,
    build_dev_seed_result,
    seed_dev_data,
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app


def test_device_register_returns_credential_once_and_get_does_not_reveal_secret() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    device_code = f"robot-t10-{uuid.uuid4()}"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DeviceFakeObjectStorage())
        registered = _register_device(client, seed.project_id, device_code)

        assert registered.status_code == 201
        body = registered.json()
        device_id = uuid.UUID(body["device"]["device_id"])
        credential = body["credential"]
        assert credential["credential_material"].startswith("ucp_device_")
        assert credential["credential_version"] == 1

        fetched = client.get(
            f"/v1/projects/{seed.project_id}/devices/{device_id}",
            headers=_api_headers("req-device-get"),
        )
        assert fetched.status_code == 200
        assert "credential" not in fetched.json()
        assert "credential_material" not in str(fetched.json())

        with _session_scope(session_factory) as session:
            stored = session.get(DeviceCredential, uuid.UUID(credential["credential_id"]))
            assert stored is not None
            assert credential["credential_material"] not in stored.credential_hash
            assert stored.credential_hash.startswith("sha256:")
    finally:
        _delete_devices_by_code(session_factory, device_code)


def test_device_upload_creates_ordinary_upload_task_session_and_uuid_source_device() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DeviceFakeObjectStorage()
    device_code = f"robot-t10-upload-{uuid.uuid4()}"
    idempotency_key = "idem-device-upload"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        registered = _register_device(client, seed.project_id, device_code).json()
        device_id = uuid.UUID(registered["device"]["device_id"])
        credential = registered["credential"]["credential_material"]

        response = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-upload", credential),
                "Idempotency-Key": idempotency_key,
            },
            json=_upload_payload(source_device_code="spoofed-code"),
        )

        assert response.status_code == 201
        body = response.json()
        created = body["objects"][0]
        assert storage.create_calls
        with _session_scope(session_factory) as session:
            task = session.get(UploadTask, uuid.UUID(body["task_id"]))
            upload_session = session.get(UploadSession, uuid.UUID(created["session_id"]))
            dataset = session.get(Dataset, uuid.UUID(created["dataset_id"]))
        assert task is not None
        assert upload_session is not None
        assert dataset is not None
        assert task.source_device_id == device_id
        assert upload_session.source_device_id == device_id
        assert dataset.source_device_id == device_id
        assert task.source_device_code == device_code
        assert upload_session.source_device_code == device_code
        assert dataset.source_device_code == device_code
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
        _delete_devices_by_code(session_factory, device_code)


def test_disabled_device_credential_cannot_create_upload_or_presign() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DeviceFakeObjectStorage()
    device_code = f"robot-t10-disabled-{uuid.uuid4()}"
    idempotency_key = "idem-device-disabled-before"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        registered = _register_device(client, seed.project_id, device_code).json()
        device_id = uuid.UUID(registered["device"]["device_id"])
        credential = registered["credential"]["credential_material"]
        created = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-upload-before-disable", credential),
                "Idempotency-Key": idempotency_key,
            },
            json=_upload_payload(),
        )
        assert created.status_code == 201
        session_id = created.json()["objects"][0]["session_id"]

        disabled = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/disable",
            headers=_api_headers("req-device-disable"),
        )
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "DISABLED"

        upload = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-upload-disabled", credential),
                "Idempotency-Key": "idem-device-disabled-after",
            },
            json=_upload_payload(),
        )
        presign = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_device_headers("req-device-presign-disabled", credential),
            json={"part_numbers": [1]},
        )

        assert upload.status_code == 403
        assert upload.json()["error"]["code"] == "device.inactive"
        assert presign.status_code == 403
        assert presign.json()["error"]["code"] == "device.inactive"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key, "idem-device-disabled-after")
        _delete_devices_by_code(session_factory, device_code)


def test_rotation_revokes_old_credential_without_overlap_and_new_credential_can_upload() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DeviceFakeObjectStorage()
    device_code = f"robot-t10-rotate-{uuid.uuid4()}"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        registered = _register_device(client, seed.project_id, device_code).json()
        device_id = uuid.UUID(registered["device"]["device_id"])
        old_credential = registered["credential"]["credential_material"]
        rotated = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/credentials/rotate",
            headers=_api_headers("req-device-rotate"),
            json={"overlap_seconds": 0},
        )
        assert rotated.status_code == 200
        new_credential = rotated.json()["credential"]["credential_material"]
        assert new_credential != old_credential

        old_upload = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-old-revoked", old_credential),
                "Idempotency-Key": "idem-device-old-revoked",
            },
            json=_upload_payload(),
        )
        new_upload = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-new-credential", new_credential),
                "Idempotency-Key": "idem-device-new-credential",
            },
            json=_upload_payload(),
        )

        assert old_upload.status_code == 401
        assert old_upload.json()["error"]["code"] == "device.credential_revoked"
        assert new_upload.status_code == 201
    finally:
        _delete_upload_artifacts(
            session_factory,
            "idem-device-old-revoked",
            "idem-device-new-credential",
        )
        _delete_devices_by_code(session_factory, device_code)


def test_expired_device_credential_cannot_upload() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    device_code = f"robot-t10-expired-{uuid.uuid4()}"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DeviceFakeObjectStorage())
        registered = _register_device(client, seed.project_id, device_code).json()
        credential = registered["credential"]["credential_material"]
        credential_id = uuid.UUID(registered["credential"]["credential_id"])
        device_id = registered["device"]["device_id"]
        with _session_scope(session_factory) as session:
            stored = session.get(DeviceCredential, credential_id)
            assert stored is not None
            stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        response = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-expired", credential),
                "Idempotency-Key": "idem-device-expired",
            },
            json=_upload_payload(),
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "device.credential_expired"
    finally:
        _delete_upload_artifacts(session_factory, "idem-device-expired")
        _delete_devices_by_code(session_factory, device_code)


def test_source_device_code_only_is_metadata_and_not_authorization_subject() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DeviceFakeObjectStorage()
    idempotency_key = "idem-source-code-only"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_api_headers("req-source-code-only"), "Idempotency-Key": idempotency_key},
            json=_upload_payload(source_device_code="unregistered-text-code"),
        )

        assert response.status_code == 201
        created = response.json()["objects"][0]
        with _session_scope(session_factory) as session:
            task = session.get(UploadTask, uuid.UUID(response.json()["task_id"]))
            upload_session = session.get(UploadSession, uuid.UUID(created["session_id"]))
            dataset = session.get(Dataset, uuid.UUID(created["dataset_id"]))
        assert task is not None
        assert upload_session is not None
        assert dataset is not None
        assert task.source_device_id is None
        assert upload_session.source_device_id is None
        assert dataset.source_device_id is None
        assert task.source_device_code == "unregistered-text-code"
        assert upload_session.source_device_code == "unregistered-text-code"
        assert dataset.source_device_code == "unregistered-text-code"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def _register_device(client: TestClient, project_id: uuid.UUID, device_code: str) -> Any:
    return client.post(
        f"/v1/projects/{project_id}/devices",
        headers=_api_headers("req-device-register"),
        json={
            "name": device_code,
            "device_code": device_code,
            "device_type": "robot",
            "metadata": {"line": "3"},
        },
    )


def _upload_payload(*, source_device_code: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task_name": "robot-run-t10",
        "task_initiator": "device",
        "objects": [
            {
                "dataset_name": "robot-run-t10",
                "object_name": "robot-run-t10.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
                "part_size_bytes": DEFAULT_PART_SIZE,
            }
        ],
        "metadata": {"site": "factory-shanghai"},
    }
    if source_device_code is not None:
        payload["source_device_code"] = source_device_code
    return payload


def _db_session_factory_or_skip() -> sessionmaker[Session]:
    settings = get_settings()
    url = make_url(settings.database_url)
    host = url.host or "localhost"
    port = url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1):
            pass
    except OSError as exc:
        pytest.skip(f"PostgreSQL integration database is not reachable at {host}:{port}: {exc}")

    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
    except (OperationalError, ProgrammingError) as exc:
        pytest.skip(f"PostgreSQL integration database is not available or migrated: {exc}")
    return build_session_factory(engine)


def _client(
    session_factory: sessionmaker[Session],
    *,
    storage: DeviceFakeObjectStorage,
) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_object_storage] = lambda: storage
    return TestClient(app)


def _api_headers(request_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DEV_API_KEY_VALUE}",
        REQUEST_ID_HEADER: request_id,
    }


def _device_headers(request_id: str, credential: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {credential}",
        REQUEST_ID_HEADER: request_id,
    }


@contextmanager
def _session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _delete_devices_by_code(session_factory: sessionmaker[Session], *device_codes: str) -> None:
    with _session_scope(session_factory) as session:
        device_ids = list(
            session.scalars(select(Device.id).where(Device.device_code.in_(device_codes)))
        )
        if not device_ids:
            return
        session.execute(
            delete(AuditEvent).where(AuditEvent.resource_id.in_([str(i) for i in device_ids]))
        )
        session.execute(delete(PermissionGrant).where(PermissionGrant.subject_id.in_(device_ids)))
        session.execute(delete(DeviceCredential).where(DeviceCredential.device_id.in_(device_ids)))
        session.execute(delete(Device).where(Device.id.in_(device_ids)))


def _delete_upload_artifacts(
    session_factory: sessionmaker[Session],
    *idempotency_keys: str,
) -> None:
    with _session_scope(session_factory) as session:
        task_ids = list(
            session.scalars(
                select(UploadTask.id).where(UploadTask.idempotency_key.in_(idempotency_keys))
            )
        )
        if not task_ids:
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.key.in_(idempotency_keys))
            )
            return
        object_ids = list(
            session.scalars(
                select(UploadObject.id).where(UploadObject.upload_task_id.in_(task_ids))
            )
        )
        dataset_ids = list(
            session.scalars(
                select(UploadObject.dataset_id).where(UploadObject.upload_task_id.in_(task_ids))
            )
        )
        session_ids = list(
            session.scalars(
                select(UploadSession.id).where(UploadSession.upload_task_id.in_(task_ids))
            )
        )
        if session_ids:
            session.execute(delete(UploadPart).where(UploadPart.session_id.in_(session_ids)))
        session.execute(delete(UploadEvent).where(UploadEvent.upload_task_id.in_(task_ids)))
        session.execute(
            delete(AuditEvent)
            .where(AuditEvent.resource_type == "upload_task")
            .where(AuditEvent.resource_id.in_(str(task_id) for task_id in task_ids))
        )
        session.execute(delete(UploadSession).where(UploadSession.upload_task_id.in_(task_ids)))
        if object_ids:
            session.execute(delete(UploadObject).where(UploadObject.id.in_(object_ids)))
        session.execute(delete(UploadTask).where(UploadTask.id.in_(task_ids)))
        if dataset_ids:
            session.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
        session.execute(
            delete(IdempotencyRecord).where(IdempotencyRecord.key.in_(idempotency_keys))
        )


class DeviceFakeObjectStorage:
    def __init__(self) -> None:
        self.create_calls: list[CreateMultipartUploadRequest] = []
        self.presign_calls: list[PresignUploadPartRequest] = []

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities()

    def create_multipart_upload(
        self,
        request: CreateMultipartUploadRequest,
    ) -> CreateMultipartUploadResult:
        self.create_calls.append(request)
        return CreateMultipartUploadResult(upload_id=f"fake-device-upload-{len(self.create_calls)}")

    def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
        self.presign_calls.append(request)
        return PresignedPartUrl(
            part_number=request.part_number,
            url=(
                f"http://storage.local/{request.bucket}/{request.object_key}"
                f"?partNumber={request.part_number}&uploadId={request.upload_id}&signature=redacted"
            ),
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
            required_headers={},
        )

    def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
        _ = request
        return ListedPartsPage(parts=())

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        return CompletedObject(bucket=request.bucket, object_key=request.object_key)

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        _ = request

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        return HeadObjectResult(
            bucket=request.bucket,
            object_key=request.object_key,
            etag='"etag"',
            size_bytes=DEFAULT_PART_SIZE,
        )
