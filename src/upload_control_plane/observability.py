from __future__ import annotations

import json
import logging
import math
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
    Device,
    DeviceCredential,
    OutboxEvent,
    UploadSession,
    UploadTask,
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

    def storage_backpressure_reason(
        self,
        *,
        error_rate_threshold: float,
        p95_latency_ms: int,
    ) -> str | None:
        observations = [
            value
            for (name, _labels), values in self._histograms.items()
            if name == "storage_operation_duration_seconds"
            for value in values
        ]
        if not observations:
            return None

        error_count = sum(
            value
            for (name, _labels), value in self._counters.items()
            if name == "storage_operation_errors_total"
        )
        error_rate = error_count / len(observations)
        if error_rate_threshold > 0 and error_rate >= error_rate_threshold:
            return "storage_error_rate"

        if p95_latency_ms > 0:
            sorted_observations = sorted(observations)
            p95_index = max(math.ceil(len(sorted_observations) * 0.95) - 1, 0)
            p95_latency_seconds = sorted_observations[p95_index]
            if p95_latency_seconds * 1000 >= p95_latency_ms:
                return "storage_p95_latency"
        return None

    def reset_for_tests(self) -> None:
        self._counters.clear()
        self._histograms.clear()

    def render(self, session: Session | None = None) -> str:
        lines: list[str] = []
        _render_counter(
            lines,
            "api_requests_total",
            "Total HTTP API requests.",
            self._counters,
            {"method": "unknown", "path": "unknown", "status_code": "unknown"},
        )
        _render_histogram(
            lines,
            "api_request_duration_seconds",
            "HTTP API request duration in seconds.",
            self._histograms,
            {"method": "unknown", "path": "unknown", "status_code": "unknown"},
        )
        _render_histogram(
            lines,
            "storage_operation_duration_seconds",
            "Object storage operation duration in seconds.",
            self._histograms,
            {"operation": "unknown"},
        )
        _render_counter(
            lines,
            "storage_operation_errors_total",
            "Object storage operation errors.",
            self._counters,
            {"operation": "unknown", "error_code": "unknown"},
        )
        _render_counter(
            lines,
            "storage_backpressure_rejects_total",
            "Storage backpressure rejects.",
            self._counters,
            {"reason": "unknown"},
        )
        _render_counter(
            lines,
            "quota_rejects_total",
            "Quota rejects.",
            self._counters,
            {"tenant_id": "unknown", "scope": "unknown"},
        )
        _render_counter(
            lines,
            "rate_limit_rejects_total",
            "Rate limit rejects.",
            self._counters,
            {"tenant_id": "unknown", "scope": "unknown"},
        )
        if session is not None:
            render_operational_metrics(lines, session)
        return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()


def storage_backpressure_reason(
    *,
    error_rate_threshold: float,
    p95_latency_ms: int,
) -> str | None:
    return metrics_registry.storage_backpressure_reason(
        error_rate_threshold=error_rate_threshold,
        p95_latency_ms=p95_latency_ms,
    )


def record_storage_backpressure_reject(reason: str) -> None:
    metrics_registry.increment("storage_backpressure_rejects_total", {"reason": reason})


def render_operational_metrics(lines: list[str], session: Session) -> None:
    _render_upload_session_lifecycle_metrics(lines, session)
    _render_upload_session_status(lines, session)
    _render_upload_api_placeholder_metrics(lines)
    _render_dataset_metrics(lines, session)
    _render_upload_task_metrics(lines, session)
    _render_device_metrics(lines, session)
    _render_validation_backlog(lines, session)
    _render_recovery_metrics(lines, session)
    _render_cleanup_metrics(lines, session)
    _render_outbox_metrics(lines, session)
    _render_zero_counter(lines, "storage_replication_pending_total", {"tenant_id": "unknown"})
    _render_zero_counter(lines, "storage_replication_failed_total", {"tenant_id": "unknown"})


def _render_upload_session_lifecycle_metrics(lines: list[str], session: Session) -> None:
    session_error_code = func.coalesce(UploadSession.last_error_code, "unknown").label("error_code")
    _render_count_by_tenant(
        lines,
        session,
        "upload_sessions_created_total",
        "Upload sessions created.",
        select(UploadSession.tenant_id, func.count()).group_by(UploadSession.tenant_id),
    )
    _render_count_by_tenant(
        lines,
        session,
        "upload_sessions_completed_total",
        "Upload sessions completed.",
        select(UploadSession.tenant_id, func.count())
        .where(UploadSession.status == "COMPLETED")
        .group_by(UploadSession.tenant_id),
    )
    _render_count_by_tenant(
        lines,
        session,
        "upload_sessions_aborted_total",
        "Upload sessions aborted.",
        select(UploadSession.tenant_id, func.count())
        .where(UploadSession.status == "ABORTED")
        .group_by(UploadSession.tenant_id),
    )
    _render_count_by_tenant_and_label(
        lines,
        session,
        "upload_sessions_failed_total",
        "Upload sessions failed.",
        "error_code",
        select(UploadSession.tenant_id, session_error_code, func.count())
        .where(UploadSession.status == "FAILED")
        .group_by(UploadSession.tenant_id, session_error_code),
    )
    _render_count_by_tenant(
        lines,
        session,
        "upload_sessions_expired_total",
        "Upload sessions expired.",
        select(UploadSession.tenant_id, func.count())
        .where(UploadSession.status == "EXPIRED")
        .group_by(UploadSession.tenant_id),
    )


