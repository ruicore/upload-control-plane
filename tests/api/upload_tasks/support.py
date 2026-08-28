from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.api.auth import get_db_session
from upload_control_plane.api.upload_tasks import get_object_storage
from upload_control_plane.config import Settings, get_settings
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
    StorageOperationError,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    IdempotencyRecord,
    OutboxEvent,
    UploadEvent,
    UploadObject,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import DEV_API_KEY_VALUE
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app


def _valid_payload(
    *,
    objects: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "task_name": "robot-run-2026-06-10-line-3",
        "task_initiator": "cli",
        "source_device_code": "robot-17",
        "objects": objects
        or [
            {
                "dataset_name": "front-camera-2026-06-10",
                "object_name": "front_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
                "content_type": "application/x-hdf5",
                "part_size_bytes": DEFAULT_PART_SIZE,
                "checksum_sha256": "a" * 64,
                "metadata": {"camera": "front"},
            }
        ],
        "metadata": {"site": "factory-shanghai"},
    }


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
    storage: FakeObjectStorage | None = None,
    settings: Settings | None = None,
) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    if storage is not None:
        app.dependency_overrides[get_object_storage] = lambda: storage
    return TestClient(app)


def _auth_headers(request_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DEV_API_KEY_VALUE}",
        "X-Request-ID": request_id,
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


def _settings_override(**values: object) -> Settings:
    return get_settings().model_copy(update=values)


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
        session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key))


class FakeObjectStorage:
    def __init__(
        self,
        *,
        capabilities: StorageCapabilities | None = None,
        create_error: StorageOperationError | None = None,
    ) -> None:
        self.create_calls: list[dict[str, str | None]] = []
        self._capabilities = capabilities or StorageCapabilities()
        self._create_error = create_error

    @property
    def capabilities(self) -> StorageCapabilities:
        return self._capabilities

    def create_multipart_upload(
        self,
        request: CreateMultipartUploadRequest,
    ) -> CreateMultipartUploadResult:
        create_call = {
            "bucket": request.bucket,
            "object_key": request.object_key,
            "content_type": request.content_type,
        }
        if request.encryption:
            create_call["encryption_mode"] = request.encryption.get("mode")
        self.create_calls.append(create_call)
        if self._create_error is not None:
            raise self._create_error
        return CreateMultipartUploadResult(upload_id=f"fake-upload-{len(self.create_calls)}")

    def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
        raise NotImplementedError

    def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
        raise NotImplementedError

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        raise NotImplementedError

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        raise NotImplementedError

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        raise NotImplementedError
