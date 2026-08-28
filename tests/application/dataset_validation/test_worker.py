from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from upload_control_plane.application.dataset_validation import DatasetValidationWorkerService
from upload_control_plane.application.dataset_validation_plugins import (
    ExtractedMetadata,
    ValidationErrorDetail,
)
from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.domain.storage import ObjectStorage
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    DatasetValidationResult,
    IdempotencyRecord,
    OutboxEvent,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import seed_dev_data

from .support import (
    ValidationFakeObjectStorage,
    _db_session_factory_or_skip,
    _delete_validation_test_artifacts,
    _insert_completed_dataset,
    _session_scope,
    _test_settings,
)


class InjectedMetadataExtractor:
    name = "injected_metadata"
    version = "2026.07"

    def extract(self, dataset: Dataset, storage: ObjectStorage) -> ExtractedMetadata:
        _ = (dataset, storage)
        return ExtractedMetadata(
            preview_status="AVAILABLE",
            preview_metadata={"format": "CUSTOM", "source": self.name},
            extracted_metadata={
                "format": "CUSTOM",
                "extractor": {"name": self.name, "version": self.version},
            },
        )


class RejectingInspectionHook:
    name = "rejecting_inspection"
    version = "1"

    def inspect(
        self, dataset: Dataset, storage: ObjectStorage
    ) -> tuple[ValidationErrorDetail, ...]:
        _ = (dataset, storage)
        return (
            ValidationErrorDetail(
                code="inspection.rejected",
                message="Inspection rejected the object.",
                details={"hook": self.name},
            ),
        )


class MustNotRunMetadataExtractor:
    name = "must_not_run"
    version = "1"

    def extract(self, dataset: Dataset, storage: ObjectStorage) -> ExtractedMetadata:
        _ = (dataset, storage)
        raise AssertionError("metadata extraction must not run after inspection rejection")


class UnexpectedErrorMetadataExtractor:
    name = "unexpected_error"
    version = "1"

    def extract(self, dataset: Dataset, storage: ObjectStorage) -> ExtractedMetadata:
        _ = storage
        dataset.preview_status = "TRANSIENT"
        raise RuntimeError("plugin exploded")


def test_validation_worker_marks_completed_dataset_ready_and_persists_metadata() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = ValidationFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_validation_test_artifacts(session)
        ids = _insert_completed_dataset(
            session, key="ucp-test-validation-success", filename="robot-run.hdf5"
        )
        storage.heads[("robot-data", "ucp-test-validation/ucp-test-validation-success.hdf5")] = (
            DEFAULT_PART_SIZE
        )

    try:
        with _session_scope(session_factory) as session:
            service = DatasetValidationWorkerService(
                session=session,
                storage=storage,
                settings=_test_settings(enable_dataset_validation=True),
            )
            summary = service.run_once(now=now)
            assert (summary.scanned, summary.passed, summary.failed, summary.errors) == (1, 1, 0, 0)

        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, ids.dataset_id)
            assert dataset is not None
            assert dataset.status == "READY"
            assert dataset.validation_status == "PASSED"
            assert dataset.ready_at == now
            assert dataset.preview_status == "AVAILABLE"
            assert dataset.preview_metadata["format"] == "HDF5"
            assert dataset.metadata_["extracted_metadata"]["format"] == "HDF5"

            result = session.scalar(
                select(DatasetValidationResult).where(
                    DatasetValidationResult.dataset_id == ids.dataset_id
                )
            )
            assert result is not None
            assert result.status == "PASSED"
            assert result.extracted_metadata["object"]["size_bytes"] == DEFAULT_PART_SIZE
            assert result.errors == []

            audit_action = session.scalar(
                select(AuditEvent.action).where(AuditEvent.dataset_id == ids.dataset_id)
            )
            outbox_event = session.scalar(
                select(OutboxEvent.event_type).where(OutboxEvent.aggregate_id == ids.dataset_id)
            )
            assert audit_action == "dataset.validation_passed"
            assert outbox_event == "dataset.validation_passed"
    finally:
        with _session_scope(session_factory) as session:
            _delete_validation_test_artifacts(session)


