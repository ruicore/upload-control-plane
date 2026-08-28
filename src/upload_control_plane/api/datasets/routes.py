from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import DB_SESSION, AuthenticatedActor
from upload_control_plane.api.request_context import get_request_id
from upload_control_plane.application.datasets import compose_dataset_services
from upload_control_plane.config import Settings
from upload_control_plane.domain.datasets import (
    DatasetStatus,
    RecoveryStatus,
    ValidationStatus,
)
from upload_control_plane.domain.storage import ObjectStorage

from .dependencies import AUTH_ACTOR, OBJECT_STORAGE, SETTINGS_DEPENDENCY
from .mappers import (
    detail_response,
    download_response,
    retry_validation_response,
    summary_response,
    validation_response,
)
from .permissions import require_dataset_permission, require_project_permission
from .schemas import (
    DatasetDetailResponse,
    DatasetListResponse,
    DatasetUpdateRequest,
    DatasetValidationResponse,
    DownloadUrlRequest,
    DownloadUrlResponse,
    PurgeDatasetRequest,
    RetryValidationResponse,
)
from .tag_routes import (
    create_tag,
    create_tag_category,
    delete_tag,
    delete_tag_category,
    list_tag_categories,
    list_tags,
    update_tag,
    update_tag_category,
)
from .tag_routes import (
    router as tag_router,
)

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["datasets"])


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
    require_project_permission(
        session, actor=actor, project_id=project_id, permission="dataset.view"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    datasets = services.queries.list_datasets(
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
    return DatasetListResponse(datasets=[summary_response(item) for item in datasets])


@router.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> DatasetDetailResponse:
    require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.view"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return detail_response(
        services.queries.get_dataset(
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
    require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.view"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return validation_response(
        services.queries.get_validation_result(
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
    require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.validate"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return retry_validation_response(
        services.validation.retry_validation(
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
    require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.update"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return detail_response(
        services.updates.update_dataset(
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
    require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.download"
    )
    response.headers["Cache-Control"] = "no-store"
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return download_response(
        services.downloads.create_download_url(
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
    require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.archive"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return detail_response(
        services.lifecycle.archive_dataset(
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
    require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.delete"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return detail_response(
        services.lifecycle.soft_delete_dataset(
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
    require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.restore"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return detail_response(
        services.lifecycle.restore_dataset(
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
    require_dataset_permission(
        session, actor=actor, dataset_id=dataset_id, permission="dataset.purge"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return detail_response(
        services.purge.purge_dataset(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
            actor=actor,
            request_id=get_request_id(),
            confirm_purge=request.confirm_purge,
        )
    )


router.include_router(tag_router)


__all__ = [
    "archive_dataset",
    "create_download_url",
    "create_tag",
    "create_tag_category",
    "delete_tag",
    "delete_tag_category",
    "get_dataset",
    "get_dataset_validation",
    "list_datasets",
    "list_tag_categories",
    "list_tags",
    "purge_dataset",
    "restore_dataset",
    "retry_dataset_validation",
    "router",
    "soft_delete_dataset",
    "update_dataset",
    "update_tag",
    "update_tag_category",
]
