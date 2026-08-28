from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from upload_control_plane.application.upload_tasks import (
    CreatedUploadTask,
    CreateUploadObjectInput,
)
from upload_control_plane.domain.errors import DomainError
from upload_control_plane.domain.object_keys import sanitize_object_name
from upload_control_plane.domain.parts import choose_part_size, get_part_count


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


def _response(result: CreatedUploadTask) -> UploadTaskCreateResponse:
    return UploadTaskCreateResponse(
        task_id=result.task_id,
        project_id=result.project_id,
        status=result.status,
        object_count=result.object_count,
        total_size_bytes=result.total_size_bytes,
        objects=[
            UploadTaskCreatedObjectResponse(
                object_id=item.object_id,
                dataset_id=item.dataset_id,
                session_id=item.session_id,
                status=item.status,
                object_name=item.object_name,
                bucket=item.bucket,
                object_key=item.object_key,
                file_size_bytes=item.file_size_bytes,
                part_size_bytes=item.part_size_bytes,
                part_count=item.part_count,
                expires_at=item.expires_at,
            )
            for item in result.objects
        ],
        created_at=result.created_at,
    )
