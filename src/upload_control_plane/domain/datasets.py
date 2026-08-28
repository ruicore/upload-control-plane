"""Dataset lifecycle, validation, recovery, and exposure rules."""

from enum import StrEnum

from upload_control_plane.domain.errors import InvalidStateTransitionError
from upload_control_plane.domain.session_state import UploadSessionStatus


class DatasetStatus(StrEnum):
    CREATED = "CREATED"
    UPLOAD_PENDING = "UPLOAD_PENDING"
    UPLOADING = "UPLOADING"
    PAUSED = "PAUSED"
    PROCESSING = "PROCESSING"
    QUARANTINED = "QUARANTINED"
    READY = "READY"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"
    PURGED = "PURGED"


class ValidationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class RecoveryStatus(StrEnum):
    NORMAL = "NORMAL"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    RECOVERY_VERIFIED = "RECOVERY_VERIFIED"
    RECOVERY_MISSING_OBJECT = "RECOVERY_MISSING_OBJECT"
    RECOVERY_METADATA_ONLY = "RECOVERY_METADATA_ONLY"
    RECOVERY_OBJECT_ONLY = "RECOVERY_OBJECT_ONLY"


EXPOSABLE_DATASET_STATUSES = frozenset({DatasetStatus.READY, DatasetStatus.ARCHIVED})
BLOCKED_DATASET_STATUSES = frozenset(
    {
        DatasetStatus.CREATED,
        DatasetStatus.UPLOAD_PENDING,
        DatasetStatus.UPLOADING,
        DatasetStatus.PAUSED,
        DatasetStatus.PROCESSING,
        DatasetStatus.QUARANTINED,
        DatasetStatus.REJECTED,
        DatasetStatus.DELETED,
        DatasetStatus.PURGED,
    }
)
VALIDATION_EXPOSURE_STATUSES = frozenset(
    {
        ValidationStatus.NOT_REQUIRED,
        ValidationStatus.PASSED,
        ValidationStatus.SKIPPED,
    }
)

ALLOWED_DATASET_TRANSITIONS = frozenset(
    {
        (DatasetStatus.CREATED, DatasetStatus.UPLOAD_PENDING),
        (DatasetStatus.UPLOAD_PENDING, DatasetStatus.UPLOADING),
        (DatasetStatus.UPLOADING, DatasetStatus.PAUSED),
        (DatasetStatus.PAUSED, DatasetStatus.UPLOADING),
        (DatasetStatus.UPLOADING, DatasetStatus.PROCESSING),
        (DatasetStatus.PAUSED, DatasetStatus.PROCESSING),
        (DatasetStatus.PROCESSING, DatasetStatus.READY),
        (DatasetStatus.PROCESSING, DatasetStatus.QUARANTINED),
        (DatasetStatus.PROCESSING, DatasetStatus.REJECTED),
        (DatasetStatus.QUARANTINED, DatasetStatus.PROCESSING),
        (DatasetStatus.QUARANTINED, DatasetStatus.READY),
        (DatasetStatus.READY, DatasetStatus.ARCHIVED),
        (DatasetStatus.ARCHIVED, DatasetStatus.READY),
        (DatasetStatus.READY, DatasetStatus.DELETED),
        (DatasetStatus.ARCHIVED, DatasetStatus.DELETED),
        (DatasetStatus.REJECTED, DatasetStatus.DELETED),
        (DatasetStatus.DELETED, DatasetStatus.READY),
        (DatasetStatus.DELETED, DatasetStatus.ARCHIVED),
        (DatasetStatus.DELETED, DatasetStatus.PURGED),
    }
)

SESSION_TO_DATASET_UPLOAD_STATUS = {
    UploadSessionStatus.INITIATING: DatasetStatus.UPLOAD_PENDING,
    UploadSessionStatus.INITIATED: DatasetStatus.UPLOAD_PENDING,
    UploadSessionStatus.UPLOADING: DatasetStatus.UPLOADING,
    UploadSessionStatus.PAUSED: DatasetStatus.PAUSED,
}


def apply_dataset_transition(
    current_status: DatasetStatus,
    next_status: DatasetStatus,
) -> DatasetStatus:
    if (current_status, next_status) not in ALLOWED_DATASET_TRANSITIONS:
        raise InvalidStateTransitionError(
            f"cannot transition dataset from {current_status} to {next_status}"
        )
    return next_status


def derive_dataset_upload_status(session_status: UploadSessionStatus) -> DatasetStatus | None:
    """Map active upload transport states to dataset lifecycle states.

    Completed upload sessions intentionally do not map to READY because validation and
    recovery checks still own exposure.
    """
    return SESSION_TO_DATASET_UPLOAD_STATUS.get(session_status)


def validation_allows_exposure(validation_status: ValidationStatus) -> bool:
    return validation_status in VALIDATION_EXPOSURE_STATUSES


def recovery_allows_exposure(recovery_status: RecoveryStatus) -> bool:
    return recovery_status is RecoveryStatus.NORMAL


def dataset_allows_exposure(
    dataset_status: DatasetStatus,
    validation_status: ValidationStatus,
    recovery_status: RecoveryStatus,
) -> bool:
    if dataset_status in BLOCKED_DATASET_STATUSES:
        return False
    return (
        dataset_status in EXPOSABLE_DATASET_STATUSES
        and validation_allows_exposure(validation_status)
        and recovery_allows_exposure(recovery_status)
    )
