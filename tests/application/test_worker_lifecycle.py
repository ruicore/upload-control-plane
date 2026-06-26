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

from upload_control_plane.application.worker_lifecycle import (
    ObjectReference,
    WorkerLifecycleService,
)
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
    StoragePolicy,
    UploadEvent,
    UploadObject,
    UploadPart,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory


def test_expired_session_transitions_to_aborted_and_is_retry_safe() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_t11_artifacts(session)
        ids = _insert_upload_graph(session, key="t11-expired", status="PAUSED", expires_at=now)

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            assert service.expire_old_sessions(now=now + timedelta(seconds=1)) == 1
            upload_session = session.get(UploadSession, ids.session_id)
            assert upload_session is not None
            assert upload_session.status == "EXPIRED"

        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            summary = service.abort_expired_multipart_uploads(now=now + timedelta(seconds=2))
            assert summary.aborted_sessions == 1
            assert summary.errors == 0
            upload_session = session.get(UploadSession, ids.session_id)
            upload_task = session.get(UploadTask, ids.task_id)
            upload_object = session.get(UploadObject, ids.object_id)
            assert upload_session is not None
            assert upload_session.status == "ABORTED"
            assert upload_task is not None
            assert upload_task.status == "CANCELLED"
            assert upload_object is not None
            assert upload_object.status == "CANCELLED"

        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            rerun = service.run_once(now=now + timedelta(seconds=3))
            assert rerun.expired_sessions == 0
            assert rerun.aborted_sessions == 0
            events = list(
                session.scalars(
                    select(UploadEvent)
                    .where(UploadEvent.session_id == ids.session_id)
                    .order_by(UploadEvent.created_at.asc())
                )
            )
            assert [event.event_type for event in events] == [
                "upload.expired",
                "upload.abort_requested",
                "upload.aborted",
            ]
        assert storage.abort_calls == [("robot-data", "t11/t11-expired.bin", "upload-t11-expired")]
    finally:
        with _session_scope(session_factory) as session:
            _delete_t11_artifacts(session)


def test_completed_session_is_not_aborted_by_expiry_worker() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_t11_artifacts(session)
        ids = _insert_upload_graph(session, key="t11-completed", status="COMPLETED", expires_at=now)

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            summary = service.run_once(now=now + timedelta(days=1))
            upload_session = session.get(UploadSession, ids.session_id)
            assert upload_session is not None
            assert upload_session.status == "COMPLETED"
            assert summary.expired_sessions == 0
            assert summary.aborted_sessions == 0
        assert storage.abort_calls == []
        assert storage.delete_calls == []
    finally:
        with _session_scope(session_factory) as session:
            _delete_t11_artifacts(session)


def test_recycle_bin_retention_purges_only_after_governance_allows_it() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_t11_artifacts(session)
        ids = _insert_upload_graph(
            session,
            key="t11-recycle",
            status="COMPLETED",
            dataset_status="DELETED",
            deleted_at=now - timedelta(days=1),
            expires_at=now,
        )
        policy = session.get(StoragePolicy, build_dev_seed_result().storage_policy_id)
        assert policy is not None
        policy.retention_days = 30

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            candidates, purged, errors = service.enforce_recycle_bin_retention(now=now)
            dataset = session.get(Dataset, ids.dataset_id)
            assert (candidates, purged, errors) == (1, 0, 0)
            assert dataset is not None
            assert dataset.status == "DELETED"
            assert storage.delete_calls == []

        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, ids.dataset_id)
            policy = session.get(StoragePolicy, build_dev_seed_result().storage_policy_id)
            assert dataset is not None
            assert policy is not None
            dataset.deleted_at = now - timedelta(days=31)
            policy.retention_days = 30

        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            candidates, purged, errors = service.enforce_recycle_bin_retention(now=now)
            dataset = session.get(Dataset, ids.dataset_id)
            assert (candidates, purged, errors) == (1, 1, 0)
            assert dataset is not None
            assert dataset.status == "PURGED"
            assert dataset.object_key is None

        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            candidates, purged, errors = service.enforce_recycle_bin_retention(now=now)
            assert (candidates, purged, errors) == (0, 0, 0)
        assert storage.delete_calls == [("robot-data", "t11/t11-recycle.bin")]
    finally:
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, build_dev_seed_result().storage_policy_id)
            if policy is not None:
                policy.retention_days = None
            _delete_t11_artifacts(session)


