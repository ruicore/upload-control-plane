from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: str
    original_filename: str | None
    content_type: str | None
    file_size_bytes: int | None
    validation_status: str
    recovery_status: str
    labels: tuple[str, ...]
    tag_ids: tuple[uuid.UUID, ...]
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None
    archived_at: datetime | None
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True)
class DatasetDetail(DatasetSummary):
    bucket: str | None
    object_key: str | None
    object_etag: str | None
    object_size_bytes: int | None
    object_version_id: str | None
    checksum_sha256: str | None
    source_device_id: uuid.UUID | None
    source_device_code: str | None
    preview_status: str
    preview_metadata: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DatasetValidationResultItem:
    validation_result_id: uuid.UUID
    status: str
    validator_name: str
    validator_version: str | None
    extracted_metadata: dict[str, Any]
    errors: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DatasetValidationStatusResult:
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    dataset_status: str
    validation_status: str
    preview_status: str
    preview_metadata: dict[str, Any]
    extracted_metadata: dict[str, Any]
    latest_result: DatasetValidationResultItem | None
    results: tuple[DatasetValidationResultItem, ...]


@dataclass(frozen=True, slots=True)
class RetryValidationResult:
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    dataset_status: str
    validation_status: str
    retry_queued: bool
