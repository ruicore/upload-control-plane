from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.datasets.audit import DatasetAuditWriter
from upload_control_plane.application.datasets.contracts import RetryValidationResult
from upload_control_plane.application.errors import ApiError
from upload_control_plane.domain.datasets import DatasetStatus, ValidationStatus
from upload_control_plane.infrastructure.db.models import Dataset, OutboxEvent


class DatasetValidationCommandService:
    """Own validation retry eligibility and its atomic state transition."""

    def __init__(self, *, session: Session, audit: DatasetAuditWriter) -> None:
        self._session = session
        self._audit = audit

    def retry_validation(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
    ) -> RetryValidationResult:
        dataset = self._get_dataset_for_update(
            tenant_id=tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
        if dataset.validation_status in {
            ValidationStatus.PENDING.value,
            ValidationStatus.RUNNING.value,
        }:
            return RetryValidationResult(
                dataset_id=dataset.id,
                project_id=dataset.project_id,
                dataset_status=dataset.status,
                validation_status=dataset.validation_status,
                retry_queued=False,
            )
        if dataset.validation_status != ValidationStatus.FAILED.value or dataset.status not in {
            DatasetStatus.REJECTED.value,
            DatasetStatus.QUARANTINED.value,
            DatasetStatus.PROCESSING.value,
        }:
            raise ApiError(
                status_code=409,
                code="dataset.validation_retry_not_eligible",
                message="Dataset validation cannot be retried in its current state.",
                details={
                    "dataset_status": dataset.status,
                    "validation_status": dataset.validation_status,
                },
            )
        if dataset.bucket_name is None or dataset.object_key is None:
            raise ApiError(
                status_code=409,
                code="dataset.object_missing",
                message="Dataset has no completed storage object.",
            )

        before = self._audit.snapshot(dataset)
        now = datetime.now(UTC)
        dataset.status = DatasetStatus.PROCESSING.value
        dataset.validation_status = ValidationStatus.PENDING.value
        dataset.updated_at = now
        after = self._audit.snapshot(dataset)
        self._audit.add(
            dataset,
            actor=actor,
            action="dataset.validation_retry",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=after,
        )
        self._session.add(
            OutboxEvent(
                tenant_id=dataset.tenant_id,
                aggregate_type="dataset",
                aggregate_id=dataset.id,
                event_type="dataset.validation_retry",
                payload={
                    "dataset_id": str(dataset.id),
                    "project_id": str(dataset.project_id),
                    "status": dataset.status,
                    "validation_status": dataset.validation_status,
                    "result": "SUCCESS",
                },
                created_at=now,
                next_attempt_at=now,
            )
        )
        self._session.commit()
        return RetryValidationResult(
            dataset_id=dataset.id,
            project_id=dataset.project_id,
            dataset_status=dataset.status,
            validation_status=dataset.validation_status,
            retry_queued=True,
        )

    def _get_dataset_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
    ) -> Dataset:
        dataset = self._session.scalar(
            select(Dataset).where(Dataset.id == dataset_id).with_for_update()
        )
        if dataset is None or dataset.tenant_id != tenant_id or dataset.project_id != project_id:
            raise ApiError(status_code=404, code="dataset.not_found", message="Dataset not found.")
        return dataset
