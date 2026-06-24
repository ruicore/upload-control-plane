from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

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
    ListedPart,
    ListedPartsPage,
    ListPartsRequest,
    PresignedPartUrl,
    PresignUploadPartRequest,
    StorageCapabilities,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    IdempotencyRecord,
    PermissionGrant,
    Tenant,
    UploadEvent,
    UploadObject,
    UploadPart,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import (
    DEV_API_KEY_VALUE,
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app


def test_runtime_status_presign_ack_and_db_list_parts() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-happy"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        created_object = _created_object(created)
        session_id = uuid.UUID(created_object["session_id"])

        status = client.get(f"/v1/uploads/{session_id}", headers=_auth_headers("req-status"))
        assert status.status_code == 200
        assert status.json()["status"] == "INITIATED"
        assert status.json()["uploaded_part_count"] == 0

        presign = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign"),
            json={"part_numbers": [1], "expires_in_seconds": 600},
        )
        assert presign.status_code == 200
        presign_body = presign.json()
        assert presign_body["method"] == "PUT"
        assert presign_body["parts"][0]["part_number"] == 1
        assert "fake-signature" in presign_body["parts"][0]["url"]
        assert storage.presign_calls == [(created_object["bucket"], 1, 600)]

        with _session_scope(session_factory) as session:
            part = session.get(UploadPart, (session_id, 1))
            upload_session = session.get(UploadSession, session_id)
            assert part is not None
            assert upload_session is not None
            assert part.status == "PRESIGNED"
            assert part.last_presigned_at is not None
            assert part.presign_expires_at is not None
            assert upload_session.status == "UPLOADING"

        ack = client.post(
            f"/v1/uploads/{session_id}/parts/ack",
            headers=_auth_headers("req-ack"),
            json={
                "parts": [
                    {
                        "part_number": 1,
                        "etag": '"etag-1"',
                        "size_bytes": DEFAULT_PART_SIZE,
                    }
                ]
            },
        )
        assert ack.status_code == 200
        assert ack.json() == {
            "session_id": str(session_id),
            "acknowledged_part_count": 1,
            "uploaded_part_count": 1,
        }

        second_ack = client.post(
            f"/v1/uploads/{session_id}/parts/ack",
            headers=_auth_headers("req-ack-retry"),
            json={
                "parts": [
                    {
                        "part_number": 1,
                        "etag": '"etag-1"',
                        "size_bytes": DEFAULT_PART_SIZE,
                    }
                ]
            },
        )
        assert second_ack.status_code == 200
        assert second_ack.json()["uploaded_part_count"] == 1

        parts = client.get(
            f"/v1/uploads/{session_id}/parts?source=db",
            headers=_auth_headers("req-list-db"),
        )
        assert parts.status_code == 200
        assert parts.json()["uploaded_part_count"] == 1
        assert parts.json()["missing_part_numbers"] == []
        assert parts.json()["parts"][0]["status"] == "UPLOADED"

        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            assert upload_session.status == "UPLOADING"
            assert upload_session.completed_at is None
            assert upload_session.object_etag is None
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_presign_rejects_paused_session() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-paused"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            upload_session.status = "PAUSED"

        response = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-paused"),
            json={"part_numbers": [1]},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "upload.invalid_state"
        assert storage.presign_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_runtime_re_evaluates_current_permissions() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-permission"
    deny_grants = (
        dev_seed_uuid("test-grant:runtime-deny-dataset-upload"),
        dev_seed_uuid("test-grant:runtime-deny-upload-create"),
    )
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        with _session_scope(session_factory) as session:
            _upsert_grant(
                session,
                grant_id=deny_grants[0],
                resource_id=seed.project_id,
                permission_code="dataset.upload",
                effect="DENY",
            )
            _upsert_grant(
                session,
                grant_id=deny_grants[1],
                resource_id=seed.project_id,
                permission_code="upload.create",
                effect="DENY",
            )

        response = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-denied"),
            json={"part_numbers": [1]},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization.permission_denied"
        assert storage.presign_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
        _delete_test_grants(session_factory, *deny_grants)


