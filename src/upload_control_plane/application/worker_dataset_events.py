from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from upload_control_plane.application.outbox import OutboxAppend, append_outbox_event
from upload_control_plane.infrastructure.db.models import AuditEvent, Dataset


class WorkerDatasetEventWriter:
    """Record dataset audit and outbox events produced by lifecycle workers."""

    def __init__(self, *, session: Session) -> None:
        self._session = session

    def write(
        self,
        dataset: Dataset,
        *,
        action: str,
        result: str,
        now: datetime,
        before_state: dict[str, object] | None = None,
        after_state: dict[str, object] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._session.add(
            AuditEvent(
                tenant_id=dataset.tenant_id,
                project_id=dataset.project_id,
                dataset_id=dataset.id,
                actor_type="system",
                actor_id="worker:lifecycle",
                action=action,
                resource_type="dataset",
                resource_id=str(dataset.id),
                result=result,
                request_id=None,
                before_state=before_state,
                after_state=after_state,
                metadata_=metadata or {"source": "worker.lifecycle"},
                created_at=now,
            )
        )
        append_outbox_event(
            self._session,
            OutboxAppend(
                tenant_id=dataset.tenant_id,
                aggregate_type="dataset",
                aggregate_id=dataset.id,
                event_type=action,
                payload={
                    "dataset_id": str(dataset.id),
                    "project_id": str(dataset.project_id),
                    "status": dataset.status,
                    "recovery_status": dataset.recovery_status,
                    "result": result,
                    "metadata": metadata or {"source": "worker.lifecycle"},
                },
                created_at=now,
                next_attempt_at=now,
            ),
        )

    def snapshot(self, dataset: Dataset) -> dict[str, object]:
        return {
            "dataset_id": str(dataset.id),
            "status": dataset.status,
            "recovery_status": dataset.recovery_status,
            "bucket": dataset.bucket_name,
            "object_key": dataset.object_key,
            "deleted_at": _iso(dataset.deleted_at),
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
