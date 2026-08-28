from __future__ import annotations

import pytest

from upload_control_plane.application.dataset_validation_plugins import (
    Hdf5MetadataExtractor,
    ValidationWorkerError,
)
from upload_control_plane.infrastructure.db.models import Dataset

from .support import ValidationFakeObjectStorage


@pytest.mark.parametrize(
    ("filename", "content_type", "expected_format", "expected_preview_status"),
    [
        ("capture.hdf5", "application/octet-stream", "HDF5", "AVAILABLE"),
        ("trace.mcap", "application/octet-stream", "MCAP", "NOT_AVAILABLE"),
        ("robot.db3", "application/octet-stream", "ROS_BAG", "NOT_AVAILABLE"),
        ("camera.raw", "video/mp4", "VIDEO", "NOT_AVAILABLE"),
        ("archive.data", "application/zip", "ZIP", "NOT_AVAILABLE"),
        ("unknown.data", "application/octet-stream", "UNKNOWN", "NOT_AVAILABLE"),
    ],
)
def test_hdf5_metadata_extractor_infers_format_and_preview_status(
    filename: str,
    content_type: str,
    expected_format: str,
    expected_preview_status: str,
) -> None:
    storage = ValidationFakeObjectStorage()
    object_key = "validation/format-probe.bin"
    storage.heads[("robot-data", object_key)] = 128
    dataset = Dataset(
        bucket_name="robot-data",
        object_key=object_key,
        original_filename=filename,
        content_type=content_type,
        source_device_id=None,
        source_device_code=None,
    )

    extracted = Hdf5MetadataExtractor().extract(dataset, storage)

    assert extracted.extracted_metadata["format"] == expected_format
    assert extracted.preview_status == expected_preview_status


def test_hdf5_metadata_extractor_translates_storage_error_context() -> None:
    dataset = Dataset(
        bucket_name="robot-data",
        object_key="validation/missing.hdf5",
        original_filename="missing.hdf5",
        content_type="application/x-hdf5",
        source_device_id=None,
        source_device_code=None,
    )

    with pytest.raises(ValidationWorkerError) as exc_info:
        Hdf5MetadataExtractor().extract(dataset, ValidationFakeObjectStorage())

    assert exc_info.value.code == "storage.head_failed"
    assert exc_info.value.retryable is False
    assert exc_info.value.details == {
        "operation": "head_object",
        "provider_code": "404",
    }
