from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DatasetSummaryResponse(BaseModel):
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    status: str
    original_filename: str | None
    content_type: str | None
    file_size_bytes: int | None
    validation_status: str
    recovery_status: str
    labels: list[str]
    tag_ids: list[uuid.UUID]
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None
    archived_at: datetime | None
    deleted_at: datetime | None


class DatasetDetailResponse(DatasetSummaryResponse):
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


class DatasetListResponse(BaseModel):
    datasets: list[DatasetSummaryResponse]


class DatasetValidationResultResponse(BaseModel):
    validation_result_id: uuid.UUID
    status: str
    validator_name: str
    validator_version: str | None
    extracted_metadata: dict[str, Any]
    errors: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class DatasetValidationResponse(BaseModel):
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    dataset_status: str
    validation_status: str
    preview_status: str
    preview_metadata: dict[str, Any]
    extracted_metadata: dict[str, Any]
    latest_result: DatasetValidationResultResponse | None
    results: list[DatasetValidationResultResponse]


class DatasetUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    metadata: dict[str, Any] | None = None
    labels: list[str] | None = None
    tag_ids: list[uuid.UUID] | None = None

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(set(value)) != len(value):
            raise ValueError("labels must not contain duplicates")
        if any(not item or len(item) > 64 for item in value):
            raise ValueError("labels must be non-empty and at most 64 characters")
        return value


class DownloadUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expires_in_seconds: int = Field(default=900, gt=0)
    purpose: str | None = Field(default=None, max_length=256)


class DownloadUrlResponse(BaseModel):
    dataset_id: uuid.UUID
    method: Literal["GET"]
    url: str
    expires_at: datetime


class RetryValidationResponse(BaseModel):
    dataset_id: uuid.UUID
    project_id: uuid.UUID
    dataset_status: str
    validation_status: str
    retry_queued: bool


class PurgeDatasetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_purge: bool = False


class TagCategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)
    sort_order: int = 0


class TagCategoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)
    sort_order: int | None = None


class TagCategoryResponse(BaseModel):
    category_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    color: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


class TagCategoryListResponse(BaseModel):
    tag_categories: list[TagCategoryResponse]


class TagCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)


class TagUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = Field(default=None, max_length=32)


class TagResponse(BaseModel):
    tag_id: uuid.UUID
    project_id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    color: str | None
    created_at: datetime
    updated_at: datetime


class TagListResponse(BaseModel):
    tags: list[TagResponse]


__all__ = [
    "DatasetDetailResponse",
    "DatasetListResponse",
    "DatasetSummaryResponse",
    "DatasetUpdateRequest",
    "DatasetValidationResponse",
    "DatasetValidationResultResponse",
    "DownloadUrlRequest",
    "DownloadUrlResponse",
    "PurgeDatasetRequest",
    "RetryValidationResponse",
    "TagCategoryCreateRequest",
    "TagCategoryListResponse",
    "TagCategoryResponse",
    "TagCategoryUpdateRequest",
    "TagCreateRequest",
    "TagListResponse",
    "TagResponse",
    "TagUpdateRequest",
]
