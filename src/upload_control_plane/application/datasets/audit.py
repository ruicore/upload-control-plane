from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.infrastructure.db.models import AuditEvent, Dataset


class DatasetAuditWriter:
    """Own dataset audit snapshots and persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def snapshot(self, dataset: Dataset) -> dict[str, Any]:
        return {
            "dataset_id": str(dataset.id),
            "status": dataset.status,
            "name": dataset.name,
            "validation_status": dataset.validation_status,
            "recovery_status": dataset.recovery_status,
            "bucket": dataset.bucket_name,
            "object_key": dataset.object_key,
            "deleted_at": dataset.deleted_at.isoformat() if dataset.deleted_at else None,
        }

    def add(
        self,
        dataset: Dataset,
        *,
        actor: AuthenticatedActor,
        action: str,
        result: str,
        request_id: str | None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuditEvent(
                tenant_id=dataset.tenant_id,
                project_id=dataset.project_id,
                dataset_id=dataset.id,
                actor_type="api_key",
                actor_id=str(actor.subject_id),
                action=action,
                resource_type="dataset",
                resource_id=str(dataset.id),
                result=result,
                request_id=request_id,
                before_state=before_state,
                after_state=after_state,
                metadata_=metadata or {"source": "dataset_lifecycle"},
            )
        )