def test_validation_cleanup_preserves_unrelated_generic_data_prefixes() -> None:
    session_factory = _db_session_factory_or_skip()
    suffix = uuid.uuid4().hex
    owned_key = f"ucp-test-validation-cleanup-counterexample-{suffix}"
    unrelated_key = f"data-unrelated-{suffix}"
    idempotency_record_id = uuid.uuid4()

    with session_factory() as session:
        seed_dev_data(session, get_settings())
        _delete_validation_test_artifacts(session)
        owned_ids = _insert_completed_dataset(
            session,
            key=owned_key,
            filename="owned.hdf5",
        )
        unrelated_ids = _insert_completed_dataset(
            session,
            key=unrelated_key,
            filename="unrelated.hdf5",
        )
        session.flush()
        unrelated_dataset = session.get(Dataset, unrelated_ids.dataset_id)
        unrelated_session = session.get(UploadSession, unrelated_ids.session_id)
        assert unrelated_dataset is not None
        assert unrelated_session is not None
        unrelated_object_key = f"data/unrelated-{suffix}.hdf5"
        unrelated_dataset.object_key = unrelated_object_key
        unrelated_session.object_key = unrelated_object_key
        session.add(
            IdempotencyRecord(
                id=idempotency_record_id,
                tenant_id=unrelated_dataset.tenant_id,
                key=unrelated_key,
                request_method="POST",
                request_path="/unrelated-validation-cleanup",
                request_fingerprint=f"unrelated-{suffix}",
                expires_at=datetime.now(UTC),
            )
        )
        session.flush()

        _delete_validation_test_artifacts(session)
        session.flush()

        assert session.get(Dataset, owned_ids.dataset_id) is None
        assert session.get(UploadTask, owned_ids.task_id) is None
        assert session.get(Dataset, unrelated_ids.dataset_id) is not None
        assert session.get(UploadTask, unrelated_ids.task_id) is not None
        assert session.get(UploadSession, unrelated_ids.session_id) is not None
        assert session.get(IdempotencyRecord, idempotency_record_id) is not None
        assert unrelated_dataset.object_key == unrelated_object_key
        session.rollback()


def test_validation_worker_records_failure_without_deleting_object_or_exposing_dataset() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = ValidationFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_validation_test_artifacts(session)
        ids = _insert_completed_dataset(
            session, key="ucp-test-validation-failure", filename="missing.hdf5"
        )

    try:
        with _session_scope(session_factory) as session:
            service = DatasetValidationWorkerService(
                session=session,
                storage=storage,
                settings=_test_settings(enable_dataset_validation=True),
            )
            summary = service.run_once(now=now)
            assert (summary.scanned, summary.passed, summary.failed, summary.errors) == (1, 0, 1, 0)

        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, ids.dataset_id)
            assert dataset is not None
            assert dataset.status == "REJECTED"
            assert dataset.validation_status == "FAILED"
            assert dataset.object_key == "ucp-test-validation/ucp-test-validation-failure.hdf5"
            assert storage.delete_calls == []

            result = session.scalar(
                select(DatasetValidationResult).where(
                    DatasetValidationResult.dataset_id == ids.dataset_id
                )
            )
            assert result is not None
            assert result.status == "FAILED"
            assert result.errors[0]["code"] == "storage.head_failed"
    finally:
        with _session_scope(session_factory) as session:
            _delete_validation_test_artifacts(session)


def test_validation_worker_is_noop_when_validation_disabled() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = ValidationFakeObjectStorage()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_validation_test_artifacts(session)
        ids = _insert_completed_dataset(
            session, key="ucp-test-validation-disabled", filename="disabled.hdf5"
        )

    try:
        with _session_scope(session_factory) as session:
            service = DatasetValidationWorkerService(
                session=session,
                storage=storage,
                settings=_test_settings(enable_dataset_validation=False),
            )
            summary = service.run_once(now=datetime.now(UTC))
            assert summary.scanned == 0
            assert summary.skipped == 1

        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, ids.dataset_id)
            assert dataset is not None
            assert dataset.status == "PROCESSING"
            assert dataset.validation_status == "PENDING"
    finally:
        with _session_scope(session_factory) as session:
            _delete_validation_test_artifacts(session)


