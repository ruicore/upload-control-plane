from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from upload_control_plane.application.authentication import AuthenticatedActor


@dataclass(frozen=True, slots=True)
class CreateUploadObjectInput:
    dataset_name: str
    object_name: str
    file_size_bytes: int
    content_type: str | None
    part_size_bytes: int
    part_count: int
    checksum_sha256: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CreateUploadTaskCommand:
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    actor: AuthenticatedActor
    request_path: str
    request_body: dict[str, Any]
    request_id: str | None
    task_name: str
    task_initiator: str
    source_device_id: uuid.UUID | None
    source_device_code: str | None
    storage_policy_id: uuid.UUID | None
    idempotency_key: str | None
    objects: tuple[CreateUploadObjectInput, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CreatedUploadObject:
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


@dataclass(frozen=True, slots=True)
class CreatedUploadTask:
    task_id: uuid.UUID
    project_id: uuid.UUID
    status: str
    object_count: int
    total_size_bytes: int
    objects: tuple[CreatedUploadObject, ...]
    created_at: datetime
