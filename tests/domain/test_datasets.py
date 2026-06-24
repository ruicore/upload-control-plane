import pytest

from upload_control_plane.domain.datasets import (
    DatasetStatus,
    RecoveryStatus,
    ValidationStatus,
    apply_dataset_transition,
    dataset_allows_exposure,
    derive_dataset_upload_status,
)
from upload_control_plane.domain.errors import InvalidStateTransitionError
from upload_control_plane.domain.session_state import UploadSessionStatus


def test_upload_completed_is_not_equivalent_to_dataset_ready() -> None:
    assert derive_dataset_upload_status(UploadSessionStatus.COMPLETED) is None
    assert not dataset_allows_exposure(
        DatasetStatus.PROCESSING,
        ValidationStatus.PASSED,
        RecoveryStatus.NORMAL,
    )


@pytest.mark.parametrize(
    "dataset_status",
    [
        DatasetStatus.QUARANTINED,
        DatasetStatus.REJECTED,
        DatasetStatus.PROCESSING,
        DatasetStatus.DELETED,
        DatasetStatus.PURGED,
    ],
)
def test_dataset_lifecycle_states_block_exposure(dataset_status: DatasetStatus) -> None:
    assert not dataset_allows_exposure(
        dataset_status,
        ValidationStatus.PASSED,
        RecoveryStatus.NORMAL,
    )


@pytest.mark.parametrize(
    "validation_status",
    [
        ValidationStatus.PENDING,
        ValidationStatus.RUNNING,
        ValidationStatus.FAILED,
    ],
)
def test_validation_states_block_exposure_until_allowed(
    validation_status: ValidationStatus,
) -> None:
    assert not dataset_allows_exposure(
        DatasetStatus.READY,
        validation_status,
        RecoveryStatus.NORMAL,
    )


@pytest.mark.parametrize(
    "recovery_status",
    [
        RecoveryStatus.RECOVERY_PENDING,
        RecoveryStatus.RECOVERY_VERIFIED,
        RecoveryStatus.RECOVERY_MISSING_OBJECT,
        RecoveryStatus.RECOVERY_METADATA_ONLY,
        RecoveryStatus.RECOVERY_OBJECT_ONLY,
    ],
)
def test_non_normal_recovery_states_block_exposure(recovery_status: RecoveryStatus) -> None:
    assert not dataset_allows_exposure(
        DatasetStatus.READY,
        ValidationStatus.PASSED,
        recovery_status,
    )


def test_ready_dataset_with_allowed_validation_and_normal_recovery_can_be_exposed() -> None:
    assert dataset_allows_exposure(
        DatasetStatus.READY,
        ValidationStatus.PASSED,
        RecoveryStatus.NORMAL,
    )
    assert dataset_allows_exposure(
        DatasetStatus.READY,
        ValidationStatus.NOT_REQUIRED,
        RecoveryStatus.NORMAL,
    )


def test_dataset_lifecycle_transitions_are_explicit() -> None:
    assert (
        apply_dataset_transition(DatasetStatus.UPLOADING, DatasetStatus.PROCESSING)
        is DatasetStatus.PROCESSING
    )
    assert (
        apply_dataset_transition(DatasetStatus.PROCESSING, DatasetStatus.QUARANTINED)
        is DatasetStatus.QUARANTINED
    )

    with pytest.raises(InvalidStateTransitionError):
        apply_dataset_transition(DatasetStatus.REJECTED, DatasetStatus.READY)
