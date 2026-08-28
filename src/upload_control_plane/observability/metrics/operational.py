from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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

from .formatting import (
    render_counter,
    render_help,
    render_sample,
    render_zero_counter,
)


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
    render_zero_counter(lines, "storage_replication_pending_total", {"tenant_id": "unknown"})
    render_zero_counter(lines, "storage_replication_failed_total", {"tenant_id": "unknown"})


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
    render_help(lines, "upload_sessions_by_status", "Current upload sessions by status.", "gauge")
    rows = session.execute(
        select(UploadSession.status, func.count())
        .group_by(UploadSession.status)
        .order_by(UploadSession.status)
    ).all()
    for status, count in rows:
        lines.append(
            render_sample("upload_sessions_by_status", {"status": str(status)}, float(count))
        )
    if not rows:
        lines.append(render_sample("upload_sessions_by_status", {"status": "unknown"}, 0.0))


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
        render_zero_counter(lines, name, {"tenant_id": "unknown"})


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
    render_zero_counter(lines, "dataset_download_url_requests_total", {"tenant_id": "unknown"})
    _render_dataset_status_counter(lines, session, "dataset_quarantined_total", "QUARANTINED")
    _render_dataset_status_counter(lines, session, "dataset_rejected_total", "REJECTED")
    render_zero_counter(lines, "dataset_legal_hold_denied_purge_total", {"tenant_id": "unknown"})


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

    render_help(lines, "device_last_seen_age_seconds", "Device last-seen age by tenant.", "gauge")
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
            render_sample(
                "device_last_seen_age_seconds",
                {"tenant_id": str(tenant_id)},
                max((now - last_seen_at).total_seconds(), 0.0),
            )
        )
    if not seen_rows:
        lines.append(render_sample("device_last_seen_age_seconds", {"tenant_id": "unknown"}, 0.0))

    _render_count_by_tenant(
        lines,
        session,
        "device_credential_revoked_total",
        "Device credentials revoked.",
        select(DeviceCredential.tenant_id, func.count())
        .where(DeviceCredential.revoked_at.is_not(None))
        .group_by(DeviceCredential.tenant_id),
    )
    render_zero_counter(
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
    render_help(lines, "validation_queue_depth", "Validation backlog queue depth.", "gauge")
    lines.append(render_sample("validation_queue_depth", {}, float(depth or 0)))

    oldest = session.scalar(
        select(func.min(Dataset.updated_at)).where(Dataset.validation_status.in_(backlog_statuses))
    )
    age = 0.0
    if oldest is not None:
        if oldest.tzinfo is None or oldest.utcoffset() is None:
            oldest = oldest.replace(tzinfo=UTC)
        age = max((now - oldest).total_seconds(), 0.0)
    render_help(
        lines,
        "validation_queue_oldest_age_seconds",
        "Age of the oldest validation backlog item.",
        "gauge",
    )
    lines.append(render_sample("validation_queue_oldest_age_seconds", {}, age))


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
    render_help(lines, name, description, "counter")
    rows = session.execute(statement.order_by(statement.selected_columns[0])).all()
    for tenant_id, count in rows:
        lines.append(render_sample(name, {"tenant_id": str(tenant_id)}, float(count)))
    if not rows:
        lines.append(render_sample(name, {"tenant_id": "unknown"}, 0.0))


def _render_count_by_tenant_and_label(
    lines: list[str],
    session: Session,
    name: str,
    description: str,
    label_name: str,
    statement: Select[tuple[Any, str, int]],
) -> None:
    render_help(lines, name, description, "counter")
    rows = session.execute(
        statement.order_by(statement.selected_columns[0], statement.selected_columns[1])
    ).all()
    for tenant_id, label_value, count in rows:
        lines.append(
            render_sample(
                name,
                {"tenant_id": str(tenant_id), label_name: str(label_value)},
                float(count),
            )
        )
    if not rows:
        lines.append(render_sample(name, {"tenant_id": "unknown", label_name: "unknown"}, 0.0))


def _render_recovery_metrics(lines: list[str], session: Session) -> None:
    render_help(
        lines,
        "recovery_datasets_by_status",
        "Datasets by non-normal recovery status.",
        "gauge",
    )
    rows = session.execute(
        select(Dataset.recovery_status, func.count())
        .where(Dataset.recovery_status != "NORMAL")
        .group_by(Dataset.recovery_status)
        .order_by(Dataset.recovery_status)
    ).all()
    for status, count in rows:
        lines.append(
            render_sample("recovery_datasets_by_status", {"status": str(status)}, float(count))
        )


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
    render_help(
        lines,
        "cleanup_expired_sessions_backlog",
        "Expired sessions awaiting cleanup.",
        "gauge",
    )
    lines.append(render_sample("cleanup_expired_sessions_backlog", {}, float(expired_count or 0)))
    render_counter(lines, "cleanup_sessions_scanned_total", "Cleanup sessions scanned.", {})
    render_counter(lines, "cleanup_sessions_aborted_total", "Cleanup sessions aborted.", {})
    render_counter(lines, "cleanup_errors_total", "Cleanup errors.", {})


def _render_outbox_metrics(lines: list[str], session: Session) -> None:
    render_help(lines, "outbox_events_pending", "Current outbox events not delivered.", "gauge")
    pending_rows = session.execute(
        select(OutboxEvent.tenant_id, func.count())
        .where(OutboxEvent.status.in_(("PENDING", "PROCESSING", "FAILED", "DEAD_LETTERED")))
        .group_by(OutboxEvent.tenant_id)
        .order_by(OutboxEvent.tenant_id)
    ).all()
    for tenant_id, count in pending_rows:
        lines.append(
            render_sample("outbox_events_pending", {"tenant_id": str(tenant_id)}, float(count))
        )
    if not pending_rows:
        lines.append(render_sample("outbox_events_pending", {"tenant_id": "unknown"}, 0.0))

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

    render_help(
        lines,
        "outbox_events_dead_lettered",
        "Current dead-lettered outbox events.",
        "gauge",
    )
    dead_rows = session.execute(
        select(OutboxEvent.tenant_id, OutboxEvent.event_type, func.count())
        .where(OutboxEvent.status == "DEAD_LETTERED")
        .group_by(OutboxEvent.tenant_id, OutboxEvent.event_type)
        .order_by(OutboxEvent.tenant_id, OutboxEvent.event_type)
    ).all()
    for tenant_id, event_type, count in dead_rows:
        lines.append(
            render_sample(
                "outbox_events_dead_lettered",
                {"tenant_id": str(tenant_id), "event_type": str(event_type)},
                float(count),
            )
        )
    if not dead_rows:
        lines.append(
            render_sample(
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


def render_select_count(
    session: Session,
    statement: Select[tuple[Any]],
) -> int:
    return int(session.scalar(statement) or 0)
