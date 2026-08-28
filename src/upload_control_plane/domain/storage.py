"""Object storage adapter boundary without provider SDK dependencies."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from upload_control_plane.domain.parts import MAX_PART_COUNT

StorageMetadata = Mapping[str, str]


class StorageError(RuntimeError):
    """Base exception for storage adapter failures."""

    def __init__(
        self,
        message: str,
        *,
        operation: str | None = None,
        provider_code: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.provider_code = provider_code
        self.retryable = retryable


class StorageConfigurationError(StorageError):
    """Raised when storage settings or capabilities are invalid."""


class StorageOperationError(StorageError):
    """Raised for provider operation failures that do not fit a narrower type."""


class StorageAccessDeniedError(StorageError):
    """Raised when the storage provider denies the operation."""


class StorageNotFoundError(StorageError):
    """Raised when an object or multipart upload cannot be found."""


class StorageConflictError(StorageError):
    """Raised when provider state conflicts with the requested operation."""


class StoragePreconditionFailedError(StorageConflictError):
    """Raised when a conditional write or complete precondition fails."""


class StorageChecksumMismatchError(StorageOperationError):
    """Raised when storage-native checksum validation fails."""


class StorageCapabilityUnsupportedError(StorageConfigurationError):
    """Raised when a policy requests a capability the adapter cannot provide."""


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be empty")


def _require_positive(value: int, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _require_part_number(value: int) -> None:
    if value < 1 or value > MAX_PART_COUNT:
        raise ValueError("part_number must be in the range 1..10000")


def _immutable_metadata(value: StorageMetadata | None, field_name: str) -> StorageMetadata:
    if value is None:
        return MappingProxyType({})
    copied: dict[str, str] = {}
    for key, item in value.items():
        _require_non_empty(key, f"{field_name} key")
        copied[key] = item
    return MappingProxyType(copied)


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class StorageCapabilities:
    supports_native_checksums: bool = False
    supports_conditional_complete: bool = False
    supported_encryption_modes: frozenset[str] = frozenset()
    supports_object_lock: bool = False
    supports_legal_hold: bool = False
    exposes_replication_metadata: bool = False
    supports_incomplete_multipart_listing: bool = False
    supports_cors_inspection: bool = False


@dataclass(frozen=True, slots=True)
class CreateMultipartUploadRequest:
    bucket: str
    object_key: str
    content_type: str | None = None
    metadata: StorageMetadata = MappingProxyType({})
    checksum_algorithm: str | None = None
    encryption: StorageMetadata | None = None
    object_lock: StorageMetadata | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata, "metadata"))
        object.__setattr__(self, "encryption", _immutable_metadata(self.encryption, "encryption"))
        object.__setattr__(
            self, "object_lock", _immutable_metadata(self.object_lock, "object_lock")
        )


@dataclass(frozen=True, slots=True)
class CreateMultipartUploadResult:
    upload_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.upload_id, "upload_id")


@dataclass(frozen=True, slots=True)
class PresignUploadPartRequest:
    bucket: str
    object_key: str
    upload_id: str
    part_number: int
    expires_in_seconds: int
    checksum_algorithm: str | None = None
    required_headers: StorageMetadata = MappingProxyType({})

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")
        _require_non_empty(self.upload_id, "upload_id")
        _require_part_number(self.part_number)
        _require_positive(self.expires_in_seconds, "expires_in_seconds")
        object.__setattr__(
            self,
            "required_headers",
            _immutable_metadata(self.required_headers, "required_headers"),
        )


@dataclass(frozen=True, slots=True)
class PresignedPartUrl:
    part_number: int
    url: str
    expires_at: datetime
    required_headers: StorageMetadata = MappingProxyType({})

    def __post_init__(self) -> None:
        _require_part_number(self.part_number)
        _require_non_empty(self.url, "url")
        _require_aware_datetime(self.expires_at, "expires_at")
        object.__setattr__(
            self,
            "required_headers",
            _immutable_metadata(self.required_headers, "required_headers"),
        )


@dataclass(frozen=True, slots=True)
class PresignDownloadObjectRequest:
    bucket: str
    object_key: str
    expires_in_seconds: int

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")
        _require_positive(self.expires_in_seconds, "expires_in_seconds")


@dataclass(frozen=True, slots=True)
class PresignedDownloadUrl:
    url: str
    expires_at: datetime
    method: str = "GET"

    def __post_init__(self) -> None:
        _require_non_empty(self.url, "url")
        _require_non_empty(self.method, "method")
        _require_aware_datetime(self.expires_at, "expires_at")


@dataclass(frozen=True, slots=True)
class ListedPart:
    part_number: int
    etag: str
    size_bytes: int
    last_modified: datetime | None = None
    checksum: StorageMetadata = MappingProxyType({})

    def __post_init__(self) -> None:
        _require_part_number(self.part_number)
        _require_non_empty(self.etag, "etag")
        _require_positive(self.size_bytes, "size_bytes")
        if self.last_modified is not None:
            _require_aware_datetime(self.last_modified, "last_modified")
        object.__setattr__(self, "checksum", _immutable_metadata(self.checksum, "checksum"))


@dataclass(frozen=True, slots=True)
class ListPartsRequest:
    bucket: str
    object_key: str
    upload_id: str
    part_number_marker: int | None = None
    max_parts: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")
        _require_non_empty(self.upload_id, "upload_id")
        if self.part_number_marker is not None and (
            self.part_number_marker < 0 or self.part_number_marker > MAX_PART_COUNT
        ):
            raise ValueError("part_number_marker must be in the range 0..10000")
        if self.max_parts is not None:
            _require_positive(self.max_parts, "max_parts")


@dataclass(frozen=True, slots=True)
class ListedPartsPage:
    parts: tuple[ListedPart, ...]
    is_truncated: bool = False
    next_part_number_marker: int | None = None

    def __post_init__(self) -> None:
        sorted_parts = tuple(sorted(self.parts, key=lambda part: part.part_number))
        if len({part.part_number for part in sorted_parts}) != len(sorted_parts):
            raise ValueError("parts must not contain duplicate part numbers")
        object.__setattr__(self, "parts", sorted_parts)
        if self.next_part_number_marker is not None and (
            self.next_part_number_marker < 0 or self.next_part_number_marker > MAX_PART_COUNT
        ):
            raise ValueError("next_part_number_marker must be in the range 0..10000")


@dataclass(frozen=True, slots=True)
class CompletionPart:
    part_number: int
    etag: str
    checksum: StorageMetadata = MappingProxyType({})

    def __post_init__(self) -> None:
        _require_part_number(self.part_number)
        _require_non_empty(self.etag, "etag")
        object.__setattr__(self, "checksum", _immutable_metadata(self.checksum, "checksum"))


@dataclass(frozen=True, slots=True)
class CompleteMultipartUploadRequest:
    bucket: str
    object_key: str
    upload_id: str
    parts: tuple[CompletionPart, ...]
    checksum: StorageMetadata = MappingProxyType({})
    preconditions: StorageMetadata = MappingProxyType({})

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")
        _require_non_empty(self.upload_id, "upload_id")
        sorted_parts = tuple(sorted(self.parts, key=lambda part: part.part_number))
        if not sorted_parts:
            raise ValueError("parts must not be empty")
        if len({part.part_number for part in sorted_parts}) != len(sorted_parts):
            raise ValueError("parts must not contain duplicate part numbers")
        object.__setattr__(self, "parts", sorted_parts)
        object.__setattr__(self, "checksum", _immutable_metadata(self.checksum, "checksum"))
        object.__setattr__(
            self,
            "preconditions",
            _immutable_metadata(self.preconditions, "preconditions"),
        )


@dataclass(frozen=True, slots=True)
class CompletedObject:
    bucket: str
    object_key: str
    etag: str | None = None
    version_id: str | None = None
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")


@dataclass(frozen=True, slots=True)
class HeadObjectResult:
    bucket: str
    object_key: str
    etag: str | None
    size_bytes: int
    last_modified: datetime | None = None
    version_id: str | None = None
    metadata: StorageMetadata = MappingProxyType({})
    checksum: StorageMetadata = MappingProxyType({})
    encryption: StorageMetadata = MappingProxyType({})
    object_lock: StorageMetadata = MappingProxyType({})
    replication: StorageMetadata = MappingProxyType({})

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")
        if self.etag is not None:
            _require_non_empty(self.etag, "etag")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must not be negative")
        if self.last_modified is not None:
            _require_aware_datetime(self.last_modified, "last_modified")
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata, "metadata"))
        object.__setattr__(self, "checksum", _immutable_metadata(self.checksum, "checksum"))
        object.__setattr__(self, "encryption", _immutable_metadata(self.encryption, "encryption"))
        object.__setattr__(
            self, "object_lock", _immutable_metadata(self.object_lock, "object_lock")
        )
        object.__setattr__(
            self, "replication", _immutable_metadata(self.replication, "replication")
        )


@dataclass(frozen=True, slots=True)
class HeadObjectRequest:
    bucket: str
    object_key: str

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")


@dataclass(frozen=True, slots=True)
class DeleteObjectRequest:
    bucket: str
    object_key: str
    version_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")
        if self.version_id is not None:
            _require_non_empty(self.version_id, "version_id")


@dataclass(frozen=True, slots=True)
class AbortMultipartUploadRequest:
    bucket: str
    object_key: str
    upload_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.bucket, "bucket")
        _require_non_empty(self.object_key, "object_key")
        _require_non_empty(self.upload_id, "upload_id")


@runtime_checkable
class ObjectStorage(Protocol):
    @property
    def capabilities(self) -> StorageCapabilities:
        """Return provider features that application services must branch on."""

    def create_multipart_upload(
        self,
        request: CreateMultipartUploadRequest,
    ) -> CreateMultipartUploadResult:
        """Create a storage-side multipart upload and return its provider upload ID."""

    def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
        """Create a scoped PUT URL for one multipart part."""

    def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
        """List a page of uploaded parts for an in-progress multipart upload."""

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        """Complete an upload from storage-observed parts supplied by application services."""

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        """Abort an in-progress multipart upload without deleting completed objects."""

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        """Read metadata for a completed object."""

    def presign_download_object(
        self,
        request: PresignDownloadObjectRequest,
    ) -> PresignedDownloadUrl:
        """Create a scoped GET URL for a completed object."""

    def delete_object(self, request: DeleteObjectRequest) -> None:
        """Delete a completed object after application lifecycle policy allows purge."""
