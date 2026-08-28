from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from upload_control_plane.application.worker_lifecycle import WorkerLifecycleService
from upload_control_plane.config import get_settings
from upload_control_plane.domain.storage import (
    DeleteObjectRequest,
    StorageError,
    StorageNotFoundError,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    OutboxEvent,
    StoragePolicy,
)
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    seed_dev_data,
)

from .support import (
    WorkerFakeObjectStorage,
    _db_session_factory_or_skip,
    _delete_lifecycle_test_artifacts,
    _insert_upload_graph,
    _session_scope,
    _test_settings,
)


def test_recycle_bin_retention_purges_only_after_governance_allows_it() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        ids = _insert_upload_graph(
            session,
            key="ucp-test-lifecycle-recycle",
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
        assert storage.delete_calls == [
            ("robot-data", "ucp-test-lifecycle/ucp-test-lifecycle-recycle.bin")
        ]
    finally:
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, build_dev_seed_result().storage_policy_id)
            if policy is not None:
                policy.retention_days = None
            _delete_lifecycle_test_artifacts(session)


def test_recycle_bin_retention_treats_missing_versioned_object_as_purged() -> None:
    session_factory = _db_session_factory_or_skip()

    class MissingDeleteStorage(WorkerFakeObjectStorage):
        def delete_object(self, request: DeleteObjectRequest) -> None:
            super().delete_object(request)
            raise StorageNotFoundError(
                "not found",
                operation="delete_object",
                provider_code="NoSuchVersion",
            )

    storage = MissingDeleteStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        ids = _insert_upload_graph(
            session,
            key="ucp-test-lifecycle-recycle-missing",
            status="COMPLETED",
            dataset_status="DELETED",
            deleted_at=now - timedelta(days=30),
            expires_at=now,
        )
        dataset = session.get(Dataset, ids.dataset_id)
        policy = session.get(StoragePolicy, build_dev_seed_result().storage_policy_id)
        assert dataset is not None
        assert policy is not None
        dataset.object_version_id = "version-missing"
        policy.retention_days = None

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            assert service.enforce_recycle_bin_retention(now=now) == (1, 1, 0)

            dataset = session.get(Dataset, ids.dataset_id)
            assert dataset is not None
            assert dataset.status == "PURGED"
            assert dataset.bucket_name is None
            assert dataset.object_key is None
            assert dataset.object_version_id is None

            audit = session.scalar(
                select(AuditEvent).where(
                    (AuditEvent.dataset_id == ids.dataset_id)
                    & (AuditEvent.action == "dataset.purge")
                    & (AuditEvent.result == "SUCCESS")
                )
            )
            assert audit is not None
            assert audit.actor_type == "system"
            assert audit.actor_id == "worker:lifecycle"
            assert audit.resource_type == "dataset"
            assert audit.resource_id == str(ids.dataset_id)
            assert audit.metadata_ == {"source": "worker.recycle_retention"}
            assert audit.before_state == {
                "dataset_id": str(ids.dataset_id),
                "status": "DELETED",
                "recovery_status": "NORMAL",
                "bucket": "robot-data",
                "object_key": "ucp-test-lifecycle/ucp-test-lifecycle-recycle-missing.bin",
                "deleted_at": (now - timedelta(days=30)).isoformat(),
            }
            assert audit.after_state == {
                "dataset_id": str(ids.dataset_id),
                "status": "PURGED",
                "recovery_status": "NORMAL",
                "bucket": None,
                "object_key": None,
                "deleted_at": (now - timedelta(days=30)).isoformat(),
            }

            outbox = session.scalar(
                select(OutboxEvent).where(
                    (OutboxEvent.aggregate_id == ids.dataset_id)
                    & (OutboxEvent.event_type == "dataset.purge")
                )
            )
            assert outbox is not None
            assert outbox.payload == {
                "dataset_id": str(ids.dataset_id),
                "project_id": str(dataset.project_id),
                "status": "PURGED",
                "recovery_status": "NORMAL",
                "result": "SUCCESS",
                "metadata": {"source": "worker.recycle_retention"},
            }
        assert storage.delete_requests == [
            DeleteObjectRequest(
                bucket="robot-data",
                object_key="ucp-test-lifecycle/ucp-test-lifecycle-recycle-missing.bin",
                version_id="version-missing",
            )
        ]
    finally:
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, build_dev_seed_result().storage_policy_id)
            if policy is not None:
                policy.retention_days = None
            _delete_lifecycle_test_artifacts(session)


def test_recycle_bin_retention_storage_error_keeps_object_metadata_and_emits_failure() -> None:
    session_factory = _db_session_factory_or_skip()

    class FailingDeleteStorage(WorkerFakeObjectStorage):
        def delete_object(self, request: DeleteObjectRequest) -> None:
            super().delete_object(request)
            raise StorageError(
                "delete failed",
                operation="delete_object",
                provider_code="ServiceUnavailable",
                retryable=True,
            )

    storage = FailingDeleteStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        ids = _insert_upload_graph(
            session,
            key="ucp-test-lifecycle-recycle-error",
            status="COMPLETED",
            dataset_status="DELETED",
            deleted_at=now - timedelta(days=31),
            expires_at=now,
        )
        dataset = session.get(Dataset, ids.dataset_id)
        policy = session.get(StoragePolicy, build_dev_seed_result().storage_policy_id)
        assert dataset is not None
        assert policy is not None
        dataset.object_version_id = "version-error"
        policy.retention_days = None

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            assert service.enforce_recycle_bin_retention(now=now) == (1, 0, 1)

            dataset = session.get(Dataset, ids.dataset_id)
            assert dataset is not None
            assert dataset.status == "DELETED"
            assert dataset.bucket_name == "robot-data"
            assert dataset.object_key == "ucp-test-lifecycle/ucp-test-lifecycle-recycle-error.bin"
            assert dataset.object_version_id == "version-error"

            audit = session.scalar(
                select(AuditEvent).where(
                    (AuditEvent.dataset_id == ids.dataset_id)
                    & (AuditEvent.action == "dataset.purge")
                    & (AuditEvent.result == "FAILED")
                )
            )
            assert audit is not None
            assert audit.actor_type == "system"
            assert audit.actor_id == "worker:lifecycle"
            assert audit.metadata_ == {
                "source": "worker.recycle_retention",
                "operation": "delete_object",
                "provider_code": "ServiceUnavailable",
            }
            assert audit.before_state is None
            assert audit.after_state is None

            outbox = session.scalar(
                select(OutboxEvent).where(
                    (OutboxEvent.aggregate_id == ids.dataset_id)
                    & (OutboxEvent.event_type == "dataset.purge")
                )
            )
            assert outbox is not None
            assert outbox.payload == {
                "dataset_id": str(ids.dataset_id),
                "project_id": str(dataset.project_id),
                "status": "DELETED",
                "recovery_status": "NORMAL",
                "result": "FAILED",
                "metadata": {
                    "source": "worker.recycle_retention",
                    "operation": "delete_object",
                    "provider_code": "ServiceUnavailable",
                },
            }
        assert storage.delete_requests == [
            DeleteObjectRequest(
                bucket="robot-data",
                object_key="ucp-test-lifecycle/ucp-test-lifecycle-recycle-error.bin",
                version_id="version-error",
            )
        ]
    finally:
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, build_dev_seed_result().storage_policy_id)
            if policy is not None:
                policy.retention_days = None
            _delete_lifecycle_test_artifacts(session)
