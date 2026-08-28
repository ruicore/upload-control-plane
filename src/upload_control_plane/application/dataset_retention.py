from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.application.worker_dataset_events import (
    WorkerDatasetEventWriter,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.datasets import DatasetStatus
from upload_control_plane.domain.storage import (
    DeleteObjectRequest,
    ObjectStorage,
    StorageError,
    StorageNotFoundError,
)
from upload_control_plane.infrastructure.db.models import Dataset, Project, StoragePolicy


class DatasetRetentionService:
    """Enforce automatic retention for datasets already in the recycle bin."""

    def __init__(
        self,
        *,
        session: Session,
        storage: ObjectStorage,
        settings: Settings,
        events: WorkerDatasetEventWriter,
    ) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._events = events

    def enforce_recycle_bin_retention(
        self, *, now: datetime, batch_size: int | None = None
    ) -> tuple[int, int, int]:
        limit = batch_size or self._settings.worker_batch_size
        candidates = list(
            self._session.scalars(
                select(Dataset)
                .where(Dataset.status == DatasetStatus.DELETED.value)
                .where(Dataset.deleted_at.is_not(None))
                .order_by(Dataset.deleted_at.asc(), Dataset.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        purged = 0
        errors = 0
        for dataset in candidates:
            policy = self._storage_policy_for_dataset(dataset)
            denial = self._purge_policy_denial(dataset, policy=policy, now=now)
            if denial is not None:
                self._events.write(
                    dataset,
                    action="dataset.purge",
                    result="DENIED",
                    metadata=denial | {"source": "worker.recycle_retention"},
                    now=now,
                )
                continue
            if self._purge_one_dataset(dataset, now=now):
                purged += 1
            else:
                errors += 1
        self._session.commit()
        return len(candidates), purged, errors

    def _purge_one_dataset(self, dataset: Dataset, *, now: datetime) -> bool:
        before_state = self._events.snapshot(dataset)
        if dataset.bucket_name and dataset.object_key:
            try:
                self._storage.delete_object(
                    DeleteObjectRequest(
                        bucket=dataset.bucket_name,
                        object_key=dataset.object_key,
                        version_id=dataset.object_version_id,
                    )
                )
            except StorageNotFoundError:
                pass
            except StorageError as exc:
                self._events.write(
                    dataset,
                    action="dataset.purge",
                    result="FAILED",
                    metadata={
                        "source": "worker.recycle_retention",
                        "operation": exc.operation,
                        "provider_code": exc.provider_code,
                    },
                    now=now,
                )
                return False
        dataset.status = DatasetStatus.PURGED.value
        dataset.updated_at = now
        dataset.bucket_name = None
        dataset.object_key = None
        dataset.object_etag = None
        dataset.object_size_bytes = None
        dataset.object_version_id = None
        self._events.write(
            dataset,
            action="dataset.purge",
            result="SUCCESS",
            before_state=before_state,
            after_state=self._events.snapshot(dataset),
            metadata={"source": "worker.recycle_retention"},
            now=now,
        )
        return True

    def _storage_policy_for_dataset(self, dataset: Dataset) -> StoragePolicy | None:
        project = self._session.get(Project, dataset.project_id)
        if project is None or project.storage_policy_id is None:
            return None
        policy = self._session.get(StoragePolicy, project.storage_policy_id)
        if policy is None or policy.tenant_id != dataset.tenant_id:
            return None
        return policy

    def _purge_policy_denial(
        self,
        dataset: Dataset,
        *,
        policy: StoragePolicy | None,
        now: datetime,
    ) -> dict[str, object] | None:
        if dataset.deleted_at is None:
            return {"reason": "deleted_timestamp_missing"}
        if policy is not None:
            if policy.legal_hold_default:
                return {"reason": "legal_hold", "storage_policy_id": str(policy.id)}
            if policy.object_lock_mode:
                return {
                    "reason": "object_lock",
                    "storage_policy_id": str(policy.id),
                    "object_lock_mode": policy.object_lock_mode,
                }
        retention_days = (
            policy.retention_days
            if policy is not None and policy.retention_days is not None
            else self._settings.default_recycle_retention_days
        )
        purge_after = dataset.deleted_at + timedelta(days=retention_days)
        if now < purge_after:
            details: dict[str, object] = {
                "reason": "retention_active",
                "purge_after": purge_after.isoformat(),
                "retention_days": retention_days,
            }
            if policy is not None:
                details["storage_policy_id"] = str(policy.id)
            return details
        return None