def test_recovery_reconciliation_marks_missing_metadata_and_object_only_cases() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_t11_artifacts(session)
        missing = _insert_upload_graph(
            session,
            key="t11-missing",
            status="COMPLETED",
            dataset_status="READY",
            recovery_status="RECOVERY_PENDING",
            expires_at=now,
        )
        metadata_only = _insert_upload_graph(
            session,
            key="t11-metadata-only",
            status="COMPLETED",
            dataset_status="READY",
            recovery_status="RECOVERY_PENDING",
            expires_at=now,
        )
        verified = _insert_upload_graph(
            session,
            key="t11-verified",
            status="COMPLETED",
            dataset_status="READY",
            recovery_status="RECOVERY_PENDING",
            expires_at=now,
        )
        dataset = session.get(Dataset, metadata_only.dataset_id)
        assert dataset is not None
        dataset.bucket_name = None
        dataset.object_key = None
        for bucket, object_key in session.execute(
            select(Dataset.bucket_name, Dataset.object_key).where(Dataset.object_key.is_not(None))
        ):
            if bucket is not None and object_key is not None:
                storage.heads[(bucket, object_key)] = DEFAULT_PART_SIZE
        storage.heads.pop(("robot-data", "t11/t11-missing.bin"), None)
        storage.heads[("robot-data", "t11/t11-verified.bin")] = DEFAULT_PART_SIZE
        storage.heads[("robot-data", "t11/orphan.bin")] = 12

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            summary = service.reconcile_recovery_status(
                now=now,
                object_refs=(ObjectReference(bucket="robot-data", object_key="t11/orphan.bin"),),
            )
            missing_dataset = session.get(Dataset, missing.dataset_id)
            metadata_dataset = session.get(Dataset, metadata_only.dataset_id)
            verified_dataset = session.get(Dataset, verified.dataset_id)
            assert missing_dataset is not None
            assert metadata_dataset is not None
            assert verified_dataset is not None
            assert missing_dataset.recovery_status == "RECOVERY_MISSING_OBJECT"
            assert metadata_dataset.recovery_status == "RECOVERY_METADATA_ONLY"
            assert verified_dataset.recovery_status == "RECOVERY_VERIFIED"
            assert summary.recovery_missing_objects >= 1
            assert summary.recovery_metadata_only >= 1
            assert summary.recovery_verified >= 1
            assert summary.recovery_object_only == 1
    finally:
        with _session_scope(session_factory) as session:
            _delete_t11_artifacts(session)


def test_recovery_reconciliation_restores_missing_object_metadata_when_object_returns() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_t11_artifacts(session)
        ids = _insert_upload_graph(
            session,
            key="t11-restored-object",
            status="COMPLETED",
            dataset_status="READY",
            recovery_status="RECOVERY_MISSING_OBJECT",
            expires_at=now,
        )
        dataset = session.get(Dataset, ids.dataset_id)
        assert dataset is not None
        dataset.object_etag = None
        dataset.object_size_bytes = None
        storage.heads[("robot-data", "t11/t11-restored-object.bin")] = DEFAULT_PART_SIZE

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            summary = service.reconcile_recovery_status(now=now)
            dataset = session.get(Dataset, ids.dataset_id)
            assert dataset is not None
            assert dataset.recovery_status == "RECOVERY_VERIFIED"
            assert dataset.object_etag == '"etag"'
            assert dataset.object_size_bytes == DEFAULT_PART_SIZE
            assert summary.recovery_verified >= 1
            audit = session.scalar(
                select(AuditEvent).where(
                    (AuditEvent.dataset_id == ids.dataset_id)
                    & (AuditEvent.action == "dataset.recovery_reconcile")
                    & (AuditEvent.result == "SUCCESS")
                )
            )
            assert audit is not None
    finally:
        with _session_scope(session_factory) as session:
            _delete_t11_artifacts(session)


def test_recovery_reconciliation_rebuilds_object_only_dataset_for_operator_review() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    seed = build_dev_seed_result()
    now = datetime.now(UTC)
    object_key = "t11-rebuild/object-only.bin"
    rebuilt_dataset_id = dev_seed_uuid("test-dataset:t11-object-only-rebuild")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_t11_artifacts(session)
        storage.heads[("robot-data", object_key)] = 123
        storage.head_metadata[("robot-data", object_key)] = {
            "tenant_id": str(seed.tenant_id),
            "project_id": str(seed.project_id),
            "dataset_id": str(rebuilt_dataset_id),
            "content_type": "application/octet-stream",
        }

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            summary = service.reconcile_recovery_status(
                now=now,
                object_refs=(ObjectReference(bucket="robot-data", object_key=object_key),),
            )
            dataset = session.get(Dataset, rebuilt_dataset_id)
            assert dataset is not None
            assert dataset.status == "QUARANTINED"
            assert dataset.validation_status == "PENDING"
            assert dataset.recovery_status == "RECOVERY_OBJECT_ONLY"
            assert dataset.bucket_name == "robot-data"
            assert dataset.object_key == object_key
            assert dataset.object_size_bytes == 123
            assert dataset.metadata_["operator_review_required"] is True
            assert summary.recovery_object_only == 1
            assert not storage.download_calls
            audit = session.scalar(
                select(AuditEvent).where(
                    (AuditEvent.dataset_id == rebuilt_dataset_id)
                    & (AuditEvent.action == "dataset.recovery_rebuild")
                    & (AuditEvent.result == "SUCCESS")
                )
            )
            assert audit is not None

        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            rerun = service.reconcile_recovery_status(
                now=now,
                object_refs=(ObjectReference(bucket="robot-data", object_key=object_key),),
            )
            assert rerun.recovery_object_only == 0
            assert session.get(Dataset, rebuilt_dataset_id) is not None
    finally:
        with _session_scope(session_factory) as session:
            _delete_t11_artifacts(session)


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
    object_key = f"t11/{key}.bin"
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


def _delete_t11_artifacts(session: Session) -> None:
    task_ids = list(
        session.scalars(select(UploadTask.id).where(UploadTask.idempotency_key.like("t11-%")))
    )
    dataset_ids = list(
        session.scalars(
            select(Dataset.id).where(
                (Dataset.name.like("t11-%")) | (Dataset.object_key.like("t11%"))
            )
        )
    )
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
    session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.key.like("t11-%")))


class WorkerFakeObjectStorage:
    def __init__(self) -> None:
        self.abort_calls: list[tuple[str, str, str]] = []
        self.delete_calls: list[tuple[str, str]] = []
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
        self.delete_calls.append((request.bucket, request.object_key))
