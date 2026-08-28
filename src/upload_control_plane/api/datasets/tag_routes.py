from __future__ import annotations

import uuid

from fastapi import APIRouter, Response
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import DB_SESSION, AuthenticatedActor
from upload_control_plane.application.datasets import compose_dataset_services
from upload_control_plane.config import Settings
from upload_control_plane.domain.storage import ObjectStorage

from .dependencies import AUTH_ACTOR, OBJECT_STORAGE, SETTINGS_DEPENDENCY
from .mappers import category_response, tag_response
from .permissions import require_project_permission
from .schemas import (
    TagCategoryCreateRequest,
    TagCategoryListResponse,
    TagCategoryResponse,
    TagCategoryUpdateRequest,
    TagCreateRequest,
    TagListResponse,
    TagResponse,
    TagUpdateRequest,
)

router = APIRouter()


@router.get("/tag-categories", response_model=TagCategoryListResponse)
def list_tag_categories(
    project_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> TagCategoryListResponse:
    require_project_permission(
        session, actor=actor, project_id=project_id, permission="dataset.view"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return TagCategoryListResponse(
        tag_categories=[
            category_response(item)
            for item in services.tags.list_tag_categories(
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
    require_project_permission(session, actor=actor, project_id=project_id, permission="tag.create")
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return category_response(
        services.tags.create_tag_category(
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
    require_project_permission(session, actor=actor, project_id=project_id, permission="tag.update")
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return category_response(
        services.tags.update_tag_category(
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
    require_project_permission(session, actor=actor, project_id=project_id, permission="tag.delete")
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    services.tags.delete_tag_category(
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
    require_project_permission(
        session, actor=actor, project_id=project_id, permission="dataset.view"
    )
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return TagListResponse(
        tags=[
            tag_response(item)
            for item in services.tags.list_tags(
                tenant_id=actor.tenant_id,
                project_id=project_id,
            )
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
    require_project_permission(session, actor=actor, project_id=project_id, permission="tag.create")
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return tag_response(
        services.tags.create_tag(
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
    require_project_permission(session, actor=actor, project_id=project_id, permission="tag.update")
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    return tag_response(
        services.tags.update_tag(
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
    require_project_permission(session, actor=actor, project_id=project_id, permission="tag.delete")
    services = compose_dataset_services(session=session, storage=storage, settings=settings)
    services.tags.delete_tag(
        tenant_id=actor.tenant_id,
        project_id=project_id,
        tag_id=tag_id,
    )
    return Response(status_code=204)
