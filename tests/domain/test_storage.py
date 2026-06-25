from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompletedObject,
    CompleteMultipartUploadRequest,
    CompletionPart,
    CreateMultipartUploadRequest,
    CreateMultipartUploadResult,
    DeleteObjectRequest,
    HeadObjectRequest,
    HeadObjectResult,
    ListedPart,
    ListedPartsPage,
    ListPartsRequest,
    ObjectStorage,
    PresignDownloadObjectRequest,
    PresignedDownloadUrl,
    PresignedPartUrl,
    PresignUploadPartRequest,
    StorageCapabilities,
    StorageError,
)

BUCKET: Final = "robot-data"
OBJECT_KEY: Final = "tenants/t/projects/p/datasets/d/2026/06/25/s/front_camera.hdf5"
UPLOAD_ID: Final = "upload-123"


def test_create_multipart_request_copies_and_freezes_metadata() -> None:
    metadata = {"original-name": "front_camera.hdf5"}

    request = CreateMultipartUploadRequest(
        bucket=BUCKET,
        object_key=OBJECT_KEY,
        metadata=metadata,
        encryption={"mode": "SSE_KMS"},
        object_lock={"mode": "GOVERNANCE"},
    )
    metadata["original-name"] = "mutated.hdf5"

    assert request.metadata["original-name"] == "front_camera.hdf5"
    assert request.encryption is not None
    assert request.encryption["mode"] == "SSE_KMS"
    with pytest.raises(TypeError):
        request.metadata["new"] = "blocked"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        request.bucket = "other"  # type: ignore[misc]


def test_presigned_part_url_requires_scoped_part_and_aware_expiry() -> None:
    expires_at = datetime.now(tz=UTC) + timedelta(minutes=15)

    url = PresignedPartUrl(
        part_number=1,
        url="http://localhost:19000/robot-data/key?partNumber=1&uploadId=upload-123",
        expires_at=expires_at,
        required_headers={"x-amz-checksum-sha256": "abc"},
    )

    assert url.part_number == 1
    assert url.required_headers["x-amz-checksum-sha256"] == "abc"

    with pytest.raises(ValueError, match="part_number"):
        PresignedPartUrl(part_number=0, url="http://example.test", expires_at=expires_at)
    with pytest.raises(ValueError, match="timezone-aware"):
        PresignedPartUrl(part_number=1, url="http://example.test", expires_at=datetime.now())


def test_listed_parts_page_sorts_parts_and_rejects_duplicates() -> None:
    second = ListedPart(part_number=2, etag='"etag-2"', size_bytes=5)
    first = ListedPart(part_number=1, etag='"etag-1"', size_bytes=5)

    page = ListedPartsPage(parts=(second, first), is_truncated=True, next_part_number_marker=2)

    assert [part.part_number for part in page.parts] == [1, 2]
    assert page.is_truncated is True
    assert page.next_part_number_marker == 2
    with pytest.raises(ValueError, match="duplicate"):
        ListedPartsPage(parts=(first, first))


def test_complete_request_sorts_completion_parts_and_requires_non_empty_unique_parts() -> None:
    request = CompleteMultipartUploadRequest(
        bucket=BUCKET,
        object_key=OBJECT_KEY,
        upload_id=UPLOAD_ID,
        parts=(
            CompletionPart(part_number=2, etag='"etag-2"'),
            CompletionPart(part_number=1, etag='"etag-1"'),
        ),
        preconditions={"if-none-match": "*"},
    )

    assert [part.part_number for part in request.parts] == [1, 2]
    assert request.preconditions["if-none-match"] == "*"
    with pytest.raises(ValueError, match="empty"):
        CompleteMultipartUploadRequest(
            bucket=BUCKET,
            object_key=OBJECT_KEY,
            upload_id=UPLOAD_ID,
            parts=(),
        )
    with pytest.raises(ValueError, match="duplicate"):
        CompleteMultipartUploadRequest(
            bucket=BUCKET,
            object_key=OBJECT_KEY,
            upload_id=UPLOAD_ID,
            parts=(CompletionPart(part_number=1, etag='"etag-1"'),) * 2,
        )


