from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.config import Settings
from upload_control_plane.infrastructure.db.models import OutboxEvent

LOGGER = logging.getLogger(__name__)

PENDING_OUTBOX_STATUSES = ("PENDING", "FAILED")
FORBIDDEN_PAYLOAD_KEY_PARTS = (
    "access_key",
    "secret_key",
    "credential",
    "credentials",
    "password",
    "private_key",
    "presigned_url",
    "signed_url",
    "upload_url",
    "download_url",
)


class OutboxPayloadError(ValueError):
    """Raised when an outbox payload would persist data-plane or credential material."""


class OutboxSink(Protocol):
    def deliver(self, event: OutboxEvent) -> None:
        """Deliver one outbox event or raise to schedule a retry."""


class LoggingOutboxSink:
    def deliver(self, event: OutboxEvent) -> None:
        LOGGER.info(
            "outbox event delivered to logging sink",
            extra={
                "outbox_event_id": str(event.id),
                "tenant_id": str(event.tenant_id),
                "event_type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
            },
        )


@dataclass(frozen=True, slots=True)
class OutboxAppend:
    tenant_id: uuid.UUID
    aggregate_type: str
    aggregate_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    event_id: uuid.UUID | None = None
    next_attempt_at: datetime | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OutboxDispatchSummary:
    claimed: int = 0
    delivered: int = 0
    failed: int = 0
    dead_lettered: int = 0


def append_outbox_event(session: Session, event: OutboxAppend) -> OutboxEvent:
    """Append an outbox event to the caller's current SQLAlchemy transaction."""

    _validate_outbox_payload(event.payload)
    now = event.created_at or datetime.now(UTC)
    outbox_event = OutboxEvent(
        id=event.event_id or uuid.uuid4(),
        tenant_id=event.tenant_id,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        event_type=event.event_type,
        payload=event.payload,
        status="PENDING",
        attempts=0,
        next_attempt_at=event.next_attempt_at or now,
        locked_until=None,
        last_error=None,
        created_at=now,
        delivered_at=None,
    )
    session.add(outbox_event)
    return outbox_event


class OutboxDispatcher:
    def __init__(self, *, session: Session, sink: OutboxSink, settings: Settings) -> None:
        self._session = session
        self._sink = sink
        self._settings = settings

    def dispatch_due(self, *, now: datetime | None = None) -> OutboxDispatchSummary:
        if not self._settings.enable_outbox_dispatcher:
            return OutboxDispatchSummary()

        run_at = now or datetime.now(UTC)
        events = self._claim_due_events(now=run_at)
        delivered = failed = dead_lettered = 0
        for event_id in events:
            event = self._session.get(OutboxEvent, event_id)
            if event is None or event.status != "PROCESSING":
                continue
            try:
                self._sink.deliver(event)
            except Exception as exc:
                if self._mark_failed_or_dead_lettered(event, exc, now=run_at):
                    dead_lettered += 1
                else:
                    failed += 1
            else:
                event.status = "DELIVERED"
                event.attempts += 1
                event.delivered_at = run_at
                event.locked_until = None
                event.last_error = None
                event.next_attempt_at = run_at
                delivered += 1
            self._session.commit()
        return OutboxDispatchSummary(
            claimed=len(events),
            delivered=delivered,
            failed=failed,
            dead_lettered=dead_lettered,
        )

    def _claim_due_events(self, *, now: datetime) -> tuple[uuid.UUID, ...]:
        limit = self._settings.outbox_batch_size
        events = list(
            self._session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.status.in_(PENDING_OUTBOX_STATUSES))
                .where(OutboxEvent.next_attempt_at <= now)
                .order_by(OutboxEvent.next_attempt_at.asc(), OutboxEvent.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        event_ids: list[uuid.UUID] = []
        locked_until = now + timedelta(minutes=5)
        for event in events:
            event.status = "PROCESSING"
            event.locked_until = locked_until
            event.last_error = None
            event_ids.append(event.id)
        self._session.commit()
        return tuple(event_ids)

    def _mark_failed_or_dead_lettered(
        self,
        event: OutboxEvent,
        exc: Exception,
        *,
        now: datetime,
    ) -> bool:
        event.attempts += 1
        event.locked_until = None
        event.last_error = _truncate_error(str(exc))
        if event.attempts >= self._settings.outbox_max_attempts:
            event.status = "DEAD_LETTERED"
            event.next_attempt_at = now
            return True

        event.status = "FAILED"
        event.next_attempt_at = now + _retry_delay(event.attempts)
        return False


def _retry_delay(attempts: int) -> timedelta:
    seconds = min(300, 2 ** max(0, attempts - 1))
    return timedelta(seconds=seconds)


def _truncate_error(message: str) -> str:
    return message[:1000]


def _validate_outbox_payload(payload: Any, *, path: str = "payload") -> None:
    if isinstance(payload, bytes | bytearray | memoryview):
        raise OutboxPayloadError(f"{path} must not contain file bytes")
    if isinstance(payload, dict):
        for key, value in payload.items():
            lower_key = str(key).lower()
            if any(part in lower_key for part in FORBIDDEN_PAYLOAD_KEY_PARTS):
                raise OutboxPayloadError(f"{path}.{key} must not contain credentials or URLs")
            _validate_outbox_payload(value, path=f"{path}.{key}")
        return
    if isinstance(payload, list | tuple):
        for index, value in enumerate(payload):
            _validate_outbox_payload(value, path=f"{path}[{index}]")
        return
    if isinstance(payload, str) and _looks_like_presigned_url(payload):
        raise OutboxPayloadError(f"{path} must not contain presigned URL material")


def _looks_like_presigned_url(value: str) -> bool:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.query:
        return False
    query = parsed.query.lower()
    return (
        "x-amz-signature" in query
        or "x-amz-credential" in query
        or "signature=" in query
        or "expires=" in query
    )
