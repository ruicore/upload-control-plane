from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.errors import ApiError
from upload_control_plane.application.upload_sessions.contracts import (
    CompleteUploadSessionResult,
    _complete_result_from_json,
    _complete_result_to_json,
)
from upload_control_plane.application.upload_sessions.event_writer import UploadEventWriter
from upload_control_plane.application.upload_sessions.idempotency import (
    resolve_idempotency,
    rollback_idempotency_on_failure,
    store_idempotency_response,
)
from upload_control_plane.application.upload_sessions.part_records import UploadPartStore
from upload_control_plane.application.upload_sessions.persisted_projection import (
    PersistedUploadAggregateProjector,
)
from upload_control_plane.domain.parts import get_part_range
from upload_control_plane.domain.session_state import UploadSessionStatus, can_complete
from upload_control_plane.domain.storage import (
    CompletedObject,
    CompleteMultipartUploadRequest,
    CompletionPart,
    ListedPart,
    ListPartsRequest,
    ObjectStorage,
    StorageError,
)
from upload_control_plane.infrastructure.db.models import UploadSession


class CompletionContext(Protocol):
    """Capabilities required to complete an upload session."""

    @property
    def _session(self) -> Session: ...

    @property
    def _storage(self) -> ObjectStorage: ...

    _part_store: UploadPartStore

    def _get_session_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> UploadSession: ...

    def _invalid_lifecycle_state(
        self,
        *,
        action: str,
        upload_session: UploadSession,
    ) -> ApiError: ...

    def _restore_status_after_storage_failure(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        previous_status: UploadSessionStatus,
        error_code: str,
        error_message: str,
    ) -> None: ...


def complete_upload_session(
    context: CompletionContext,
    *,
    projection: PersistedUploadAggregateProjector,
    event_writer: UploadEventWriter,
    tenant_id: uuid.UUID,
    actor: AuthenticatedActor,
    session_id: uuid.UUID,
    request_path: str,
    request_body: dict[str, Any],
    idempotency_key: str | None,
    request_id: str,
    checksum_sha256: str | None,
) -> CompleteUploadSessionResult:
    existing = resolve_idempotency(
        context._session,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        request_path=request_path,
        request_body=request_body,
        result_loader=_complete_result_from_json,
    )
    if existing is not None:
        return existing

    previous_status: UploadSessionStatus | None = None
    try:
        upload_session = context._get_session_for_update(
            tenant_id=tenant_id,
            session_id=session_id,
        )
        status = UploadSessionStatus(upload_session.status)
        if status is UploadSessionStatus.COMPLETED:
            result = _completed_result(upload_session)
            store_idempotency_response(
                context._session,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                response_status=200,
                response_body=_complete_result_to_json(result),
            )
            context._session.commit()
            return result
        if not can_complete(status):
            raise context._invalid_lifecycle_state(
                action="complete",
                upload_session=upload_session,
            )
        if upload_session.storage_upload_id is None:
            raise ApiError(
                status_code=409,
                code="upload.storage_upload_missing",
                message="Upload session has no storage multipart upload ID.",
            )
        previous_status = status
        now = datetime.now(UTC)
        upload_session.status = UploadSessionStatus.COMPLETING.value
        upload_session.updated_at = now
        projection.project_runtime_transition(
            upload_session,
            status=UploadSessionStatus.COMPLETING,
            now=now,
        )
        event_writer.write_actor_event(
            upload_session,
            actor=actor,
            request_id=request_id,
            event_type="upload.complete_requested",
            payload={"checksum_sha256": checksum_sha256},
        )
        context._session.commit()

        storage_parts = _list_storage_parts(context, upload_session)
        completion_parts = _validate_complete_parts(
            context,
            upload_session,
            storage_parts,
            projection=projection,
            previous_status=previous_status,
        )
        storage_result = context._storage.complete_multipart_upload(
            CompleteMultipartUploadRequest(
                bucket=upload_session.bucket_name,
                object_key=upload_session.object_key,
                upload_id=upload_session.storage_upload_id,
                parts=completion_parts,
                checksum={"sha256": checksum_sha256} if checksum_sha256 else {},
            )
        )
        result = _mark_completed(
            context,
            projection=projection,
            event_writer=event_writer,
            tenant_id=tenant_id,
            session_id=session_id,
            actor=actor,
            request_id=request_id,
            storage_result=storage_result,
            idempotency_key=idempotency_key,
        )
        context._session.commit()
        return result
    except ApiError:
        rollback_idempotency_on_failure(context._session, tenant_id, idempotency_key)
        raise
    except StorageError as exc:
        if previous_status is not None:
            context._restore_status_after_storage_failure(
                tenant_id=tenant_id,
                session_id=session_id,
                previous_status=previous_status,
                error_code="storage.complete_failed",
                error_message=str(exc),
            )
        rollback_idempotency_on_failure(context._session, tenant_id, idempotency_key)
        raise ApiError(
            status_code=502,
            code="storage.complete_failed",
            message="Storage multipart complete failed.",
            details={"operation": exc.operation, "provider_code": exc.provider_code},
        ) from exc


def _list_storage_parts(
    context: CompletionContext,
    upload_session: UploadSession,
) -> tuple[ListedPart, ...]:
    if upload_session.storage_upload_id is None:
        raise ApiError(
            status_code=409,
            code="upload.storage_upload_missing",
            message="Upload session has no storage multipart upload ID.",
        )
    observed_parts: list[ListedPart] = []
    marker: int | None = None
    while True:
        page = context._storage.list_parts(
            ListPartsRequest(
                bucket=upload_session.bucket_name,
                object_key=upload_session.object_key,
                upload_id=upload_session.storage_upload_id,
                part_number_marker=marker,
            )
        )
        observed_parts.extend(page.parts)
        if not page.is_truncated:
            break
        marker = page.next_part_number_marker
        if marker is None:
            break
    return tuple(sorted(observed_parts, key=lambda part: part.part_number))