def _render_upload_session_status(lines: list[str], session: Session) -> None:
    _help(lines, "upload_sessions_by_status", "Current upload sessions by status.", "gauge")
    rows = session.execute(
        select(UploadSession.status, func.count())
        .group_by(UploadSession.status)
        .order_by(UploadSession.status)
    ).all()
    for status, count in rows:
        lines.append(_sample("upload_sessions_by_status", {"status": str(status)}, float(count)))
    if not rows:
        lines.append(_sample("upload_sessions_by_status", {"status": "unknown"}, 0.0))


def _render_upload_api_placeholder_metrics(lines: list[str]) -> None:
    for name in (
        "upload_presign_requests_total",
        "upload_presign_parts_total",
        "upload_part_ack_total",
        "upload_pause_requests_total",
        "upload_resume_requests_total",
        "upload_complete_requests_total",
        "upload_complete_missing_parts_total",
    ):
        _render_zero_counter(lines, name, {"tenant_id": "unknown"})


def _render_dataset_metrics(lines: list[str], session: Session) -> None:
    _render_count_by_tenant(
        lines,
        session,
        "dataset_created_total",
        "Datasets created.",
        select(Dataset.tenant_id, func.count()).group_by(Dataset.tenant_id),
    )
    _render_dataset_status_counter(lines, session, "dataset_ready_total", "READY")
    _render_count_by_tenant(
        lines,
        session,
        "dataset_validation_failed_total",
        "Datasets with failed validation.",
        select(Dataset.tenant_id, func.count())
        .where(Dataset.validation_status == "FAILED")
        .group_by(Dataset.tenant_id),
    )
    _render_dataset_status_counter(lines, session, "dataset_deleted_total", "DELETED")
    _render_dataset_status_counter(lines, session, "dataset_purged_total", "PURGED")
    _render_zero_counter(lines, "dataset_download_url_requests_total", {"tenant_id": "unknown"})
    _render_dataset_status_counter(lines, session, "dataset_quarantined_total", "QUARANTINED")
    _render_dataset_status_counter(lines, session, "dataset_rejected_total", "REJECTED")
    _render_zero_counter(lines, "dataset_legal_hold_denied_purge_total", {"tenant_id": "unknown"})


def _render_upload_task_metrics(lines: list[str], session: Session) -> None:
    task_error_code = func.coalesce(UploadTask.last_error_code, "unknown").label("error_code")
    _render_count_by_tenant(
        lines,
        session,
        "upload_tasks_created_total",
        "Upload tasks created.",
        select(UploadTask.tenant_id, func.count()).group_by(UploadTask.tenant_id),
    )
    _render_count_by_tenant(
        lines,
        session,
        "upload_tasks_completed_total",
        "Upload tasks completed.",
        select(UploadTask.tenant_id, func.count())
        .where(UploadTask.status == "COMPLETED")
        .group_by(UploadTask.tenant_id),
    )
    _render_count_by_tenant_and_label(
        lines,
        session,
        "upload_tasks_failed_total",
        "Upload tasks failed.",
        "error_code",
        select(UploadTask.tenant_id, task_error_code, func.count())
        .where(UploadTask.status == "FAILED")
        .group_by(UploadTask.tenant_id, task_error_code),
    )


def _render_device_metrics(lines: list[str], session: Session) -> None:
    now = datetime.now(UTC)
    _render_count_by_tenant(
        lines,
        session,
        "device_registered_total",
        "Devices registered.",
        select(Device.tenant_id, func.count()).group_by(Device.tenant_id),
    )

    _help(lines, "device_last_seen_age_seconds", "Device last-seen age by tenant.", "gauge")
    seen_rows = session.execute(
        select(Device.tenant_id, func.max(Device.last_seen_at))
        .where(Device.last_seen_at.is_not(None))
        .group_by(Device.tenant_id)
        .order_by(Device.tenant_id)
    ).all()
    for tenant_id, last_seen_at in seen_rows:
        if last_seen_at.tzinfo is None or last_seen_at.utcoffset() is None:
            last_seen_at = last_seen_at.replace(tzinfo=UTC)
        lines.append(
            _sample(
                "device_last_seen_age_seconds",
                {"tenant_id": str(tenant_id)},
                max((now - last_seen_at).total_seconds(), 0.0),
            )
        )
    if not seen_rows:
        lines.append(_sample("device_last_seen_age_seconds", {"tenant_id": "unknown"}, 0.0))

    _render_count_by_tenant(
        lines,
        session,
        "device_credential_revoked_total",
        "Device credentials revoked.",
        select(DeviceCredential.tenant_id, func.count())
        .where(DeviceCredential.revoked_at.is_not(None))
        .group_by(DeviceCredential.tenant_id),
    )
    _render_zero_counter(
        lines,
        "device_auth_failures_total",
        {"tenant_id": "unknown", "error_code": "unknown"},
    )


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


