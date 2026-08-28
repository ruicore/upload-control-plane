from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from upload_control_plane.application.upload_sessions import PartListSource


class UploadSessionStatusResponse(BaseModel):
    session_id: uuid.UUID
    project_id: uuid.UUID | None
    dataset_id: uuid.UUID | None
    status: str
    bucket: str
    object_key: str
    original_filename: str
    file_size_bytes: int
    part_size_bytes: int
    part_count: int
    uploaded_part_count: int
    missing_part_count: int
    paused_at: datetime | None = None
    pause_reason: str | None = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class PresignPartsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_numbers: list[int] | None = None
    part_number_start: int | None = Field(default=None, ge=1)
    part_number_end: int | None = Field(default=None, ge=1)
    expires_in_seconds: int = Field(default=900, gt=0)

    @field_validator("part_numbers")
    @classmethod
    def validate_part_numbers(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("part_numbers must not be empty")
        if any(part_number < 1 for part_number in value):
            raise ValueError("part_numbers must be positive")
        if len(set(value)) != len(value):
            raise ValueError("part_numbers must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_part_selection(self) -> PresignPartsRequest:
        has_list = self.part_numbers is not None
        has_range = self.part_number_start is not None or self.part_number_end is not None
        if has_list == has_range:
            raise ValueError("provide either part_numbers or part_number_start and part_number_end")
        if has_range and (self.part_number_start is None or self.part_number_end is None):
            raise ValueError("part_number_start and part_number_end must be provided together")
        if (
            self.part_number_start is not None
            and self.part_number_end is not None
            and self.part_number_end < self.part_number_start
        ):
            raise ValueError("part_number_end must be greater than or equal to part_number_start")
        return self


class PresignedPartResponse(BaseModel):
    part_number: int
    url: str
    expected_size_bytes: int
    offset_start: int
    offset_end_exclusive: int
    required_headers: dict[str, str]


class PresignPartsResponse(BaseModel):
    session_id: uuid.UUID
    method: Literal["PUT"]
    expires_at: datetime
    parts: list[PresignedPartResponse]


class AckUploadedPartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_number: int = Field(ge=1)
    etag: str = Field(min_length=1)
    size_bytes: int = Field(gt=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum_sha256(cls, value: str | None) -> str | None:
        hex_characters = "0123456789abcdefABCDEF"
        if value is not None and any(character not in hex_characters for character in value):
            raise ValueError("checksum_sha256 must be a hex string")
        return value


class AckPartsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[AckUploadedPartRequest] = Field(min_length=1)

    @field_validator("parts")
    @classmethod
    def validate_unique_parts(
        cls,
        value: list[AckUploadedPartRequest],
    ) -> list[AckUploadedPartRequest]:
        part_numbers = [item.part_number for item in value]
        if len(set(part_numbers)) != len(part_numbers):
            raise ValueError("parts must not contain duplicate part numbers")
        return value


class AckPartsResponse(BaseModel):
    session_id: uuid.UUID
    acknowledged_part_count: int
    uploaded_part_count: int


class RuntimePartResponse(BaseModel):
    part_number: int
    etag: str | None
    size_bytes: int | None
    status: str
    uploaded_at: datetime | None
    expected_size_bytes: int
    offset_start: int
    offset_end_exclusive: int
    last_presigned_at: datetime | None
    presign_expires_at: datetime | None


class ListPartsResponse(BaseModel):
    session_id: uuid.UUID
    source: PartListSource
    part_count: int
    uploaded_part_count: int
    missing_part_numbers: list[int]
    parts: list[RuntimePartResponse]


class PauseUploadSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=256)
    client_inflight_behavior: Literal["allow_finish", "cancel_inflight"] | None = None


class PauseUploadSessionResponse(BaseModel):
    session_id: uuid.UUID
    status: Literal["PAUSED"]
    paused_at: datetime
    pause_reason: str | None


class ResumeUploadSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=256)


class ResumeUploadSessionResponse(BaseModel):
    session_id: uuid.UUID
    status: Literal["UPLOADING"]
    resumed_at: datetime


class CompleteReportedPartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_number: int = Field(ge=1)
    etag: str = Field(min_length=1)


class CompleteUploadSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_reported_parts: list[CompleteReportedPartRequest] | None = None
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum_sha256(cls, value: str | None) -> str | None:
        hex_characters = "0123456789abcdefABCDEF"
        if value is not None and any(character not in hex_characters for character in value):
            raise ValueError("checksum_sha256 must be a hex string")
        return value


class CompleteUploadSessionResponse(BaseModel):
    session_id: uuid.UUID
    status: Literal["COMPLETED"]
    bucket: str
    object_key: str
    object_size_bytes: int | None
    etag: str | None
    completed_at: datetime


class AbortUploadSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=256)


class AbortUploadSessionResponse(BaseModel):
    session_id: uuid.UUID
    status: Literal["ABORTED"]
    aborted_at: datetime
