from __future__ import annotations

import pytest

from upload_control_plane.application.upload_sessions.persisted_projection import (
    persisted_dataset_status,
    persisted_upload_object_status,
    persisted_upload_task_status,
)
from upload_control_plane.domain.aggregates import derive_upload_object_status
from upload_control_plane.domain.session_state import UploadSessionStatus


@pytest.mark.parametrize(
    ("session_status", "object_status", "task_status", "dataset_status"),
    (
        (UploadSessionStatus.INITIATING, "PENDING", "PENDING", "UPLOAD_PENDING"),
        (UploadSessionStatus.INITIATED, "PENDING", "PENDING", "UPLOAD_PENDING"),
        (UploadSessionStatus.UPLOADING, "UPLOADING", "PROCESSING", "UPLOADING"),
        (UploadSessionStatus.PAUSED, "PAUSED", "PAUSED", "PAUSED"),
        (UploadSessionStatus.COMPLETING, "COMPLETING", "PROCESSING", "PROCESSING"),
        (UploadSessionStatus.COMPLETED, "COMPLETED", "COMPLETED", "PROCESSING"),
        (UploadSessionStatus.ABORTING, "CANCELLED", "CANCELLED", None),
        (UploadSessionStatus.ABORTED, "CANCELLED", "CANCELLED", None),
        (UploadSessionStatus.EXPIRED, "FAILED", "FAILED", None),
        (UploadSessionStatus.FAILED, "FAILED", "FAILED", None),
    ),
)
def test_runtime_persisted_projection_status_mapping(
    session_status: UploadSessionStatus,
    object_status: str,
    task_status: str,
    dataset_status: str | None,
) -> None:
    assert persisted_upload_object_status(session_status) == object_status
    assert persisted_upload_task_status(session_status) == task_status
    assert persisted_dataset_status(session_status) == dataset_status


@pytest.mark.parametrize(
    ("session_status", "object_status", "task_status"),
    (
        (UploadSessionStatus.EXPIRED, "FAILED", "FAILED"),
        (UploadSessionStatus.ABORTING, "CANCELLED", "CANCELLED"),
        (UploadSessionStatus.ABORTED, "CANCELLED", "CANCELLED"),
    ),
)
def test_cleanup_uses_the_same_persisted_projection_statuses(
    session_status: UploadSessionStatus,
    object_status: str,
    task_status: str,
) -> None:
    assert persisted_upload_object_status(session_status) == object_status
    assert persisted_upload_task_status(session_status) == task_status


@pytest.mark.parametrize(
    ("session_status", "domain_status", "persisted_status"),
    (
        (UploadSessionStatus.ABORTING, "CANCELING", "CANCELLED"),
        (UploadSessionStatus.ABORTED, "CANCELED", "CANCELLED"),
        (UploadSessionStatus.EXPIRED, "EXPIRED", "FAILED"),
    ),
)
def test_persisted_projection_is_a_compatibility_boundary_from_domain_vocabulary(
    session_status: UploadSessionStatus,
    domain_status: str,
    persisted_status: str,
) -> None:
    assert derive_upload_object_status(session_status).value == domain_status
    assert persisted_upload_object_status(session_status) == persisted_status
