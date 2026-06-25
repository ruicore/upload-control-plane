from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import DB_SESSION, AuthenticatedActor, require_api_key
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.domain.permissions import ResourceType
from upload_control_plane.infrastructure.db.models import AuditEvent
from upload_control_plane.observability import metrics_registry, sanitize_for_observability

router = APIRouter(tags=["observability"])
AUTH_ACTOR = Depends(require_api_key)


class AuditEventResponse(BaseModel):
    audit_event_id: uuid.UUID
    project_id: uuid.UUID | None
    dataset_id: uuid.UUID | None
    actor_type: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str
    result: str
    request_id: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    metadata: dict[str, Any]
    created_at: datetime


class AuditEventListResponse(BaseModel):
    audit_events: list[AuditEventResponse]


@router.get("/metrics", include_in_schema=False)
def metrics(session: Session = DB_SESSION) -> Response:
    body = metrics_registry.render(session=session)
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get(
    "/v1/projects/{project_id}/audit-events",
    response_model=AuditEventListResponse,
)
def list_project_audit_events(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID | None = None,
    action: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
) -> AuditEventListResponse:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="audit.view",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    statement = (
        select(AuditEvent)
        .where(AuditEvent.tenant_id == actor.tenant_id)
        .where(AuditEvent.project_id == project_id)
        .order_by(desc(AuditEvent.created_at), desc(AuditEvent.id))
        .limit(limit)
    )
    if dataset_id is not None:
        statement = statement.where(AuditEvent.dataset_id == dataset_id)
    if action is not None:
        statement = statement.where(AuditEvent.action == action)
    events = session.scalars(statement).all()
    return AuditEventListResponse(audit_events=[_audit_response(event) for event in events])


def _audit_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        audit_event_id=event.id,
        project_id=event.project_id,
        dataset_id=event.dataset_id,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        result=event.result,
        request_id=event.request_id,
        before_state=sanitize_for_observability(event.before_state),
        after_state=sanitize_for_observability(event.after_state),
        metadata=sanitize_for_observability(event.metadata_),
        created_at=event.created_at,
    )
