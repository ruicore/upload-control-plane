from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from upload_control_plane.api.auth import AuthenticatedActor
from upload_control_plane.api.errors import ApiError


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
    task_name: str
    task_initiator: str
    source_device_id: uuid.UUID | None
    source_device_code: str | None
    storage_policy_id: uuid.UUID | None
    idempotency_key: str | None
    objects: tuple[CreateUploadObjectInput, ...]
    metadata: dict[str, Any]


class UploadTaskCreationService:
    """Application boundary for T05 transactional upload task creation."""

    def create_upload_task(self, command: CreateUploadTaskCommand) -> None:
        _ = command
        raise ApiError(
            status_code=501,
            code="upload_task.not_implemented",
            message="Upload task transactional creation is not implemented yet.",
        )
