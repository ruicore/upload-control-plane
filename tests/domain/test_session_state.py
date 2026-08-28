import pytest

from upload_control_plane.domain.errors import InvalidStateTransitionError
from upload_control_plane.domain.session_state import (
    UploadSessionStatus,
    apply_transition,
    can_abort,
    can_complete,
    can_pause,
    can_presign,
    can_resume,
    is_terminal,
)


def test_valid_upload_session_transitions_include_pause_resume_complete_and_abort() -> None:
    assert (
        apply_transition(UploadSessionStatus.INITIATING, UploadSessionStatus.INITIATED)
        is UploadSessionStatus.INITIATED
    )
    assert (
        apply_transition(UploadSessionStatus.INITIATED, UploadSessionStatus.UPLOADING)
        is UploadSessionStatus.UPLOADING
    )
    assert (
        apply_transition(UploadSessionStatus.UPLOADING, UploadSessionStatus.PAUSED)
        is UploadSessionStatus.PAUSED
    )
    assert (
        apply_transition(UploadSessionStatus.PAUSED, UploadSessionStatus.UPLOADING)
        is UploadSessionStatus.UPLOADING
    )
    assert (
        apply_transition(UploadSessionStatus.UPLOADING, UploadSessionStatus.COMPLETING)
        is UploadSessionStatus.COMPLETING
    )
    assert (
        apply_transition(UploadSessionStatus.COMPLETING, UploadSessionStatus.COMPLETED)
        is UploadSessionStatus.COMPLETED
    )
    assert (
        apply_transition(UploadSessionStatus.EXPIRED, UploadSessionStatus.ABORTING)
        is UploadSessionStatus.ABORTING
    )
    assert (
        apply_transition(UploadSessionStatus.ABORTING, UploadSessionStatus.ABORTED)
        is UploadSessionStatus.ABORTED
    )


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        (UploadSessionStatus.COMPLETED, UploadSessionStatus.UPLOADING),
        (UploadSessionStatus.ABORTED, UploadSessionStatus.COMPLETING),
        (UploadSessionStatus.FAILED, UploadSessionStatus.UPLOADING),
        (UploadSessionStatus.PAUSED, UploadSessionStatus.COMPLETED),
        (UploadSessionStatus.EXPIRED, UploadSessionStatus.UPLOADING),
    ],
)
def test_invalid_upload_session_transitions_are_rejected(
    current_status: UploadSessionStatus,
    next_status: UploadSessionStatus,
) -> None:
    with pytest.raises(InvalidStateTransitionError):
        apply_transition(current_status, next_status)


def test_terminal_statuses_are_explicit_and_expired_is_not_terminal() -> None:
    assert is_terminal(UploadSessionStatus.COMPLETED)
    assert is_terminal(UploadSessionStatus.ABORTED)
    assert is_terminal(UploadSessionStatus.FAILED)
    assert not is_terminal(UploadSessionStatus.EXPIRED)


def test_presign_is_rejected_while_paused_and_other_non_uploadable_states() -> None:
    assert can_presign(UploadSessionStatus.INITIATED)
    assert can_presign(UploadSessionStatus.UPLOADING)
    assert not can_presign(UploadSessionStatus.PAUSED)
    assert not can_presign(UploadSessionStatus.COMPLETING)
    assert not can_presign(UploadSessionStatus.COMPLETED)
    assert not can_presign(UploadSessionStatus.ABORTING)
    assert not can_presign(UploadSessionStatus.ABORTED)
    assert not can_presign(UploadSessionStatus.FAILED)


def test_action_guards_include_idempotent_pause_resume_complete_abort_cases() -> None:
    assert can_pause(UploadSessionStatus.INITIATED)
    assert can_pause(UploadSessionStatus.UPLOADING)
    assert can_pause(UploadSessionStatus.PAUSED)
    assert not can_pause(UploadSessionStatus.COMPLETING)

    assert can_resume(UploadSessionStatus.PAUSED)
    assert can_resume(UploadSessionStatus.UPLOADING)
    assert not can_resume(UploadSessionStatus.EXPIRED)

    assert can_complete(UploadSessionStatus.INITIATED)
    assert can_complete(UploadSessionStatus.UPLOADING)
    assert can_complete(UploadSessionStatus.PAUSED)
    assert can_complete(UploadSessionStatus.COMPLETED)
    assert not can_complete(UploadSessionStatus.EXPIRED)
    assert not can_complete(UploadSessionStatus.ABORTING)

    assert can_abort(UploadSessionStatus.INITIATED)
    assert can_abort(UploadSessionStatus.UPLOADING)
    assert can_abort(UploadSessionStatus.PAUSED)
    assert can_abort(UploadSessionStatus.EXPIRED)
    assert can_abort(UploadSessionStatus.ABORTED)
    assert not can_abort(UploadSessionStatus.COMPLETED)
