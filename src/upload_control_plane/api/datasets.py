from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import DB_SESSION, AuthenticatedActor, require_api_key
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.api.request_context import get_request_id
from upload_control_plane.api.upload_tasks import OBJECT_STORAGE, SETTINGS_DEPENDENCY
from upload_control_plane.application.datasets import (
    DatasetDetail,
    DatasetLifecycleService,
    DatasetSummary,
    DatasetValidationResultItem,
    DatasetValidationStatusResult,
    DownloadUrlResult,
    RetryValidationResult,
    TagCategoryResult,
    TagResult,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.datasets import DatasetStatus, RecoveryStatus, ValidationStatus
from upload_control_plane.domain.permissions import ResourceType
from upload_control_plane.domain.storage import ObjectStorage

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["datasets"])
AUTH_ACTOR = Depends(require_api_key)


class DatasetSummaryResponse(BaseModel):
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: str
    original_filename: str | None
    content_type: str | None
    file_size_bytes: int | None
    validation_status: str
    recovery_status: str
    labels: list[str]
    tag_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None
    archived_at: datetime | None
    deleted_at: datetime | None


class DatasetDetailResponse(DatasetSummaryResponse):
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


class DatasetListResponse(BaseModel):
    datasets: list[DatasetSummaryResponse]


class DatasetValidationResultResponse(BaseModel):
    validation_result_id: uuid.UUID
    status: str
    validator_name: str
    validator_version: str | None
    extracted_metadata: dict[str, Any]
    errors: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class DatasetValidationResponse(BaseModel):
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    dataset_status: str
    validation_status: str
    preview_status: str
    preview_metadata: dict[str, Any]
    extracted_metadata: dict[str, Any]
    latest_result: DatasetValidationResultResponse | None
    results: list[DatasetValidationResultResponse]


class DatasetUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    metadata: dict[str, Any] | None = None
    labels: list[str] | None = None
    tag_ids: list[uuid.UUID] | None = None

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(set(value)) != len(value):
            raise ValueError("labels must not contain duplicates")
        if any(not item or len(item) > 64 for item in value):
            raise ValueError("labels must be non-empty and at most 64 characters")
        return value


class DownloadUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_in_seconds: int = Field(default=900, gt=0)
    purpose: str | None = Field(default=None, max_length=256)


class DownloadUrlResponse(BaseModel):
    dataset_id: uuid.UUID
    method: Literal["GET"]
    url: str
    expires_at: datetime


class RetryValidationResponse(BaseModel):
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    dataset_status: str
    validation_status: str
    retry_queued: bool


class PurgeDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_purge: bool = False


class TagCategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)
    sort_order: int = 0


class TagCategoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)
    sort_order: int | None = None


class TagCategoryResponse(BaseModel):
    category_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    color: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TagCategoryListResponse(BaseModel):
    tag_categories: list[TagCategoryResponse]


class TagCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)


class TagUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)


class TagResponse(BaseModel):
    tag_id: uuid.UUID
    project_id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    color: str | None
    created_at: datetime
    updated_at: datetime


class TagListResponse(BaseModel):
    tags: list[TagResponse]


