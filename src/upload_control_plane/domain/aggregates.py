"""Pure aggregate status rules for upload objects and tasks."""

from collections.abc import Iterable
from enum import StrEnum

from upload_control_plane.domain.session_state import UploadSessionStatus


class UploadObjectStatus(StrEnum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    PAUSED = "PAUSED"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    CANCELING = "CANCELING"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class UploadTaskStatus(StrEnum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    PAUSED = "PAUSED"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    CANCELING = "CANCELING"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


SESSION_TO_OBJECT_STATUS = {
    UploadSessionStatus.INITIATING: UploadObjectStatus.PENDING,
    UploadSessionStatus.INITIATED: UploadObjectStatus.PENDING,
    UploadSessionStatus.UPLOADING: UploadObjectStatus.UPLOADING,
    UploadSessionStatus.PAUSED: UploadObjectStatus.PAUSED,
    UploadSessionStatus.COMPLETING: UploadObjectStatus.COMPLETING,
    UploadSessionStatus.COMPLETED: UploadObjectStatus.COMPLETED,
    UploadSessionStatus.ABORTING: UploadObjectStatus.CANCELING,
    UploadSessionStatus.ABORTED: UploadObjectStatus.CANCELED,
    UploadSessionStatus.EXPIRED: UploadObjectStatus.EXPIRED,
    UploadSessionStatus.FAILED: UploadObjectStatus.FAILED,
}


def derive_upload_object_status(session_status: UploadSessionStatus) -> UploadObjectStatus:
    return SESSION_TO_OBJECT_STATUS[session_status]


def derive_upload_task_status(object_statuses: Iterable[UploadObjectStatus]) -> UploadTaskStatus:
    statuses = frozenset(object_statuses)
    if not statuses:
        raise ValueError("upload task must contain at least one object")

    if UploadObjectStatus.FAILED in statuses:
        return UploadTaskStatus.FAILED
    if UploadObjectStatus.CANCELING in statuses:
        return UploadTaskStatus.CANCELING
    if UploadObjectStatus.EXPIRED in statuses:
        return UploadTaskStatus.EXPIRED
    if UploadObjectStatus.COMPLETING in statuses:
        return UploadTaskStatus.COMPLETING
    if statuses == {UploadObjectStatus.COMPLETED}:
        return UploadTaskStatus.COMPLETED
    if statuses == {UploadObjectStatus.CANCELED}:
        return UploadTaskStatus.CANCELED
    if UploadObjectStatus.UPLOADING in statuses:
        return UploadTaskStatus.UPLOADING
    if UploadObjectStatus.PAUSED in statuses:
        return UploadTaskStatus.PAUSED
    return UploadTaskStatus.PENDING
