from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Protocol

from upload_control_plane.domain.storage import HeadObjectRequest, ObjectStorage, StorageError
from upload_control_plane.infrastructure.db.models import Dataset


@dataclass(frozen=True, slots=True)
class ExtractedMetadata:
    preview_status: str
    preview_metadata: dict[str, Any]
    extracted_metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ValidationErrorDetail:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] | None = None

    def as_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class MetadataExtractor(Protocol):
    name: str
    version: str

    def extract(self, dataset: Dataset, storage: ObjectStorage) -> ExtractedMetadata:
        """Extract bounded metadata for a completed dataset object."""


class FileInspectionHook(Protocol):
    name: str
    version: str

    def inspect(
        self, dataset: Dataset, storage: ObjectStorage
    ) -> tuple[ValidationErrorDetail, ...]:
        """Return validation errors. Empty return means the object passed inspection."""


class NoopFileInspectionHook:
    name = "noop_file_inspection"
    version = "1"

    def inspect(
        self, dataset: Dataset, storage: ObjectStorage
    ) -> tuple[ValidationErrorDetail, ...]:
        _ = (dataset, storage)
        return ()


class Hdf5MetadataExtractor:
    """Lightweight HDF5 metadata extractor stub for dataset validation."""

    name = "hdf5_metadata_stub"
    version = "1"

    def extract(self, dataset: Dataset, storage: ObjectStorage) -> ExtractedMetadata:
        if dataset.bucket_name is None or dataset.object_key is None:
            raise ValidationWorkerError(
                "dataset.object_missing",
                "Dataset has no completed object location.",
                retryable=False,
            )
        try:
            head = storage.head_object(
                HeadObjectRequest(bucket=dataset.bucket_name, object_key=dataset.object_key)
            )
        except StorageError as exc:
            raise ValidationWorkerError(
                "storage.head_failed",
                "Storage object metadata could not be read during validation.",
                retryable=exc.retryable,
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc

        filename = dataset.original_filename or PurePosixPath(dataset.object_key).name
        suffix = PurePosixPath(filename).suffix.lower()
        format_name = _infer_format(filename=filename, content_type=dataset.content_type)
        preview_status = "AVAILABLE" if format_name == "HDF5" else "NOT_AVAILABLE"
        preview_metadata: dict[str, Any] = {
            "format": format_name,
            "filename": filename,
            "object_size_bytes": head.size_bytes,
            "extractor": self.name,
        }
        if format_name == "HDF5":
            preview_metadata["hdf5"] = {
                "parser": "stub",
                "groups": [],
                "datasets": [],
            }
        extracted_metadata: dict[str, Any] = {
            "format": format_name,
            "content_type": dataset.content_type,
            "filename_extension": suffix,
            "object": {
                "bucket": head.bucket,
                "key": head.object_key,
                "etag": head.etag,
                "size_bytes": head.size_bytes,
                "version_id": head.version_id,
                "last_modified": head.last_modified.isoformat()
                if head.last_modified is not None
                else None,
            },
            "source_device_id": str(dataset.source_device_id)
            if dataset.source_device_id is not None
            else None,
            "source_device_code": dataset.source_device_code,
            "extractor": {"name": self.name, "version": self.version},
        }
        return ExtractedMetadata(
            preview_status=preview_status,
            preview_metadata=preview_metadata,
            extracted_metadata=extracted_metadata,
        )


class ValidationWorkerError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.details = details or {}


def _infer_format(*, filename: str, content_type: str | None) -> str:
    lower_name = filename.lower()
    lower_content_type = (content_type or "").lower()
    if lower_name.endswith((".h5", ".hdf5")) or "hdf5" in lower_content_type:
        return "HDF5"
    if lower_name.endswith(".mcap"):
        return "MCAP"
    if lower_name.endswith((".bag", ".db3")):
        return "ROS_BAG"
    if lower_name.endswith((".mp4", ".mov", ".avi")) or lower_content_type.startswith("video/"):
        return "VIDEO"
    if lower_name.endswith(".zip") or lower_content_type == "application/zip":
        return "ZIP"
    return "UNKNOWN"