@router.get("/datasets", response_model=DatasetListResponse)
def list_datasets(
    project_id: uuid.UUID,
    search: str | None = Query(default=None, max_length=255),
    status: DatasetStatus | None = None,
    validation_status: ValidationStatus | None = None,
    recovery_status: RecoveryStatus | None = None,
    include_deleted: bool = False,
    tag_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DatasetListResponse:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="dataset.view",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    datasets = service.list_datasets(
        tenant_id=actor.tenant_id,
        project_id=project_id,
        search=search,
        status=status.value if status is not None else None,
        validation_status=validation_status.value if validation_status is not None else None,
        recovery_status=recovery_status.value if recovery_status is not None else None,
        include_deleted=include_deleted,
        tag_id=tag_id,
        limit=limit,
        offset=offset,
    )
    return DatasetListResponse(datasets=[_summary_response(item) for item in datasets])


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DatasetDetailResponse:
    _require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.view"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _detail_response(
        service.get_dataset(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
    )


@router.get("/datasets/{dataset_id}/validation", response_model=DatasetValidationResponse)
def get_dataset_validation(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DatasetValidationResponse:
    _require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.view"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _validation_response(
        service.get_validation_result(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
    )


@router.post(
    "/datasets/{dataset_id}/validation/retry",
    response_model=RetryValidationResponse,
)
def retry_dataset_validation(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> RetryValidationResponse:
    _require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.validate"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _retry_validation_response(
        service.retry_validation(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
            actor=actor,
            request_id=get_request_id(),
        )
    )


@router.patch("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def update_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    request: DatasetUpdateRequest,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DatasetDetailResponse:
    _require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.update"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _detail_response(
        service.update_dataset(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
            actor=actor,
            request_id=get_request_id(),
            name=request.name,
            metadata=request.metadata,
            labels=tuple(request.labels) if request.labels is not None else None,
            tag_ids=tuple(request.tag_ids) if request.tag_ids is not None else None,
        )
    )


@router.post("/datasets/{dataset_id}/download-url", response_model=DownloadUrlResponse)
def create_download_url(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    request: DownloadUrlRequest,
    response: Response,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DownloadUrlResponse:
    _ = request.purpose
    _require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.download"
    )
    response.headers["Cache-Control"] = "no-store"
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _download_response(
        service.create_download_url(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
            actor=actor,
            request_id=get_request_id(),
            expires_in_seconds=request.expires_in_seconds,
        )
    )


@router.post("/datasets/{dataset_id}/archive", response_model=DatasetDetailResponse)
def archive_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DatasetDetailResponse:
    _require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.archive"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _detail_response(
        service.archive_dataset(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
            actor=actor,
            request_id=get_request_id(),
        )
    )


@router.delete("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def soft_delete_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DatasetDetailResponse:
    _require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.delete"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _detail_response(
        service.soft_delete_dataset(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
            actor=actor,
            request_id=get_request_id(),
        )
    )


@router.post("/datasets/{dataset_id}/restore", response_model=DatasetDetailResponse)
def restore_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DatasetDetailResponse:
    _require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.restore"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _detail_response(
        service.restore_dataset(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
            actor=actor,
            request_id=get_request_id(),
        )
    )


@router.delete("/datasets/{dataset_id}/purge", response_model=DatasetDetailResponse)
def purge_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    request: PurgeDatasetRequest,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DatasetDetailResponse:
    _require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.purge"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _detail_response(
        service.purge_dataset(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
            actor=actor,
            request_id=get_request_id(),
            confirm_purge=request.confirm_purge,
        )
    )


