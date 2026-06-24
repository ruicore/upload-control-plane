from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import DB_SESSION, AuthenticatedActor, require_api_key
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.application.upload_tasks import (
    CreateUploadObjectInput,
    CreateUploadTaskCommand,
    UploadTaskCreationService,
)
from upload_control_plane.domain.errors import DomainError
from upload_control_plane.domain.object_keys import sanitize_object_name
from upload_control_plane.domain.parts import choose_part_size, get_part_count
from upload_control_plane.domain.permissions import ResourceType

router = APIRouter(prefix="/v1/projects/{project_id}/upload-tasks", tags=["upload-tasks"])
AUTH_ACTOR = Depends(require_api_key)
IDEMPOTENCY_KEY_HEADER = Header(default=None, alias="Idempotency-Key")


class UploadTaskObjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name: str = Field(min_length=1, max_length=255)
    object_name: str = Field(min_length=1, max_length=255)
    file_size_bytes: int = Field(gt=0)
    content_type: str | None = Field(default=None, max_length=255)
    part_size_bytes: int | None = Field(default=None, gt=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("dataset_name", "object_name")
    @classmethod
    def validate_safe_name(cls, value: str) -> str:
        try:
            sanitize_object_name(value)
        except DomainError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum_sha256(cls, value: str | None) -> str | None:
        hex_characters = "0123456789abcdefABCDEF"
        if value is not None and any(character not in hex_characters for character in value):
            raise ValueError("checksum_sha256 must be a hex string")
        return value

    @model_validator(mode="after")
    def validate_part_size(self) -> UploadTaskObjectCreateRequest:
        try:
            choose_part_size(self.file_size_bytes, self.part_size_bytes)
        except DomainError as exc:
            raise ValueError(str(exc)) from exc
        return self


class UploadTaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_name: str = Field(min_length=1, max_length=255)
    task_initiator: Literal["web", "cli", "device", "api"] = "api"
    source_device_id: uuid.UUID | None = None
    source_device_code: str | None = Field(default=None, max_length=255)
    storage_policy_id: uuid.UUID | None = None
    objects: list[UploadTaskObjectCreateRequest] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("task_name")
    @classmethod
    def validate_task_name(cls, value: str) -> str:
        try:
            sanitize_object_name(value)
        except DomainError as exc:
            raise ValueError(str(exc)) from exc
        return value


class UploadTaskCreatedObjectResponse(BaseModel):
    object_id: uuid.UUID
    dataset_id: uuid.UUID
    session_id: uuid.UUID
    status: str
    object_name: str
    bucket: str
    object_key: str
    file_size_bytes: int
    part_size_bytes: int
    part_count: int
    expires_at: datetime


class UploadTaskCreateResponse(BaseModel):
    task_id: uuid.UUID
    project_id: uuid.UUID
    status: str
    object_count: int
    total_size_bytes: int
    objects: list[UploadTaskCreatedObjectResponse]
    created_at: datetime


@router.post("", status_code=201, response_model=UploadTaskCreateResponse)
def create_upload_task(
    project_id: uuid.UUID,
    request: UploadTaskCreateRequest,
    idempotency_key: str | None = IDEMPOTENCY_KEY_HEADER,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
) -> UploadTaskCreateResponse:
    authorization = AuthorizationService(session)
    authorization.require_any_permission(
        actor=actor,
        permission_codes=("dataset.upload", "upload.create"),
        resource_type=ResourceType.PROJECT,
        resource_id=project_id,
    )

    service = UploadTaskCreationService()
    service.create_upload_task(
        CreateUploadTaskCommand(
            tenant_id=actor.tenant_id,
            project_id=project_id,
            actor=actor,
            task_name=request.task_name,
            task_initiator=request.task_initiator,
            source_device_id=request.source_device_id,
            source_device_code=request.source_device_code,
            storage_policy_id=request.storage_policy_id,
            idempotency_key=idempotency_key,
            objects=tuple(_object_input(item) for item in request.objects),
            metadata=request.metadata,
        )
    )
    raise AssertionError("UploadTaskCreationService returned without a response")


def _object_input(item: UploadTaskObjectCreateRequest) -> CreateUploadObjectInput:
    part_size = choose_part_size(item.file_size_bytes, item.part_size_bytes)
    return CreateUploadObjectInput(
        dataset_name=item.dataset_name,
        object_name=item.object_name,
        file_size_bytes=item.file_size_bytes,
        content_type=item.content_type,
        part_size_bytes=part_size,
        part_count=get_part_count(item.file_size_bytes, part_size),
        checksum_sha256=item.checksum_sha256,
        metadata=item.metadata,
    )
