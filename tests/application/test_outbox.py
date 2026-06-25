from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.application.outbox import (
    OutboxAppend,
    OutboxDispatcher,
    OutboxPayloadError,
    append_outbox_event,
)
from upload_control_plane.config import Settings, get_settings
from upload_control_plane.infrastructure.db.models import Dataset, OutboxEvent
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory


def test_domain_write_and_outbox_append_commit_atomically() -> None:
    session_factory = _db_session_factory_or_skip()
    dataset_id = dev_seed_uuid("test-outbox:atomic")
    event_id = dev_seed_uuid("test-outbox-event:atomic")

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_outbox_artifacts(session)

    try:
        with (
            pytest.raises(RuntimeError, match="force rollback"),
            _session_scope(session_factory) as session,
        ):
            _insert_dataset(session, dataset_id=dataset_id, name="t11-outbox-atomic")
            append_outbox_event(
                session,
                _append(
                    event_id=event_id,
                    aggregate_id=dataset_id,
                    event_type="t11.outbox.atomic",
                ),
            )
            raise RuntimeError("force rollback")

        with _session_scope(session_factory) as session:
            assert session.get(Dataset, dataset_id) is None
            assert session.get(OutboxEvent, event_id) is None

        with _session_scope(session_factory) as session:
            _insert_dataset(session, dataset_id=dataset_id, name="t11-outbox-atomic")
            append_outbox_event(
                session,
                _append(
                    event_id=event_id,
                    aggregate_id=dataset_id,
                    event_type="t11.outbox.atomic",
                ),
            )

        with _session_scope(session_factory) as session:
            assert session.get(Dataset, dataset_id) is not None
            assert session.get(OutboxEvent, event_id) is not None
    finally:
        with _session_scope(session_factory) as session:
            _delete_outbox_artifacts(session)


def test_successful_delivery_and_repeated_runs_are_idempotent() -> None:
    session_factory = _db_session_factory_or_skip()
    event_id = dev_seed_uuid("test-outbox-event:success")
    now = datetime.now(UTC) + timedelta(seconds=1)
    sink = RecordingSink()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_outbox_artifacts(session)
        append_outbox_event(
            session,
            _append(event_id=event_id, aggregate_id=build_dev_seed_result().project_id),
        )

    try:
        with _session_scope(session_factory) as session:
            dispatcher = OutboxDispatcher(session=session, sink=sink, settings=_test_settings())
            summary = dispatcher.dispatch_due(now=now)
            assert (summary.claimed, summary.delivered, summary.failed, summary.dead_lettered) == (
                1,
                1,
                0,
                0,
            )
            event = session.get(OutboxEvent, event_id)
            assert event is not None
            assert event.status == "DELIVERED"
            assert event.attempts == 1
            assert event.delivered_at == now

        with _session_scope(session_factory) as session:
            dispatcher = OutboxDispatcher(session=session, sink=sink, settings=_test_settings())
            summary = dispatcher.dispatch_due(now=now + timedelta(seconds=1))
            assert (summary.claimed, summary.delivered) == (0, 0)
        assert sink.delivered == [event_id]
    finally:
        with _session_scope(session_factory) as session:
            _delete_outbox_artifacts(session)


def test_retry_scheduling_after_transient_delivery_failure() -> None:
    session_factory = _db_session_factory_or_skip()
    event_id = dev_seed_uuid("test-outbox-event:retry")
    now = datetime.now(UTC) + timedelta(seconds=1)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_outbox_artifacts(session)
        append_outbox_event(
            session,
            _append(event_id=event_id, aggregate_id=build_dev_seed_result().project_id),
        )

    try:
        with _session_scope(session_factory) as session:
            dispatcher = OutboxDispatcher(
                session=session,
                sink=FailingSink("temporary broker outage"),
                settings=_test_settings(outbox_max_attempts=3),
            )
            summary = dispatcher.dispatch_due(now=now)
            event = session.get(OutboxEvent, event_id)
            assert event is not None
            assert (summary.claimed, summary.failed, summary.dead_lettered) == (1, 1, 0)
            assert event.status == "FAILED"
            assert event.attempts == 1
            assert event.next_attempt_at == now + timedelta(seconds=1)
            assert event.last_error == "temporary broker outage"

        with _session_scope(session_factory) as session:
            dispatcher = OutboxDispatcher(
                session=session,
                sink=RecordingSink(),
                settings=_test_settings(outbox_max_attempts=3),
            )
            summary = dispatcher.dispatch_due(now=now + timedelta(milliseconds=500))
            assert summary.claimed == 0
    finally:
        with _session_scope(session_factory) as session:
            _delete_outbox_artifacts(session)


