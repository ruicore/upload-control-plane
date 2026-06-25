from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from upload_control_plane.infrastructure.db.models import (
    Dataset,
    OutboxEvent,
    UploadSession,
)

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_REQUEST_CONTEXT_KEYS = ("project_id", "dataset_id", "session_id")
_SENSITIVE_KEYS = {
    "access_key",
    "accesskey",
    "api_key",
    "authorization",
    "credential",
    "password",
    "presigned_url",
    "private_key",
    "secret",
    "secret_key",
    "signed_url",
    "token",
    "upload_url",
    "url",
    "x-amz-credential",
    "x-amz-signature",
}


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for key in (
            "request_id",
            "trace_id",
            "tenant_id",
            "project_id",
            "task_id",
            "object_id",
            "dataset_id",
            "session_id",
            "actor_id",
            "operation",
            "path",
            "method",
            "status",
            "status_code",
            "latency_ms",
            "error_code",
            "storage_operation",
        ):
            if hasattr(record, key):
                payload[key] = sanitize_for_observability(getattr(record, key))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def configure_logging(*, level: str, app_env: str) -> None:
    logger = logging.getLogger("upload_control_plane")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter: logging.Formatter
    if app_env == "local":
        formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
    else:
        formatter = JsonLogFormatter()
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    for handler in logger.handlers:
        handler.setFormatter(formatter)


def monotonic_time() -> float:
    return time.perf_counter()


