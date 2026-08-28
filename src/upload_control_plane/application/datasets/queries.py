from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from upload_control_plane.application.datasets.contracts import (
    DatasetDetail,
    DatasetSummary,
    DatasetValidationResultItem,
    DatasetValidationStatusResult,
)
from upload_control_plane.application.errors import ApiError
from upload_control_plane.domain.datasets import DatasetStatus
from upload_control_plane.infrastructure.db.models import (
    Dataset,
    DatasetTag,
    DatasetValidationResult,
    Project,
)


class DatasetQueryService:
    def __init__(self, *, session: Session) -> None:
        self._session = session

    def list_datasets(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        search: str | None,
        status: str | None,
        validation_status: str | None,
        recovery_status: str | None,
        include_deleted: bool,
        tag_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[DatasetSummary, ...]:
        self.require_project(tenant_id=tenant_id, project_id=project_id)
        statement = (
            select(Dataset)
            .where(Dataset.tenant_id == tenant_id)
            .where(Dataset.project_id == project_id)
            .order_by(Dataset.created_at.desc(), Dataset.id.asc())
            .limit(limit)
            .offset(offset)
        )
        if not include_deleted:
            statement = statement.where(Dataset.status != DatasetStatus.DELETED.value)
        if status is not None:
            statement = statement.where(Dataset.status == status)
        if validation_status is not None:
            statement = statement.where(Dataset.validation_status == validation_status)
        if recovery_status is not None:
            statement = statement.where(Dataset.recovery_status == recovery_status)
        if search:
            pattern = f"%{search}%"
            statement = statement.where(
                or_(Dataset.name.ilike(pattern), Dataset.original_filename.ilike(pattern))
            )
        if tag_id is not None:
            statement = statement.join(DatasetTag, DatasetTag.dataset_id == Dataset.id).where(
                DatasetTag.tag_id == tag_id
            )
        return tuple(self.summary(row) for row in self._session.scalars(statement).all())

    def get_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
    ) -> DatasetDetail:
        return self.detail(
            self._get_dataset(
                tenant_id=tenant_id,
                project_id=project_id,
                dataset_id=dataset_id,
            )
        )

    def get_validation_result(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
    ) -> DatasetValidationStatusResult:
        dataset = self._get_dataset(
            tenant_id=tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
        results = tuple(
            _validation_result(row)
            for row in self._session.scalars(
                select(DatasetValidationResult)
                .where(DatasetValidationResult.tenant_id == tenant_id)
                .where(DatasetValidationResult.project_id == project_id)
                .where(DatasetValidationResult.dataset_id == dataset_id)
                .order_by(
                    DatasetValidationResult.created_at.desc(),
                    DatasetValidationResult.id.desc(),
                )
            )
        )
        latest = results[0] if results else None
        return DatasetValidationStatusResult(
            dataset_id=dataset.id,
            project_id=dataset.project_id,
            dataset_status=dataset.status,
            validation_status=dataset.validation_status,
            preview_status=dataset.preview_status,
            preview_metadata=dict(dataset.preview_metadata or {}),
            extracted_metadata=dict((dataset.metadata_ or {}).get("extracted_metadata") or {}),
            latest_result=latest,
            results=results,
        )

    def get_dataset_model(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
    ) -> Dataset:
        return self._get_dataset(
            tenant_id=tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )

    def _get_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
    ) -> Dataset:
        dataset = self._session.get(Dataset, dataset_id)
        if dataset is None or dataset.tenant_id != tenant_id or dataset.project_id != project_id:
            raise ApiError(status_code=404, code="dataset.not_found", message="Dataset not found.")
        return dataset

    def require_project(self, *, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        project = self._session.get(Project, project_id)
        if project is None or project.tenant_id != tenant_id or project.deleted_at is not None:
            raise ApiError(status_code=404, code="project.not_found", message="Project not found.")
        return project

    def summary(self, dataset: Dataset) -> DatasetSummary:
        return DatasetSummary(
            dataset_id=dataset.id,
            project_id=dataset.project_id,
            name=dataset.name,
            status=dataset.status,
            original_filename=dataset.original_filename,
            content_type=dataset.content_type,
            file_size_bytes=dataset.file_size_bytes,
            validation_status=dataset.validation_status,
            recovery_status=dataset.recovery_status,
            labels=tuple(dataset.labels or ()),
            tag_ids=self._dataset_tag_ids(dataset.id),
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
            ready_at=dataset.ready_at,
            archived_at=dataset.archived_at,
            deleted_at=dataset.deleted_at,
        )

    def detail(self, dataset: Dataset) -> DatasetDetail:
        summary = self.summary(dataset)
        return DatasetDetail(
            dataset_id=summary.dataset_id,
            project_id=summary.project_id,
            name=summary.name,
            status=summary.status,
            original_filename=summary.original_filename,
            content_type=summary.content_type,
            file_size_bytes=summary.file_size_bytes,
            validation_status=summary.validation_status,
            recovery_status=summary.recovery_status,
            labels=summary.labels,
            tag_ids=summary.tag_ids,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            ready_at=summary.ready_at,
            archived_at=summary.archived_at,
            deleted_at=summary.deleted_at,
            bucket=dataset.bucket_name,
            object_key=dataset.object_key,
            object_etag=dataset.object_etag,
            object_size_bytes=dataset.object_size_bytes,
            object_version_id=dataset.object_version_id,
            checksum_sha256=dataset.checksum_sha256,
            source_device_id=dataset.source_device_id,
            source_device_code=dataset.source_device_code,
            preview_status=dataset.preview_status,
            preview_metadata=dict(dataset.preview_metadata or {}),
            metadata=dict(dataset.metadata_ or {}),
        )

    def _dataset_tag_ids(self, dataset_id: uuid.UUID) -> tuple[uuid.UUID, ...]:
        return tuple(
            self._session.scalars(
                select(DatasetTag.tag_id)
                .where(DatasetTag.dataset_id == dataset_id)
                .order_by(DatasetTag.tag_id.asc())
            )
        )


def _validation_result(row: DatasetValidationResult) -> DatasetValidationResultItem:
    return DatasetValidationResultItem(
        validation_result_id=row.id,
        status=row.status,
        validator_name=row.validator_name,
        validator_version=row.validator_version,
        extracted_metadata=dict(row.extracted_metadata or {}),
        errors=list(row.errors or []),
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )
