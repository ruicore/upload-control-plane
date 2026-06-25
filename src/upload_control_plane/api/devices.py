from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import (
    DB_SESSION,
    AuthenticatedActor,
    require_api_key,
    require_platform_api_key,
)
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.api.request_context import get_request_id
from upload_control_plane.api.upload_tasks import (
    OBJECT_STORAGE,
    SETTINGS_DEPENDENCY,
    UploadTaskCreateRequest,
    UploadTaskCreateResponse,
    _object_input,
    _response,
)
from upload_control_plane.application.devices import (
    DeviceRecord,
    DeviceService,
    DeviceWithCredential,
)
from upload_control_plane.application.upload_tasks import (
    CreateUploadTaskCommand,
    UploadTaskCreationService,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.permissions import ResourceType
from upload_control_plane.domain.storage import ObjectStorage
from upload_control_plane.infrastructure.db.models import Device

router = APIRouter(prefix="/v1/projects/{project_id}/devices", tags=["devices"])
IDEMPOTENCY_KEY_HEADER = Header(default=None, alias="Idempotency-Key")
PLATFORM_ACTOR = Depends(require_platform_api_key)
AUTH_ACTOR = Depends(require_api_key)


class DeviceRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    device_code: str | None = Field(default=None, max_length=255)
    device_type: str = Field(min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    credential_expires_in_seconds: int | None = Field(default=None, gt=0)


class DeviceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    device_code: str | None = Field(default=None, max_length=255)
    device_type: str | None = Field(default=None, min_length=1, max_length=64)
    metadata: dict[str, Any] | None = None


class DeviceCredentialResponse(BaseModel):
    credential_id: uuid.UUID
    credential_version: int
    credential_material: str
    issued_at: datetime
    expires_at: datetime | None


class DeviceResponse(BaseModel):
    device_id: uuid.UUID
    project_id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    device_code: str | None
    device_type: str
    status: str
    credential_version: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None
    last_ip: str | None
    client_version: str | None


class DeviceProvisionResponse(BaseModel):
    device: DeviceResponse
    credential: DeviceCredentialResponse


class RotateCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_in_seconds: int | None = Field(default=None, gt=0)
    overlap_seconds: int = Field(default=0, ge=0, le=86_400)


@router.get("", response_model=list[DeviceResponse])
def list_devices(
    project_id: uuid.UUID,
    actor: AuthenticatedActor = PLATFORM_ACTOR,
    session: Session = DB_SESSION,
) -> list[DeviceResponse]:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="device.view",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    service = DeviceService(session)
    return [
        _device_response(item)
        for item in service.list_project_devices(
            tenant_id=actor.tenant_id,
            project_id=project_id,
        )
    ]


@router.post("", status_code=201, response_model=DeviceProvisionResponse)
def register_device(
    project_id: uuid.UUID,
    request: DeviceRegisterRequest,
    actor: AuthenticatedActor = PLATFORM_ACTOR,
    session: Session = DB_SESSION,
) -> DeviceProvisionResponse:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="device.create",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    result = DeviceService(session).register_device(
        tenant_id=actor.tenant_id,
        project_id=project_id,
        actor=actor,
        request_id=get_request_id(),
        name=request.name,
        device_code=request.device_code,
        device_type=request.device_type,
        metadata=request.metadata,
        credential_expires_in_seconds=request.credential_expires_in_seconds,
    )
    return _provision_response(result)


@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    project_id: uuid.UUID,
    device_id: uuid.UUID,
    actor: AuthenticatedActor = PLATFORM_ACTOR,
    session: Session = DB_SESSION,
) -> DeviceResponse:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="device.view",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    return _device_response(
        DeviceService(session).get_project_device(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            device_id=device_id,
        )
    )


@router.patch("/{device_id}", response_model=DeviceResponse)
def update_device(
    project_id: uuid.UUID,
    device_id: uuid.UUID,
    request: DeviceUpdateRequest,
    actor: AuthenticatedActor = PLATFORM_ACTOR,
    session: Session = DB_SESSION,
) -> DeviceResponse:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="device.update",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    return _device_response(
        DeviceService(session).update_device(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            device_id=device_id,
            actor=actor,
            request_id=get_request_id(),
            name=request.name,
            device_code=request.device_code,
            device_type=request.device_type,
            metadata=request.metadata,
        )
    )


@router.post("/{device_id}/disable", response_model=DeviceResponse)
def disable_device(
    project_id: uuid.UUID,
    device_id: uuid.UUID,
    actor: AuthenticatedActor = PLATFORM_ACTOR,
    session: Session = DB_SESSION,
) -> DeviceResponse:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="device.disable",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    return _device_response(
        DeviceService(session).set_device_status(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            device_id=device_id,
            actor=actor,
            request_id=get_request_id(),
            status="DISABLED",
        )
    )


@router.post("/{device_id}/enable", response_model=DeviceResponse)
def enable_device(
    project_id: uuid.UUID,
    device_id: uuid.UUID,
    actor: AuthenticatedActor = PLATFORM_ACTOR,
    session: Session = DB_SESSION,
) -> DeviceResponse:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="device.disable",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    return _device_response(
        DeviceService(session).set_device_status(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            device_id=device_id,
            actor=actor,
            request_id=get_request_id(),
            status="ACTIVE",
        )
    )


@router.post("/{device_id}/credentials/rotate", response_model=DeviceProvisionResponse)
def rotate_device_credential(
    project_id: uuid.UUID,
    device_id: uuid.UUID,
    request: RotateCredentialRequest,
    actor: AuthenticatedActor = PLATFORM_ACTOR,
    session: Session = DB_SESSION,
) -> DeviceProvisionResponse:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="device.credentials.rotate",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    return _provision_response(
        DeviceService(session).rotate_credential(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            device_id=device_id,
            actor=actor,
            request_id=get_request_id(),
            expires_in_seconds=request.expires_in_seconds,
            overlap_seconds=request.overlap_seconds,
        )
    )


@router.post("/{device_id}/credentials/revoke", response_model=DeviceResponse)
def revoke_device_credentials(
    project_id: uuid.UUID,
    device_id: uuid.UUID,
    actor: AuthenticatedActor = PLATFORM_ACTOR,
    session: Session = DB_SESSION,
) -> DeviceResponse:
    AuthorizationService(session).require_permission(
        actor=actor,
        permission_code="device.credentials.revoke",
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )
    return _device_response(
        DeviceService(session).revoke_credentials(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            device_id=device_id,
            actor=actor,
            request_id=get_request_id(),
        )
    )


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


def _device_response(device: DeviceRecord) -> DeviceResponse:
    return DeviceResponse(
        device_id=device.device_id,
        project_id=device.project_id,
        tenant_id=device.tenant_id,
        name=device.name,
        device_code=device.device_code,
        device_type=device.device_type,
        status=device.status,
        credential_version=device.credential_version,
        metadata=device.metadata,
        created_at=device.created_at,
        updated_at=device.updated_at,
        last_seen_at=device.last_seen_at,
        last_ip=device.last_ip,
        client_version=device.client_version,
    )


def _provision_response(result: DeviceWithCredential) -> DeviceProvisionResponse:
    return DeviceProvisionResponse(
        device=_device_response(result.device),
        credential=DeviceCredentialResponse(
            credential_id=result.credential.credential_id,
            credential_version=result.credential.credential_version,
            credential_material=result.credential.credential_material,
            issued_at=result.credential.issued_at,
            expires_at=result.credential.expires_at,
        ),
    )