def test_runtime_session_tenant_isolation_returns_not_found_before_permission_check() -> None:
    session_factory = _db_session_factory_or_skip()
    foreign_tenant_id = dev_seed_uuid("test-tenant:runtime-foreign")
    foreign_session_id = dev_seed_uuid("test-session:runtime-foreign")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        tenant = session.get(Tenant, foreign_tenant_id)
        if tenant is None:
            tenant = Tenant(id=foreign_tenant_id)
            session.add(tenant)
        tenant.slug = "runtime-foreign"
        tenant.name = "Runtime Foreign"
        tenant.status = "ACTIVE"
        session.add(
            UploadSession(
                id=foreign_session_id,
                tenant_id=foreign_tenant_id,
                status="INITIATED",
                bucket_name="foreign-bucket",
                object_key=f"foreign/{foreign_session_id}",
                storage_provider="minio",
                storage_upload_id="foreign-upload",
                original_filename="foreign.bin",
                file_size_bytes=DEFAULT_PART_SIZE,
                part_size_bytes=DEFAULT_PART_SIZE,
                part_count=1,
                checksum_mode="CLIENT_REPORTED",
                metadata_={},
                uploaded_part_count=0,
                completed_part_count=0,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )

    try:
        client = _client(session_factory, storage=RuntimeFakeObjectStorage())
        response = client.get(
            f"/v1/uploads/{foreign_session_id}",
            headers=_auth_headers("req-foreign-session"),
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "upload_session.not_found"
    finally:
        with _session_scope(session_factory) as session:
            session.execute(delete(UploadSession).where(UploadSession.id == foreign_session_id))
            session.execute(delete(Tenant).where(Tenant.id == foreign_tenant_id))


def test_storage_and_reconcile_sources_use_object_storage_list_parts() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-reconcile"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        storage_only = client.get(
            f"/v1/uploads/{session_id}/parts?source=storage",
            headers=_auth_headers("req-list-storage"),
        )
        assert storage_only.status_code == 200
        assert storage_only.json()["uploaded_part_count"] == 1
        with _session_scope(session_factory) as session:
            assert session.get(UploadPart, (session_id, 1)) is None

        reconciled = client.get(
            f"/v1/uploads/{session_id}/parts?source=reconcile",
            headers=_auth_headers("req-list-reconcile"),
        )
        assert reconciled.status_code == 200
        assert reconciled.json()["uploaded_part_count"] == 1
        with _session_scope(session_factory) as session:
            part = session.get(UploadPart, (session_id, 1))
            assert part is not None
            assert part.etag == '"storage-etag"'
            assert part.source == "storage"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def _create_upload_task(
    client: TestClient,
    project_id: uuid.UUID,
    idempotency_key: str,
) -> dict[str, Any]:
    response = client.post(
        f"/v1/projects/{project_id}/upload-tasks",
        headers={
            **_auth_headers(f"req-create-{idempotency_key}"),
            "Idempotency-Key": idempotency_key,
        },
        json={
            "task_name": f"runtime-{idempotency_key}",
            "task_initiator": "api",
            "objects": [
                {
                    "dataset_name": f"runtime-{idempotency_key}",
                    "object_name": f"runtime-{idempotency_key}.bin",
                    "file_size_bytes": DEFAULT_PART_SIZE,
                    "part_size_bytes": DEFAULT_PART_SIZE,
                }
            ],
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def _created_object(created: dict[str, Any]) -> dict[str, Any]:
    objects = created["objects"]
    assert isinstance(objects, list)
    first = objects[0]
    assert isinstance(first, dict)
    return first


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
    storage: RuntimeFakeObjectStorage,
) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_object_storage] = lambda: storage
    return TestClient(app)


def _auth_headers(request_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DEV_API_KEY_VALUE}",
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


def _upsert_grant(
    session: Session,
    *,
    grant_id: uuid.UUID,
    resource_id: uuid.UUID,
    permission_code: str,
    effect: str = "ALLOW",
) -> None:
    seed = build_dev_seed_result()
    grant = session.get(PermissionGrant, grant_id)
    if grant is None:
        grant = PermissionGrant(id=grant_id)
        session.add(grant)
    grant.tenant_id = seed.tenant_id
    grant.subject_type = "api_key"
    grant.subject_id = seed.api_key_id
    grant.resource_type = "project"
    grant.resource_id = resource_id
    grant.permission_code = permission_code
    grant.effect = effect
    grant.conditions = {}
    grant.source = "test"
    grant.created_by = seed.api_key_id
    grant.expires_at = datetime.now(UTC) + timedelta(hours=1)


def _delete_test_grants(session_factory: sessionmaker[Session], *grant_ids: uuid.UUID) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(PermissionGrant).where(PermissionGrant.id.in_(grant_ids)))


def _delete_upload_artifacts(session_factory: sessionmaker[Session], idempotency_key: str) -> None:
    with _session_scope(session_factory) as session:
        task_ids = list(
            session.scalars(
                select(UploadTask.id).where(UploadTask.idempotency_key == idempotency_key)
            )
        )
        if not task_ids:
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key)
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
        session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key))


class RuntimeFakeObjectStorage:
    def __init__(self) -> None:
        self.create_calls: list[CreateMultipartUploadRequest] = []
        self.presign_calls: list[tuple[str, int, int]] = []
        self.list_calls: list[ListPartsRequest] = []
        self.listed_parts: tuple[ListedPart, ...] = ()

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities()

    def create_multipart_upload(
        self,
        request: CreateMultipartUploadRequest,
    ) -> CreateMultipartUploadResult:
        self.create_calls.append(request)
        return CreateMultipartUploadResult(upload_id=f"fake-upload-{len(self.create_calls)}")

    def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
        self.presign_calls.append((request.bucket, request.part_number, request.expires_in_seconds))
        return PresignedPartUrl(
            part_number=request.part_number,
            url=(
                f"http://storage.local/{request.bucket}/{request.object_key}"
                f"?partNumber={request.part_number}&uploadId={request.upload_id}&fake-signature=1"
            ),
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
            required_headers={},
        )

    def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
        self.list_calls.append(request)
        return ListedPartsPage(parts=self.listed_parts)

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        raise NotImplementedError

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        raise NotImplementedError

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        raise NotImplementedError
