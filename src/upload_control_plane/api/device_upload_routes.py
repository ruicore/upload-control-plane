from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import DB_SESSION, AuthenticatedActor, require_api_key
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.api.request_context import get_request_id
from upload_control_plane.api.upload_task_contracts import (
    UploadTaskCreateRequest,
    UploadTaskCreateResponse,
    _object_input,
    _response,
)
from upload_control_plane.api.upload_tasks import (
    OBJECT_STORAGE,
    SETTINGS_DEPENDENCY,
)
from upload_control_plane.application.upload_tasks import (
    CreateUploadTaskCommand,
    UploadTaskCreationService,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.permissions import ResourceType
from upload_control_plane.domain.storage import ObjectStorage
from upload_control_plane.infrastructure.db.models import Device

router = APIRouter()
IDEMPOTENCY_KEY_HEADER = Header(default=None, alias="Idempotency-Key")
AUTH_ACTOR = Depends(require_api_key)


@router.post("/{device_id}/upload", status_code=201, response_model=UploadTaskCreateResponse)
def create_device_upload_task(
    project_id: uuid.UUID,
    device_id: uuid.UUID,
    request: UploadTaskCreateRequest,
    idempotency_key: str | None = IDEMPOTENCY_KEY_HEADER,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> UploadTaskCreateResponse:
    if actor.actor_type != "device" or actor.device_id != device_id:
        from upload_control_plane.api.errors import ApiError

        raise ApiError(
            status_code=403,
            code="device.identity_mismatch",
            message="Device upload requires the matching device credential.",
        )
    device = _require_upload_device(session, actor=actor, device_id=device_id)
    AuthorizationService(session).require_any_permission(
        actor=actor,
        permission_codes=("dataset.upload", "upload.create"),
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    service = UploadTaskCreationService(session=session, storage=storage, settings=settings)
    payload = request.model_copy(
        update={
            "task_initiator": "device",
            "source_device_id": device.id,
            "source_device_code": device.device_code or request.source_device_code,
        }
    )
    result = service.create_upload_task(
        CreateUploadTaskCommand(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            actor=actor,
            request_path=f"/v1/projects/{project_id}/devices/{device_id}/upload",
            request_body=payload.model_dump(mode="json"),
            request_id=get_request_id(),
            task_name=payload.task_name,
            task_initiator="device",
            source_device_id=device.id,
            source_device_code=payload.source_device_code,
            storage_policy_id=payload.storage_policy_id,
            idempotency_key=idempotency_key,
            objects=tuple(_object_input(item) for item in payload.objects),
            metadata=payload.metadata,
        )
    )
    return _response(result)


def _require_upload_device(
    session: Session,
    *,
    actor: AuthenticatedActor,
    device_id: uuid.UUID,
) -> Device:
    device = session.get(Device, device_id)
    if device is None or device.tenant_id != actor.tenant_id or device.status != "ACTIVE":
        from upload_control_plane.api.errors import ApiError

        raise ApiError(status_code=404, code="device.not_found", message="Device not found.")
    return device
