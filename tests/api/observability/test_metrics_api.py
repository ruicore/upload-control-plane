from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete

from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.infrastructure.db.models import OutboxEvent
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)

from .support import (
    _auth_headers,
    _client,
    _db_session_factory_or_skip,
    _session_scope,
    _settings_override,
)

_PRD_METRICS_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "prd"
    / "resumable-multipart-upload-control-plane"
    / "12-observability-testing-failure-modes.md"
)


def test_metrics_registry_is_one_object_across_public_import_paths() -> None:
    import upload_control_plane.api.middleware as api_middleware
    import upload_control_plane.api.observability as api_observability
    import upload_control_plane.observability as observability
    import upload_control_plane.observability.metrics as metrics_package
    import upload_control_plane.observability.metrics.registry as registry_module

    assert (
        observability.metrics_registry
        is metrics_package.metrics_registry
        is registry_module.metrics_registry
        is vars(api_middleware)["metrics_registry"]
        is vars(api_observability)["metrics_registry"]
    )


def test_metrics_returns_prometheus_text_and_expected_metric_names() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    dead_letter_id = dev_seed_uuid("test-outbox:metrics-dead-letter")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        outbox = session.get(OutboxEvent, dead_letter_id)
        if outbox is None:
            outbox = OutboxEvent(id=dead_letter_id)
            session.add(outbox)
        outbox.tenant_id = seed.tenant_id
        outbox.aggregate_type = "dataset"
        outbox.aggregate_id = seed.dataset_id
        outbox.event_type = "dataset.validation_failed"
        outbox.payload = {"dataset_id": str(seed.dataset_id)}
        outbox.status = "DEAD_LETTERED"
        outbox.attempts = 12
        outbox.next_attempt_at = datetime.now(UTC)

    try:
        response = _client(session_factory).get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        body = response.text
        assert "api_requests_total" in body
        assert "api_request_duration_seconds_bucket" in body
        assert "storage_operation_duration_seconds_bucket" in body
        assert "upload_sessions_by_status" in body
        assert "upload_sessions_created_total" in body
        assert "upload_presign_requests_total" in body
        assert "dataset_created_total" in body
        assert "upload_tasks_created_total" in body
        assert "device_registered_total" in body
        assert "validation_queue_depth" in body
        assert "cleanup_expired_sessions_backlog" in body
        assert "outbox_events_pending" in body
        assert "outbox_events_delivered_total" in body
        assert "outbox_events_dead_lettered" in body
    finally:
        with _session_scope(session_factory) as session:
            session.execute(delete(OutboxEvent).where(OutboxEvent.id == dead_letter_id))


def test_metrics_covers_complete_prd_required_metric_family_list() -> None:
    session_factory = _db_session_factory_or_skip()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    response = _client(session_factory).get("/metrics")

    assert response.status_code == 200
    rendered_families = _rendered_metric_families(response.text)
    required_families = _prd_required_metric_families()
    assert sorted(required_families - rendered_families) == []


def test_storage_backpressure_rejection_metric_renders_bounded_reason() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    settings = _settings_override(storage_backpressure_forced_reason="custom-test-reason")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, settings)

    response = _client(session_factory, settings=settings).post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers={
            **_auth_headers("req-observe-storage-backpressure"),
            "Idempotency-Key": "idem-observe-storage-backpressure",
        },
        json={
            "task_name": "observability-backpressure",
            "task_initiator": "api",
            "objects": [
                {
                    "dataset_name": "observability-backpressure",
                    "object_name": "observability-backpressure.bin",
                    "file_size_bytes": DEFAULT_PART_SIZE,
                    "part_size_bytes": DEFAULT_PART_SIZE,
                }
            ],
        },
    )
    assert response.status_code == 503

    metrics = _client(session_factory).get("/metrics")

    assert metrics.status_code == 200
    assert 'storage_backpressure_rejects_total{reason="manual"}' in metrics.text


def _prd_required_metric_families() -> set[str]:
    prd = _PRD_METRICS_PATH.read_text(encoding="utf-8")
    block = prd.split("Required metrics:", maxsplit=1)[1].split("```", maxsplit=2)[1]
    return {
        metric.split("{", maxsplit=1)[0]
        for metric in block.splitlines()
        if metric and not metric.isspace() and metric != "text"
    }


def _rendered_metric_families(body: str) -> set[str]:
    import re

    families: set[str] = set()
    for line in body.splitlines():
        match = re.match(r"# TYPE (?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*) ", line)
        if match:
            families.add(match.group("name"))
    return families
