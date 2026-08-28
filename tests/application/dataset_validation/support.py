from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
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
    DatasetValidationResult,
    IdempotencyRecord,
    OutboxEvent,
    UploadEvent,
    UploadObject,
    UploadPart,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import build_dev_seed_result, dev_seed_uuid
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


def _insert_completed_dataset(session: Session, *, key: str, filename: str) -> _GraphIds:
    seed = build_dev_seed_result()
    task_id = dev_seed_uuid(f"test-task:{key}")
    object_id = dev_seed_uuid(f"test-object:{key}")
    dataset_id = dev_seed_uuid(f"test-dataset:{key}")
    session_id = dev_seed_uuid(f"test-session:{key}")
    now = datetime.now(UTC)
    object_key = f"ucp-test-validation/{key}.hdf5"
    session.add(
        Dataset(
            id=dataset_id,
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            name=key,
            status="PROCESSING",
            original_filename=filename,
            content_type="application/x-hdf5",
            file_size_bytes=DEFAULT_PART_SIZE,
            bucket_name="robot-data",
            object_key=object_key,
            object_size_bytes=DEFAULT_PART_SIZE,
            validation_status="PENDING",
            recovery_status="NORMAL",
            preview_status="NOT_AVAILABLE",
            preview_metadata={},
            metadata_={},
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
            status="COMPLETED",
            task_initiator="api",
            object_count=1,
            completed_object_count=1,
            total_size_bytes=DEFAULT_PART_SIZE,
            idempotency_key=key,
            created_at=now,
            updated_at=now,
            completed_at=now,
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
            status="COMPLETED",
            object_name=filename,
            file_size_bytes=DEFAULT_PART_SIZE,
            upload_session_id=session_id,
            created_at=now,
            updated_at=now,
            completed_at=now,
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
            status="COMPLETED",
            bucket_name="robot-data",
            object_key=object_key,
            storage_provider="minio",
            storage_upload_id=f"upload-{key}",
            original_filename=filename,
            content_type="application/x-hdf5",
            file_size_bytes=DEFAULT_PART_SIZE,
            part_size_bytes=DEFAULT_PART_SIZE,
            part_count=1,
            object_etag='"etag"',
            object_size_bytes=DEFAULT_PART_SIZE,
            expires_at=now + timedelta(hours=1),
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
    )
    return _GraphIds((task_id, object_id, dataset_id, session_id))


def _test_settings(**overrides: object) -> Settings:
    return get_settings().model_copy(
        update={
            "worker_batch_size": 50,
            "enable_dataset_validation": True,
            **overrides,
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


def _delete_validation_test_artifacts(session: Session) -> None:
    task_ids = list(
        session.scalars(
            select(UploadTask.id).where(UploadTask.idempotency_key.like("ucp-test-validation-%"))
        )
    )
    dataset_ids = list(
        session.scalars(select(Dataset.id).where(Dataset.name.like("ucp-test-validation-%")))
    )
    session_ids = list(
        session.scalars(select(UploadSession.id).where(UploadSession.upload_task_id.in_(task_ids)))
    )
    if session_ids:
        session.execute(delete(UploadPart).where(UploadPart.session_id.in_(session_ids)))
        session.execute(delete(UploadEvent).where(UploadEvent.session_id.in_(session_ids)))
        session.execute(delete(UploadSession).where(UploadSession.id.in_(session_ids)))
    if dataset_ids:
        session.execute(
            delete(DatasetValidationResult).where(
                DatasetValidationResult.dataset_id.in_(dataset_ids)
            )
        )
        session.execute(delete(DatasetTag).where(DatasetTag.dataset_id.in_(dataset_ids)))
        session.execute(delete(AuditEvent).where(AuditEvent.dataset_id.in_(dataset_ids)))
        session.execute(
            delete(OutboxEvent).where(
                (OutboxEvent.aggregate_type == "dataset")
                & (OutboxEvent.aggregate_id.in_(dataset_ids))
            )
        )
    if task_ids:
        session.execute(delete(UploadObject).where(UploadObject.upload_task_id.in_(task_ids)))
        session.execute(delete(UploadTask).where(UploadTask.id.in_(task_ids)))
    if dataset_ids:
        session.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
    session.execute(
        delete(IdempotencyRecord).where(IdempotencyRecord.key.like("ucp-test-validation-%"))
    )


class ValidationFakeObjectStorage:
    def __init__(self) -> None:
        self.heads: dict[tuple[str, str], int] = {}
        self.delete_calls: list[tuple[str, str]] = []

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

    def abort_multipart_upload(self, _request: AbortMultipartUploadRequest) -> None:
        return None

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        key = (request.bucket, request.object_key)
        if key not in self.heads:
            raise StorageNotFoundError("not found", operation="head_object", provider_code="404")
        return HeadObjectResult(
            bucket=request.bucket,
            object_key=request.object_key,
            etag='"etag"',
            size_bytes=self.heads[key],
        )

    def presign_download_object(
        self, request: PresignDownloadObjectRequest
    ) -> PresignedDownloadUrl:
        return PresignedDownloadUrl(
            url=f"http://storage.local/{request.bucket}/{request.object_key}?signature=1",
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
        )

    def delete_object(self, request: DeleteObjectRequest) -> None:
        self.delete_calls.append((request.bucket, request.object_key))
