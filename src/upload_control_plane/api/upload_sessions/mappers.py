from __future__ import annotations

from upload_control_plane.api.upload_sessions.schemas import (
    AbortUploadSessionResponse,
    AckPartsResponse,
    CompleteUploadSessionResponse,
    ListPartsResponse,
    PauseUploadSessionResponse,
    PresignedPartResponse,
    PresignPartsResponse,
    ResumeUploadSessionResponse,
    RuntimePartResponse,
    UploadSessionStatusResponse,
)
from upload_control_plane.application.upload_sessions import (
    AbortUploadSessionResult,
    AckUploadedPartsResult,
    CompleteUploadSessionResult,
    ListRuntimePartsResult,
    PauseUploadSessionResult,
    PresignRuntimePartsResult,
    ResumeUploadSessionResult,
    RuntimeUploadSession,
)


def _status_response(result: RuntimeUploadSession) -> UploadSessionStatusResponse:
    return UploadSessionStatusResponse(
        session_id=result.session_id,
        project_id=result.project_id,
        dataset_id=result.dataset_id,
        status=result.status,
        bucket=result.bucket,
        object_key=result.object_key,
        original_filename=result.original_filename,
        file_size_bytes=result.file_size_bytes,
        part_size_bytes=result.part_size_bytes,
        part_count=result.part_count,
        uploaded_part_count=result.uploaded_part_count,
        missing_part_count=result.missing_part_count,
        paused_at=result.paused_at,
        pause_reason=result.pause_reason,
        expires_at=result.expires_at,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


def _presign_response(result: PresignRuntimePartsResult) -> PresignPartsResponse:
    return PresignPartsResponse(
        session_id=result.session_id,
        method="PUT",
        expires_at=result.expires_at,
        parts=[
            PresignedPartResponse(
                part_number=part.part_number,
                url=part.url,
                expected_size_bytes=part.expected_size_bytes,
                offset_start=part.offset_start,
                offset_end_exclusive=part.offset_end_exclusive,
                required_headers=part.required_headers,
            )
            for part in result.parts
        ],
    )


def _ack_response(result: AckUploadedPartsResult) -> AckPartsResponse:
    return AckPartsResponse(
        session_id=result.session_id,
        acknowledged_part_count=result.acknowledged_part_count,
        uploaded_part_count=result.uploaded_part_count,
    )


def _list_parts_response(result: ListRuntimePartsResult) -> ListPartsResponse:
    return ListPartsResponse(
        session_id=result.session_id,
        source=result.source,
        part_count=result.part_count,
        uploaded_part_count=result.uploaded_part_count,
        missing_part_numbers=list(result.missing_part_numbers),
        parts=[
            RuntimePartResponse(
                part_number=part.part_number,
                etag=part.etag,
                size_bytes=part.size_bytes,
                status=part.status,
                uploaded_at=part.uploaded_at,
                expected_size_bytes=part.expected_size_bytes,
                offset_start=part.offset_start,
                offset_end_exclusive=part.offset_end_exclusive,
                last_presigned_at=part.last_presigned_at,
                presign_expires_at=part.presign_expires_at,
            )
            for part in result.parts
        ],
    )


def _pause_response(result: PauseUploadSessionResult) -> PauseUploadSessionResponse:
    return PauseUploadSessionResponse(
        session_id=result.session_id,
        status="PAUSED",
        paused_at=result.paused_at,
        pause_reason=result.pause_reason,
    )


def _resume_response(result: ResumeUploadSessionResult) -> ResumeUploadSessionResponse:
    return ResumeUploadSessionResponse(
        session_id=result.session_id,
        status="UPLOADING",
        resumed_at=result.resumed_at,
    )


def _complete_response(result: CompleteUploadSessionResult) -> CompleteUploadSessionResponse:
    return CompleteUploadSessionResponse(
        session_id=result.session_id,
        status="COMPLETED",
        bucket=result.bucket,
        object_key=result.object_key,
        object_size_bytes=result.object_size_bytes,
        etag=result.etag,
        completed_at=result.completed_at,
    )


def _abort_response(result: AbortUploadSessionResult) -> AbortUploadSessionResponse:
    return AbortUploadSessionResponse(
        session_id=result.session_id,
        status="ABORTED",
        aborted_at=result.aborted_at,
    )