def _validate_complete_parts(
    context: CompletionContext,
    upload_session: UploadSession,
    storage_parts: tuple[ListedPart, ...],
    *,
    projection: PersistedUploadAggregateProjector,
    previous_status: UploadSessionStatus,
) -> tuple[CompletionPart, ...]:
    by_number = {part.part_number: part for part in storage_parts}
    expected_numbers = set(range(1, upload_session.part_count + 1))
    actual_numbers = set(by_number)
    missing = tuple(sorted(expected_numbers - actual_numbers))
    unexpected = tuple(sorted(actual_numbers - expected_numbers))
    size_mismatches: list[dict[str, int]] = []
    for part_number in sorted(expected_numbers & actual_numbers):
        part_range = get_part_range(
            upload_session.file_size_bytes,
            upload_session.part_size_bytes,
            part_number,
        )
        actual = by_number[part_number]
        if actual.size_bytes != part_range.expected_size:
            size_mismatches.append(
                {
                    "part_number": part_number,
                    "expected_size_bytes": part_range.expected_size,
                    "size_bytes": actual.size_bytes,
                }
            )
    if missing or unexpected or size_mismatches:
        _restore_after_missing_parts(
            context,
            projection=projection,
            tenant_id=upload_session.tenant_id,
            session_id=upload_session.id,
            fallback_status=(
                UploadSessionStatus.PAUSED
                if previous_status is UploadSessionStatus.PAUSED
                else UploadSessionStatus.UPLOADING
            ),
            storage_parts=storage_parts,
            missing=missing,
            unexpected=unexpected,
            size_mismatches=size_mismatches,
        )
        details: dict[str, object] = {
            "session_id": str(upload_session.id),
            "missing_part_count": len(missing),
            "missing_part_numbers": list(missing[:100]),
        }
        if unexpected:
            details["unexpected_part_numbers"] = list(unexpected[:100])
        if size_mismatches:
            details["size_mismatches"] = size_mismatches[:100]
        raise ApiError(
            status_code=409,
            code="upload.missing_parts",
            message="Upload cannot be completed because some parts are missing.",
            details=details,
        )
    return tuple(
        CompletionPart(
            part_number=part.part_number,
            etag=part.etag,
            checksum=part.checksum,
        )
        for part in storage_parts
    )


def _restore_after_missing_parts(
    context: CompletionContext,
    *,
    projection: PersistedUploadAggregateProjector,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    fallback_status: UploadSessionStatus,
    storage_parts: tuple[ListedPart, ...],
    missing: tuple[int, ...],
    unexpected: tuple[int, ...],
    size_mismatches: list[dict[str, int]],
) -> None:
    upload_session = context._get_session_for_update(
        tenant_id=tenant_id,
        session_id=session_id,
    )
    now = datetime.now(UTC)
    upload_session.status = fallback_status.value
    upload_session.last_error_code = "upload.missing_parts"
    upload_session.last_error_message = (
        "Upload cannot be completed because storage parts are missing."
    )
    upload_session.updated_at = now
    for part in storage_parts:
        context._part_store.upsert(
            upload_session=upload_session,
            part_number=part.part_number,
            status="UPLOADED",
            now=now,
            etag=part.etag,
            size_bytes=part.size_bytes,
            checksum_sha256=part.checksum.get("sha256"),
            uploaded_at=part.last_modified or now,
            source="storage",
        )
    upload_session.uploaded_part_count = context._part_store.uploaded_count(session_id)
    projection.project_runtime_transition(upload_session, status=fallback_status, now=now)
    context._session.commit()
    _ = (missing, unexpected, size_mismatches)


def _mark_completed(
    context: CompletionContext,
    *,
    projection: PersistedUploadAggregateProjector,
    event_writer: UploadEventWriter,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    actor: AuthenticatedActor,
    request_id: str,
    storage_result: CompletedObject,
    idempotency_key: str | None,
) -> CompleteUploadSessionResult:
    upload_session = context._get_session_for_update(
        tenant_id=tenant_id,
        session_id=session_id,
    )
    now = datetime.now(UTC)
    upload_session.status = UploadSessionStatus.COMPLETED.value
    upload_session.object_etag = storage_result.etag
    upload_session.object_size_bytes = storage_result.size_bytes
    upload_session.object_version_id = storage_result.version_id
    upload_session.completed_part_count = upload_session.part_count
    upload_session.uploaded_part_count = upload_session.part_count
    upload_session.completed_at = now
    upload_session.updated_at = now
    projection.project_runtime_transition(
        upload_session,
        status=UploadSessionStatus.COMPLETED,
        now=now,
        storage_result=storage_result,
    )
    event_writer.write_actor_event(
        upload_session,
        actor=actor,
        request_id=request_id,
        event_type="upload.completed",
        payload={
            "etag": storage_result.etag,
            "object_size_bytes": storage_result.size_bytes,
            "object_version_id": storage_result.version_id,
        },
    )
    result = _completed_result(upload_session)
    store_idempotency_response(
        context._session,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        response_status=200,
        response_body=_complete_result_to_json(result),
    )
    return result


def _completed_result(upload_session: UploadSession) -> CompleteUploadSessionResult:
    completed_at = upload_session.completed_at or datetime.now(UTC)
    return CompleteUploadSessionResult(
        session_id=upload_session.id,
        status=upload_session.status,
        bucket=upload_session.bucket_name,
        object_key=upload_session.object_key,
        object_size_bytes=upload_session.object_size_bytes,
        etag=upload_session.object_etag,
        completed_at=completed_at,
    )
