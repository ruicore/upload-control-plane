from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from upload_control_plane.application.worker_lifecycle import (
    ObjectReference,
    WorkerLifecycleService,
)
from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.infrastructure.db.models import AuditEvent, Dataset, OutboxEvent
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
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


def test_cleanup_preserves_unrelated_recovery_outbox_events() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex
    unrelated_datasets = (
        Dataset(
            id=uuid.uuid4(),
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            name=f"validation-{suffix}",
            status="READY",
            original_filename=f"validation-{suffix}.bin",
            content_type="application/octet-stream",
            file_size_bytes=DEFAULT_PART_SIZE,
            bucket_name="robot-data",
            object_key=f"validation/{suffix}.bin",
            object_size_bytes=DEFAULT_PART_SIZE,
            validation_status="PASSED",
            recovery_status="RECOVERY_PENDING",
            created_at=now,
            updated_at=now,
        ),
        Dataset(
            id=uuid.uuid4(),
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            name=f"ucp-retention-{suffix}",
            status="READY",
            original_filename=f"ucp-retention-{suffix}.bin",
            content_type="application/octet-stream",
            file_size_bytes=DEFAULT_PART_SIZE,
            bucket_name="robot-data",
            object_key=f"ucp-retention/{suffix}.bin",
            object_size_bytes=DEFAULT_PART_SIZE,
            validation_status="PASSED",
            recovery_status="RECOVERY_PENDING",
            created_at=now,
            updated_at=now,
        ),
    )
    unrelated_events = tuple(
        OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=seed.tenant_id,
            aggregate_type="dataset",
            aggregate_id=dataset.id,
            event_type="dataset.recovery_reconcile",
            payload={"dataset_id": str(dataset.id)},
        )
        for dataset in unrelated_datasets
    )

    with session_factory() as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        owned = _insert_upload_graph(
            session,
            key=f"ucp-test-lifecycle-cleanup-ownership-{suffix}",
            status="PAUSED",
            expires_at=now,
        )
        session.add_all((*unrelated_datasets, *unrelated_events))
        session.flush()

        _delete_lifecycle_test_artifacts(session)
        session.flush()

        assert session.get(Dataset, owned.dataset_id) is None
        for dataset in unrelated_datasets:
            assert session.get(Dataset, dataset.id) is not None
        for event in unrelated_events:
            assert session.get(OutboxEvent, event.id) is not None
        session.rollback()


def test_recovery_reconciliation_marks_missing_metadata_and_object_only_cases() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        missing = _insert_upload_graph(
            session,
            key="ucp-test-lifecycle-missing",
            status="COMPLETED",
            dataset_status="READY",
            recovery_status="RECOVERY_PENDING",
            expires_at=now,
        )
        metadata_only = _insert_upload_graph(
            session,
            key="ucp-test-lifecycle-metadata-only",
            status="COMPLETED",
            dataset_status="READY",
            recovery_status="RECOVERY_PENDING",
            expires_at=now,
        )
        verified = _insert_upload_graph(
            session,
            key="ucp-test-lifecycle-verified",
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
        storage.heads.pop(("robot-data", "ucp-test-lifecycle/ucp-test-lifecycle-missing.bin"), None)
        storage.heads[("robot-data", "ucp-test-lifecycle/ucp-test-lifecycle-verified.bin")] = (
            DEFAULT_PART_SIZE
        )
        storage.heads[("robot-data", "ucp-test-lifecycle/orphan.bin")] = 12

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            summary = service.reconcile_recovery_status(
                now=now,
                object_refs=(
                    ObjectReference(
                        bucket="robot-data", object_key="ucp-test-lifecycle/orphan.bin"
                    ),
                ),
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
            _delete_lifecycle_test_artifacts(session)


def test_recovery_reconciliation_restores_missing_object_metadata_when_object_returns() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        ids = _insert_upload_graph(
            session,
            key="ucp-test-lifecycle-restored-object",
            status="COMPLETED",
            dataset_status="READY",
            recovery_status="RECOVERY_MISSING_OBJECT",
            expires_at=now,
        )
        dataset = session.get(Dataset, ids.dataset_id)
        assert dataset is not None
        dataset.object_etag = None
        dataset.object_size_bytes = None
        storage.heads[
            ("robot-data", "ucp-test-lifecycle/ucp-test-lifecycle-restored-object.bin")
        ] = DEFAULT_PART_SIZE

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
            _delete_lifecycle_test_artifacts(session)


def test_recovery_reconciliation_rebuilds_object_only_dataset_for_operator_review() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    seed = build_dev_seed_result()
    now = datetime.now(UTC)
    object_key = "ucp-test-lifecycle/rebuild/object-only.bin"
    rebuilt_dataset_id = dev_seed_uuid("test-dataset:ucp-test-lifecycle-object-only-rebuild")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
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
            _delete_lifecycle_test_artifacts(session)