def test_dead_letter_after_max_attempts() -> None:
    session_factory = _db_session_factory_or_skip()
    event_id = dev_seed_uuid("test-outbox-event:dead-letter")
    now = datetime.now(UTC) + timedelta(seconds=1)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_outbox_artifacts(session)
        append_outbox_event(
            session,
            _append(event_id=event_id, aggregate_id=build_dev_seed_result().project_id),
        )

    try:
        settings = _test_settings(outbox_max_attempts=2)
        with _session_scope(session_factory) as session:
            dispatcher = OutboxDispatcher(
                session=session,
                sink=FailingSink("down"),
                settings=settings,
            )
            assert dispatcher.dispatch_due(now=now).failed == 1

        with _session_scope(session_factory) as session:
            event = session.get(OutboxEvent, event_id)
            assert event is not None
            event.next_attempt_at = now

        with _session_scope(session_factory) as session:
            dispatcher = OutboxDispatcher(
                session=session,
                sink=FailingSink("down"),
                settings=settings,
            )
            summary = dispatcher.dispatch_due(now=now)
            event = session.get(OutboxEvent, event_id)
            assert event is not None
            assert (summary.claimed, summary.dead_lettered) == (1, 1)
            assert event.status == "DEAD_LETTERED"
            assert event.attempts == 2
    finally:
        with _session_scope(session_factory) as session:
            _delete_outbox_artifacts(session)


def test_delivery_failure_does_not_roll_back_committed_domain_state() -> None:
    session_factory = _db_session_factory_or_skip()
    dataset_id = dev_seed_uuid("test-outbox:domain-survives")
    event_id = dev_seed_uuid("test-outbox-event:domain-survives")
    now = datetime.now(UTC) + timedelta(seconds=1)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_outbox_artifacts(session)
        _insert_dataset(session, dataset_id=dataset_id, name="t11-outbox-domain-survives")
        append_outbox_event(
            session,
            _append(event_id=event_id, aggregate_id=dataset_id, event_type="t11.outbox.domain"),
        )

    try:
        with _session_scope(session_factory) as session:
            dispatcher = OutboxDispatcher(
                session=session,
                sink=FailingSink("delivery failed"),
                settings=_test_settings(outbox_max_attempts=3),
            )
            summary = dispatcher.dispatch_due(now=now)
            dataset = session.get(Dataset, dataset_id)
            event = session.get(OutboxEvent, event_id)
            assert summary.failed == 1
            assert dataset is not None
            assert dataset.status == "READY"
            assert event is not None
            assert event.status == "FAILED"
    finally:
        with _session_scope(session_factory) as session:
            _delete_outbox_artifacts(session)


def test_outbox_payload_rejects_presigned_urls_credentials_and_bytes() -> None:
    session_factory = _db_session_factory_or_skip()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        payloads: tuple[dict[str, object], ...] = (
            {"url": "http://localhost:9000/bucket/key?X-Amz-Signature=abc"},
            {"s3_secret_key": "secret"},
            {"file": b"bytes"},
        )
        for payload in payloads:
            with pytest.raises(OutboxPayloadError):
                append_outbox_event(
                    session,
                    _append(
                        event_id=uuid.uuid4(),
                        aggregate_id=build_dev_seed_result().project_id,
                        payload=payload,
                    ),
                )


class RecordingSink:
    def __init__(self) -> None:
        self.delivered: list[uuid.UUID] = []

    def deliver(self, event: OutboxEvent) -> None:
        self.delivered.append(event.id)


class FailingSink:
    def __init__(self, message: str) -> None:
        self._message = message

    def deliver(self, _event: OutboxEvent) -> None:
        raise RuntimeError(self._message)


def _append(
    *,
    event_id: uuid.UUID,
    aggregate_id: uuid.UUID,
    event_type: str = "t11.outbox.test",
    payload: dict[str, object] | None = None,
) -> OutboxAppend:
    seed = build_dev_seed_result()
    return OutboxAppend(
        event_id=event_id,
        tenant_id=seed.tenant_id,
        aggregate_type="dataset",
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload or {"dataset_id": str(aggregate_id), "status": "READY"},
    )


def _insert_dataset(session: Session, *, dataset_id: uuid.UUID, name: str) -> None:
    seed = build_dev_seed_result()
    now = datetime.now(UTC)
    session.add(
        Dataset(
            id=dataset_id,
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            name=name,
            status="READY",
            original_filename=f"{name}.bin",
            content_type="application/octet-stream",
            file_size_bytes=1,
            bucket_name="robot-data",
            object_key=f"t11-outbox/{name}.bin",
            object_size_bytes=1,
            validation_status="PASSED",
            recovery_status="NORMAL",
            created_at=now,
            updated_at=now,
            ready_at=now,
        )
    )


def _test_settings(**overrides: object) -> Settings:
    return get_settings().model_copy(
        update={
            "enable_outbox_dispatcher": True,
            "outbox_batch_size": 100,
            "outbox_max_attempts": 3,
            **overrides,
        }
    )


def _db_session_factory_or_skip() -> sessionmaker[Session]:
    settings = get_settings()
    url = make_url(settings.database_url)
    host = url.host or "localhost"
    port = url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1):
            pass
    except OSError as exc:
        pytest.skip(f"PostgreSQL integration database is not reachable at {host}:{port}: {exc}")

    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
    except (OperationalError, ProgrammingError) as exc:
        pytest.skip(f"PostgreSQL integration database is not available or migrated: {exc}")
    return build_session_factory(engine)


@contextmanager
def _session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _delete_outbox_artifacts(session: Session) -> None:
    dataset_ids = list(session.scalars(select(Dataset.id).where(Dataset.name.like("t11-outbox-%"))))
    session.execute(delete(OutboxEvent).where(OutboxEvent.event_type.like("t11.outbox.%")))
    if dataset_ids:
        session.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
