from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import AuthenticatedActor
from upload_control_plane.api.errors import ApiError
from upload_control_plane.config import Settings
from upload_control_plane.domain.datasets import (
    DatasetStatus,
    RecoveryStatus,
    ValidationStatus,
    dataset_allows_exposure,
)
from upload_control_plane.domain.storage import (
    DeleteObjectRequest,
    ObjectStorage,
    PresignDownloadObjectRequest,
    StorageError,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    DatasetTag,
    DatasetValidationResult,
    OutboxEvent,
    Project,
    StoragePolicy,
    Tag,
    TagCategory,
)


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: str
    original_filename: str | None
    content_type: str | None
    file_size_bytes: int | None
    validation_status: str
    recovery_status: str
    labels: tuple[str, ...]
    tag_ids: tuple[uuid.UUID, ...]
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None
    archived_at: datetime | None
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True)
class DatasetDetail(DatasetSummary):
    bucket: str | None
    object_key: str | None
    object_etag: str | None
    object_size_bytes: int | None
    object_version_id: str | None
    checksum_sha256: str | None
    source_device_id: uuid.UUID | None
    source_device_code: str | None
    preview_status: str
    preview_metadata: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DatasetValidationResultItem:
    validation_result_id: uuid.UUID
    status: str
    validator_name: str
    validator_version: str | None
    extracted_metadata: dict[str, Any]
    errors: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DatasetValidationStatusResult:
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    dataset_status: str
    validation_status: str
    preview_status: str
    preview_metadata: dict[str, Any]
    extracted_metadata: dict[str, Any]
    latest_result: DatasetValidationResultItem | None
    results: tuple[DatasetValidationResultItem, ...]


@dataclass(frozen=True, slots=True)
class RetryValidationResult:
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    dataset_status: str
    validation_status: str
    retry_queued: bool


@dataclass(frozen=True, slots=True)
class DownloadUrlResult:
    dataset_id: uuid.UUID
    method: str
    url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TagCategoryResult:
    category_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    color: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TagResult:
    tag_id: uuid.UUID
    project_id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    color: str | None
    created_at: datetime
    updated_at: datetime


