from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.application.dataset_validation_plugins import (
    ExtractedMetadata,
    FileInspectionHook,
    Hdf5MetadataExtractor,
    MetadataExtractor,
    NoopFileInspectionHook,
    ValidationErrorDetail,
    ValidationWorkerError,
)
from upload_control_plane.application.outbox import OutboxAppend, append_outbox_event
from upload_control_plane.config import Settings
from upload_control_plane.domain.datasets import DatasetStatus, ValidationStatus
from upload_control_plane.domain.storage import ObjectStorage
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    DatasetValidationResult,
    UploadSession,
)


@dataclass(frozen=True, slots=True)
class DatasetValidationRunSummary:
    scanned: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0


class DatasetValidationWorkerService:
    def __init__(
        self,
        *,
        session: Session,
        storage: ObjectStorage,
        settings: Settings,
        metadata_extractor: MetadataExtractor | None = None,
        inspection_hooks: tuple[FileInspectionHook, ...] | None = None,
    ) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._metadata_extractor = metadata_extractor or Hdf5MetadataExtractor()
        self._inspection_hooks = inspection_hooks if inspection_hooks is not None else ()

    def run_once(
        self, *, now: datetime | None = None, batch_size: int | None = None
    ) -> DatasetValidationRunSummary:
        if not self._settings.enable_dataset_validation:
            return DatasetValidationRunSummary(skipped=1)

        run_at = now or datetime.now(UTC)
        dataset_ids = self._claim_candidates(now=run_at, batch_size=batch_size)
        passed = failed = errors = 0
        for dataset_id in dataset_ids:
            try:
                if self._validate_one(dataset_id, now=run_at):
                    passed += 1
                else:
                    failed += 1
            except Exception as exc:
                self._mark_unexpected_error(dataset_id, exc, now=run_at)
                errors += 1
        return DatasetValidationRunSummary(
            scanned=len(dataset_ids),
            passed=passed,
            failed=failed,
            errors=errors,
        )

    def _claim_candidates(self, *, now: datetime, batch_size: int | None) -> tuple[uuid.UUID, ...]:
        limit = batch_size or self._settings.worker_batch_size
        datasets = list(
            self._session.scalars(
                select(Dataset)
                .join(UploadSession, UploadSession.dataset_id == Dataset.id)
                .where(Dataset.status == DatasetStatus.PROCESSING.value)
                .where(Dataset.validation_status == ValidationStatus.PENDING.value)
                .where(UploadSession.status == "COMPLETED")
                .where(Dataset.bucket_name.is_not(None))
                .where(Dataset.object_key.is_not(None))
                .order_by(Dataset.updated_at.asc(), Dataset.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        dataset_ids: list[uuid.UUID] = []
        for dataset in datasets:
            dataset.validation_status = ValidationStatus.RUNNING.value
            dataset.status = DatasetStatus.QUARANTINED.value
            dataset.updated_at = now
            dataset_ids.append(dataset.id)
        self._session.commit()
        return tuple(dataset_ids)

    def _validate_one(self, dataset_id: uuid.UUID, *, now: datetime) -> bool:
        dataset = self._session.get(Dataset, dataset_id)
        if dataset is None:
            return False

        inspection_errors: list[ValidationErrorDetail] = []
        hooks = self._inspection_hooks
        if self._settings.enable_malware_scan and not hooks:
            hooks = (NoopFileInspectionHook(),)
        for hook in hooks:
            inspection_errors.extend(hook.inspect(dataset, self._storage))
        if inspection_errors:
            self._record_failure(dataset, inspection_errors, now=now)
            self._session.commit()
            return False

        try:
            extracted = self._metadata_extractor.extract(dataset, self._storage)
        except ValidationWorkerError as exc:
            self._record_failure(
                dataset,
                (
                    ValidationErrorDetail(
                        code=exc.code,
                        message=str(exc),
                        retryable=exc.retryable,
                        details=exc.details,
                    ),
                ),
                now=now,
            )
            self._session.commit()
            return False

        self._record_success(dataset, extracted, now=now)
        self._session.commit()
        return True

    def _record_success(
        self, dataset: Dataset, extracted: ExtractedMetadata, *, now: datetime
    ) -> None:
        before_state = _dataset_state(dataset)
        dataset.validation_status = ValidationStatus.PASSED.value
        dataset.status = DatasetStatus.READY.value
        dataset.preview_status = extracted.preview_status
        dataset.preview_metadata = extracted.preview_metadata
        metadata = dict(dataset.metadata_ or {})
        metadata["extracted_metadata"] = extracted.extracted_metadata
        dataset.metadata_ = metadata
        dataset.ready_at = dataset.ready_at or now
        dataset.updated_at = now
        self._session.add(
            DatasetValidationResult(
                id=uuid.uuid4(),
                tenant_id=dataset.tenant_id,
                project_id=dataset.project_id,
                dataset_id=dataset.id,
                status=ValidationStatus.PASSED.value,
                validator_name=self._metadata_extractor.name,
                validator_version=self._metadata_extractor.version,
                extracted_metadata=extracted.extracted_metadata,
                errors=[],
                started_at=now,
                completed_at=now,
                created_at=now,
            )
        )
        self._add_audit_and_outbox(
            dataset,
            action="dataset.validation_passed",
            result="SUCCESS",
            before_state=before_state,
            after_state=_dataset_state(dataset),
            metadata={
                "validator_name": self._metadata_extractor.name,
                "validator_version": self._metadata_extractor.version,
                "preview_status": extracted.preview_status,
            },
            now=now,
        )

    def _record_failure(
        self,
        dataset: Dataset,
        errors: tuple[ValidationErrorDetail, ...] | list[ValidationErrorDetail],
        *,
        now: datetime,
    ) -> None:
        before_state = _dataset_state(dataset)
        error_payload = [error.as_json() for error in errors]
        dataset.validation_status = ValidationStatus.FAILED.value
        dataset.status = DatasetStatus.REJECTED.value
        dataset.preview_status = "NOT_AVAILABLE"
        dataset.updated_at = now
        self._session.add(
            DatasetValidationResult(
                id=uuid.uuid4(),
                tenant_id=dataset.tenant_id,
                project_id=dataset.project_id,
                dataset_id=dataset.id,
                status=ValidationStatus.FAILED.value,
                validator_name=self._metadata_extractor.name,
                validator_version=self._metadata_extractor.version,
                extracted_metadata={},
                errors=error_payload,
                started_at=now,
                completed_at=now,
                created_at=now,
            )
        )
        self._add_audit_and_outbox(
            dataset,
            action="dataset.validation_failed",
            result="FAILED",
            before_state=before_state,
            after_state=_dataset_state(dataset),
            metadata={"errors": error_payload},
            now=now,
        )

    def _mark_unexpected_error(
        self, dataset_id: uuid.UUID, exc: Exception, *, now: datetime
    ) -> None:
        self._session.rollback()
        dataset = self._session.get(Dataset, dataset_id)
        if dataset is None:
            return
        self._record_failure(
            dataset,
            (
                ValidationErrorDetail(
                    code="validation.worker_error",
                    message=str(exc),
                    retryable=True,
                ),
            ),
            now=now,
        )
        self._session.commit()

    def _add_audit_and_outbox(
        self,
        dataset: Dataset,
        *,
        action: str,
        result: str,
        before_state: dict[str, Any],
        after_state: dict[str, Any],
        metadata: dict[str, Any],
        now: datetime,
    ) -> None:
        self._session.add(
            AuditEvent(
                tenant_id=dataset.tenant_id,
                project_id=dataset.project_id,
                dataset_id=dataset.id,
                actor_type="system",
                actor_id="worker:dataset-validation",
                action=action,
                resource_type="dataset",
                resource_id=str(dataset.id),
                result=result,
                request_id=None,
                before_state=before_state,
                after_state=after_state,
                metadata_=metadata,
                created_at=now,
            )
        )
        append_outbox_event(
            self._session,
            OutboxAppend(
                tenant_id=dataset.tenant_id,
                aggregate_type="dataset",
                aggregate_id=dataset.id,
                event_type=action,
                payload={
                    "dataset_id": str(dataset.id),
                    "project_id": str(dataset.project_id),
                    "status": dataset.status,
                    "validation_status": dataset.validation_status,
                    "result": result,
                    "metadata": metadata,
                },
                created_at=now,
                next_attempt_at=now,
            ),
        )


def _dataset_state(dataset: Dataset) -> dict[str, Any]:
    return {
        "dataset_id": str(dataset.id),
        "status": dataset.status,
        "validation_status": dataset.validation_status,
        "recovery_status": dataset.recovery_status,
        "preview_status": dataset.preview_status,
        "ready_at": dataset.ready_at.isoformat() if dataset.ready_at else None,
    }
