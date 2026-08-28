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
    OutboxEvent,
    PermissionGrant,
    UploadEvent,
    UploadObject,
    UploadPart,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import DEV_API_KEY_VALUE
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app


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
        "task_name": "robot-run-device",
        "task_initiator": "device",
        "objects": [
            {
                "dataset_name": "robot-run-device",
                "object_name": "robot-run-device.hdf5",
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
        aggregate_ids = [*task_ids, *object_ids, *dataset_ids, *session_ids]
        if aggregate_ids:
            session.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(aggregate_ids)))
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
