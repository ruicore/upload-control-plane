"""Upload session state machine and action guards."""

from enum import StrEnum

from upload_control_plane.domain.errors import InvalidStateTransitionError


class UploadSessionStatus(StrEnum):
    INITIATING = "INITIATING"
    INITIATED = "INITIATED"
    UPLOADING = "UPLOADING"
    PAUSED = "PAUSED"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


TERMINAL_SESSION_STATUSES = frozenset(
    {
        UploadSessionStatus.COMPLETED,
        UploadSessionStatus.ABORTED,
        UploadSessionStatus.FAILED,
    }
)

ALLOWED_TRANSITIONS = frozenset(
    {
        (UploadSessionStatus.INITIATING, UploadSessionStatus.INITIATED),
        (UploadSessionStatus.INITIATING, UploadSessionStatus.FAILED),
        (UploadSessionStatus.INITIATED, UploadSessionStatus.UPLOADING),
        (UploadSessionStatus.UPLOADING, UploadSessionStatus.UPLOADING),
        (UploadSessionStatus.INITIATED, UploadSessionStatus.PAUSED),
        (UploadSessionStatus.UPLOADING, UploadSessionStatus.PAUSED),
        (UploadSessionStatus.PAUSED, UploadSessionStatus.UPLOADING),
        (UploadSessionStatus.INITIATED, UploadSessionStatus.COMPLETING),
        (UploadSessionStatus.UPLOADING, UploadSessionStatus.COMPLETING),
        (UploadSessionStatus.PAUSED, UploadSessionStatus.COMPLETING),
        (UploadSessionStatus.COMPLETING, UploadSessionStatus.COMPLETED),
        (UploadSessionStatus.COMPLETING, UploadSessionStatus.FAILED),
        (UploadSessionStatus.INITIATED, UploadSessionStatus.ABORTING),
        (UploadSessionStatus.UPLOADING, UploadSessionStatus.ABORTING),
        (UploadSessionStatus.PAUSED, UploadSessionStatus.ABORTING),
        (UploadSessionStatus.EXPIRED, UploadSessionStatus.ABORTING),
        (UploadSessionStatus.ABORTING, UploadSessionStatus.ABORTED),
        (UploadSessionStatus.INITIATED, UploadSessionStatus.EXPIRED),
        (UploadSessionStatus.UPLOADING, UploadSessionStatus.EXPIRED),
        (UploadSessionStatus.PAUSED, UploadSessionStatus.EXPIRED),
    }
)

NON_TERMINAL_SESSION_STATUSES = frozenset(set(UploadSessionStatus) - TERMINAL_SESSION_STATUSES)
ALLOWED_TRANSITIONS = ALLOWED_TRANSITIONS | frozenset(
    (status, UploadSessionStatus.FAILED)
    for status in NON_TERMINAL_SESSION_STATUSES
    if status is not UploadSessionStatus.FAILED
)


def is_terminal(status: UploadSessionStatus) -> bool:
    return status in TERMINAL_SESSION_STATUSES


def apply_transition(
    current_status: UploadSessionStatus,
    next_status: UploadSessionStatus,
) -> UploadSessionStatus:
    if (current_status, next_status) not in ALLOWED_TRANSITIONS:
        raise InvalidStateTransitionError(
            f"cannot transition upload session from {current_status} to {next_status}"
        )
    return next_status


def can_presign(status: UploadSessionStatus) -> bool:
    return status in {UploadSessionStatus.INITIATED, UploadSessionStatus.UPLOADING}


def can_pause(status: UploadSessionStatus) -> bool:
    return status in {
        UploadSessionStatus.INITIATED,
        UploadSessionStatus.UPLOADING,
        UploadSessionStatus.PAUSED,
    }


def can_resume(status: UploadSessionStatus) -> bool:
    return status in {UploadSessionStatus.PAUSED, UploadSessionStatus.UPLOADING}


def can_complete(status: UploadSessionStatus) -> bool:
    return status in {
        UploadSessionStatus.INITIATED,
        UploadSessionStatus.UPLOADING,
        UploadSessionStatus.PAUSED,
        UploadSessionStatus.COMPLETED,
    }


def can_abort(status: UploadSessionStatus) -> bool:
    return status in {
        UploadSessionStatus.INITIATED,
        UploadSessionStatus.UPLOADING,
        UploadSessionStatus.PAUSED,
        UploadSessionStatus.EXPIRED,
        UploadSessionStatus.ABORTED,
    }
