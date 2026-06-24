from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest
from botocore.exceptions import BotoCoreError, ClientError

from upload_control_plane.config import Settings
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompleteMultipartUploadRequest,
    CompletionPart,
    CreateMultipartUploadRequest,
    HeadObjectRequest,
    ListPartsRequest,
    PresignUploadPartRequest,
)
from upload_control_plane.infrastructure.storage import build_s3_clients, build_s3_object_storage

pytestmark = pytest.mark.integration


def _settings() -> Settings:
    return Settings(
        s3_endpoint_url="http://localhost:19000",
        s3_public_endpoint_url="http://localhost:19000",
        s3_bucket="robot-data",
    )


def _require_minio(settings: Settings) -> None:
    internal_client, _ = build_s3_clients(settings)
    try:
        internal_client.head_bucket(Bucket=settings.s3_bucket)
    except (BotoCoreError, ClientError) as exc:
        pytest.skip(f"MinIO bucket {settings.s3_bucket!r} is not available: {exc}")


def test_minio_multipart_presign_put_list_complete_head_and_read() -> None:
    settings = _settings()
    _require_minio(settings)
    storage = build_s3_object_storage(settings)
    internal_client, _ = build_s3_clients(settings)
    object_key = f"integration/{datetime.now(tz=UTC):%Y%m%d}/{uuid4()}.bin"
    body = b"x" * (5 * 1024 * 1024)
    upload_id: str | None = None

    try:
        created = storage.create_multipart_upload(
            CreateMultipartUploadRequest(
                bucket=settings.s3_bucket,
                object_key=object_key,
                content_type="application/octet-stream",
                metadata={"test": "storage-integration"},
            )
        )
        upload_id = created.upload_id
        presigned = storage.presign_upload_part(
            PresignUploadPartRequest(
                bucket=settings.s3_bucket,
                object_key=object_key,
                upload_id=upload_id,
                part_number=1,
                expires_in_seconds=900,
            )
        )

        parsed = urlparse(presigned.url)
        assert parsed.scheme == "http"
        assert parsed.netloc == "localhost:19000"

        put_response = httpx.put(presigned.url, content=body, timeout=30)
        assert put_response.status_code == 200
        assert put_response.headers["etag"]

        listed = storage.list_parts(
            ListPartsRequest(
                bucket=settings.s3_bucket,
                object_key=object_key,
                upload_id=upload_id,
            )
        )
        assert len(listed.parts) == 1
        assert listed.parts[0].part_number == 1
        assert listed.parts[0].size_bytes == len(body)

        completed = storage.complete_multipart_upload(
            CompleteMultipartUploadRequest(
                bucket=settings.s3_bucket,
                object_key=object_key,
                upload_id=upload_id,
                parts=(CompletionPart(part_number=1, etag=listed.parts[0].etag),),
            )
        )
        upload_id = None
        assert completed.bucket == settings.s3_bucket
        assert completed.object_key == object_key
        assert completed.etag is not None

        head = storage.head_object(
            HeadObjectRequest(bucket=settings.s3_bucket, object_key=object_key)
        )
        assert head.size_bytes == len(body)
        assert head.etag == completed.etag

        get_response = internal_client.get_object(Bucket=settings.s3_bucket, Key=object_key)
        stream = get_response["Body"]
        try:
            assert stream.read() == body
        finally:
            stream.close()
    finally:
        if upload_id is not None:
            with suppress(Exception):
                storage.abort_multipart_upload(
                    AbortMultipartUploadRequest(
                        bucket=settings.s3_bucket,
                        object_key=object_key,
                        upload_id=upload_id,
                    )
                )
        with suppress(Exception):
            internal_client.delete_object(Bucket=settings.s3_bucket, Key=object_key)
