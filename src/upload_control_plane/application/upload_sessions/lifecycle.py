from __future__ import annotations

import uuid
from abc import abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.errors import ApiError
from upload_control_plane.application.upload_sessions.completion import (
    complete_upload_session as execute_complete_upload_session,
)
from upload_control_plane.application.upload_sessions.contracts import (
    AbortUploadSessionResult,
    CompleteUploadSessionResult,
    PauseUploadSessionResult,
    ResumeUploadSessionResult,
)
from upload_control_plane.application.upload_sessions.lifecycle_commands import (
    abort_upload_session as execute_abort_upload_session,
)
from upload_control_plane.application.upload_sessions.lifecycle_commands import (
    pause_upload_session as execute_pause_upload_session,
)
from upload_control_plane.application.upload_sessions.lifecycle_commands import (
    resume_upload_session as execute_resume_upload_session,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.session_state import UploadSessionStatus
from upload_control_plane.domain.storage import ObjectStorage
from upload_control_plane.infrastructure.db.models import UploadSession

if TYPE_CHECKING:
    from upload_control_plane.application.upload_sessions.event_writer import UploadEventWriter
    from upload_control_plane.application.upload_sessions.persisted_projection import (
        PersistedUploadAggregateProjector,
    )


class UploadSessionLifecycleMixin:
    """Lifecycle, idempotency, recovery, and aggregate-sync responsibilities."""

    if TYPE_CHECKING:

        @property
        @abstractmethod
        def _session(self) -> Session: ...

        @property
        @abstractmethod
        def _storage(self) -> ObjectStorage: ...

        @property
        @abstractmethod
        def _settings(self) -> Settings: ...

        @property
        @abstractmethod
        def _projection(self) -> PersistedUploadAggregateProjector: ...

        @property
        @abstractmethod
        def _event_writer(self) -> UploadEventWriter: ...

        def __getattr__(self, name: str) -> Any: ...
    else:

        def __getattr__(self, name: str) -> Any:
            """Declare facade-provided dependencies for static mixin checking."""
            raise AttributeError(name)

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
        return execute_pause_upload_session(
            self,
            projection=self._projection,
            event_writer=self._event_writer,
            tenant_id=tenant_id,
            actor=actor,
            session_id=session_id,
            request_path=request_path,
            request_body=request_body,
            idempotency_key=idempotency_key,
            request_id=request_id,
            reason=reason,
            client_inflight_behavior=client_inflight_behavior,
        )

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
        return execute_resume_upload_session(
            self,
            projection=self._projection,
            event_writer=self._event_writer,
            tenant_id=tenant_id,
            actor=actor,
            session_id=session_id,
            request_path=request_path,
            request_body=request_body,
            idempotency_key=idempotency_key,
            request_id=request_id,
            reason=reason,
        )

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
        return execute_complete_upload_session(
            self,
            projection=self._projection,
            event_writer=self._event_writer,
            tenant_id=tenant_id,
            actor=actor,
            session_id=session_id,
            request_path=request_path,
            request_body=request_body,
            idempotency_key=idempotency_key,
            request_id=request_id,
            checksum_sha256=checksum_sha256,
        )

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
        return execute_abort_upload_session(
            self,
            projection=self._projection,
            event_writer=self._event_writer,
            tenant_id=tenant_id,
            actor=actor,
            session_id=session_id,
            request_path=request_path,
            request_body=request_body,
            idempotency_key=idempotency_key,
            request_id=request_id,
            reason=reason,
        )

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

    def _add_event(
        self,
        upload_session: UploadSession,
        *,
        actor: AuthenticatedActor,
        request_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        """Compatibility seam for part mixins that also emit upload events."""
        self._event_writer.write_actor_event(
            upload_session,
            actor=actor,
            request_id=request_id,
            event_type=event_type,
            payload=payload,
        )

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
        self._projection.project_runtime_transition(
            upload_session,
            status=previous_status,
            now=now,
        )
        self._session.commit()

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
