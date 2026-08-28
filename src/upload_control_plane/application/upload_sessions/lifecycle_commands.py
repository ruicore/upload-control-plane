from __future__ import annotations

import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.errors import ApiError
from upload_control_plane.application.upload_sessions.contracts import (
    AbortUploadSessionResult,
    PauseUploadSessionResult,
    ResumeUploadSessionResult,
    _abort_result_from_json,
    _abort_result_to_json,
    _pause_result_from_json,
    _pause_result_to_json,
    _resume_result_from_json,
    _resume_result_to_json,
)
from upload_control_plane.application.upload_sessions.event_writer import UploadEventWriter
from upload_control_plane.application.upload_sessions.idempotency import (
    resolve_idempotency,
    rollback_idempotency_on_failure,
    store_idempotency_response,
)
from upload_control_plane.application.upload_sessions.persisted_projection import (
    PersistedUploadAggregateProjector,
)
from upload_control_plane.domain.session_state import (
    UploadSessionStatus,
    can_abort,
    can_pause,
    can_resume,
)
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    ObjectStorage,
    StorageError,
    StorageNotFoundError,
)
from upload_control_plane.infrastructure.db.models import UploadSession


class LifecycleCommandContext(Protocol):
    """Capabilities required by upload-session lifecycle commands."""

    @property
    def _session(self) -> Session: ...

    @property
    def _storage(self) -> ObjectStorage: ...

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

    def _set_pause_metadata(
        self,
        upload_session: UploadSession,
        *,
        paused_at: datetime,
        reason: str | None,
    ) -> None: ...

    def _clear_pause_metadata(self, upload_session: UploadSession) -> None: ...

    def _paused_at(self, upload_session: UploadSession) -> datetime | None: ...

    def _pause_reason(self, upload_session: UploadSession) -> str | None: ...


def pause_upload_session(
    context: LifecycleCommandContext,
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
    reason: str | None,
    client_inflight_behavior: str | None,
) -> PauseUploadSessionResult:
    existing = resolve_idempotency(
        context._session,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        request_path=request_path,
        request_body=request_body,
        result_loader=_pause_result_from_json,
    )
    if existing is not None:
        return existing

    try:
        upload_session = context._get_session_for_update(
            tenant_id=tenant_id,
            session_id=session_id,
        )
        status = UploadSessionStatus(upload_session.status)
        if not can_pause(status):
            raise context._invalid_lifecycle_state(
                action="pause",
                upload_session=upload_session,
            )
        now = datetime.now(UTC)
        if status is not UploadSessionStatus.PAUSED:
            upload_session.status = UploadSessionStatus.PAUSED.value
            context._set_pause_metadata(upload_session, paused_at=now, reason=reason)
            projection.project_runtime_transition(
                upload_session,
                status=UploadSessionStatus.PAUSED,
                now=now,
            )
            event_type = "upload.paused"
        else:
            paused_at = context._paused_at(upload_session) or now
            context._set_pause_metadata(upload_session, paused_at=paused_at, reason=reason)
            event_type = "upload.pause_requested"
        upload_session.updated_at = now
        event_writer.write_actor_event(
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
            paused_at=context._paused_at(upload_session) or now,
            pause_reason=context._pause_reason(upload_session),
        )
        store_idempotency_response(
            context._session,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            response_status=200,
            response_body=_pause_result_to_json(result),
        )
        context._session.commit()
        return result
    except Exception:
        rollback_idempotency_on_failure(context._session, tenant_id, idempotency_key)
        raise