def milliseconds_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def redact_url_query(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.query:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", parsed.fragment))
    return value


def sanitize_for_observability(value: Any) -> Any:
    if isinstance(value, str):
        return redact_url_query(value)
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                sanitized[key_text] = _redacted_sensitive_value(item)
            else:
                sanitized[key_text] = sanitize_for_observability(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_observability(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_observability(item) for item in value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or any(part in normalized for part in _SENSITIVE_KEYS)


def _redacted_sensitive_value(value: Any) -> str:
    if isinstance(value, str) and ("://" in value):
        return redact_url_query(value)
    return "[REDACTED]"


def route_context(path_params: Mapping[str, Any]) -> dict[str, str]:
    context: dict[str, str] = {}
    for key in _REQUEST_CONTEXT_KEYS:
        value = path_params.get(key)
        if value is not None:
            context[key] = str(value)
    return context


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._histograms: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            list[float],
        ] = defaultdict(list)

    def increment(
        self, name: str, labels: Mapping[str, str] | None = None, amount: float = 1
    ) -> None:
        self._counters[(name, _label_key(labels))] += amount

    def observe(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self._histograms[(name, _label_key(labels))].append(value)

    def render(self, session: Session | None = None) -> str:
        lines: list[str] = []
        _render_counter(
            lines,
            "api_requests_total",
            "Total HTTP API requests.",
            self._counters,
        )
        _render_histogram(
            lines,
            "api_request_duration_seconds",
            "HTTP API request duration in seconds.",
            self._histograms,
        )
        _render_histogram(
            lines,
            "storage_operation_duration_seconds",
            "Object storage operation duration in seconds.",
            self._histograms,
        )
        _render_counter(
            lines,
            "storage_operation_errors_total",
            "Object storage operation errors.",
            self._counters,
        )
        _render_counter(
            lines,
            "storage_backpressure_rejects_total",
            "Storage backpressure rejects.",
            self._counters,
        )
        _render_counter(lines, "quota_rejects_total", "Quota rejects.", self._counters)
        _render_counter(lines, "rate_limit_rejects_total", "Rate limit rejects.", self._counters)
        if session is not None:
            render_operational_metrics(lines, session)
        return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()


def render_operational_metrics(lines: list[str], session: Session) -> None:
    _render_upload_session_status(lines, session)
    _render_validation_backlog(lines, session)
    _render_recovery_metrics(lines, session)
    _render_cleanup_metrics(lines, session)
    _render_outbox_metrics(lines, session)
    _render_zero_gauge(lines, "storage_replication_pending_total", {"tenant_id": "unknown"})
    _render_zero_gauge(lines, "storage_replication_failed_total", {"tenant_id": "unknown"})


def _render_upload_session_status(lines: list[str], session: Session) -> None:
    _help(lines, "upload_sessions_by_status", "Current upload sessions by status.", "gauge")
    rows = session.execute(
        select(UploadSession.status, func.count())
        .group_by(UploadSession.status)
        .order_by(UploadSession.status)
    ).all()
    for status, count in rows:
        lines.append(_sample("upload_sessions_by_status", {"status": str(status)}, float(count)))


def _render_validation_backlog(lines: list[str], session: Session) -> None:
    now = datetime.now(UTC)
    backlog_statuses = ("PENDING", "RUNNING")
    depth = session.scalar(
        select(func.count())
        .select_from(Dataset)
        .where(Dataset.validation_status.in_(backlog_statuses))
    )
    _help(lines, "validation_queue_depth", "Validation backlog queue depth.", "gauge")
    lines.append(_sample("validation_queue_depth", {}, float(depth or 0)))

    oldest = session.scalar(
        select(func.min(Dataset.updated_at)).where(Dataset.validation_status.in_(backlog_statuses))
    )
    age = 0.0
    if oldest is not None:
        if oldest.tzinfo is None or oldest.utcoffset() is None:
            oldest = oldest.replace(tzinfo=UTC)
        age = max((now - oldest).total_seconds(), 0.0)
    _help(
        lines,
        "validation_queue_oldest_age_seconds",
        "Age of the oldest validation backlog item.",
        "gauge",
    )
    lines.append(_sample("validation_queue_oldest_age_seconds", {}, age))


def _render_recovery_metrics(lines: list[str], session: Session) -> None:
    _help(lines, "recovery_datasets_by_status", "Datasets by non-normal recovery status.", "gauge")
    rows = session.execute(
        select(Dataset.recovery_status, func.count())
        .where(Dataset.recovery_status != "NORMAL")
        .group_by(Dataset.recovery_status)
        .order_by(Dataset.recovery_status)
    ).all()
    for status, count in rows:
        lines.append(_sample("recovery_datasets_by_status", {"status": str(status)}, float(count)))


def _render_cleanup_metrics(lines: list[str], session: Session) -> None:
    now = datetime.now(UTC)
    expired_count = session.scalar(
        select(func.count())
        .select_from(UploadSession)
        .where(
            UploadSession.status.in_(("INITIATED", "UPLOADING", "PAUSED", "EXPIRED", "ABORTING"))
        )
        .where(UploadSession.expires_at < now)
    )
    _help(lines, "cleanup_expired_sessions_backlog", "Expired sessions awaiting cleanup.", "gauge")
    lines.append(_sample("cleanup_expired_sessions_backlog", {}, float(expired_count or 0)))
    _render_counter(lines, "cleanup_sessions_scanned_total", "Cleanup sessions scanned.", {})
    _render_counter(lines, "cleanup_sessions_aborted_total", "Cleanup sessions aborted.", {})
    _render_counter(lines, "cleanup_errors_total", "Cleanup errors.", {})


def _render_outbox_metrics(lines: list[str], session: Session) -> None:
    _help(lines, "outbox_events_pending", "Current outbox events not delivered.", "gauge")
    pending_rows = session.execute(
        select(OutboxEvent.tenant_id, func.count())
        .where(OutboxEvent.status.in_(("PENDING", "PROCESSING", "FAILED", "DEAD_LETTERED")))
        .group_by(OutboxEvent.tenant_id)
        .order_by(OutboxEvent.tenant_id)
    ).all()
    for tenant_id, count in pending_rows:
        lines.append(_sample("outbox_events_pending", {"tenant_id": str(tenant_id)}, float(count)))

    _help(lines, "outbox_events_dead_lettered", "Current dead-lettered outbox events.", "gauge")
    dead_rows = session.execute(
        select(OutboxEvent.tenant_id, OutboxEvent.event_type, func.count())
        .where(OutboxEvent.status == "DEAD_LETTERED")
        .group_by(OutboxEvent.tenant_id, OutboxEvent.event_type)
        .order_by(OutboxEvent.tenant_id, OutboxEvent.event_type)
    ).all()
    for tenant_id, event_type, count in dead_rows:
        lines.append(
            _sample(
                "outbox_events_dead_lettered",
                {"tenant_id": str(tenant_id), "event_type": str(event_type)},
                float(count),
            )
        )


def storage_operation_started() -> float:
    return monotonic_time()


def record_storage_operation(
    operation: str, started_at: float, error_code: str | None = None
) -> None:
    metrics_registry.observe(
        "storage_operation_duration_seconds",
        (time.perf_counter() - started_at),
        {"operation": operation},
    )
    if error_code is not None:
        metrics_registry.increment(
            "storage_operation_errors_total",
            {"operation": operation, "error_code": error_code},
        )


def render_select_count(
    session: Session,
    statement: Select[tuple[Any]],
) -> int:
    return int(session.scalar(statement) or 0)


def _label_key(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, value) for key, value in (labels or {}).items()))


def _render_counter(
    lines: list[str],
    name: str,
    description: str,
    counters: Mapping[tuple[str, tuple[tuple[str, str], ...]], float],
) -> None:
    _help(lines, name, description, "counter")
    found = False
    for (metric_name, labels), value in sorted(counters.items()):
        if metric_name == name:
            found = True
            lines.append(_sample(name, dict(labels), value))
    if not found:
        lines.append(_sample(name, {}, 0.0))


def _render_histogram(
    lines: list[str],
    name: str,
    description: str,
    histograms: Mapping[tuple[str, tuple[tuple[str, str], ...]], list[float]],
) -> None:
    _help(lines, name, description, "histogram")
    found = False
    for (metric_name, labels), observations in sorted(histograms.items()):
        if metric_name != name:
            continue
        found = True
        label_dict = dict(labels)
        for bucket in _LATENCY_BUCKETS:
            count = sum(1 for value in observations if value <= bucket)
            lines.append(_sample(f"{name}_bucket", {**label_dict, "le": str(bucket)}, float(count)))
        lines.append(
            _sample(f"{name}_bucket", {**label_dict, "le": "+Inf"}, float(len(observations)))
        )
        lines.append(_sample(f"{name}_count", label_dict, float(len(observations))))
        lines.append(_sample(f"{name}_sum", label_dict, float(sum(observations))))
    if not found:
        for bucket in _LATENCY_BUCKETS:
            lines.append(_sample(f"{name}_bucket", {"le": str(bucket)}, 0.0))
        lines.append(_sample(f"{name}_bucket", {"le": "+Inf"}, 0.0))
        lines.append(_sample(f"{name}_count", {}, 0.0))
        lines.append(_sample(f"{name}_sum", {}, 0.0))


def _render_zero_gauge(lines: list[str], name: str, labels: Mapping[str, str]) -> None:
    _help(lines, name, "Not yet provider-backed in local implementation.", "gauge")
    lines.append(_sample(name, labels, 0.0))


def _help(lines: list[str], name: str, description: str, metric_type: str) -> None:
    lines.append(f"# HELP {name} {description}")
    lines.append(f"# TYPE {name} {metric_type}")


def _sample(name: str, labels: Mapping[str, str], value: float) -> str:
    label_text = ""
    if labels:
        label_text = (
            "{" + ",".join(f'{key}="{_escape_label(value)}"' for key, value in labels.items()) + "}"
        )
    return f"{name}{label_text} {_format_value(value)}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_value(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")
