import pytest

from upload_control_plane.domain.aggregates import (
    UploadObjectStatus,
    UploadTaskStatus,
    derive_upload_object_status,
    derive_upload_task_status,
)
from upload_control_plane.domain.session_state import UploadSessionStatus


@pytest.mark.parametrize(
    ("session_status", "object_status"),
    [
        (UploadSessionStatus.INITIATING, UploadObjectStatus.PENDING),
        (UploadSessionStatus.INITIATED, UploadObjectStatus.PENDING),
        (UploadSessionStatus.UPLOADING, UploadObjectStatus.UPLOADING),
        (UploadSessionStatus.PAUSED, UploadObjectStatus.PAUSED),
        (UploadSessionStatus.COMPLETING, UploadObjectStatus.COMPLETING),
        (UploadSessionStatus.COMPLETED, UploadObjectStatus.COMPLETED),
        (UploadSessionStatus.ABORTING, UploadObjectStatus.CANCELING),
        (UploadSessionStatus.ABORTED, UploadObjectStatus.CANCELED),
        (UploadSessionStatus.EXPIRED, UploadObjectStatus.EXPIRED),
        (UploadSessionStatus.FAILED, UploadObjectStatus.FAILED),
    ],
)
def test_upload_object_status_is_derived_from_session_status(
    session_status: UploadSessionStatus,
    object_status: UploadObjectStatus,
) -> None:
    assert derive_upload_object_status(session_status) is object_status


@pytest.mark.parametrize(
    ("object_statuses", "task_status"),
    [
        ([UploadObjectStatus.PENDING], UploadTaskStatus.PENDING),
        ([UploadObjectStatus.UPLOADING, UploadObjectStatus.PENDING], UploadTaskStatus.UPLOADING),
        ([UploadObjectStatus.PAUSED, UploadObjectStatus.PENDING], UploadTaskStatus.PAUSED),
        (
            [UploadObjectStatus.COMPLETING, UploadObjectStatus.COMPLETED],
            UploadTaskStatus.COMPLETING,
        ),
        ([UploadObjectStatus.COMPLETED, UploadObjectStatus.COMPLETED], UploadTaskStatus.COMPLETED),
        ([UploadObjectStatus.CANCELING, UploadObjectStatus.PENDING], UploadTaskStatus.CANCELING),
        ([UploadObjectStatus.CANCELED, UploadObjectStatus.CANCELED], UploadTaskStatus.CANCELED),
        ([UploadObjectStatus.EXPIRED, UploadObjectStatus.PENDING], UploadTaskStatus.EXPIRED),
        ([UploadObjectStatus.FAILED, UploadObjectStatus.COMPLETED], UploadTaskStatus.FAILED),
    ],
)
def test_upload_task_status_is_derived_from_child_upload_objects(
    object_statuses: list[UploadObjectStatus],
    task_status: UploadTaskStatus,
) -> None:
    assert derive_upload_task_status(object_statuses) is task_status


def test_upload_task_requires_at_least_one_upload_object() -> None:
    with pytest.raises(ValueError, match="at least one object"):
        derive_upload_task_status([])
