from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

import typer
from sqlalchemy.orm import Session

from upload_control_plane.application.outbox import LoggingOutboxSink, OutboxDispatcher
from upload_control_plane.application.worker_lifecycle import (
    ObjectReference,
    WorkerLifecycleService,
)
from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.infrastructure.storage import build_s3_object_storage

app = typer.Typer(help="Upload control plane background lifecycle worker.")


@contextmanager
def _service() -> Iterator[WorkerLifecycleService]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    session: Session = session_factory()
    try:
        yield WorkerLifecycleService(
            session=session,
            storage=build_s3_object_storage(settings),
            settings=settings,
        )
    finally:
        session.close()


@app.command("run-once")
def run_once() -> None:
    """Run one lifecycle pass and exit."""

    with _service() as service:
        summary = service.run_once()
        typer.echo(json.dumps(asdict(summary), sort_keys=True))


@app.command("dispatch-outbox")
def dispatch_outbox() -> None:
    """Run one outbox dispatcher pass and exit."""

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    session: Session = session_factory()
    try:
        dispatcher = OutboxDispatcher(
            session=session,
            sink=LoggingOutboxSink(),
            settings=settings,
        )
        summary = dispatcher.dispatch_due()
        typer.echo(json.dumps(asdict(summary), sort_keys=True))
    finally:
        session.close()


@app.command("reconcile")
def reconcile(
    object_ref: Annotated[
        list[str] | None,
        typer.Option(
            "--object-ref",
            help="Optional storage object ref in bucket:object/key form for object-only detection.",
        ),
    ] = None,
) -> None:
    """Run backup/restore reconciliation without cleanup side effects."""

    refs = tuple(_parse_object_ref(value) for value in (object_ref or ()))
    with _service() as service:
        summary = service.reconcile_recovery_status(
            now=datetime.now(UTC),
            object_refs=refs,
        )
        typer.echo(json.dumps(asdict(summary), sort_keys=True))


@app.command("run")
def run() -> None:
    """Run lifecycle automation periodically."""

    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    logging.basicConfig(level=settings.log_level)
    logger = logging.getLogger(__name__)
    while True:
        with _service() as service:
            summary = service.run_once()
            logger.info("worker lifecycle pass completed", extra=asdict(summary))
        if settings.enable_outbox_dispatcher:
            session: Session = session_factory()
            try:
                dispatcher = OutboxDispatcher(
                    session=session,
                    sink=LoggingOutboxSink(),
                    settings=settings,
                )
                outbox_summary = dispatcher.dispatch_due()
                logger.info("worker outbox pass completed", extra=asdict(outbox_summary))
            finally:
                session.close()
        time.sleep(settings.worker_poll_interval_seconds)


def _parse_object_ref(value: str) -> ObjectReference:
    bucket, separator, object_key = value.partition(":")
    if not separator or not bucket or not object_key:
        raise typer.BadParameter("object ref must use bucket:object/key form")
    return ObjectReference(bucket=bucket, object_key=object_key)


if __name__ == "__main__":
    app()
