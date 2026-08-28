from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from botocore.exceptions import ClientError

from upload_control_plane.config import Settings
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompleteMultipartUploadRequest,
    CompletionPart,
    CreateMultipartUploadRequest,
    DeleteObjectRequest,
    HeadObjectRequest,
    ListPartsRequest,
    PresignDownloadObjectRequest,
    PresignUploadPartRequest,
    StorageAccessDeniedError,
    StorageConflictError,
    StorageError,
    StorageNotFoundError,
    StorageOperationError,
    StoragePreconditionFailedError,
)
from upload_control_plane.infrastructure.storage import S3ObjectStorage, build_s3_clients

BUCKET = "robot-data"
OBJECT_KEY = "tenants/t/projects/p/datasets/d/2026/06/25/session/front_camera.hdf5"
UPLOAD_ID = "upload-123"


class FakeS3Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.error: ClientError | None = None

    def create_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
        self._record("create_multipart_upload", kwargs)
        return {"UploadId": UPLOAD_ID}

    def generate_presigned_url(self, **kwargs: Any) -> str:
        self._record("generate_presigned_url", kwargs)
        return "http://localhost:19000/robot-data/object?partNumber=1&uploadId=upload-123"

    def list_parts(self, **kwargs: Any) -> dict[str, Any]:
        self._record("list_parts", kwargs)
        return {
            "Parts": [
                {
                    "PartNumber": 2,
                    "ETag": '"etag-2"',
                    "Size": 5,
                    "LastModified": datetime(2026, 6, 25, 4, 0, tzinfo=UTC),
                    "ChecksumSHA256": "sha256-part-2",
                },
                {"PartNumber": 1, "ETag": '"etag-1"', "Size": 5},
            ],
            "IsTruncated": True,
            "NextPartNumberMarker": 2,
        }

    def complete_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
        self._record("complete_multipart_upload", kwargs)
        return {"Bucket": BUCKET, "Key": OBJECT_KEY, "ETag": '"final"', "VersionId": "v1"}

    def abort_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
        self._record("abort_multipart_upload", kwargs)
        return {}

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self._record("delete_object", kwargs)
        return {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self._record("head_object", kwargs)
        return {
            "ETag": '"final"',
            "ContentLength": 10,
            "LastModified": datetime(2026, 6, 25, 4, 1, tzinfo=UTC),
            "Metadata": {"source": "test"},
            "ChecksumSHA256": "sha256-object",
            "ServerSideEncryption": "AES256",
            "ReplicationStatus": "COMPLETED",
        }

    def _record(self, name: str, kwargs: dict[str, Any]) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append((name, kwargs))


def test_build_s3_clients_uses_separate_internal_and_public_endpoints() -> None:
    settings = Settings(
        s3_endpoint_url="http://minio:9000",
        s3_public_endpoint_url="http://localhost:19000",
    )

    internal_client, presign_client = build_s3_clients(settings)

    assert internal_client.meta.endpoint_url == "http://minio:9000"
    assert presign_client.meta.endpoint_url == "http://localhost:19000"


def test_s3_storage_maps_create_presign_list_complete_abort_and_head() -> None:
    internal_client = FakeS3Client()
    presign_client = FakeS3Client()
    storage = S3ObjectStorage(
        internal_client=cast(Any, internal_client),
        presign_client=cast(Any, presign_client),
        now=lambda: datetime(2026, 6, 25, 4, 0, tzinfo=UTC),
    )

    created = storage.create_multipart_upload(
        CreateMultipartUploadRequest(
            bucket=BUCKET,
            object_key=OBJECT_KEY,
            content_type="application/x-hdf5",
            metadata={"original-name": "front_camera.hdf5"},
            checksum_algorithm="SHA256",
            encryption={"mode": "SSE_S3"},
        )
    )
    presigned = storage.presign_upload_part(
        PresignUploadPartRequest(
            bucket=BUCKET,
            object_key=OBJECT_KEY,
            upload_id=created.upload_id,
            part_number=1,
            expires_in_seconds=900,
            required_headers={"x-amz-checksum-sha256": "abc"},
        )
    )
    page = storage.list_parts(
        ListPartsRequest(
            bucket=BUCKET,
            object_key=OBJECT_KEY,
            upload_id=created.upload_id,
            part_number_marker=1,
            max_parts=1000,
        )
    )
    completed = storage.complete_multipart_upload(
        CompleteMultipartUploadRequest(
            bucket=BUCKET,
            object_key=OBJECT_KEY,
            upload_id=created.upload_id,
            parts=tuple(CompletionPart(part_number=p.part_number, etag=p.etag) for p in page.parts),
            preconditions={"if-none-match": "*"},
        )
    )
    storage.abort_multipart_upload(
        AbortMultipartUploadRequest(
            bucket=BUCKET, object_key=OBJECT_KEY, upload_id=created.upload_id
        )
    )
    head = storage.head_object(HeadObjectRequest(bucket=BUCKET, object_key=OBJECT_KEY))
    download = storage.presign_download_object(
        PresignDownloadObjectRequest(bucket=BUCKET, object_key=OBJECT_KEY, expires_in_seconds=300)
    )
    storage.delete_object(
        DeleteObjectRequest(bucket=BUCKET, object_key=OBJECT_KEY, version_id="v1")
    )

    assert created.upload_id == UPLOAD_ID
    assert presigned.url.startswith("http://localhost:19000/")
    assert download.method == "GET"
    assert presigned.required_headers["x-amz-checksum-sha256"] == "abc"
    assert [part.part_number for part in page.parts] == [1, 2]
    assert page.is_truncated is True
    assert page.next_part_number_marker == 2
    assert page.parts[1].checksum["sha256"] == "sha256-part-2"
    assert completed.etag == '"final"'
    assert head.size_bytes == 10
    assert head.metadata["source"] == "test"
    assert head.checksum["sha256"] == "sha256-object"
    assert internal_client.calls[0][1]["ServerSideEncryption"] == "AES256"
    assert internal_client.calls[1][1]["PartNumberMarker"] == 1
    assert internal_client.calls[2][1]["MultipartUpload"]["Parts"] == [
        {"PartNumber": 1, "ETag": '"etag-1"'},
        {"PartNumber": 2, "ETag": '"etag-2"'},
    ]
    assert internal_client.calls[2][1]["IfNoneMatch"] == "*"
    assert presign_client.calls[0][1]["ClientMethod"] == "upload_part"
    assert presign_client.calls[0][1]["HttpMethod"] == "PUT"
    assert presign_client.calls[1][1]["ClientMethod"] == "get_object"
    assert presign_client.calls[1][1]["HttpMethod"] == "GET"
    assert internal_client.calls[-1] == (
        "delete_object",
        {"Bucket": BUCKET, "Key": OBJECT_KEY, "VersionId": "v1"},
    )


@pytest.mark.parametrize(
    ("provider_code", "status_code", "expected_type", "retryable"),
    [
        ("AccessDenied", 403, StorageAccessDeniedError, False),
        ("NoSuchUpload", 404, StorageNotFoundError, False),
        ("PreconditionFailed", 412, StoragePreconditionFailedError, False),
        ("EntityTooSmall", 400, StorageConflictError, False),
        ("SlowDown", 503, StorageOperationError, True),
    ],
)
def test_s3_storage_maps_provider_errors(
    provider_code: str,
    status_code: int,
    expected_type: type[StorageError],
    retryable: bool,
) -> None:
    internal_client = FakeS3Client()
    internal_client.error = ClientError(
        cast(
            Any,
            {
                "Error": {"Code": provider_code, "Message": "provider failed"},
                "ResponseMetadata": {"HTTPStatusCode": status_code},
            },
        ),
        "HeadObject",
    )
    storage = S3ObjectStorage(
        internal_client=cast(Any, internal_client),
        presign_client=cast(Any, FakeS3Client()),
    )

    with pytest.raises(expected_type) as exc_info:
        storage.head_object(HeadObjectRequest(bucket=BUCKET, object_key=OBJECT_KEY))

    assert exc_info.value.operation == "head_object"
    assert exc_info.value.provider_code == provider_code
    assert exc_info.value.retryable is retryable