def test_storage_capabilities_model_required_flags() -> None:
    capabilities = StorageCapabilities(
        supports_native_checksums=True,
        supports_conditional_complete=True,
        supported_encryption_modes=frozenset({"SSE_S3", "SSE_KMS"}),
        supports_object_lock=True,
        supports_legal_hold=True,
        exposes_replication_metadata=True,
        supports_incomplete_multipart_listing=True,
    )

    assert capabilities.supports_native_checksums is True
    assert capabilities.supports_conditional_complete is True
    assert "SSE_KMS" in capabilities.supported_encryption_modes
    assert capabilities.supports_object_lock is True
    assert capabilities.supports_legal_hold is True
    assert capabilities.exposes_replication_metadata is True
    assert capabilities.supports_incomplete_multipart_listing is True


def test_storage_error_carries_provider_context_without_transport_dependency() -> None:
    error = StorageError(
        "storage throttled",
        operation="list_parts",
        provider_code="SlowDown",
        retryable=True,
    )

    assert str(error) == "storage throttled"
    assert error.operation == "list_parts"
    assert error.provider_code == "SlowDown"
    assert error.retryable is True


def test_object_storage_protocol_accepts_structural_implementation() -> None:
    class FakeStorage:
        capabilities = StorageCapabilities()

        def create_multipart_upload(
            self,
            request: CreateMultipartUploadRequest,
        ) -> CreateMultipartUploadResult:
            assert request.bucket == BUCKET
            return CreateMultipartUploadResult(upload_id=UPLOAD_ID)

        def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
            assert request.part_number == 1
            return PresignedPartUrl(
                part_number=request.part_number,
                url="http://localhost:19000/robot-data/key?partNumber=1&uploadId=upload-123",
                expires_at=datetime.now(tz=UTC) + timedelta(minutes=15),
            )

        def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
            assert request.upload_id == UPLOAD_ID
            return ListedPartsPage(
                parts=(ListedPart(part_number=1, etag='"etag-1"', size_bytes=5),)
            )

        def complete_multipart_upload(
            self,
            request: CompleteMultipartUploadRequest,
        ) -> CompletedObject:
            assert request.parts[0].part_number == 1
            return CompletedObject(
                bucket=request.bucket, object_key=request.object_key, etag='"final"'
            )

        def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
            assert request.upload_id == UPLOAD_ID

        def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
            return HeadObjectResult(
                bucket=request.bucket,
                object_key=request.object_key,
                etag='"final"',
                size_bytes=5,
            )

        def presign_download_object(
            self,
            request: PresignDownloadObjectRequest,
        ) -> PresignedDownloadUrl:
            return PresignedDownloadUrl(
                url=f"http://localhost:19000/{request.bucket}/{request.object_key}?download=1",
                expires_at=datetime.now(tz=UTC) + timedelta(minutes=15),
            )

        def delete_object(self, request: DeleteObjectRequest) -> None:
            assert request.object_key == OBJECT_KEY

    storage: ObjectStorage = FakeStorage()

    assert isinstance(storage, ObjectStorage)
    created = storage.create_multipart_upload(
        CreateMultipartUploadRequest(bucket=BUCKET, object_key=OBJECT_KEY),
    )
    assert created.upload_id == UPLOAD_ID
    page = storage.list_parts(
        ListPartsRequest(bucket=BUCKET, object_key=OBJECT_KEY, upload_id=UPLOAD_ID)
    )
    completed = storage.complete_multipart_upload(
        CompleteMultipartUploadRequest(
            bucket=BUCKET,
            object_key=OBJECT_KEY,
            upload_id=UPLOAD_ID,
            parts=(CompletionPart(part_number=1, etag=page.parts[0].etag),),
        ),
    )
    assert completed.etag == '"final"'
    download = storage.presign_download_object(
        PresignDownloadObjectRequest(bucket=BUCKET, object_key=OBJECT_KEY, expires_in_seconds=900)
    )
    storage.delete_object(DeleteObjectRequest(bucket=BUCKET, object_key=OBJECT_KEY))
    assert download.method == "GET"
