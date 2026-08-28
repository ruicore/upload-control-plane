from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.application.dataset_retention import DatasetRetentionService
from upload_control_plane.application.upload_session_cleanup import (
    UploadSessionCleanupService,
)
from upload_control_plane.application.worker_dataset_events import (
    WorkerDatasetEventWriter,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.datasets import DatasetStatus, RecoveryStatus
from upload_control_plane.domain.storage import (
    HeadObjectRequest,
    HeadObjectResult,
    ObjectStorage,
    StorageError,
    StorageNotFoundError,
)
from upload_control_plane.infrastructure.db.models import (
    Dataset,
    Project,
)


@dataclass(frozen=True, slots=True)
class LifecycleRunSummary:
    expired_sessions: int = 0
    aborted_sessions: int = 0
    purge_candidates: int = 0
    purged_datasets: int = 0
    recovery_checked: int = 0
    recovery_missing_objects: int = 0
    recovery_metadata_only: int = 0
    recovery_object_only: int = 0
    recovery_verified: int = 0
    errors: int = 0


@dataclass(frozen=True, slots=True)
class ObjectReference:
    bucket: str
    object_key: str


class WorkerLifecycleService:
    """Idempotent lifecycle worker operations.

    This service intentionally does not implement the outbox dispatcher. It keeps storage
    effects behind ObjectStorage and records durable state transitions before external calls.
    """

    def __init__(self, *, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._dataset_events = WorkerDatasetEventWriter(session=session)
        self._dataset_retention = DatasetRetentionService(
            session=session,
            storage=storage,
            settings=settings,
            events=self._dataset_events,
        )
        self._upload_session_cleanup = UploadSessionCleanupService(
            session=session,
            storage=storage,
            settings=settings,
        )

    def run_once(self, *, now: datetime | None = None) -> LifecycleRunSummary:
        run_at = now or datetime.now(UTC)
        expired = self.expire_old_sessions(now=run_at)
        aborted = self.abort_expired_multipart_uploads(now=run_at)
        purge_candidates, purged, purge_errors = self.enforce_recycle_bin_retention(now=run_at)
        return LifecycleRunSummary(
            expired_sessions=expired,
            aborted_sessions=aborted.aborted_sessions,
            purge_candidates=purge_candidates,
            purged_datasets=purged,
            errors=aborted.errors + purge_errors,
        )

    def expire_old_sessions(self, *, now: datetime, batch_size: int | None = None) -> int:
        return self._upload_session_cleanup.expire_old_sessions(
            now=now,
            batch_size=batch_size,
        )

    def abort_expired_multipart_uploads(
        self, *, now: datetime, batch_size: int | None = None
    ) -> LifecycleRunSummary:
        summary = self._upload_session_cleanup.abort_expired_multipart_uploads(
            now=now,
            batch_size=batch_size,
        )
        return LifecycleRunSummary(
            aborted_sessions=summary.aborted_sessions,
            errors=summary.errors,
        )

    def enforce_recycle_bin_retention(
        self, *, now: datetime, batch_size: int | None = None
    ) -> tuple[int, int, int]:
        return self._dataset_retention.enforce_recycle_bin_retention(
            now=now,
            batch_size=batch_size,
        )

    def reconcile_recovery_status(
        self,
        *,
        now: datetime,
        object_refs: tuple[ObjectReference, ...] = (),
        batch_size: int | None = None,
    ) -> LifecycleRunSummary:
        limit = batch_size or self._settings.worker_batch_size
        datasets = list(
            self._session.scalars(
                select(Dataset)
                .where(Dataset.status != DatasetStatus.PURGED.value)
                .where(
                    (Dataset.bucket_name.is_not(None) & Dataset.object_key.is_not(None))
                    | Dataset.recovery_status.in_(
                        (
                            RecoveryStatus.RECOVERY_PENDING.value,
                            RecoveryStatus.RECOVERY_VERIFIED.value,
                        )
                    )
                )
                .order_by(Dataset.updated_at.asc(), Dataset.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        checked = missing = metadata_only = verified = errors = 0
        for dataset in datasets:
            checked += 1
            status = self._reconcile_one_dataset(dataset, now=now)
            if status is RecoveryStatus.RECOVERY_MISSING_OBJECT:
                missing += 1
            elif status is RecoveryStatus.RECOVERY_METADATA_ONLY:
                metadata_only += 1
            elif status is RecoveryStatus.RECOVERY_VERIFIED:
                verified += 1
            elif status is None:
                errors += 1

        known_refs = {
            (bucket, key)
            for bucket, key in self._session.execute(
                select(Dataset.bucket_name, Dataset.object_key).where(
                    Dataset.object_key.is_not(None)
                )
            )
        }
        object_only = 0
        for ref in object_refs:
            if (ref.bucket, ref.object_key) in known_refs:
                continue
            try:
                head = self._storage.head_object(
                    HeadObjectRequest(bucket=ref.bucket, object_key=ref.object_key)
                )
            except StorageNotFoundError:
                continue
            except StorageError:
                errors += 1
                continue
            if self._rebuild_object_only_dataset(ref, head=head, now=now):
                known_refs.add((ref.bucket, ref.object_key))
            object_only += 1

        self._session.commit()
        return LifecycleRunSummary(
            recovery_checked=checked,
            recovery_missing_objects=missing,
            recovery_metadata_only=metadata_only,
            recovery_object_only=object_only,
            recovery_verified=verified,
            errors=errors,
        )

    def _reconcile_one_dataset(self, dataset: Dataset, *, now: datetime) -> RecoveryStatus | None:
        if dataset.bucket_name is None or dataset.object_key is None:
            if dataset.status in {DatasetStatus.READY.value, DatasetStatus.ARCHIVED.value}:
                dataset.recovery_status = RecoveryStatus.RECOVERY_METADATA_ONLY.value
                dataset.updated_at = now
                self._dataset_events.write(
                    dataset,
                    action="dataset.recovery_reconcile",
                    result="MISMATCH",
                    metadata={"reason": "metadata_without_object_location"},
                    now=now,
                )
                return RecoveryStatus.RECOVERY_METADATA_ONLY
            return None
        try:
            head = self._storage.head_object(
                HeadObjectRequest(bucket=dataset.bucket_name, object_key=dataset.object_key)
            )
        except StorageNotFoundError:
            dataset.recovery_status = RecoveryStatus.RECOVERY_MISSING_OBJECT.value
            dataset.updated_at = now
            self._dataset_events.write(
                dataset,
                action="dataset.recovery_reconcile",
                result="MISMATCH",
                metadata={"reason": "final_object_missing"},
                now=now,
            )
            return RecoveryStatus.RECOVERY_MISSING_OBJECT
        except StorageError as exc:
            self._dataset_events.write(
                dataset,
                action="dataset.recovery_reconcile",
                result="FAILED",
                metadata={"operation": exc.operation, "provider_code": exc.provider_code},
                now=now,
            )
            return None

        expected_size = dataset.object_size_bytes or dataset.file_size_bytes
        if expected_size is not None and expected_size != head.size_bytes:
            dataset.recovery_status = RecoveryStatus.RECOVERY_METADATA_ONLY.value
            dataset.updated_at = now
            self._dataset_events.write(
                dataset,
                action="dataset.recovery_reconcile",
                result="MISMATCH",
                metadata={
                    "reason": "object_size_mismatch",
                    "metadata_size_bytes": expected_size,
                    "storage_size_bytes": head.size_bytes,
                },
                now=now,
            )
            return RecoveryStatus.RECOVERY_METADATA_ONLY

        if dataset.recovery_status in {
            RecoveryStatus.RECOVERY_PENDING.value,
            RecoveryStatus.RECOVERY_VERIFIED.value,
            RecoveryStatus.RECOVERY_MISSING_OBJECT.value,
        }:
            before_state = self._dataset_events.snapshot(dataset)
            dataset.object_etag = head.etag
            dataset.object_size_bytes = head.size_bytes
            dataset.object_version_id = head.version_id
            dataset.recovery_status = RecoveryStatus.RECOVERY_VERIFIED.value
            dataset.updated_at = now
            self._dataset_events.write(
                dataset,
                action="dataset.recovery_reconcile",
                result="SUCCESS",
                before_state=before_state,
                after_state=self._dataset_events.snapshot(dataset),
                metadata={"object_size_bytes": head.size_bytes},
                now=now,
            )
            return RecoveryStatus.RECOVERY_VERIFIED
        return RecoveryStatus.NORMAL

    def _rebuild_object_only_dataset(
        self,
        ref: ObjectReference,
        *,
        head: HeadObjectResult,
        now: datetime,
    ) -> bool:
        tenant_id, project_id, dataset_id = self._object_reference_identity(ref, head=head)
        if tenant_id is None or project_id is None:
            return False
        project = self._session.get(Project, project_id)
        if project is None or project.tenant_id != tenant_id:
            return False
        if dataset_id is not None and self._session.get(Dataset, dataset_id) is not None:
            return False

        object_name = ref.object_key.rstrip("/").rsplit("/", 1)[-1] or "recovered-object"
        head_metadata = dict(head.metadata)
        rebuilt = Dataset(
            id=dataset_id or uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            name=f"recovered-{object_name}",
            status=DatasetStatus.QUARANTINED.value,
            original_filename=object_name,
            content_type=head_metadata.get("content_type"),
            file_size_bytes=head.size_bytes,
            bucket_name=ref.bucket,
            object_key=ref.object_key,
            object_etag=head.etag,
            object_size_bytes=head.size_bytes,
            object_version_id=head.version_id,
            validation_status="PENDING",
            recovery_status=RecoveryStatus.RECOVERY_OBJECT_ONLY.value,
            preview_status="NOT_AVAILABLE",
            preview_metadata={},
            metadata_={
                "recovery_source": "worker.object_reference",
                "operator_review_required": True,
            },
            labels=["recovery", "object-only"],
            created_at=now,
            updated_at=now,
        )
        self._session.add(rebuilt)
        self._session.flush()
        self._dataset_events.write(
            rebuilt,
            action="dataset.recovery_rebuild",
            result="SUCCESS",
            after_state=self._dataset_events.snapshot(rebuilt),
            metadata={
                "reason": "object_without_dataset_metadata",
                "object_size_bytes": head.size_bytes,
                "operator_review_required": True,
            },
            now=now,
        )
        return True

    def _object_reference_identity(
        self,
        ref: ObjectReference,
        *,
        head: HeadObjectResult,
    ) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]:
        metadata = getattr(head, "metadata", {}) or {}
        tenant_id = _uuid_from_metadata(metadata, "tenant_id")
        project_id = _uuid_from_metadata(metadata, "project_id")
        dataset_id = _uuid_from_metadata(metadata, "dataset_id")
        if tenant_id is not None and project_id is not None:
            return tenant_id, project_id, dataset_id

        parts = ref.object_key.split("/")
        try:
            tenant_index = parts.index("tenants")
            project_index = parts.index("projects")
            dataset_index = parts.index("datasets")
        except ValueError:
            return tenant_id, project_id, dataset_id
        return (
            tenant_id or _parse_uuid_at(parts, tenant_index + 1),
            project_id or _parse_uuid_at(parts, project_index + 1),
            dataset_id or _parse_uuid_at(parts, dataset_index + 1),
        )


def _uuid_from_metadata(metadata: object, key: str) -> uuid.UUID | None:
    if not isinstance(metadata, Mapping):
        return None
    raw = metadata.get(key)
    if not isinstance(raw, str):
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _parse_uuid_at(parts: list[str], index: int) -> uuid.UUID | None:
    if index >= len(parts):
        return None
    try:
        return uuid.UUID(parts[index])
    except ValueError:
        return None