def test_validation_worker_persists_injected_extractor_identity_and_metadata() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = ValidationFakeObjectStorage()
    extractor = InjectedMetadataExtractor()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_validation_test_artifacts(session)
        ids = _insert_completed_dataset(
            session,
            key="ucp-test-validation-injected-extractor",
            filename="custom.capture",
        )

    try:
        with _session_scope(session_factory) as session:
            service = DatasetValidationWorkerService(
                session=session,
                storage=storage,
                settings=_test_settings(enable_dataset_validation=True),
                metadata_extractor=extractor,
            )

            summary = service.run_once(now=now)

            assert (summary.scanned, summary.passed, summary.failed, summary.errors) == (
                1,
                1,
                0,
                0,
            )

        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, ids.dataset_id)
            result = session.scalar(
                select(DatasetValidationResult).where(
                    DatasetValidationResult.dataset_id == ids.dataset_id
                )
            )
            assert dataset is not None
            assert result is not None
            assert dataset.preview_metadata == {
                "format": "CUSTOM",
                "source": extractor.name,
            }
            assert dataset.metadata_["extracted_metadata"] == {
                "format": "CUSTOM",
                "extractor": {
                    "name": extractor.name,
                    "version": extractor.version,
                },
            }
            assert result.validator_name == extractor.name
            assert result.validator_version == extractor.version
            assert result.extracted_metadata == dataset.metadata_["extracted_metadata"]
    finally:
        with _session_scope(session_factory) as session:
            _delete_validation_test_artifacts(session)


def test_validation_worker_records_inspection_rejection_before_metadata_extraction() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = ValidationFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_validation_test_artifacts(session)
        ids = _insert_completed_dataset(
            session,
            key="ucp-test-validation-inspection-rejection",
            filename="rejected.hdf5",
        )

    try:
        with _session_scope(session_factory) as session:
            service = DatasetValidationWorkerService(
                session=session,
                storage=storage,
                settings=_test_settings(enable_dataset_validation=True),
                metadata_extractor=MustNotRunMetadataExtractor(),
                inspection_hooks=(RejectingInspectionHook(),),
            )

            summary = service.run_once(now=now)

            assert (summary.scanned, summary.passed, summary.failed, summary.errors) == (
                1,
                0,
                1,
                0,
            )

        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, ids.dataset_id)
            result = session.scalar(
                select(DatasetValidationResult).where(
                    DatasetValidationResult.dataset_id == ids.dataset_id
                )
            )
            assert dataset is not None
            assert result is not None
            assert dataset.status == "REJECTED"
            assert dataset.validation_status == "FAILED"
            assert result.validator_name == MustNotRunMetadataExtractor.name
            assert result.errors == [
                {
                    "code": "inspection.rejected",
                    "message": "Inspection rejected the object.",
                    "retryable": False,
                    "details": {"hook": RejectingInspectionHook.name},
                }
            ]
    finally:
        with _session_scope(session_factory) as session:
            _delete_validation_test_artifacts(session)


def test_validation_worker_rolls_back_plugin_mutation_and_commits_one_error_evidence_set() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = ValidationFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_validation_test_artifacts(session)
        ids = _insert_completed_dataset(
            session,
            key="ucp-test-validation-unexpected-plugin-error",
            filename="broken.hdf5",
        )

    try:
        with _session_scope(session_factory) as session:
            service = DatasetValidationWorkerService(
                session=session,
                storage=storage,
                settings=_test_settings(enable_dataset_validation=True),
                metadata_extractor=UnexpectedErrorMetadataExtractor(),
            )

            summary = service.run_once(now=now)

            assert (summary.scanned, summary.passed, summary.failed, summary.errors) == (
                1,
                0,
                0,
                1,
            )

        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, ids.dataset_id)
            results = list(
                session.scalars(
                    select(DatasetValidationResult).where(
                        DatasetValidationResult.dataset_id == ids.dataset_id
                    )
                )
            )
            audits = list(
                session.scalars(select(AuditEvent).where(AuditEvent.dataset_id == ids.dataset_id))
            )
            outbox_events = list(
                session.scalars(
                    select(OutboxEvent).where(
                        (OutboxEvent.aggregate_type == "dataset")
                        & (OutboxEvent.aggregate_id == ids.dataset_id)
                    )
                )
            )
            assert dataset is not None
            assert dataset.status == "REJECTED"
            assert dataset.validation_status == "FAILED"
            assert dataset.preview_status == "NOT_AVAILABLE"
            assert len(results) == len(audits) == len(outbox_events) == 1
            assert results[0].errors == [
                {
                    "code": "validation.worker_error",
                    "message": "plugin exploded",
                    "retryable": True,
                }
            ]
            assert audits[0].action == "dataset.validation_failed"
            assert audits[0].before_state is not None
            assert audits[0].before_state["preview_status"] == "NOT_AVAILABLE"
            assert outbox_events[0].event_type == "dataset.validation_failed"
            assert outbox_events[0].payload["validation_status"] == "FAILED"
    finally:
        with _session_scope(session_factory) as session:
            _delete_validation_test_artifacts(session)
