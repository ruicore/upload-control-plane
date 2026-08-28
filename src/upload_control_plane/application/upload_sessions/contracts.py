from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

PartListSource = Literal["db", "storage", "reconcile"]


@dataclass(frozen=True, slots=True)
class RuntimeUploadSession:
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
    paused_at: datetime | None
    pause_reason: str | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PresignedRuntimePart:
    part_number: int
    url: str
    expected_size_bytes: int
    offset_start: int
    offset_end_exclusive: int
    required_headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class PresignRuntimePartsResult:
    session_id: uuid.UUID
    method: str
    expires_at: datetime
    parts: tuple[PresignedRuntimePart, ...]


@dataclass(frozen=True, slots=True)
class AckUploadedPartsInput:
    part_number: int
    etag: str
    size_bytes: int
    checksum_sha256: str | None


@dataclass(frozen=True, slots=True)
class AckUploadedPartsResult:
    session_id: uuid.UUID
    acknowledged_part_count: int
    uploaded_part_count: int


@dataclass(frozen=True, slots=True)
class RuntimePartState:
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


@dataclass(frozen=True, slots=True)
class ListRuntimePartsResult:
    session_id: uuid.UUID
    source: PartListSource
    part_count: int
    uploaded_part_count: int
    missing_part_numbers: tuple[int, ...]
    parts: tuple[RuntimePartState, ...]


@dataclass(frozen=True, slots=True)
class PauseUploadSessionResult:
    session_id: uuid.UUID
    status: str
    paused_at: datetime
    pause_reason: str | None


@dataclass(frozen=True, slots=True)
class ResumeUploadSessionResult:
    session_id: uuid.UUID
    status: str
    resumed_at: datetime


@dataclass(frozen=True, slots=True)
class CompleteUploadSessionResult:
    session_id: uuid.UUID
    status: str
    bucket: str
    object_key: str
    object_size_bytes: int | None
    etag: str | None
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class AbortUploadSessionResult:
    session_id: uuid.UUID
    status: str
    aborted_at: datetime


def _pause_result_to_json(result: PauseUploadSessionResult) -> dict[str, Any]:
    return {
        "session_id": str(result.session_id),
        "status": result.status,
        "paused_at": result.paused_at.isoformat(),
        "pause_reason": result.pause_reason,
    }


def _pause_result_from_json(value: dict[str, Any]) -> PauseUploadSessionResult:
    return PauseUploadSessionResult(
        session_id=uuid.UUID(value["session_id"]),
        status=value["status"],
        paused_at=datetime.fromisoformat(value["paused_at"]),
        pause_reason=value["pause_reason"],
    )


def _resume_result_to_json(result: ResumeUploadSessionResult) -> dict[str, Any]:
    return {
        "session_id": str(result.session_id),
        "status": result.status,
        "resumed_at": result.resumed_at.isoformat(),
    }


def _resume_result_from_json(value: dict[str, Any]) -> ResumeUploadSessionResult:
    return ResumeUploadSessionResult(
        session_id=uuid.UUID(value["session_id"]),
        status=value["status"],
        resumed_at=datetime.fromisoformat(value["resumed_at"]),
    )


def _complete_result_to_json(result: CompleteUploadSessionResult) -> dict[str, Any]:
    return {
        "session_id": str(result.session_id),
        "status": result.status,
        "bucket": result.bucket,
        "object_key": result.object_key,
        "object_size_bytes": result.object_size_bytes,
        "etag": result.etag,
        "completed_at": result.completed_at.isoformat(),
    }


def _complete_result_from_json(value: dict[str, Any]) -> CompleteUploadSessionResult:
    return CompleteUploadSessionResult(
        session_id=uuid.UUID(value["session_id"]),
        status=value["status"],
        bucket=value["bucket"],
        object_key=value["object_key"],
        object_size_bytes=value["object_size_bytes"],
        etag=value["etag"],
        completed_at=datetime.fromisoformat(value["completed_at"]),
    )


def _abort_result_to_json(result: AbortUploadSessionResult) -> dict[str, Any]:
    return {
        "session_id": str(result.session_id),
        "status": result.status,
        "aborted_at": result.aborted_at.isoformat(),
    }


def _abort_result_from_json(value: dict[str, Any]) -> AbortUploadSessionResult:
    return AbortUploadSessionResult(
        session_id=uuid.UUID(value["session_id"]),
        status=value["status"],
        aborted_at=datetime.fromisoformat(value["aborted_at"]),
    )
