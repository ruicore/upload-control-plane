from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from upload_control_plane.config import Settings
from upload_control_plane.domain.session_state import UploadSessionStatus
from upload_control_plane.domain.storage import CompletedObject
from upload_control_plane.infrastructure.db.models import (
    Dataset,
    UploadObject,
    UploadSession,
    UploadTask,
)


def persisted_upload_object_status(status: UploadSessionStatus) -> str:
    """Map session state to the legacy value persisted by the current ORM schema.

    This is intentionally separate from ``domain.aggregates``. The pure-domain
    vocabulary models CANCELING, CANCELED, and EXPIRED, while persisted upload
    rows retain their existing CANCELLED and FAILED compatibility values.
    """
    return {
        UploadSessionStatus.INITIATING: "PENDING",
        UploadSessionStatus.INITIATED: "PENDING",
        UploadSessionStatus.UPLOADING: "UPLOADING",
        UploadSessionStatus.PAUSED: "PAUSED",
        UploadSessionStatus.COMPLETING: "COMPLETING",
        UploadSessionStatus.COMPLETED: "COMPLETED",
        UploadSessionStatus.ABORTING: "CANCELLED",
        UploadSessionStatus.ABORTED: "CANCELLED",
        UploadSessionStatus.EXPIRED: "FAILED",
        UploadSessionStatus.FAILED: "FAILED",
    }[status]


def persisted_upload_task_status(status: UploadSessionStatus) -> str:
    """Map session state to the existing persisted upload-task vocabulary."""
    return {
        UploadSessionStatus.INITIATING: "PENDING",
        UploadSessionStatus.INITIATED: "PENDING",
        UploadSessionStatus.UPLOADING: "PROCESSING",
        UploadSessionStatus.PAUSED: "PAUSED",
        UploadSessionStatus.COMPLETING: "PROCESSING",
        UploadSessionStatus.COMPLETED: "COMPLETED",
        UploadSessionStatus.ABORTING: "CANCELLED",
        UploadSessionStatus.ABORTED: "CANCELLED",
        UploadSessionStatus.EXPIRED: "FAILED",
        UploadSessionStatus.FAILED: "FAILED",
    }[status]


def persisted_dataset_status(status: UploadSessionStatus) -> str | None:
    """Map session state to the existing dataset projection, if it owns a change."""
    return {
        UploadSessionStatus.INITIATING: "UPLOAD_PENDING",
        UploadSessionStatus.INITIATED: "UPLOAD_PENDING",
        UploadSessionStatus.UPLOADING: "UPLOADING",
        UploadSessionStatus.PAUSED: "PAUSED",
        UploadSessionStatus.COMPLETING: "PROCESSING",
        UploadSessionStatus.COMPLETED: "PROCESSING",
        UploadSessionStatus.ABORTING: None,
        UploadSessionStatus.ABORTED: None,
        UploadSessionStatus.EXPIRED: None,
        UploadSessionStatus.FAILED: None,
    }[status]


class PersistedUploadAggregateProjector:
    """Own persistence-side upload object, task, and dataset projections."""

    def __init__(self, *, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def project_runtime_transition(
        self,
        upload_session: UploadSession,
        *,
        status: UploadSessionStatus,
        now: datetime,
        storage_result: CompletedObject | None = None,
    ) -> None:
        if upload_session.upload_object_id is not None:
            upload_object = self._session.get(UploadObject, upload_session.upload_object_id)
            if upload_object is not None:
                upload_object.status = persisted_upload_object_status(status)
                upload_object.updated_at = now
                if status is UploadSessionStatus.COMPLETED:
                    upload_object.completed_at = now
        if upload_session.dataset_id is not None:
            dataset = self._session.get(Dataset, upload_session.dataset_id)
            if dataset is not None:
                dataset_status = persisted_dataset_status(status)
                if dataset_status is not None:
                    dataset.status = dataset_status
                if storage_result is not None:
                    dataset.object_etag = storage_result.etag
                    dataset.object_size_bytes = storage_result.size_bytes
                    dataset.object_version_id = storage_result.version_id
                    dataset.bucket_name = storage_result.bucket
                    dataset.object_key = storage_result.object_key
                if (
                    status is UploadSessionStatus.COMPLETED
                    and self._settings.enable_dataset_validation
                    and dataset.validation_status == "NOT_REQUIRED"
                ):
                    dataset.validation_status = "PENDING"
                dataset.updated_at = now
        if upload_session.upload_task_id is not None:
            upload_task = self._session.get(UploadTask, upload_session.upload_task_id)
            if upload_task is not None:
                upload_task.status = persisted_upload_task_status(status)
                upload_task.updated_at = now
                if status is UploadSessionStatus.COMPLETED:
                    upload_task.completed_object_count = min(
                        upload_task.object_count,
                        upload_task.completed_object_count + 1,
                    )
                    upload_task.completed_at = now
                if status is UploadSessionStatus.ABORTED:
                    upload_task.cancelled_at = now

    def project_cleanup_transition(
        self,
        upload_session: UploadSession,
        *,
        status: UploadSessionStatus,
        now: datetime,
    ) -> None:
        """Apply the cleanup path's intentionally narrower persisted projection."""
        if upload_session.upload_object_id is not None:
            upload_object = self._session.get(UploadObject, upload_session.upload_object_id)
            if upload_object is not None:
                upload_object.status = persisted_upload_object_status(status)
                upload_object.updated_at = now
        if upload_session.upload_task_id is not None:
            upload_task = self._session.get(UploadTask, upload_session.upload_task_id)
            if upload_task is not None:
                upload_task.status = persisted_upload_task_status(status)
                upload_task.updated_at = now
                if status is UploadSessionStatus.ABORTED:
                    upload_task.cancelled_at = upload_task.cancelled_at or now