def resume_upload_session(
    context: LifecycleCommandContext,
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
    reason: str | None,
) -> ResumeUploadSessionResult:
    existing = resolve_idempotency(
        context._session,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        request_path=request_path,
        request_body=request_body,
        result_loader=_resume_result_from_json,
    )
    if existing is not None:
        return existing

    try:
        upload_session = context._get_session_for_update(
            tenant_id=tenant_id,
            session_id=session_id,
        )
        status = UploadSessionStatus(upload_session.status)
        if not can_resume(status):
            raise context._invalid_lifecycle_state(
                action="resume",
                upload_session=upload_session,
            )
        now = datetime.now(UTC)
        if status is not UploadSessionStatus.UPLOADING:
            upload_session.status = UploadSessionStatus.UPLOADING.value
            context._clear_pause_metadata(upload_session)
            projection.project_runtime_transition(
                upload_session,
                status=UploadSessionStatus.UPLOADING,
                now=now,
            )
            event_type = "upload.resumed"
        else:
            event_type = "upload.resume_requested"
        upload_session.updated_at = now
        event_writer.write_actor_event(
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
        store_idempotency_response(
            context._session,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            response_status=200,
            response_body=_resume_result_to_json(result),
        )
        context._session.commit()
        return result
    except Exception:
        rollback_idempotency_on_failure(context._session, tenant_id, idempotency_key)
        raise


def abort_upload_session(
    context: LifecycleCommandContext,
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
    reason: str | None,
) -> AbortUploadSessionResult:
    existing = resolve_idempotency(
        context._session,
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
        upload_session = context._get_session_for_update(
            tenant_id=tenant_id,
            session_id=session_id,
        )
        status = UploadSessionStatus(upload_session.status)
        if status is UploadSessionStatus.ABORTED:
            result = _aborted_result(upload_session)
            store_idempotency_response(
                context._session,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                response_status=200,
                response_body=_abort_result_to_json(result),
            )
            context._session.commit()
            return result
        if not can_abort(status):
            raise context._invalid_lifecycle_state(
                action="abort",
                upload_session=upload_session,
            )
        if upload_session.storage_upload_id is None:
            result = _mark_aborted_without_storage(
                context,
                projection=projection,
                event_writer=event_writer,
                upload_session=upload_session,
                actor=actor,
                request_id=request_id,
                reason=reason,
                idempotency_key=idempotency_key,
            )
            context._session.commit()
            return result

        previous_status = status
        now = datetime.now(UTC)
        upload_session.status = UploadSessionStatus.ABORTING.value
        upload_session.updated_at = now
        projection.project_runtime_transition(
            upload_session,
            status=UploadSessionStatus.ABORTING,
            now=now,
        )
        event_writer.write_actor_event(
            upload_session,
            actor=actor,
            request_id=request_id,
            event_type="upload.abort_requested",
            payload={"reason": reason},
        )
        context._session.commit()

        with suppress(StorageNotFoundError):
            context._storage.abort_multipart_upload(
                AbortMultipartUploadRequest(
                    bucket=upload_session.bucket_name,
                    object_key=upload_session.object_key,
                    upload_id=upload_session.storage_upload_id,
                )
            )
        result = _mark_aborted(
            context,
            projection=projection,
            event_writer=event_writer,
            tenant_id=tenant_id,
            session_id=session_id,
            actor=actor,
            request_id=request_id,
            reason=reason,
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
                error_code="storage.abort_failed",
                error_message=str(exc),
            )
        rollback_idempotency_on_failure(context._session, tenant_id, idempotency_key)
        raise ApiError(
            status_code=502,
            code="storage.abort_failed",
            message="Storage multipart abort failed.",
            details={"operation": exc.operation, "provider_code": exc.provider_code},
        ) from exc


def _mark_aborted(
    context: LifecycleCommandContext,
    *,
    projection: PersistedUploadAggregateProjector,
    event_writer: UploadEventWriter,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    actor: AuthenticatedActor,
    request_id: str,
    reason: str | None,
    idempotency_key: str | None,
) -> AbortUploadSessionResult:
    upload_session = context._get_session_for_update(
        tenant_id=tenant_id,
        session_id=session_id,
    )
    return _mark_aborted_without_storage(
        context,
        projection=projection,
        event_writer=event_writer,
        upload_session=upload_session,
        actor=actor,
        request_id=request_id,
        reason=reason,
        idempotency_key=idempotency_key,
    )


def _mark_aborted_without_storage(
    context: LifecycleCommandContext,
    *,
    projection: PersistedUploadAggregateProjector,
    event_writer: UploadEventWriter,
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
    projection.project_runtime_transition(
        upload_session,
        status=UploadSessionStatus.ABORTED,
        now=now,
    )
    event_writer.write_actor_event(
        upload_session,
        actor=actor,
        request_id=request_id,
        event_type="upload.aborted",
        payload={"reason": reason},
    )
    result = _aborted_result(upload_session)
    store_idempotency_response(
        context._session,
        tenant_id=upload_session.tenant_id,
        idempotency_key=idempotency_key,
        response_status=200,
        response_body=_abort_result_to_json(result),
    )
    return result


def _aborted_result(upload_session: UploadSession) -> AbortUploadSessionResult:
    aborted_at = upload_session.aborted_at or datetime.now(UTC)
    return AbortUploadSessionResult(
        session_id=upload_session.id,
        status=upload_session.status,
        aborted_at=aborted_at,
    )
