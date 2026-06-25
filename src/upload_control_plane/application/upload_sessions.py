from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import AuthenticatedActor
from upload_control_plane.api.errors import ApiError
from upload_control_plane.config import Settings
from upload_control_plane.domain.fingerprints import assert_json_value, generate_request_fingerprint
from upload_control_plane.domain.parts import get_part_range
from upload_control_plane.domain.session_state import (
    UploadSessionStatus,
    can_abort,
    can_complete,
    can_pause,
    can_presign,
    can_resume,
)
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompletedObject,
    CompleteMultipartUploadRequest,
    CompletionPart,
    ListedPart,
    ListPartsRequest,
    ObjectStorage,
    PresignUploadPartRequest,
    StorageError,
    StorageNotFoundError,
)
from upload_control_plane.infrastructure.db.models import (
    Dataset,
    IdempotencyRecord,
    UploadEvent,
    UploadObject,
    UploadPart,
    UploadSession,
    UploadTask,
)

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


class UploadSessionRuntimeService:
    """Application boundary for T06 upload session runtime operations."""

    def __init__(self, *, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings

    def get_upload_session(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> RuntimeUploadSession:
        upload_session = self._get_session(tenant_id=tenant_id, session_id=session_id)
        uploaded_part_count = self._uploaded_part_count(upload_session.id)
        if upload_session.uploaded_part_count != uploaded_part_count:
            upload_session.uploaded_part_count = uploaded_part_count
            upload_session.updated_at = datetime.now(UTC)
            self._session.commit()
        return self._session_result(upload_session, uploaded_part_count)

    def presign_parts(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        part_numbers: tuple[int, ...],
        expires_in_seconds: int,
        request_id: str,
    ) -> PresignRuntimePartsResult:
        upload_session = self._get_session(tenant_id=tenant_id, session_id=session_id)
        status = UploadSessionStatus(upload_session.status)
        if not can_presign(status):
            raise ApiError(
                status_code=409,
                code="upload.invalid_state",
                message="Upload session is not in a state that allows presigning parts.",
                details={"status": upload_session.status},
            )
        if upload_session.storage_upload_id is None:
            raise ApiError(
                status_code=409,
                code="upload.storage_upload_missing",
                message="Upload session has no storage multipart upload ID.",
            )

        bounded_expiry = min(expires_in_seconds, self._settings.max_presign_expiry_seconds)
        now = datetime.now(UTC)
        presigned_parts: list[PresignedRuntimePart] = []
        try:
            for part_number in part_numbers:
                part_range = get_part_range(
                    upload_session.file_size_bytes,
                    upload_session.part_size_bytes,
                    part_number,
                )
                presigned = self._storage.presign_upload_part(
                    PresignUploadPartRequest(
                        bucket=upload_session.bucket_name,
                        object_key=upload_session.object_key,
                        upload_id=upload_session.storage_upload_id,
                        part_number=part_number,
                        expires_in_seconds=bounded_expiry,
                    )
                )
                self._upsert_part(
                    upload_session=upload_session,
                    part_number=part_number,
                    status="PRESIGNED",
                    now=now,
                    last_presigned_at=now,
                    presign_expires_at=presigned.expires_at,
                    preserve_uploaded=True,
                )
                presigned_parts.append(
                    PresignedRuntimePart(
                        part_number=part_number,
                        url=presigned.url,
                        expected_size_bytes=part_range.expected_size,
                        offset_start=part_range.offset_start,
                        offset_end_exclusive=part_range.offset_end_exclusive,
                        required_headers=dict(presigned.required_headers),
                    )
                )
        except StorageError as exc:
            raise ApiError(
                status_code=502,
                code="storage.presign_failed",
                message="Storage presign failed.",
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc

        if upload_session.status == UploadSessionStatus.INITIATED.value:
            upload_session.status = UploadSessionStatus.UPLOADING.value
        upload_session.updated_at = now
        updated_parts = [
            part for part in self._load_parts(upload_session.id) if part.part_number in part_numbers
        ]
        self._add_event(
            upload_session,
            actor=actor,
            request_id=request_id,
            event_type="upload.presign_issued",
            payload={
                "part_numbers": list(part_numbers),
                "expires_at": min(
                    part.presign_expires_at for part in updated_parts if part.presign_expires_at
                ).isoformat(),
            },
        )
        self._session.commit()
        expires_at = min(
            part.presign_expires_at for part in updated_parts if part.presign_expires_at
        )
        return PresignRuntimePartsResult(
            session_id=upload_session.id,
            method="PUT",
            expires_at=expires_at,
            parts=tuple(presigned_parts),
        )

    def ack_uploaded_parts(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        parts: tuple[AckUploadedPartsInput, ...],
        request_id: str,
    ) -> AckUploadedPartsResult:
        upload_session = self._get_session(tenant_id=tenant_id, session_id=session_id)
        status = UploadSessionStatus(upload_session.status)
        if status in {
            UploadSessionStatus.COMPLETING,
            UploadSessionStatus.COMPLETED,
            UploadSessionStatus.ABORTING,
            UploadSessionStatus.ABORTED,
            UploadSessionStatus.FAILED,
        }:
            raise ApiError(
                status_code=409,
                code="upload.invalid_state",
                message="Upload session is not in a state that allows acknowledging parts.",
                details={"status": upload_session.status},
            )

        now = datetime.now(UTC)
        for item in parts:
            part_range = get_part_range(
                upload_session.file_size_bytes,
                upload_session.part_size_bytes,
                item.part_number,
            )
            if item.size_bytes != part_range.expected_size:
                raise ApiError(
                    status_code=422,
                    code="upload_part.size_mismatch",
                    message="Acknowledged part size does not match the expected byte range.",
                    details={
                        "part_number": item.part_number,
                        "expected_size_bytes": part_range.expected_size,
                        "size_bytes": item.size_bytes,
                    },
                )
            self._upsert_part(
                upload_session=upload_session,
                part_number=item.part_number,
                status="UPLOADED",
                now=now,
                etag=item.etag,
                size_bytes=item.size_bytes,
                checksum_sha256=item.checksum_sha256,
                uploaded_at=now,
                source="db",
            )

        if upload_session.status == UploadSessionStatus.INITIATED.value:
            upload_session.status = UploadSessionStatus.UPLOADING.value
        uploaded_part_count = self._uploaded_part_count(upload_session.id)
        upload_session.uploaded_part_count = uploaded_part_count
        upload_session.updated_at = now
        self._add_event(
            upload_session,
            actor=actor,
            request_id=request_id,
            event_type="upload.part_acknowledged",
            payload={"part_numbers": [item.part_number for item in parts]},
        )
        self._session.commit()
        return AckUploadedPartsResult(
            session_id=upload_session.id,
            acknowledged_part_count=len(parts),
            uploaded_part_count=uploaded_part_count,
        )

    def list_parts(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        source: PartListSource,
        request_id: str,
    ) -> ListRuntimePartsResult:
        upload_session = self._get_session(tenant_id=tenant_id, session_id=session_id)
        storage_observed: tuple[RuntimePartState, ...] | None = None
        if source in {"storage", "reconcile"}:
            storage_observed = self._observe_storage_parts(
                upload_session=upload_session,
                actor=actor,
                request_id=request_id,
                reconcile=source == "reconcile",
            )
        if source == "storage":
            parts = storage_observed or ()
            uploaded_part_count = len(parts)
            uploaded_part_numbers = {part.part_number for part in parts}
        else:
            db_parts = self._load_parts(upload_session.id)
            parts = tuple(self._part_result(part) for part in db_parts)
            uploaded_part_count = len([part for part in db_parts if part.status == "UPLOADED"])
            uploaded_part_numbers = {
                part.part_number for part in db_parts if part.status == "UPLOADED"
            }
        if source == "reconcile":
            upload_session.uploaded_part_count = uploaded_part_count
            upload_session.updated_at = datetime.now(UTC)
            self._session.commit()
        missing = tuple(
            part_number
            for part_number in range(1, upload_session.part_count + 1)
            if part_number not in uploaded_part_numbers
        )
        return ListRuntimePartsResult(
            session_id=upload_session.id,
            source=source,
            part_count=upload_session.part_count,
            uploaded_part_count=uploaded_part_count,
            missing_part_numbers=missing,
            parts=parts,
        )

    def pause_upload_session(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        request_path: str,
        request_body: dict[str, Any],
        idempotency_key: str | None,
        request_id: str,
        reason: str | None,
        client_inflight_behavior: str | None,
    ) -> PauseUploadSessionResult:
        existing = self._resolve_idempotency(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            request_path=request_path,
            request_body=request_body,
            result_loader=_pause_result_from_json,
        )
        if existing is not None:
            return existing

        try:
            upload_session = self._get_session_for_update(
                tenant_id=tenant_id,
                session_id=session_id,
            )
            status = UploadSessionStatus(upload_session.status)
            if not can_pause(status):
                raise self._invalid_lifecycle_state(
                    action="pause",
                    upload_session=upload_session,
                )
            now = datetime.now(UTC)
            if status is not UploadSessionStatus.PAUSED:
                upload_session.status = UploadSessionStatus.PAUSED.value
                self._set_pause_metadata(upload_session, paused_at=now, reason=reason)
                self._sync_related_records(
                    upload_session, status=UploadSessionStatus.PAUSED, now=now
                )
                event_type = "upload.paused"
            else:
                paused_at = self._paused_at(upload_session) or now
                self._set_pause_metadata(upload_session, paused_at=paused_at, reason=reason)
                event_type = "upload.pause_requested"
            upload_session.updated_at = now
            self._add_event(
                upload_session,
                actor=actor,
                request_id=request_id,
                event_type=event_type,
                payload={
                    "reason": reason,
                    "client_inflight_behavior": client_inflight_behavior,
                },
            )
            result = PauseUploadSessionResult(
                session_id=upload_session.id,
                status=upload_session.status,
                paused_at=self._paused_at(upload_session) or now,
                pause_reason=self._pause_reason(upload_session),
            )
            self._store_idempotency_response(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                response_status=200,
                response_body=_pause_result_to_json(result),
            )
            self._session.commit()
            return result
        except Exception:
            self._rollback_idempotency_on_failure(tenant_id, idempotency_key)
            raise

    def resume_upload_session(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        request_path: str,
        request_body: dict[str, Any],
        idempotency_key: str | None,
        request_id: str,
        reason: str | None,
    ) -> ResumeUploadSessionResult:
        existing = self._resolve_idempotency(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            request_path=request_path,
            request_body=request_body,
            result_loader=_resume_result_from_json,
        )
        if existing is not None:
            return existing

        try:
            upload_session = self._get_session_for_update(
                tenant_id=tenant_id,
                session_id=session_id,
            )
            status = UploadSessionStatus(upload_session.status)
            if not can_resume(status):
                raise self._invalid_lifecycle_state(
                    action="resume",
                    upload_session=upload_session,
                )
            now = datetime.now(UTC)
            if status is not UploadSessionStatus.UPLOADING:
                upload_session.status = UploadSessionStatus.UPLOADING.value
                self._clear_pause_metadata(upload_session)
                self._sync_related_records(
                    upload_session,
                    status=UploadSessionStatus.UPLOADING,
                    now=now,
                )
                event_type = "upload.resumed"
            else:
                event_type = "upload.resume_requested"
            upload_session.updated_at = now
            self._add_event(
                upload_session,
                actor=actor,
                request_id=request_id,
                event_type=event_type,
                payload={"reason": reason},
            )
            result = ResumeUploadSessionResult(
                session_id=upload_session.id,
                status=upload_session.status,
                resumed_at=now,
            )
            self._store_idempotency_response(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                response_status=200,
                response_body=_resume_result_to_json(result),
            )
            self._session.commit()
            return result
        except Exception:
            self._rollback_idempotency_on_failure(tenant_id, idempotency_key)
            raise

    def complete_upload_session(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        request_path: str,
        request_body: dict[str, Any],
        idempotency_key: str | None,
        request_id: str,
        checksum_sha256: str | None,
    ) -> CompleteUploadSessionResult:
        existing = self._resolve_idempotency(
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
            upload_session = self._get_session_for_update(
                tenant_id=tenant_id,
                session_id=session_id,
            )
            status = UploadSessionStatus(upload_session.status)
            if status is UploadSessionStatus.COMPLETED:
                result = self._completed_result(upload_session)
                self._store_idempotency_response(
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                    response_status=200,
                    response_body=_complete_result_to_json(result),
                )
                self._session.commit()
                return result
            if not can_complete(status):
                raise self._invalid_lifecycle_state(
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
            self._sync_related_records(
                upload_session,
                status=UploadSessionStatus.COMPLETING,
                now=now,
            )
            self._add_event(
                upload_session,
                actor=actor,
                request_id=request_id,
                event_type="upload.complete_requested",
                payload={"checksum_sha256": checksum_sha256},
            )
            self._session.commit()

            storage_parts = self._list_storage_parts(upload_session)
            completion_parts = self._validate_complete_parts(
                upload_session,
                storage_parts,
                previous_status=previous_status,
            )
            storage_result = self._storage.complete_multipart_upload(
                CompleteMultipartUploadRequest(
                    bucket=upload_session.bucket_name,
                    object_key=upload_session.object_key,
                    upload_id=upload_session.storage_upload_id,
                    parts=completion_parts,
                    checksum={"sha256": checksum_sha256} if checksum_sha256 else {},
                )
            )
            result = self._mark_completed(
                tenant_id=tenant_id,
                session_id=session_id,
                actor=actor,
                request_id=request_id,
                storage_result=storage_result,
                idempotency_key=idempotency_key,
            )
            self._session.commit()
            return result
        except ApiError:
            self._rollback_idempotency_on_failure(tenant_id, idempotency_key)
            raise
        except StorageError as exc:
            if previous_status is not None:
                self._restore_status_after_storage_failure(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    previous_status=previous_status,
                    error_code="storage.complete_failed",
                    error_message=str(exc),
                )
            self._rollback_idempotency_on_failure(tenant_id, idempotency_key)
            raise ApiError(
                status_code=502,
                code="storage.complete_failed",
                message="Storage multipart complete failed.",
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc

    def abort_upload_session(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        request_path: str,
        request_body: dict[str, Any],
        idempotency_key: str | None,
        request_id: str,
        reason: str | None,
    ) -> AbortUploadSessionResult:
        existing = self._resolve_idempotency(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            request_path=request_path,
            request_body=request_body,
            result_loader=_abort_result_from_json,
        )
        if existing is not None:
            return existing

        previous_status: UploadSessionStatus | None = None
        try:
            upload_session = self._get_session_for_update(
                tenant_id=tenant_id,
                session_id=session_id,
            )
            status = UploadSessionStatus(upload_session.status)
            if status is UploadSessionStatus.ABORTED:
                result = self._aborted_result(upload_session)
                self._store_idempotency_response(
                    tenant_id=tenant_id,
                    idempotency_key=idempotency_key,
                    response_status=200,
                    response_body=_abort_result_to_json(result),
                )
                self._session.commit()
                return result
            if not can_abort(status):
                raise self._invalid_lifecycle_state(
                    action="abort",
                    upload_session=upload_session,
                )
            if upload_session.storage_upload_id is None:
                result = self._mark_aborted_without_storage(
                    upload_session=upload_session,
                    actor=actor,
                    request_id=request_id,
                    reason=reason,
                    idempotency_key=idempotency_key,
                )
                self._session.commit()
                return result

            previous_status = status
            now = datetime.now(UTC)
            upload_session.status = UploadSessionStatus.ABORTING.value
            upload_session.updated_at = now
            self._sync_related_records(
                upload_session,
                status=UploadSessionStatus.ABORTING,
                now=now,
            )
            self._add_event(
                upload_session,
                actor=actor,
                request_id=request_id,
                event_type="upload.abort_requested",
                payload={"reason": reason},
            )
            self._session.commit()

            with suppress(StorageNotFoundError):
                self._storage.abort_multipart_upload(
                    AbortMultipartUploadRequest(
                        bucket=upload_session.bucket_name,
                        object_key=upload_session.object_key,
                        upload_id=upload_session.storage_upload_id,
                    )
                )
            result = self._mark_aborted(
                tenant_id=tenant_id,
                session_id=session_id,
                actor=actor,
                request_id=request_id,
                reason=reason,
                idempotency_key=idempotency_key,
            )
            self._session.commit()
            return result
        except ApiError:
            self._rollback_idempotency_on_failure(tenant_id, idempotency_key)
            raise
        except StorageError as exc:
            if previous_status is not None:
                self._restore_status_after_storage_failure(
                    tenant_id=tenant_id,
                    session_id=session_id,
                    previous_status=previous_status,
                    error_code="storage.abort_failed",
                    error_message=str(exc),
                )
            self._rollback_idempotency_on_failure(tenant_id, idempotency_key)
            raise ApiError(
                status_code=502,
                code="storage.abort_failed",
                message="Storage multipart abort failed.",
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc

    def _get_session(self, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> UploadSession:
        upload_session = self._session.get(UploadSession, session_id)
        if upload_session is None or upload_session.tenant_id != tenant_id:
            raise ApiError(
                status_code=404,
                code="upload_session.not_found",
                message="Upload session not found.",
            )
        return upload_session

    def _get_session_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> UploadSession:
        upload_session = self._session.scalars(
            select(UploadSession)
            .where(UploadSession.id == session_id)
            .where(UploadSession.tenant_id == tenant_id)
            .with_for_update()
        ).one_or_none()
        if upload_session is None:
            raise ApiError(
                status_code=404,
                code="upload_session.not_found",
                message="Upload session not found.",
            )
        return upload_session

    def _observe_storage_parts(
        self,
        *,
        upload_session: UploadSession,
        actor: AuthenticatedActor,
        request_id: str,
        reconcile: bool,
    ) -> tuple[RuntimePartState, ...]:
        if upload_session.storage_upload_id is None:
            raise ApiError(
                status_code=409,
                code="upload.storage_upload_missing",
                message="Upload session has no storage multipart upload ID.",
            )

        observed_parts: list[ListedPart] = []
        marker: int | None = None
        try:
            while True:
                page = self._storage.list_parts(
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
        except StorageError as exc:
            raise ApiError(
                status_code=502,
                code="storage.list_parts_failed",
                message="Storage ListParts failed.",
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc

        if reconcile:
            now = datetime.now(UTC)
            for observed in observed_parts:
                self._upsert_part(
                    upload_session=upload_session,
                    part_number=observed.part_number,
                    status="UPLOADED",
                    now=now,
                    etag=observed.etag,
                    size_bytes=observed.size_bytes,
                    checksum_sha256=observed.checksum.get("sha256"),
                    uploaded_at=observed.last_modified or now,
                    source="storage",
                )
            self._add_event(
                upload_session,
                actor=actor,
                request_id=request_id,
                event_type="upload.parts_reconciled",
                payload={"observed_part_numbers": [part.part_number for part in observed_parts]},
            )
        return tuple(self._storage_part_result(upload_session, part) for part in observed_parts)

    def _list_storage_parts(self, upload_session: UploadSession) -> tuple[ListedPart, ...]:
        if upload_session.storage_upload_id is None:
            raise ApiError(
                status_code=409,
                code="upload.storage_upload_missing",
                message="Upload session has no storage multipart upload ID.",
            )
        observed_parts: list[ListedPart] = []
        marker: int | None = None
        while True:
            page = self._storage.list_parts(
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
        self,
        upload_session: UploadSession,
        storage_parts: tuple[ListedPart, ...],
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
            self._restore_after_missing_parts(
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

    def _upsert_part(
        self,
        *,
        upload_session: UploadSession,
        part_number: int,
        status: str,
        now: datetime,
        etag: str | None = None,
        size_bytes: int | None = None,
        checksum_sha256: str | None = None,
        last_presigned_at: datetime | None = None,
        presign_expires_at: datetime | None = None,
        uploaded_at: datetime | None = None,
        source: str = "db",
        preserve_uploaded: bool = False,
    ) -> UploadPart:
        part_range = get_part_range(
            upload_session.file_size_bytes,
            upload_session.part_size_bytes,
            part_number,
        )
        part = self._session.get(UploadPart, (upload_session.id, part_number))
        if part is None:
            part = UploadPart(
                session_id=upload_session.id,
                part_number=part_number,
                offset_start=part_range.offset_start,
                offset_end_exclusive=part_range.offset_end_exclusive,
                expected_size_bytes=part_range.expected_size,
                created_at=now,
            )
            self._session.add(part)
        part.offset_start = part_range.offset_start
        part.offset_end_exclusive = part_range.offset_end_exclusive
        part.expected_size_bytes = part_range.expected_size
        if not (preserve_uploaded and part.status == "UPLOADED"):
            part.status = status
        if etag is not None:
            part.etag = etag
        if size_bytes is not None:
            part.size_bytes = size_bytes
        if checksum_sha256 is not None:
            part.checksum_sha256 = checksum_sha256
        if last_presigned_at is not None:
            part.last_presigned_at = last_presigned_at
        if presign_expires_at is not None:
            part.presign_expires_at = presign_expires_at
        if uploaded_at is not None:
            part.uploaded_at = uploaded_at
        part.source = source
        part.updated_at = now
        self._session.flush()
        return part

    def _uploaded_part_count(self, session_id: uuid.UUID) -> int:
        return self._count(
            select(func.count())
            .select_from(UploadPart)
            .where(UploadPart.session_id == session_id)
            .where(UploadPart.status == "UPLOADED")
        )

    def _load_parts(self, session_id: uuid.UUID) -> list[UploadPart]:
        return list(
            self._session.scalars(
                select(UploadPart)
                .where(UploadPart.session_id == session_id)
                .order_by(UploadPart.part_number.asc())
            )
        )

    def _add_event(
        self,
        upload_session: UploadSession,
        *,
        actor: AuthenticatedActor,
        request_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        self._session.add(
            UploadEvent(
                tenant_id=upload_session.tenant_id,
                project_id=upload_session.project_id,
                dataset_id=upload_session.dataset_id,
                upload_task_id=upload_session.upload_task_id,
                upload_object_id=upload_session.upload_object_id,
                session_id=upload_session.id,
                event_type=event_type,
                actor_type=actor.actor_type,
                actor_id=str(actor.subject_id),
                request_id=request_id,
                payload=payload,
            )
        )

    def _resolve_idempotency[T](
        self,
        *,
        tenant_id: uuid.UUID,
        idempotency_key: str | None,
        request_path: str,
        request_body: dict[str, Any],
        result_loader: Callable[[dict[str, Any]], T],
    ) -> T | None:
        if idempotency_key is None:
            return None
        fingerprint = generate_request_fingerprint(
            method="POST",
            path=request_path,
            tenant_id=tenant_id,
            body=assert_json_value(request_body),
        )
        record = self._session.scalars(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.tenant_id == tenant_id)
            .where(IdempotencyRecord.key == idempotency_key)
            .with_for_update()
        ).one_or_none()
        if record is None:
            self._session.add(
                IdempotencyRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    key=idempotency_key,
                    request_method="POST",
                    request_path=request_path,
                    request_fingerprint=fingerprint,
                    response_status=None,
                    response_body=None,
                    locked_until=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            self._session.flush()
            return None
        if record.request_fingerprint != fingerprint:
            raise ApiError(
                status_code=409,
                code="idempotency.key_reused_with_different_request",
                message="Idempotency key was reused with a different request.",
            )
        if record.response_status == 200 and record.response_body is not None:
            return result_loader(record.response_body)
        raise ApiError(
            status_code=409,
            code="idempotency.request_in_progress",
            message="An idempotent request with this key is still in progress.",
        )

    def _store_idempotency_response(
        self,
        *,
        tenant_id: uuid.UUID,
        idempotency_key: str | None,
        response_status: int,
        response_body: dict[str, Any],
    ) -> None:
        if idempotency_key is None:
            return
        record = self._session.scalars(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.tenant_id == tenant_id)
            .where(IdempotencyRecord.key == idempotency_key)
        ).one()
        record.response_status = response_status
        record.response_body = response_body
        record.locked_until = None
        record.updated_at = datetime.now(UTC)

    def _rollback_idempotency_on_failure(
        self,
        tenant_id: uuid.UUID,
        idempotency_key: str | None,
    ) -> None:
        self._session.rollback()
        if idempotency_key is None:
            return
        self._session.execute(
            delete(IdempotencyRecord)
            .where(IdempotencyRecord.tenant_id == tenant_id)
            .where(IdempotencyRecord.key == idempotency_key)
            .where(IdempotencyRecord.response_status.is_(None))
        )
        self._session.commit()

    def _invalid_lifecycle_state(
        self,
        *,
        action: str,
        upload_session: UploadSession,
    ) -> ApiError:
        status_code = 410 if upload_session.status == UploadSessionStatus.EXPIRED.value else 409
        return ApiError(
            status_code=status_code,
            code="upload.invalid_state",
            message=f"Upload session is not in a state that allows {action}.",
            details={"session_id": str(upload_session.id), "status": upload_session.status},
        )

    def _mark_completed(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str,
        storage_result: CompletedObject,
        idempotency_key: str | None,
    ) -> CompleteUploadSessionResult:
        upload_session = self._get_session_for_update(tenant_id=tenant_id, session_id=session_id)
        now = datetime.now(UTC)
        upload_session.status = UploadSessionStatus.COMPLETED.value
        upload_session.object_etag = storage_result.etag
        upload_session.object_size_bytes = storage_result.size_bytes
        upload_session.object_version_id = storage_result.version_id
        upload_session.completed_part_count = upload_session.part_count
        upload_session.uploaded_part_count = upload_session.part_count
        upload_session.completed_at = now
        upload_session.updated_at = now
        self._sync_related_records(
            upload_session,
            status=UploadSessionStatus.COMPLETED,
            now=now,
            storage_result=storage_result,
        )
        self._add_event(
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
        result = self._completed_result(upload_session)
        self._store_idempotency_response(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            response_status=200,
            response_body=_complete_result_to_json(result),
        )
        return result

    def _mark_aborted(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str,
        reason: str | None,
        idempotency_key: str | None,
    ) -> AbortUploadSessionResult:
        upload_session = self._get_session_for_update(tenant_id=tenant_id, session_id=session_id)
        return self._mark_aborted_without_storage(
            upload_session=upload_session,
            actor=actor,
            request_id=request_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )

    def _mark_aborted_without_storage(
        self,
        *,
        upload_session: UploadSession,
        actor: AuthenticatedActor,
        request_id: str,
        reason: str | None,
        idempotency_key: str | None,
    ) -> AbortUploadSessionResult:
        now = datetime.now(UTC)
        upload_session.status = UploadSessionStatus.ABORTED.value
        upload_session.aborted_at = upload_session.aborted_at or now
        upload_session.updated_at = now
        self._sync_related_records(upload_session, status=UploadSessionStatus.ABORTED, now=now)
        self._add_event(
            upload_session,
            actor=actor,
            request_id=request_id,
            event_type="upload.aborted",
            payload={"reason": reason},
        )
        result = self._aborted_result(upload_session)
        self._store_idempotency_response(
            tenant_id=upload_session.tenant_id,
            idempotency_key=idempotency_key,
            response_status=200,
            response_body=_abort_result_to_json(result),
        )
        return result

    def _restore_after_missing_parts(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        fallback_status: UploadSessionStatus,
        storage_parts: tuple[ListedPart, ...],
        missing: tuple[int, ...],
        unexpected: tuple[int, ...],
        size_mismatches: list[dict[str, int]],
    ) -> None:
        upload_session = self._get_session_for_update(tenant_id=tenant_id, session_id=session_id)
        now = datetime.now(UTC)
        upload_session.status = fallback_status.value
        upload_session.last_error_code = "upload.missing_parts"
        upload_session.last_error_message = (
            "Upload cannot be completed because storage parts are missing."
        )
        upload_session.updated_at = now
        for part in storage_parts:
            self._upsert_part(
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
        upload_session.uploaded_part_count = self._uploaded_part_count(session_id)
        self._sync_related_records(upload_session, status=fallback_status, now=now)
        self._session.commit()
        _ = (missing, unexpected, size_mismatches)

    def _restore_status_after_storage_failure(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
        previous_status: UploadSessionStatus,
        error_code: str,
        error_message: str,
    ) -> None:
        self._session.rollback()
        upload_session = self._get_session_for_update(tenant_id=tenant_id, session_id=session_id)
        now = datetime.now(UTC)
        upload_session.status = previous_status.value
        upload_session.last_error_code = error_code
        upload_session.last_error_message = error_message
        upload_session.updated_at = now
        self._sync_related_records(upload_session, status=previous_status, now=now)
        self._session.commit()

    def _sync_related_records(
        self,
        upload_session: UploadSession,
        *,
        status: UploadSessionStatus,
        now: datetime,
        storage_result: CompletedObject | None = None,
    ) -> None:
        if upload_session.upload_object_id is not None:
            upload_object = self._session.get(UploadObject, upload_session.upload_object_id)
            if upload_object is not None:
                upload_object.status = _upload_object_status(status)
                upload_object.updated_at = now
                if status is UploadSessionStatus.COMPLETED:
                    upload_object.completed_at = now
        if upload_session.dataset_id is not None:
            dataset = self._session.get(Dataset, upload_session.dataset_id)
            if dataset is not None:
                dataset_status = _dataset_status(status)
                if dataset_status is not None:
                    dataset.status = dataset_status
                if storage_result is not None:
                    dataset.object_etag = storage_result.etag
                    dataset.object_size_bytes = storage_result.size_bytes
                    dataset.object_version_id = storage_result.version_id
                    dataset.bucket_name = storage_result.bucket
                    dataset.object_key = storage_result.object_key
                dataset.updated_at = now
        if upload_session.upload_task_id is not None:
            upload_task = self._session.get(UploadTask, upload_session.upload_task_id)
            if upload_task is not None:
                upload_task.status = _upload_task_status(status)
                upload_task.updated_at = now
                if status is UploadSessionStatus.COMPLETED:
                    upload_task.completed_object_count = min(
                        upload_task.object_count,
                        upload_task.completed_object_count + 1,
                    )
                    upload_task.completed_at = now
                if status is UploadSessionStatus.ABORTED:
                    upload_task.cancelled_at = now

    def _completed_result(self, upload_session: UploadSession) -> CompleteUploadSessionResult:
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

    def _aborted_result(self, upload_session: UploadSession) -> AbortUploadSessionResult:
        aborted_at = upload_session.aborted_at or datetime.now(UTC)
        return AbortUploadSessionResult(
            session_id=upload_session.id,
            status=upload_session.status,
            aborted_at=aborted_at,
        )

    def _set_pause_metadata(
        self,
        upload_session: UploadSession,
        *,
        paused_at: datetime,
        reason: str | None,
    ) -> None:
        metadata = dict(upload_session.metadata_ or {})
        metadata["paused_at"] = paused_at.isoformat()
        if reason is not None:
            metadata["pause_reason"] = reason
        upload_session.metadata_ = metadata

    def _clear_pause_metadata(self, upload_session: UploadSession) -> None:
        metadata = dict(upload_session.metadata_ or {})
        metadata.pop("paused_at", None)
        metadata.pop("pause_reason", None)
        upload_session.metadata_ = metadata

    def _paused_at(self, upload_session: UploadSession) -> datetime | None:
        value = (upload_session.metadata_ or {}).get("paused_at")
        if not isinstance(value, str):
            return None
        return datetime.fromisoformat(value)

    def _pause_reason(self, upload_session: UploadSession) -> str | None:
        value = (upload_session.metadata_ or {}).get("pause_reason")
        return value if isinstance(value, str) else None

    def _session_result(
        self,
        upload_session: UploadSession,
        uploaded_part_count: int,
    ) -> RuntimeUploadSession:
        return RuntimeUploadSession(
            session_id=upload_session.id,
            project_id=upload_session.project_id,
            dataset_id=upload_session.dataset_id,
            status=upload_session.status,
            bucket=upload_session.bucket_name,
            object_key=upload_session.object_key,
            original_filename=upload_session.original_filename,
            file_size_bytes=upload_session.file_size_bytes,
            part_size_bytes=upload_session.part_size_bytes,
            part_count=upload_session.part_count,
            uploaded_part_count=uploaded_part_count,
            missing_part_count=upload_session.part_count - uploaded_part_count,
            paused_at=self._paused_at(upload_session),
            pause_reason=self._pause_reason(upload_session),
            expires_at=upload_session.expires_at,
            created_at=upload_session.created_at,
            updated_at=upload_session.updated_at,
        )

    def _part_result(self, part: UploadPart) -> RuntimePartState:
        return RuntimePartState(
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

    def _storage_part_result(
        self,
        upload_session: UploadSession,
        part: ListedPart,
    ) -> RuntimePartState:
        part_range = get_part_range(
            upload_session.file_size_bytes,
            upload_session.part_size_bytes,
            part.part_number,
        )
        return RuntimePartState(
            part_number=part.part_number,
            etag=part.etag,
            size_bytes=part.size_bytes,
            status="UPLOADED",
            uploaded_at=part.last_modified,
            expected_size_bytes=part_range.expected_size,
            offset_start=part_range.offset_start,
            offset_end_exclusive=part_range.offset_end_exclusive,
            last_presigned_at=None,
            presign_expires_at=None,
        )

    def _count(self, statement: Select[tuple[int]]) -> int:
        return int(self._session.execute(statement).scalar_one())


def _upload_object_status(status: UploadSessionStatus) -> str:
    return {
        UploadSessionStatus.INITIATING: "PENDING",
        UploadSessionStatus.INITIATED: "PENDING",
        UploadSessionStatus.UPLOADING: "UPLOADING",
        UploadSessionStatus.PAUSED: "PAUSED",
        UploadSessionStatus.COMPLETING: "COMPLETING",
        UploadSessionStatus.COMPLETED: "COMPLETED",
        UploadSessionStatus.ABORTING: "CANCELLED",
        UploadSessionStatus.ABORTED: "CANCELLED",
        UploadSessionStatus.EXPIRED: "FAILED",
        UploadSessionStatus.FAILED: "FAILED",
    }[status]


def _upload_task_status(status: UploadSessionStatus) -> str:
    return {
        UploadSessionStatus.INITIATING: "PENDING",
        UploadSessionStatus.INITIATED: "PENDING",
        UploadSessionStatus.UPLOADING: "PROCESSING",
        UploadSessionStatus.PAUSED: "PAUSED",
        UploadSessionStatus.COMPLETING: "PROCESSING",
        UploadSessionStatus.COMPLETED: "COMPLETED",
        UploadSessionStatus.ABORTING: "CANCELLED",
        UploadSessionStatus.ABORTED: "CANCELLED",
        UploadSessionStatus.EXPIRED: "FAILED",
        UploadSessionStatus.FAILED: "FAILED",
    }[status]


def _dataset_status(status: UploadSessionStatus) -> str | None:
    return {
        UploadSessionStatus.INITIATING: "UPLOAD_PENDING",
        UploadSessionStatus.INITIATED: "UPLOAD_PENDING",
        UploadSessionStatus.UPLOADING: "UPLOADING",
        UploadSessionStatus.PAUSED: "PAUSED",
        UploadSessionStatus.COMPLETING: "PROCESSING",
        UploadSessionStatus.COMPLETED: "PROCESSING",
        UploadSessionStatus.ABORTING: None,
        UploadSessionStatus.ABORTED: None,
        UploadSessionStatus.EXPIRED: None,
        UploadSessionStatus.FAILED: None,
    }[status]


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