def _render_dataset_status_counter(
    lines: list[str],
    session: Session,
    name: str,
    status: str,
) -> None:
    _render_count_by_tenant(
        lines,
        session,
        name,
        f"Datasets with {status.lower()} status.",
        select(Dataset.tenant_id, func.count())
        .where(Dataset.status == status)
        .group_by(Dataset.tenant_id),
    )


def _render_count_by_tenant(
    lines: list[str],
    session: Session,
    name: str,
    description: str,
    statement: Select[tuple[Any, int]],
) -> None:
    _help(lines, name, description, "counter")
    rows = session.execute(statement.order_by(statement.selected_columns[0])).all()
    for tenant_id, count in rows:
        lines.append(_sample(name, {"tenant_id": str(tenant_id)}, float(count)))
    if not rows:
        lines.append(_sample(name, {"tenant_id": "unknown"}, 0.0))


def _render_count_by_tenant_and_label(
    lines: list[str],
    session: Session,
    name: str,
    description: str,
    label_name: str,
    statement: Select[tuple[Any, str, int]],
) -> None:
    _help(lines, name, description, "counter")
    rows = session.execute(
        statement.order_by(statement.selected_columns[0], statement.selected_columns[1])
    ).all()
    for tenant_id, label_value, count in rows:
        lines.append(
            _sample(
                name,
                {"tenant_id": str(tenant_id), label_name: str(label_value)},
                float(count),
            )
        )
    if not rows:
        lines.append(_sample(name, {"tenant_id": "unknown", label_name: "unknown"}, 0.0))


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
    if not pending_rows:
        lines.append(_sample("outbox_events_pending", {"tenant_id": "unknown"}, 0.0))

    _render_outbox_status_counter(
        lines,
        session,
        "outbox_events_delivered_total",
        "Outbox events delivered.",
        "DELIVERED",
    )
    _render_outbox_status_counter(
        lines,
        session,
        "outbox_events_failed_total",
        "Outbox events failed.",
        "FAILED",
    )

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
    if not dead_rows:
        lines.append(
            _sample(
                "outbox_events_dead_lettered",
                {"tenant_id": "unknown", "event_type": "unknown"},
                0.0,
            )
        )


def _render_outbox_status_counter(
    lines: list[str],
    session: Session,
    name: str,
    description: str,
    status: str,
) -> None:
    _render_count_by_tenant_and_label(
        lines,
        session,
        name,
        description,
        "event_type",
        select(OutboxEvent.tenant_id, OutboxEvent.event_type, func.count())
        .where(OutboxEvent.status == status)
        .group_by(OutboxEvent.tenant_id, OutboxEvent.event_type),
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
    default_labels: Mapping[str, str] | None = None,
) -> None:
    _help(lines, name, description, "counter")
    found = False
    for (metric_name, labels), value in sorted(counters.items()):
        if metric_name == name:
            found = True
            lines.append(_sample(name, dict(labels), value))
    if not found:
        lines.append(_sample(name, default_labels or {}, 0.0))


def _render_histogram(
    lines: list[str],
    name: str,
    description: str,
    histograms: Mapping[tuple[str, tuple[tuple[str, str], ...]], list[float]],
    default_labels: Mapping[str, str] | None = None,
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
        default_label_dict = dict(default_labels or {})
        for bucket in _LATENCY_BUCKETS:
            lines.append(_sample(f"{name}_bucket", {**default_label_dict, "le": str(bucket)}, 0.0))
        lines.append(_sample(f"{name}_bucket", {**default_label_dict, "le": "+Inf"}, 0.0))
        lines.append(_sample(f"{name}_count", default_label_dict, 0.0))
        lines.append(_sample(f"{name}_sum", default_label_dict, 0.0))


def _render_zero_counter(lines: list[str], name: str, labels: Mapping[str, str]) -> None:
    _help(lines, name, "Not yet instrumented in local implementation.", "counter")
    lines.append(_sample(name, labels, 0.0))


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
