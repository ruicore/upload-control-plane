from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import DB_SESSION, AuthenticatedActor, require_api_key
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.domain.permissions import ResourceType
from upload_control_plane.infrastructure.db.models import Project

router = APIRouter(prefix="/v1/projects", tags=["projects"])
AUTH_ACTOR = Depends(require_api_key)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: uuid.UUID
    tenant_id: uuid.UUID
    storage_policy_id: uuid.UUID | None
    slug: str
    name: str
    description: str | None
    status: str
    metadata_schema: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    effective_permissions: list[str] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]


@router.get("", response_model=ProjectListResponse)
def list_projects(
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
) -> ProjectListResponse:
    authorization = AuthorizationService(session)
    projects = authorization.visible_projects(actor)
    return ProjectListResponse(
        projects=[
            _project_response(project, authorization=authorization, actor=actor)
            for project in projects
        ]
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
) -> ProjectResponse:
    authorization = AuthorizationService(session)
    authorization.require_permission(
        actor=actor,
        permission_code="project.view",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    project = session.get(Project, project_id)
    if project is None:
        # require_permission resolves the project first, so this is only a defensive guard.
        raise AssertionError("project disappeared during request")
    return _project_response(project, authorization=authorization, actor=actor)


def _project_response(
    project: Project,
    *,
    authorization: AuthorizationService,
    actor: AuthenticatedActor,
) -> ProjectResponse:
    return ProjectResponse(
        project_id=project.id,
        tenant_id=project.tenant_id,
        storage_policy_id=project.storage_policy_id,
        slug=project.slug,
        name=project.name,
        description=project.description,
        status=project.status,
        metadata_schema=project.metadata_schema,
        metadata=project.metadata_,
        created_at=project.created_at,
        updated_at=project.updated_at,
        archived_at=project.archived_at,
        effective_permissions=list(
            authorization.effective_permissions(
                actor=actor,
                resource_type=ResourceType.PROJECT,
                resource_id=project.id,
            )
        ),
    )
