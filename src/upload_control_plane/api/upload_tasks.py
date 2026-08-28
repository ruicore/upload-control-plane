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
from upload_control_plane.application.upload_tasks import (
    CreateUploadTaskCommand,
    UploadTaskCreationService,
)
from upload_control_plane.config import Settings, get_settings
from upload_control_plane.domain.permissions import ResourceType
from upload_control_plane.domain.storage import ObjectStorage
from upload_control_plane.infrastructure.db.models import Device
from upload_control_plane.infrastructure.storage import build_s3_object_storage

router = APIRouter(prefix="/v1/projects/{project_id}/upload-tasks", tags=["upload-tasks"])
AUTH_ACTOR = Depends(require_api_key)
IDEMPOTENCY_KEY_HEADER = Header(default=None, alias="Idempotency-Key")
SETTINGS_DEPENDENCY = Depends(get_settings)


def get_object_storage(settings: Settings = SETTINGS_DEPENDENCY) -> ObjectStorage:
    return build_s3_object_storage(settings)


OBJECT_STORAGE = Depends(get_object_storage)


@router.post("", status_code=201, response_model=UploadTaskCreateResponse)
def create_upload_task(
    project_id: uuid.UUID,
    request: UploadTaskCreateRequest,
    idempotency_key: str | None = IDEMPOTENCY_KEY_HEADER,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> UploadTaskCreateResponse:
    authorization = AuthorizationService(session)
    authorization.require_any_permission(
        actor=actor,
        permission_codes=("dataset.upload", "upload.create"),
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    source_device_id = _validate_source_device(
        session=session,
        actor=actor,
        tenant_id=actor.tenant_id,
        project_id=project_id,
        source_device_id=request.source_device_id,
    )

    service = UploadTaskCreationService(session=session, storage=storage, settings=settings)
    result = service.create_upload_task(
        CreateUploadTaskCommand(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            actor=actor,
            request_path=f"/v1/projects/{project_id}/upload-tasks",
            request_body=request.model_dump(mode="json"),
            request_id=get_request_id(),
            task_name=request.task_name,
            task_initiator=request.task_initiator,
            source_device_id=source_device_id,
            source_device_code=request.source_device_code,
            storage_policy_id=request.storage_policy_id,
            idempotency_key=idempotency_key,
            objects=tuple(_object_input(item) for item in request.objects),
            metadata=request.metadata,
        )
    )
    return _response(result)


def _validate_source_device(
    *,
    session: Session,
    actor: AuthenticatedActor,
    tenant_id: uuid.UUID,
    project_id: uuid.UUID,
    source_device_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if actor.actor_type == "device":
        if source_device_id is None:
            return actor.device_id
        if source_device_id != actor.device_id:
            from upload_control_plane.api.errors import ApiError

            raise ApiError(
                status_code=403,
                code="device.identity_mismatch",
                message="Device credential cannot create uploads for another device.",
            )

    if source_device_id is None:
        return None

    device = session.get(Device, source_device_id)
    if device is None or device.tenant_id != tenant_id or device.status == "DELETED":
        from upload_control_plane.api.errors import ApiError

        raise ApiError(
            status_code=422,
            code="device.source_device_invalid",
            message="source_device_id must reference a registered device UUID.",
        )
    if device.status != "ACTIVE":
        from upload_control_plane.api.errors import ApiError

        raise ApiError(
            status_code=403,
            code="device.inactive",
            message="Device is not active.",
            details={"device_id": str(device.id), "status": device.status},
        )

    authorization = AuthorizationService(session)
    if not authorization.has_any_permission(
        actor=AuthenticatedActor(
            tenant_id=tenant_id,
            subject_id=device.id,
            actor_type="device",
            device_id=device.id,
        ),
        permission_codes=("dataset.upload", "upload.create"),
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    ):
        from upload_control_plane.api.errors import ApiError

        raise ApiError(
            status_code=403,
            code="device.project_not_authorized",
            message="Device is not authorized for this project.",
        )
    return source_device_id
