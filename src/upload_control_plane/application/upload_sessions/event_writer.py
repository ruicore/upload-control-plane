from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.outbox import OutboxAppend, append_outbox_event
from upload_control_plane.infrastructure.db.models import UploadEvent, UploadSession


class UploadEventWriter:
    """Own upload-event persistence for interactive and cleanup paths."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def write_actor_event(
        self,
        upload_session: UploadSession,
        *,
        actor: AuthenticatedActor,
        request_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        self._session.add(
            self._event(
                upload_session,
                event_type=event_type,
                actor_type=actor.actor_type,
                actor_id=str(actor.subject_id),
                request_id=request_id,
                payload=payload,
            )
        )

    def write_cleanup_event(
        self,
        upload_session: UploadSession,
        *,
        event_type: str,
        payload: dict[str, object],
        now: datetime,
    ) -> None:
        event = self._event(
            upload_session,
            event_type=event_type,
            actor_type="system",
            actor_id="worker:lifecycle",
            request_id=None,
            payload=payload,
        )
        event.created_at = now
        self._session.add(event)
        append_outbox_event(
            self._session,
            OutboxAppend(
                tenant_id=upload_session.tenant_id,
                aggregate_type="upload_session",
                aggregate_id=upload_session.id,
                event_type=event_type,
                payload={
                    "session_id": str(upload_session.id),
                    "project_id": str(upload_session.project_id)
                    if upload_session.project_id is not None
                    else None,
                    "dataset_id": str(upload_session.dataset_id)
                    if upload_session.dataset_id is not None
                    else None,
                    "upload_task_id": str(upload_session.upload_task_id)
                    if upload_session.upload_task_id is not None
                    else None,
                    "upload_object_id": str(upload_session.upload_object_id)
                    if upload_session.upload_object_id is not None
                    else None,
                    "status": upload_session.status,
                    "event": payload,
                },
                created_at=now,
                next_attempt_at=now,
            ),
        )

    @staticmethod
    def _event(
        upload_session: UploadSession,
        *,
        event_type: str,
        actor_type: str,
        actor_id: str | None,
        request_id: str | None,
        payload: dict[str, object],
    ) -> UploadEvent:
        return UploadEvent(
            tenant_id=upload_session.tenant_id,
            project_id=upload_session.project_id,
            dataset_id=upload_session.dataset_id,
            upload_task_id=upload_session.upload_task_id,
            upload_object_id=upload_session.upload_object_id,
            session_id=upload_session.id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            request_id=request_id,
            payload=payload,
        )
