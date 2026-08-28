from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.config import Settings, get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompletedObject,
    CompleteMultipartUploadRequest,
    CreateMultipartUploadRequest,
    CreateMultipartUploadResult,
    DeleteObjectRequest,
    HeadObjectRequest,
    HeadObjectResult,
    ListedPartsPage,
    ListPartsRequest,
    PresignDownloadObjectRequest,
    PresignedDownloadUrl,
    PresignedPartUrl,
    PresignUploadPartRequest,
    StorageCapabilities,
    StorageNotFoundError,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    DatasetTag,
    IdempotencyRecord,
    OutboxEvent,
    UploadEvent,
    UploadObject,
    UploadPart,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory


class _GraphIds(tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]):
    @property
    def task_id(self) -> uuid.UUID:
        return self[0]

    @property
    def object_id(self) -> uuid.UUID:
        return self[1]

    @property
    def dataset_id(self) -> uuid.UUID:
        return self[2]

    @property
    def session_id(self) -> uuid.UUID:
        return self[3]


def _insert_upload_graph(
    session: Session,
    *,
    key: str,
    status: str,
    expires_at: datetime,
    dataset_status: str = "UPLOADING",
    recovery_status: str = "NORMAL",
    deleted_at: datetime | None = None,
) -> _GraphIds:
    seed = build_dev_seed_result()
    task_id = dev_seed_uuid(f"test-task:{key}")
    object_id = dev_seed_uuid(f"test-object:{key}")
    dataset_id = dev_seed_uuid(f"test-dataset:{key}")
    session_id = dev_seed_uuid(f"test-session:{key}")
    now = datetime.now(UTC)
    object_key = f"ucp-test-lifecycle/{key}.bin"
    session.add(
        Dataset(
            id=dataset_id,
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            name=key,
            status=dataset_status,
            original_filename=f"{key}.bin",
            content_type="application/octet-stream",
            file_size_bytes=DEFAULT_PART_SIZE,
            bucket_name="robot-data",
            object_key=object_key,
            object_size_bytes=DEFAULT_PART_SIZE,
            validation_status="PASSED",
            recovery_status=recovery_status,
            deleted_at=deleted_at,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        UploadTask(
            id=task_id,
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            storage_policy_id=seed.storage_policy_id,
            status="COMPLETED" if status == "COMPLETED" else "PROCESSING",
            task_initiator="api",
            object_count=1,
            total_size_bytes=DEFAULT_PART_SIZE,
            idempotency_key=key,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    session.add(
        UploadObject(
            id=object_id,
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            dataset_id=dataset_id,
            upload_task_id=task_id,
            status="COMPLETED" if status == "COMPLETED" else "UPLOADING",
            object_name=f"{key}.bin",
            file_size_bytes=DEFAULT_PART_SIZE,
            upload_session_id=session_id,
            created_at=now,
            updated_at=now,
        )
    )
    session.flush()
    session.add(
        UploadSession(
            id=session_id,
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            dataset_id=dataset_id,
            upload_task_id=task_id,
            upload_object_id=object_id,
            status=status,
            bucket_name="robot-data",
            object_key=object_key,
            storage_provider="minio",
            storage_upload_id=f"upload-{key}",
            original_filename=f"{key}.bin",
            content_type="application/octet-stream",
            file_size_bytes=DEFAULT_PART_SIZE,
            part_size_bytes=DEFAULT_PART_SIZE,
            part_count=1,
            object_size_bytes=DEFAULT_PART_SIZE if status == "COMPLETED" else None,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
            completed_at=now if status == "COMPLETED" else None,
        )
    )
    return _GraphIds((task_id, object_id, dataset_id, session_id))


def _test_settings() -> Settings:
    return get_settings().model_copy(
        update={
            "worker_batch_size": 50,
            "expired_session_abort_grace_seconds": 0,
            "default_recycle_retention_days": 30,
        }
    )


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


@contextmanager
def _session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _delete_lifecycle_test_artifacts(session: Session) -> None:
    task_ids = list(
        session.scalars(
            select(UploadTask.id).where(UploadTask.idempotency_key.like("ucp-test-lifecycle-%"))
        )
    )
    dataset_ids = list(
        session.scalars(
            select(Dataset.id).where(
                (Dataset.name.like("ucp-test-lifecycle-%"))
                | (Dataset.object_key.like("ucp-test-lifecycle/%"))
            )
        )
    )
    recovery_outbox_dataset_ids = _worker_lifecycle_recovery_outbox_dataset_ids(session)
    session_ids = list(
        session.scalars(select(UploadSession.id).where(UploadSession.upload_task_id.in_(task_ids)))
    )
    if session_ids:
        session.execute(delete(UploadPart).where(UploadPart.session_id.in_(session_ids)))
        session.execute(delete(UploadEvent).where(UploadEvent.session_id.in_(session_ids)))
        session.execute(delete(UploadSession).where(UploadSession.id.in_(session_ids)))
    if dataset_ids:
        session.execute(delete(DatasetTag).where(DatasetTag.dataset_id.in_(dataset_ids)))
        session.execute(delete(AuditEvent).where(AuditEvent.dataset_id.in_(dataset_ids)))
        session.execute(
            delete(OutboxEvent).where(
                (OutboxEvent.aggregate_type == "dataset")
                & (OutboxEvent.aggregate_id.in_(dataset_ids))
            )
        )
    if recovery_outbox_dataset_ids:
        session.execute(
            delete(OutboxEvent).where(
                (OutboxEvent.aggregate_type == "dataset")
                & (OutboxEvent.event_type == "dataset.recovery_reconcile")
                & (OutboxEvent.aggregate_id.in_(recovery_outbox_dataset_ids))
            )
        )
    if session_ids:
        session.execute(
            delete(OutboxEvent).where(
                (OutboxEvent.aggregate_type == "upload_session")
                & (OutboxEvent.aggregate_id.in_(session_ids))
            )
        )
    if task_ids:
        session.execute(delete(UploadObject).where(UploadObject.upload_task_id.in_(task_ids)))
        session.execute(delete(UploadTask).where(UploadTask.id.in_(task_ids)))
    if dataset_ids:
        session.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
    session.execute(
        delete(IdempotencyRecord).where(IdempotencyRecord.key.like("ucp-test-lifecycle-%"))
    )


def _worker_lifecycle_recovery_outbox_dataset_ids(session: Session) -> list[uuid.UUID]:
    return list(
        session.scalars(
            select(Dataset.id).where(
                or_(
                    Dataset.name.like("ucp-test-lifecycle-%"),
                    Dataset.object_key.like("ucp-test-lifecycle/%"),
                )
            )
        )
    )


class WorkerFakeObjectStorage:
    def __init__(self) -> None:
        self.abort_calls: list[tuple[str, str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []
        self.delete_requests: list[DeleteObjectRequest] = []
        self.download_calls: list[tuple[str, str]] = []
        self.heads: dict[tuple[str, str], int] = {}
        self.head_metadata: dict[tuple[str, str], dict[str, str]] = {}

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities()

    def create_multipart_upload(
        self, request: CreateMultipartUploadRequest
    ) -> CreateMultipartUploadResult:
        return CreateMultipartUploadResult(upload_id=f"fake-{request.object_key}")

    def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
        return PresignedPartUrl(
            part_number=request.part_number,
            url="http://storage.local/upload?signature=1",
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
        )

    def list_parts(self, _request: ListPartsRequest) -> ListedPartsPage:
        return ListedPartsPage(parts=())

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        return CompletedObject(bucket=request.bucket, object_key=request.object_key)

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        self.abort_calls.append((request.bucket, request.object_key, request.upload_id))

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        key = (request.bucket, request.object_key)
        if key not in self.heads:
            raise StorageNotFoundError("not found", operation="head_object", provider_code="404")
        return HeadObjectResult(
            bucket=request.bucket,
            object_key=request.object_key,
            etag='"etag"',
            size_bytes=self.heads[key],
            metadata=self.head_metadata.get(key, {}),
        )

    def presign_download_object(
        self, request: PresignDownloadObjectRequest
    ) -> PresignedDownloadUrl:
        self.download_calls.append((request.bucket, request.object_key))
        return PresignedDownloadUrl(
            url=f"http://storage.local/{request.bucket}/{request.object_key}?signature=1",
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
        )

    def delete_object(self, request: DeleteObjectRequest) -> None:
        self.delete_requests.append(request)
        self.delete_calls.append((request.bucket, request.object_key))
