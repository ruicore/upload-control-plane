from datetime import UTC, datetime
from uuid import UUID

import pytest

from upload_control_plane.domain.errors import InvalidObjectNameError
from upload_control_plane.domain.object_keys import build_object_key, sanitize_object_name


def test_sanitize_object_name_rejects_path_traversal_and_separators() -> None:
    for raw_name in ["../camera.hdf5", "nested/camera.hdf5", r"nested\camera.hdf5", ".", ".."]:
        with pytest.raises(InvalidObjectNameError):
            sanitize_object_name(raw_name)


def test_sanitize_object_name_rejects_empty_control_and_useless_names() -> None:
    for raw_name in ["", "   ", "camera\x00.hdf5", "!!!"]:
        with pytest.raises(InvalidObjectNameError):
            sanitize_object_name(raw_name)


def test_sanitize_object_name_normalizes_non_path_punctuation() -> None:
    assert sanitize_object_name("front camera (raw).hdf5") == "front_camera_raw_.hdf5"


def test_build_object_key_uses_server_namespace_and_safe_name() -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000001")
    project_id = UUID("00000000-0000-4000-8000-000000000002")
    dataset_id = UUID("00000000-0000-4000-8000-000000000003")
    session_id = UUID("00000000-0000-4000-8000-000000000004")

    key = build_object_key(
        tenant_id=tenant_id,
        project_id=project_id,
        dataset_id=dataset_id,
        session_id=session_id,
        raw_object_name="front camera.hdf5",
        created_at=datetime(2026, 6, 24, 8, 30, tzinfo=UTC),
    )

    assert key == (
        "tenants/00000000-0000-4000-8000-000000000001/"
        "projects/00000000-0000-4000-8000-000000000002/"
        "datasets/00000000-0000-4000-8000-000000000003/"
        "2026/06/24/00000000-0000-4000-8000-000000000004/front_camera.hdf5"
    )
