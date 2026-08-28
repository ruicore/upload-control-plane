from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from upload_control_plane.api.auth import AuthenticatedActor
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.domain.permissions import ResourceType


def require_project_permission(
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


def require_dataset_permission(
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
