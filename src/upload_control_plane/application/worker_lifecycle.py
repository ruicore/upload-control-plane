from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.application.outbox import OutboxAppend, append_outbox_event
from upload_control_plane.config import Settings
from upload_control_plane.domain.datasets import DatasetStatus, RecoveryStatus
from upload_control_plane.domain.session_state import UploadSessionStatus
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    DeleteObjectRequest,
    HeadObjectRequest,
    ObjectStorage,
    StorageError,
    StorageNotFoundError,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    Project,
    StoragePolicy,
    UploadEvent,
    UploadObject,
    UploadSession,
    UploadTask,
)

EXPIRABLE_SESSION_STATUSES = (
    UploadSessionStatus.INITIATED.value,
    UploadSessionStatus.UPLOADING.value,
    UploadSessionStatus.PAUSED.value,
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
    """Idempotent T11 lifecycle worker operations.

    This service intentionally does not implement the outbox dispatcher. It keeps storage
    effects behind ObjectStorage and records durable state transitions before external calls.
    """

    def __init__(self, *, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings

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
        limit = batch_size or self._settings.worker_batch_size
        sessions = list(
            self._session.scalars(
                select(UploadSession)
                .where(UploadSession.status.in_(EXPIRABLE_SESSION_STATUSES))
                .where(UploadSession.expires_at < now)
                .order_by(UploadSession.expires_at.asc(), UploadSession.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for upload_session in sessions:
            previous_status = upload_session.status
            upload_session.status = UploadSessionStatus.EXPIRED.value
            upload_session.updated_at = now
            upload_session.last_error_code = "upload.expired"
            upload_session.last_error_message = "Upload session expired before completion."
            self._sync_related_records(upload_session, UploadSessionStatus.EXPIRED, now=now)
            self._add_upload_event(
                upload_session,
                event_type="upload.expired",
                payload={
                    "previous_status": previous_status,
                    "expires_at": _iso(upload_session.expires_at),
                },
                now=now,
            )
        self._session.commit()
        return len(sessions)

    def abort_expired_multipart_uploads(
        self, *, now: datetime, batch_size: int | None = None
    ) -> LifecycleRunSummary:
        limit = batch_size or self._settings.worker_batch_size
        grace_cutoff = now - timedelta(seconds=self._settings.expired_session_abort_grace_seconds)
        sessions = list(
            self._session.scalars(
                select(UploadSession)
                .where(
                    UploadSession.status.in_(
                        (UploadSessionStatus.EXPIRED.value, UploadSessionStatus.ABORTING.value)
                    )
                )
                .where(UploadSession.updated_at <= grace_cutoff)
                .order_by(UploadSession.updated_at.asc(), UploadSession.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        aborted = 0
        errors = 0
        for upload_session in sessions:
            if self._abort_one_expired_session(upload_session, now=now):
                aborted += 1
            else:
                errors += 1
        return LifecycleRunSummary(aborted_sessions=aborted, errors=errors)

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
                self._add_audit(
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
                self._storage.head_object(
                    HeadObjectRequest(bucket=ref.bucket, object_key=ref.object_key)
                )
            except StorageNotFoundError:
                continue
            except StorageError:
                errors += 1
                continue
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

    def _abort_one_expired_session(self, upload_session: UploadSession, *, now: datetime) -> bool:
        if upload_session.status == UploadSessionStatus.EXPIRED.value:
            upload_session.status = UploadSessionStatus.ABORTING.value
            upload_session.updated_at = now
            self._sync_related_records(upload_session, UploadSessionStatus.ABORTING, now=now)
            self._add_upload_event(
                upload_session,
                event_type="upload.abort_requested",
                payload={"reason": "expired_session_cleanup"},
                now=now,
            )
            self._session.commit()

        if upload_session.storage_upload_id is not None:
            try:
                self._storage.abort_multipart_upload(
                    AbortMultipartUploadRequest(
                        bucket=upload_session.bucket_name,
                        object_key=upload_session.object_key,
                        upload_id=upload_session.storage_upload_id,
                    )
                )
            except StorageNotFoundError:
                pass
            except StorageError as exc:
                self._mark_session_cleanup_failed(upload_session.id, exc, now=now)
                return False

        refreshed_session = self._session.get(UploadSession, upload_session.id)
        if (
            refreshed_session is None
            or refreshed_session.status == UploadSessionStatus.ABORTED.value
        ):
            return False
        refreshed_session.status = UploadSessionStatus.ABORTED.value
        refreshed_session.aborted_at = refreshed_session.aborted_at or now
        refreshed_session.updated_at = now
        refreshed_session.last_error_code = None
        refreshed_session.last_error_message = None
        self._sync_related_records(refreshed_session, UploadSessionStatus.ABORTED, now=now)
        self._add_upload_event(
            refreshed_session,
            event_type="upload.aborted",
            payload={"reason": "expired_session_cleanup"},
            now=now,
        )
        self._session.commit()
        return True

    def _mark_session_cleanup_failed(
        self, session_id: uuid.UUID, exc: StorageError, *, now: datetime
    ) -> None:
        self._session.rollback()
        upload_session = self._session.get(UploadSession, session_id)
        if upload_session is None:
            return
        upload_session.status = UploadSessionStatus.ABORTING.value
        upload_session.updated_at = now
        upload_session.last_error_code = "storage.abort_failed"
        upload_session.last_error_message = str(exc)
        self._add_upload_event(
            upload_session,
            event_type="upload.cleanup_failed",
            payload={"operation": exc.operation, "provider_code": exc.provider_code},
            now=now,
        )
        self._session.commit()

    def _purge_one_dataset(self, dataset: Dataset, *, now: datetime) -> bool:
        before_state = self._dataset_audit_state(dataset)
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
                self._add_audit(
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
        self._add_audit(
            dataset,
            action="dataset.purge",
            result="SUCCESS",
            before_state=before_state,
            after_state=self._dataset_audit_state(dataset),
            metadata={"source": "worker.recycle_retention"},
            now=now,
        )
        return True

    def _reconcile_one_dataset(self, dataset: Dataset, *, now: datetime) -> RecoveryStatus | None:
        if dataset.bucket_name is None or dataset.object_key is None:
            if dataset.status in {DatasetStatus.READY.value, DatasetStatus.ARCHIVED.value}:
                dataset.recovery_status = RecoveryStatus.RECOVERY_METADATA_ONLY.value
                dataset.updated_at = now
                self._add_audit(
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
            self._add_audit(
                dataset,
                action="dataset.recovery_reconcile",
                result="MISMATCH",
                metadata={"reason": "final_object_missing"},
                now=now,
            )
            return RecoveryStatus.RECOVERY_MISSING_OBJECT
        except StorageError as exc:
            self._add_audit(
                dataset,
                action="dataset.recovery_reconcile",
                result="FAILED",
                metadata={"operation": exc.operation, "provider_code": exc.provider_code},
                now=now,
            )
            return None

        if dataset.object_size_bytes is not None and dataset.object_size_bytes != head.size_bytes:
            dataset.recovery_status = RecoveryStatus.RECOVERY_METADATA_ONLY.value
            dataset.updated_at = now
            self._add_audit(
                dataset,
                action="dataset.recovery_reconcile",
                result="MISMATCH",
                metadata={
                    "reason": "object_size_mismatch",
                    "metadata_size_bytes": dataset.object_size_bytes,
                    "storage_size_bytes": head.size_bytes,
                },
                now=now,
            )
            return RecoveryStatus.RECOVERY_METADATA_ONLY

        if dataset.recovery_status in {
            RecoveryStatus.RECOVERY_PENDING.value,
            RecoveryStatus.RECOVERY_VERIFIED.value,
        }:
            dataset.recovery_status = RecoveryStatus.RECOVERY_VERIFIED.value
            dataset.updated_at = now
            self._add_audit(
                dataset,
                action="dataset.recovery_reconcile",
                result="SUCCESS",
                metadata={"object_size_bytes": head.size_bytes},
                now=now,
            )
            return RecoveryStatus.RECOVERY_VERIFIED
        return RecoveryStatus.NORMAL

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

    def _sync_related_records(
        self, upload_session: UploadSession, status: UploadSessionStatus, *, now: datetime
    ) -> None:
        if upload_session.upload_object_id is not None:
            upload_object = self._session.get(UploadObject, upload_session.upload_object_id)
            if upload_object is not None:
                upload_object.status = _upload_object_status(status)
                upload_object.updated_at = now
        if upload_session.upload_task_id is not None:
            upload_task = self._session.get(UploadTask, upload_session.upload_task_id)
            if upload_task is not None:
                upload_task.status = _upload_task_status(status)
                upload_task.updated_at = now
                if status is UploadSessionStatus.ABORTED:
                    upload_task.cancelled_at = upload_task.cancelled_at or now

    def _add_upload_event(
        self,
        upload_session: UploadSession,
        *,
        event_type: str,
        payload: dict[str, object],
        now: datetime,
    ) -> None:
        self._session.add(
            UploadEvent(
                tenant_id=upload_session.tenant_id,
                project_id=upload_session.project_id,
                dataset_id=upload_session.dataset_id,
                upload_task_id=upload_session.upload_task_id,
                upload_object_id=upload_session.upload_object_id,
                session_id=upload_session.id,
                event_type=event_type,
                actor_type="system",
                actor_id="worker:lifecycle",
                request_id=None,
                payload=payload,
                created_at=now,
            )
        )
        append_outbox_event(
            self._session,
            OutboxAppend(
                tenant_id=upload_session.tenant_id,
                aggregate_type="upload_session",
                aggregate_id=upload_session.id,
                event_type=event_type,
                payload={
                    "session_id": str(upload_session.id),
                    "project_id": str(upload_session.project_id)
                    if upload_session.project_id is not None
                    else None,
                    "dataset_id": str(upload_session.dataset_id)
                    if upload_session.dataset_id is not None
                    else None,
                    "upload_task_id": str(upload_session.upload_task_id)
                    if upload_session.upload_task_id is not None
                    else None,
                    "upload_object_id": str(upload_session.upload_object_id)
                    if upload_session.upload_object_id is not None
                    else None,
                    "status": upload_session.status,
                    "event": payload,
                },
                created_at=now,
                next_attempt_at=now,
            ),
        )

    def _add_audit(
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

    def _dataset_audit_state(self, dataset: Dataset) -> dict[str, object]:
        return {
            "dataset_id": str(dataset.id),
            "status": dataset.status,
            "recovery_status": dataset.recovery_status,
            "bucket": dataset.bucket_name,
            "object_key": dataset.object_key,
            "deleted_at": _iso(dataset.deleted_at),
        }


def _upload_object_status(status: UploadSessionStatus) -> str:
    return {
        UploadSessionStatus.EXPIRED: "FAILED",
        UploadSessionStatus.ABORTING: "CANCELLED",
        UploadSessionStatus.ABORTED: "CANCELLED",
    }.get(status, "FAILED")


def _upload_task_status(status: UploadSessionStatus) -> str:
    return {
        UploadSessionStatus.EXPIRED: "FAILED",
        UploadSessionStatus.ABORTING: "CANCELLED",
        UploadSessionStatus.ABORTED: "CANCELLED",
    }.get(status, "FAILED")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