class DatasetLifecycleService:
    def __init__(self, *, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings

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
        self._require_project(tenant_id=tenant_id, project_id=project_id)
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
        return tuple(self._summary(row) for row in self._session.scalars(statement).all())

    def get_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
    ) -> DatasetDetail:
        dataset = self._get_dataset(
            tenant_id=tenant_id, project_id=project_id, dataset_id=dataset_id
        )
        return self._detail(dataset)

    def get_validation_result(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
    ) -> DatasetValidationStatusResult:
        dataset = self._get_dataset(
            tenant_id=tenant_id, project_id=project_id, dataset_id=dataset_id
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

        before = self._audit_state(dataset)
        now = datetime.now(UTC)
        dataset.status = DatasetStatus.PROCESSING.value
        dataset.validation_status = ValidationStatus.PENDING.value
        dataset.updated_at = now
        after = self._audit_state(dataset)
        self._add_audit(
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

    def update_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        name: str | None,
        metadata: dict[str, Any] | None,
        labels: tuple[str, ...] | None,
        tag_ids: tuple[uuid.UUID, ...] | None,
    ) -> DatasetDetail:
        dataset = self._get_dataset(
            tenant_id=tenant_id, project_id=project_id, dataset_id=dataset_id
        )
        if dataset.status in {DatasetStatus.DELETED.value, DatasetStatus.PURGED.value}:
            raise ApiError(
                status_code=409,
                code="dataset.invalid_state",
                message="Dataset cannot be updated in its current lifecycle state.",
                details={"status": dataset.status},
            )
        before = self._audit_state(dataset)
        now = datetime.now(UTC)
        if name is not None:
            dataset.name = name
        if metadata is not None:
            dataset.metadata_ = dict(metadata)
        if labels is not None:
            dataset.labels = list(labels)
        if tag_ids is not None:
            self._replace_dataset_tags(dataset, tag_ids)
        dataset.updated_at = now
        self._add_audit(
            dataset,
            actor=actor,
            action="dataset.update",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit_state(dataset),
        )
        self._session.commit()
        return self._detail(dataset)

    def create_download_url(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        expires_in_seconds: int,
    ) -> DownloadUrlResult:
        dataset = self._get_dataset(
            tenant_id=tenant_id, project_id=project_id, dataset_id=dataset_id
        )
        if not dataset_allows_exposure(
            DatasetStatus(dataset.status),
            ValidationStatus(dataset.validation_status),
            RecoveryStatus(dataset.recovery_status),
        ):
            self._add_audit(
                dataset,
                actor=actor,
                action="dataset.download_url",
                result="DENIED",
                request_id=request_id,
                metadata={"reason": "exposure_policy"},
            )
            self._session.commit()
            raise ApiError(
                status_code=409,
                code="dataset.exposure_denied",
                message="Dataset is not available for download in its current exposure state.",
                details={
                    "dataset_status": dataset.status,
                    "validation_status": dataset.validation_status,
                    "recovery_status": dataset.recovery_status,
                },
            )
        if dataset.bucket_name is None or dataset.object_key is None:
            self._add_audit(
                dataset,
                actor=actor,
                action="dataset.download_url",
                result="DENIED",
                request_id=request_id,
                metadata={"reason": "object_missing"},
            )
            self._session.commit()
            raise ApiError(
                status_code=409,
                code="dataset.object_missing",
                message="Dataset has no completed storage object.",
            )
        bounded_expiry = min(expires_in_seconds, self._settings.max_download_url_expiry_seconds)
        try:
            presigned = self._storage.presign_download_object(
                PresignDownloadObjectRequest(
                    bucket=dataset.bucket_name,
                    object_key=dataset.object_key,
                    expires_in_seconds=bounded_expiry,
                )
            )
        except StorageError as exc:
            raise ApiError(
                status_code=502,
                code="storage.download_presign_failed",
                message="Storage download URL presign failed.",
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc
        self._add_audit(
            dataset,
            actor=actor,
            action="dataset.download_url",
            result="SUCCESS",
            request_id=request_id,
            metadata={"expires_at": presigned.expires_at.isoformat()},
        )
        self._session.commit()
        return DownloadUrlResult(
            dataset_id=dataset.id,
            method=presigned.method,
            url=presigned.url,
            expires_at=presigned.expires_at,
        )

    def archive_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
    ) -> DatasetDetail:
        dataset = self._get_dataset(
            tenant_id=tenant_id, project_id=project_id, dataset_id=dataset_id
        )
        if dataset.status != DatasetStatus.READY.value:
            raise self._invalid_state(dataset, "archive")
        before = self._audit_state(dataset)
        now = datetime.now(UTC)
        dataset.status = DatasetStatus.ARCHIVED.value
        dataset.archived_at = now
        dataset.updated_at = now
        self._add_audit(
            dataset,
            actor=actor,
            action="dataset.archive",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit_state(dataset),
        )
        self._session.commit()
        return self._detail(dataset)

    def soft_delete_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
    ) -> DatasetDetail:
        dataset = self._get_dataset(
            tenant_id=tenant_id, project_id=project_id, dataset_id=dataset_id
        )
        if dataset.status == DatasetStatus.PURGED.value:
            raise self._invalid_state(dataset, "delete")
        before = self._audit_state(dataset)
        now = datetime.now(UTC)
        if dataset.status != DatasetStatus.DELETED.value:
            metadata = dict(dataset.metadata_ or {})
            metadata.setdefault("deleted_from_status", dataset.status)
            dataset.metadata_ = metadata
            dataset.status = DatasetStatus.DELETED.value
            dataset.deleted_at = now
            dataset.updated_at = now
        self._add_audit(
            dataset,
            actor=actor,
            action="dataset.delete",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit_state(dataset),
        )
        self._session.commit()
        return self._detail(dataset)

    def restore_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
    ) -> DatasetDetail:
        dataset = self._get_dataset(
            tenant_id=tenant_id, project_id=project_id, dataset_id=dataset_id
        )
        if dataset.status != DatasetStatus.DELETED.value:
            raise self._invalid_state(dataset, "restore")
        before = self._audit_state(dataset)
        metadata = dict(dataset.metadata_ or {})
        restored_status = metadata.pop("deleted_from_status", DatasetStatus.READY.value)
        if restored_status not in {DatasetStatus.READY.value, DatasetStatus.ARCHIVED.value}:
            restored_status = DatasetStatus.READY.value
        dataset.metadata_ = metadata
        dataset.status = restored_status
        dataset.deleted_at = None
        dataset.updated_at = datetime.now(UTC)
        self._add_audit(
            dataset,
            actor=actor,
            action="dataset.restore",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit_state(dataset),
        )
        self._session.commit()
        return self._detail(dataset)

    def purge_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        confirm_purge: bool,
    ) -> DatasetDetail:
        dataset = self._get_dataset(
            tenant_id=tenant_id, project_id=project_id, dataset_id=dataset_id
        )
        if dataset.status != DatasetStatus.DELETED.value:
            raise self._invalid_state(dataset, "purge")
        policy = self._storage_policy_for_project(tenant_id=tenant_id, project_id=project_id)
        denial = self._purge_policy_denial(dataset, policy=policy, confirm_purge=confirm_purge)
        if denial is not None:
            self._add_audit(
                dataset,
                actor=actor,
                action="dataset.purge",
                result="DENIED",
                request_id=request_id,
                metadata=denial,
            )
            self._session.commit()
            raise ApiError(
                status_code=409,
                code="dataset.purge_policy_denied",
                message="Dataset purge is denied by retention or storage governance policy.",
                details=denial,
            )
        before = self._audit_state(dataset)
        if dataset.bucket_name and dataset.object_key:
            try:
                self._storage.delete_object(
                    DeleteObjectRequest(
                        bucket=dataset.bucket_name,
                        object_key=dataset.object_key,
                        version_id=dataset.object_version_id,
                    )
                )
            except StorageError as exc:
                raise ApiError(
                    status_code=502,
                    code="storage.delete_object_failed",
                    message="Storage object delete failed.",
                    details={"operation": exc.operation, "provider_code": exc.provider_code},
                ) from exc
        now = datetime.now(UTC)
        dataset.status = DatasetStatus.PURGED.value
        dataset.updated_at = now
        dataset.bucket_name = None
        dataset.object_key = None
        dataset.object_etag = None
        dataset.object_size_bytes = None
        dataset.object_version_id = None
        self._add_audit(
            dataset,
            actor=actor,
            action="dataset.purge",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit_state(dataset),
        )
        self._session.commit()
        return self._detail(dataset)

    def list_tag_categories(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> tuple[TagCategoryResult, ...]:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        rows = self._session.scalars(
            select(TagCategory)
            .where(TagCategory.tenant_id == tenant_id)
            .where(TagCategory.project_id == project_id)
            .order_by(TagCategory.sort_order.asc(), TagCategory.name.asc())
        ).all()
        return tuple(_category_result(row) for row in rows)

    def create_tag_category(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        color: str | None,
        sort_order: int,
    ) -> TagCategoryResult:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        now = datetime.now(UTC)
        category = TagCategory(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            name=name,
            color=color,
            sort_order=sort_order,
            created_at=now,
            updated_at=now,
        )
        self._session.add(category)
        self._session.commit()
        return _category_result(category)

    def update_tag_category(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        category_id: uuid.UUID,
        name: str | None,
        color: str | None,
        sort_order: int | None,
    ) -> TagCategoryResult:
        category = self._get_tag_category(
            tenant_id=tenant_id, project_id=project_id, category_id=category_id
        )
        if name is not None:
            category.name = name
        if color is not None:
            category.color = color
        if sort_order is not None:
            category.sort_order = sort_order
        category.updated_at = datetime.now(UTC)
        self._session.commit()
        return _category_result(category)

    def delete_tag_category(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        category_id: uuid.UUID,
    ) -> None:
        category = self._get_tag_category(
            tenant_id=tenant_id, project_id=project_id, category_id=category_id
        )
        self._session.delete(category)
        self._session.commit()

    def list_tags(self, *, tenant_id: uuid.UUID, project_id: uuid.UUID) -> tuple[TagResult, ...]:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        rows = self._session.scalars(
            select(Tag)
            .where(Tag.tenant_id == tenant_id)
            .where(Tag.project_id == project_id)
            .order_by(Tag.name.asc(), Tag.id.asc())
        ).all()
        return tuple(_tag_result(row) for row in rows)

    def create_tag(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        category_id: uuid.UUID | None,
        name: str,
        color: str | None,
    ) -> TagResult:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        if category_id is not None:
            self._get_tag_category(
                tenant_id=tenant_id, project_id=project_id, category_id=category_id
            )
        now = datetime.now(UTC)
        tag = Tag(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            category_id=category_id,
            name=name,
            color=color,
            created_at=now,
            updated_at=now,
        )
        self._session.add(tag)
        self._session.commit()
        return _tag_result(tag)

    def update_tag(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        tag_id: uuid.UUID,
        category_id: uuid.UUID | None,
        name: str | None,
        color: str | None,
    ) -> TagResult:
        tag = self._get_tag(tenant_id=tenant_id, project_id=project_id, tag_id=tag_id)
        if category_id is not None:
            self._get_tag_category(
                tenant_id=tenant_id, project_id=project_id, category_id=category_id
            )
            tag.category_id = category_id
        if name is not None:
            tag.name = name
        if color is not None:
            tag.color = color
        tag.updated_at = datetime.now(UTC)
        self._session.commit()
        return _tag_result(tag)

    def delete_tag(self, *, tenant_id: uuid.UUID, project_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        self._get_tag(tenant_id=tenant_id, project_id=project_id, tag_id=tag_id)
        self._session.execute(delete(DatasetTag).where(DatasetTag.tag_id == tag_id))
        self._session.execute(delete(Tag).where(Tag.id == tag_id))
        self._session.commit()

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

    def _require_project(self, *, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        project = self._session.get(Project, project_id)
        if project is None or project.tenant_id != tenant_id or project.deleted_at is not None:
            raise ApiError(status_code=404, code="project.not_found", message="Project not found.")
        return project

    def _storage_policy_for_project(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> StoragePolicy | None:
        project = self._require_project(tenant_id=tenant_id, project_id=project_id)
        if project.storage_policy_id is None:
            return None
        policy = self._session.get(StoragePolicy, project.storage_policy_id)
        if policy is None or policy.tenant_id != tenant_id:
            return None
        return policy

    def _purge_policy_denial(
        self,
        dataset: Dataset,
        *,
        policy: StoragePolicy | None,
        confirm_purge: bool,
    ) -> dict[str, Any] | None:
        if not confirm_purge:
            return {"reason": "confirmation_required"}
        if dataset.deleted_at is None:
            return {"reason": "deleted_timestamp_missing"}
        if policy is None:
            return None
        if policy.legal_hold_default:
            return {"reason": "legal_hold", "storage_policy_id": str(policy.id)}
        if policy.object_lock_mode:
            return {
                "reason": "object_lock",
                "storage_policy_id": str(policy.id),
                "object_lock_mode": policy.object_lock_mode,
            }
        if policy.retention_days is not None:
            purge_after = dataset.deleted_at + timedelta(days=policy.retention_days)
            if datetime.now(UTC) < purge_after:
                return {
                    "reason": "retention_active",
                    "storage_policy_id": str(policy.id),
                    "purge_after": purge_after.isoformat(),
                    "retention_days": policy.retention_days,
                }
        return None

    def _replace_dataset_tags(self, dataset: Dataset, tag_ids: tuple[uuid.UUID, ...]) -> None:
        if len(set(tag_ids)) != len(tag_ids):
            raise ApiError(
                status_code=422,
                code="tag.duplicate_ids",
                message="Dataset tag IDs must not contain duplicates.",
            )
        if tag_ids:
            count = self._session.scalar(
                select(func.count())
                .select_from(Tag)
                .where(Tag.tenant_id == dataset.tenant_id)
                .where(Tag.project_id == dataset.project_id)
                .where(Tag.id.in_(tag_ids))
            )
            if count != len(tag_ids):
                raise ApiError(status_code=404, code="tag.not_found", message="Tag not found.")
        self._session.execute(delete(DatasetTag).where(DatasetTag.dataset_id == dataset.id))
        for tag_id in tag_ids:
            self._session.add(DatasetTag(dataset_id=dataset.id, tag_id=tag_id))

    def _get_tag_category(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        category_id: uuid.UUID,
    ) -> TagCategory:
        category = self._session.get(TagCategory, category_id)
        if category is None or category.tenant_id != tenant_id or category.project_id != project_id:
            raise ApiError(
                status_code=404,
                code="tag_category.not_found",
                message="Tag category not found.",
            )
        return category

    def _get_tag(self, *, tenant_id: uuid.UUID, project_id: uuid.UUID, tag_id: uuid.UUID) -> Tag:
        tag = self._session.get(Tag, tag_id)
        if tag is None or tag.tenant_id != tenant_id or tag.project_id != project_id:
            raise ApiError(status_code=404, code="tag.not_found", message="Tag not found.")
        return tag

    def _invalid_state(self, dataset: Dataset, action: str) -> ApiError:
        return ApiError(
            status_code=409,
            code="dataset.invalid_state",
            message=f"Dataset is not in a state that allows {action}.",
            details={"dataset_status": dataset.status},
        )

    def _summary(self, dataset: Dataset) -> DatasetSummary:
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

    def _detail(self, dataset: Dataset) -> DatasetDetail:
        summary = self._summary(dataset)
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

    def _audit_state(self, dataset: Dataset) -> dict[str, Any]:
        return {
            "dataset_id": str(dataset.id),
            "status": dataset.status,
            "name": dataset.name,
            "validation_status": dataset.validation_status,
            "recovery_status": dataset.recovery_status,
            "bucket": dataset.bucket_name,
            "object_key": dataset.object_key,
            "deleted_at": dataset.deleted_at.isoformat() if dataset.deleted_at else None,
        }

    def _add_audit(
        self,
        dataset: Dataset,
        *,
        actor: AuthenticatedActor,
        action: str,
        result: str,
        request_id: str | None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuditEvent(
                tenant_id=dataset.tenant_id,
                project_id=dataset.project_id,
                dataset_id=dataset.id,
                actor_type="api_key",
                actor_id=str(actor.subject_id),
                action=action,
                resource_type="dataset",
                resource_id=str(dataset.id),
                result=result,
                request_id=request_id,
                before_state=before_state,
                after_state=after_state,
                metadata_=metadata or {"source": "dataset_lifecycle"},
            )
        )


def _category_result(category: TagCategory) -> TagCategoryResult:
    return TagCategoryResult(
        category_id=category.id,
        project_id=category.project_id,
        name=category.name,
        color=category.color,
        sort_order=category.sort_order,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def _tag_result(tag: Tag) -> TagResult:
    return TagResult(
        tag_id=tag.id,
        project_id=tag.project_id,
        category_id=tag.category_id,
        name=tag.name,
        color=tag.color,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
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
