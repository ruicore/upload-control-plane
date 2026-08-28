from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.application.upload_sessions.event_writer import UploadEventWriter
from upload_control_plane.application.upload_sessions.persisted_projection import (
    PersistedUploadAggregateProjector,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.session_state import UploadSessionStatus
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    ObjectStorage,
    StorageError,
    StorageNotFoundError,
)
from upload_control_plane.infrastructure.db.models import UploadSession

EXPIRABLE_SESSION_STATUSES = (
    UploadSessionStatus.INITIATED.value,
    UploadSessionStatus.UPLOADING.value,
    UploadSessionStatus.PAUSED.value,
)


@dataclass(frozen=True, slots=True)
class UploadSessionCleanupSummary:
    aborted_sessions: int = 0
    errors: int = 0


class UploadSessionCleanupService:
    """Expire stale upload sessions and clean up their multipart uploads."""

    def __init__(self, *, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._projection = PersistedUploadAggregateProjector(
            session=session,
            settings=settings,
        )
        self._event_writer = UploadEventWriter(session)

    def expire_old_sessions(self, *, now: datetime, batch_size: int | None = None) -> int:
        limit = batch_size or self._settings.worker_batch_size
        sessions = list(
            self._session.scalars(
                select(UploadSession)
                .where(UploadSession.status.in_(EXPIRABLE_SESSION_STATUSES))
                .where(UploadSession.expires_at < now)
                .order_by(UploadSession.expires_at.asc(), UploadSession.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for upload_session in sessions:
            previous_status = upload_session.status
            upload_session.status = UploadSessionStatus.EXPIRED.value
            upload_session.updated_at = now
            upload_session.last_error_code = "upload.expired"
            upload_session.last_error_message = "Upload session expired before completion."
            self._projection.project_cleanup_transition(
                upload_session,
                status=UploadSessionStatus.EXPIRED,
                now=now,
            )
            self._event_writer.write_cleanup_event(
                upload_session,
                event_type="upload.expired",
                payload={
                    "previous_status": previous_status,
                    "expires_at": _iso(upload_session.expires_at),
                },
                now=now,
            )
        self._session.commit()
        return len(sessions)

    def abort_expired_multipart_uploads(
        self, *, now: datetime, batch_size: int | None = None
    ) -> UploadSessionCleanupSummary:
        limit = batch_size or self._settings.worker_batch_size
        grace_cutoff = now - timedelta(seconds=self._settings.expired_session_abort_grace_seconds)
        sessions = list(
            self._session.scalars(
                select(UploadSession)
                .where(
                    UploadSession.status.in_(
                        (UploadSessionStatus.EXPIRED.value, UploadSessionStatus.ABORTING.value)
                    )
                )
                .where(UploadSession.updated_at <= grace_cutoff)
                .order_by(UploadSession.updated_at.asc(), UploadSession.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        aborted = 0
        errors = 0
        for upload_session in sessions:
            if self._abort_one_expired_session(upload_session, now=now):
                aborted += 1
            else:
                errors += 1
        return UploadSessionCleanupSummary(aborted_sessions=aborted, errors=errors)

    def _abort_one_expired_session(self, upload_session: UploadSession, *, now: datetime) -> bool:
        if upload_session.status == UploadSessionStatus.EXPIRED.value:
            upload_session.status = UploadSessionStatus.ABORTING.value
            upload_session.updated_at = now
            self._projection.project_cleanup_transition(
                upload_session,
                status=UploadSessionStatus.ABORTING,
                now=now,
            )
            self._event_writer.write_cleanup_event(
                upload_session,
                event_type="upload.abort_requested",
                payload={"reason": "expired_session_cleanup"},
                now=now,
            )
            self._session.commit()

        if upload_session.storage_upload_id is not None:
            try:
                self._storage.abort_multipart_upload(
                    AbortMultipartUploadRequest(
                        bucket=upload_session.bucket_name,
                        object_key=upload_session.object_key,
                        upload_id=upload_session.storage_upload_id,
                    )
                )
            except StorageNotFoundError:
                pass
            except StorageError as exc:
                self._mark_session_cleanup_failed(upload_session.id, exc, now=now)
                return False

        refreshed_session = self._session.get(UploadSession, upload_session.id)
        if (
            refreshed_session is None
            or refreshed_session.status == UploadSessionStatus.ABORTED.value
        ):
            return False
        refreshed_session.status = UploadSessionStatus.ABORTED.value
        refreshed_session.aborted_at = refreshed_session.aborted_at or now
        refreshed_session.updated_at = now
        refreshed_session.last_error_code = None
        refreshed_session.last_error_message = None
        self._projection.project_cleanup_transition(
            refreshed_session,
            status=UploadSessionStatus.ABORTED,
            now=now,
        )
        self._event_writer.write_cleanup_event(
            refreshed_session,
            event_type="upload.aborted",
            payload={"reason": "expired_session_cleanup"},
            now=now,
        )
        self._session.commit()
        return True

    def _mark_session_cleanup_failed(
        self, session_id: uuid.UUID, exc: StorageError, *, now: datetime
    ) -> None:
        self._session.rollback()
        upload_session = self._session.get(UploadSession, session_id)
        if upload_session is None:
            return
        upload_session.status = UploadSessionStatus.ABORTING.value
        upload_session.updated_at = now
        upload_session.last_error_code = "storage.abort_failed"
        upload_session.last_error_message = str(exc)
        self._event_writer.write_cleanup_event(
            upload_session,
            event_type="upload.cleanup_failed",
            payload={"operation": exc.operation, "provider_code": exc.provider_code},
            now=now,
        )
        self._session.commit()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
