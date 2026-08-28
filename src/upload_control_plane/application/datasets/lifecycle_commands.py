from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.datasets.audit import DatasetAuditWriter
from upload_control_plane.application.datasets.contracts import DatasetDetail
from upload_control_plane.application.datasets.queries import DatasetQueryService
from upload_control_plane.application.errors import ApiError
from upload_control_plane.domain.datasets import DatasetStatus
from upload_control_plane.infrastructure.db.models import Dataset


class DatasetLifecycleCommandService:
    """Own metadata-only archive, soft-delete, and restore commands."""

    def __init__(
        self,
        *,
        session: Session,
        queries: DatasetQueryService,
        audit: DatasetAuditWriter,
    ) -> None:
        self._session = session
        self._queries = queries
        self._audit = audit

    def archive_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
    ) -> DatasetDetail:
        dataset = self._queries.get_dataset_model(
            tenant_id=tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
        if dataset.status != DatasetStatus.READY.value:
            raise self._invalid_state(dataset, "archive")
        before = self._audit.snapshot(dataset)
        now = datetime.now(UTC)
        dataset.status = DatasetStatus.ARCHIVED.value
        dataset.archived_at = now
        dataset.updated_at = now
        self._audit.add(
            dataset,
            actor=actor,
            action="dataset.archive",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit.snapshot(dataset),
        )
        self._session.commit()
        return self._queries.detail(dataset)

    def soft_delete_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
    ) -> DatasetDetail:
        dataset = self._queries.get_dataset_model(
            tenant_id=tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
        if dataset.status == DatasetStatus.PURGED.value:
            raise self._invalid_state(dataset, "delete")
        before = self._audit.snapshot(dataset)
        now = datetime.now(UTC)
        if dataset.status != DatasetStatus.DELETED.value:
            metadata = dict(dataset.metadata_ or {})
            metadata.setdefault("deleted_from_status", dataset.status)
            dataset.metadata_ = metadata
            dataset.status = DatasetStatus.DELETED.value
            dataset.deleted_at = now
            dataset.updated_at = now
        self._audit.add(
            dataset,
            actor=actor,
            action="dataset.delete",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit.snapshot(dataset),
        )
        self._session.commit()
        return self._queries.detail(dataset)

    def restore_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
    ) -> DatasetDetail:
        dataset = self._queries.get_dataset_model(
            tenant_id=tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
        if dataset.status != DatasetStatus.DELETED.value:
            raise self._invalid_state(dataset, "restore")
        before = self._audit.snapshot(dataset)
        metadata = dict(dataset.metadata_ or {})
        restored_status = metadata.pop("deleted_from_status", DatasetStatus.READY.value)
        if restored_status not in {DatasetStatus.READY.value, DatasetStatus.ARCHIVED.value}:
            restored_status = DatasetStatus.READY.value
        dataset.metadata_ = metadata
        dataset.status = restored_status
        dataset.deleted_at = None
        dataset.updated_at = datetime.now(UTC)
        self._audit.add(
            dataset,
            actor=actor,
            action="dataset.restore",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit.snapshot(dataset),
        )
        self._session.commit()
        return self._queries.detail(dataset)

    def _invalid_state(self, dataset: Dataset, action: str) -> ApiError:
        return ApiError(
            status_code=409,
            code="dataset.invalid_state",
            message=f"Dataset is not in a state that allows {action}.",
            details={"dataset_status": dataset.status},
        )