@router.get("/tag-categories", response_model=TagCategoryListResponse)
def list_tag_categories(
    project_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> TagCategoryListResponse:
    _require_project_permission(
        session, actor=actor, project_id=project_id, permission="dataset.view"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return TagCategoryListResponse(
        tag_categories=[
            _category_response(item)
            for item in service.list_tag_categories(
                tenant_id=actor.tenant_id, project_id=project_id
            )
        ]
    )


@router.post("/tag-categories", status_code=201, response_model=TagCategoryResponse)
def create_tag_category(
    project_id: uuid.UUID,
    request: TagCategoryCreateRequest,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> TagCategoryResponse:
    _require_project_permission(
        session, actor=actor, project_id=project_id, permission="tag.create"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _category_response(
        service.create_tag_category(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            name=request.name,
            color=request.color,
            sort_order=request.sort_order,
        )
    )


@router.patch("/tag-categories/{category_id}", response_model=TagCategoryResponse)
def update_tag_category(
    project_id: uuid.UUID,
    category_id: uuid.UUID,
    request: TagCategoryUpdateRequest,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> TagCategoryResponse:
    _require_project_permission(
        session, actor=actor, project_id=project_id, permission="tag.update"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _category_response(
        service.update_tag_category(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            category_id=category_id,
            name=request.name,
            color=request.color,
            sort_order=request.sort_order,
        )
    )


@router.delete("/tag-categories/{category_id}", status_code=204)
def delete_tag_category(
    project_id: uuid.UUID,
    category_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> Response:
    _require_project_permission(
        session, actor=actor, project_id=project_id, permission="tag.delete"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    service.delete_tag_category(
        tenant_id=actor.tenant_id,
        project_id=project_id,
        category_id=category_id,
    )
    return Response(status_code=204)


@router.get("/tags", response_model=TagListResponse)
def list_tags(
    project_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> TagListResponse:
    _require_project_permission(
        session, actor=actor, project_id=project_id, permission="dataset.view"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return TagListResponse(
        tags=[
            _tag_response(item)
            for item in service.list_tags(tenant_id=actor.tenant_id, project_id=project_id)
        ]
    )


@router.post("/tags", status_code=201, response_model=TagResponse)
def create_tag(
    project_id: uuid.UUID,
    request: TagCreateRequest,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> TagResponse:
    _require_project_permission(
        session, actor=actor, project_id=project_id, permission="tag.create"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _tag_response(
        service.create_tag(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            category_id=request.category_id,
            name=request.name,
            color=request.color,
        )
    )


@router.patch("/tags/{tag_id}", response_model=TagResponse)
def update_tag(
    project_id: uuid.UUID,
    tag_id: uuid.UUID,
    request: TagUpdateRequest,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> TagResponse:
    _require_project_permission(
        session, actor=actor, project_id=project_id, permission="tag.update"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    return _tag_response(
        service.update_tag(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            tag_id=tag_id,
            category_id=request.category_id,
            name=request.name,
            color=request.color,
        )
    )


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(
    project_id: uuid.UUID,
    tag_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> Response:
    _require_project_permission(
        session, actor=actor, project_id=project_id, permission="tag.delete"
    )
    service = DatasetLifecycleService(session=session, storage=storage, settings=settings)
    service.delete_tag(tenant_id=actor.tenant_id, project_id=project_id, tag_id=tag_id)
    return Response(status_code=204)


def _require_project_permission(
    session: Session,
    *,
    actor: AuthenticatedActor,
    project_id: uuid.UUID,
    permission: str,
) -> None:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code=permission,
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )


def _require_dataset_permission(
    session: Session,
    *,
    actor: AuthenticatedActor,
    dataset_id: uuid.UUID,
    permission: str,
) -> None:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code=permission,
        resource_type=ResourceType.DATASET,
        resource_id=dataset_id,
    )


def _summary_response(item: DatasetSummary) -> DatasetSummaryResponse:
    return DatasetSummaryResponse(
        dataset_id=item.dataset_id,
        project_id=item.project_id,
        name=item.name,
        status=item.status,
        original_filename=item.original_filename,
        content_type=item.content_type,
        file_size_bytes=item.file_size_bytes,
        validation_status=item.validation_status,
        recovery_status=item.recovery_status,
        labels=list(item.labels),
        tag_ids=list(item.tag_ids),
        created_at=item.created_at,
        updated_at=item.updated_at,
        ready_at=item.ready_at,
        archived_at=item.archived_at,
        deleted_at=item.deleted_at,
    )


def _detail_response(item: DatasetDetail) -> DatasetDetailResponse:
    return DatasetDetailResponse(
        **_summary_response(item).model_dump(),
        bucket=item.bucket,
        object_key=item.object_key,
        object_etag=item.object_etag,
        object_size_bytes=item.object_size_bytes,
        object_version_id=item.object_version_id,
        checksum_sha256=item.checksum_sha256,
        source_device_id=item.source_device_id,
        source_device_code=item.source_device_code,
        preview_status=item.preview_status,
        preview_metadata=item.preview_metadata,
        metadata=item.metadata,
    )


def _download_response(item: DownloadUrlResult) -> DownloadUrlResponse:
    return DownloadUrlResponse(
        dataset_id=item.dataset_id,
        method="GET",
        url=item.url,
        expires_at=item.expires_at,
    )


def _validation_result_response(
    item: DatasetValidationResultItem,
) -> DatasetValidationResultResponse:
    return DatasetValidationResultResponse(
        validation_result_id=item.validation_result_id,
        status=item.status,
        validator_name=item.validator_name,
        validator_version=item.validator_version,
        extracted_metadata=item.extracted_metadata,
        errors=item.errors,
        started_at=item.started_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
    )


def _validation_response(item: DatasetValidationStatusResult) -> DatasetValidationResponse:
    return DatasetValidationResponse(
        dataset_id=item.dataset_id,
        project_id=item.project_id,
        dataset_status=item.dataset_status,
        validation_status=item.validation_status,
        preview_status=item.preview_status,
        preview_metadata=item.preview_metadata,
        extracted_metadata=item.extracted_metadata,
        latest_result=_validation_result_response(item.latest_result)
        if item.latest_result is not None
        else None,
        results=[_validation_result_response(result) for result in item.results],
    )


def _retry_validation_response(item: RetryValidationResult) -> RetryValidationResponse:
    return RetryValidationResponse(
        dataset_id=item.dataset_id,
        project_id=item.project_id,
        dataset_status=item.dataset_status,
        validation_status=item.validation_status,
        retry_queued=item.retry_queued,
    )


def _category_response(item: TagCategoryResult) -> TagCategoryResponse:
    return TagCategoryResponse(
        category_id=item.category_id,
        project_id=item.project_id,
        name=item.name,
        color=item.color,
        sort_order=item.sort_order,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _tag_response(item: TagResult) -> TagResponse:
    return TagResponse(
        tag_id=item.tag_id,
        project_id=item.project_id,
        category_id=item.category_id,
        name=item.name,
        color=item.color,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
