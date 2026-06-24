# Storage Adapter and Object Keys

Previous: [Database Schema](07-database-schema.md) | Index: [README](README.md) | Next: [Security and Governance](09-security-governance.md)

## 15. Storage Adapter Interface

Core application logic must depend on an interface, not directly on boto3.

### 15.1 Interface

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

@dataclass(frozen=True)
class CreateMultipartUploadResult:
    upload_id: str

@dataclass(frozen=True)
class PresignedPartUrl:
    part_number: int
    url: str
    expires_at: datetime
    required_headers: dict[str, str]

@dataclass(frozen=True)
class StoragePart:
    part_number: int
    etag: str
    size_bytes: int
    last_modified: datetime | None = None

@dataclass(frozen=True)
class CompleteMultipartUploadResult:
    bucket: str
    object_key: str
    etag: str | None
    version_id: str | None
    size_bytes: int | None

class ObjectStorage(Protocol):
    def create_multipart_upload(
        self,
        *,
        bucket: str,
        object_key: str,
        content_type: str | None,
        metadata: dict[str, str],
        checksum_algorithm: str | None = None,
        encryption: dict[str, str] | None = None,
        object_lock: dict[str, str] | None = None,
    ) -> CreateMultipartUploadResult:
        ...

    def presign_upload_part(
        self,
        *,
        bucket: str,
        object_key: str,
        upload_id: str,
        part_number: int,
        expires_in_seconds: int,
        checksum_algorithm: str | None = None,
        required_headers: dict[str, str] | None = None,
    ) -> PresignedPartUrl:
        ...

    def list_parts(
        self,
        *,
        bucket: str,
        object_key: str,
        upload_id: str,
    ) -> list[StoragePart]:
        ...

    def complete_multipart_upload(
        self,
        *,
        bucket: str,
        object_key: str,
        upload_id: str,
        parts: list[StoragePart],
        checksum: dict[str, str] | None = None,
        preconditions: dict[str, str] | None = None,
    ) -> CompleteMultipartUploadResult:
        ...

    def abort_multipart_upload(
        self,
        *,
        bucket: str,
        object_key: str,
        upload_id: str,
    ) -> None:
        ...

    def head_object(
        self,
        *,
        bucket: str,
        object_key: str,
    ) -> dict:
        ...
```

Adapter capability flags should describe provider support for:

- Storage-native multipart checksums.
- Conditional `CompleteMultipartUpload`.
- Server-side encryption modes.
- Object lock and legal hold headers.
- Listing incomplete multipart uploads.
- Bucket or object replication status metadata.
- Browser CORS policy inspection if the provider exposes it.

Application services must branch on these explicit capabilities instead of assuming AWS S3 and MinIO behavior are identical.

### 15.2 MinIO/S3 adapter implementation

Use boto3 against MinIO because boto3 exposes low-level S3 multipart APIs and presigned URL generation for `upload_part`.

Client initialization:

```python
import boto3
from botocore.config import Config

s3_client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name=settings.s3_region,
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 3, "mode": "standard"},
    ),
)
```

Create multipart upload:

```python
response = s3_client.create_multipart_upload(
    Bucket=bucket,
    Key=object_key,
    ContentType=content_type,
    Metadata=metadata,
    # Optional provider-specific fields:
    # ChecksumAlgorithm=checksum_algorithm,
    # ServerSideEncryption="aws:kms",
    # SSEKMSKeyId=kms_key_ref,
)
upload_id = response["UploadId"]
```

Presign upload part:

```python
url = s3_client.generate_presigned_url(
    ClientMethod="upload_part",
    Params={
        "Bucket": bucket,
        "Key": object_key,
        "UploadId": upload_id,
        "PartNumber": part_number,
        # Include checksum or SSE-C headers only when policy requires
        # them and the client will send the same headers on PUT.
    },
    ExpiresIn=expires_in_seconds,
    HttpMethod="PUT",
)
```

List parts with pagination:

```python
parts: list[StoragePart] = []
part_number_marker = None

while True:
    kwargs = {
        "Bucket": bucket,
        "Key": object_key,
        "UploadId": upload_id,
    }
    if part_number_marker is not None:
        kwargs["PartNumberMarker"] = part_number_marker

    response = s3_client.list_parts(**kwargs)

    for item in response.get("Parts", []):
        parts.append(
            StoragePart(
                part_number=item["PartNumber"],
                etag=item["ETag"],
                size_bytes=item["Size"],
                last_modified=item.get("LastModified"),
            )
        )

    if not response.get("IsTruncated"):
        break

    part_number_marker = response.get("NextPartNumberMarker")

return sorted(parts, key=lambda p: p.part_number)
```

Complete multipart upload:

```python
response = s3_client.complete_multipart_upload(
    Bucket=bucket,
    Key=object_key,
    UploadId=upload_id,
    # Optional overwrite protection:
    # IfNoneMatch="*",
    MultipartUpload={
        "Parts": [
            {"PartNumber": p.part_number, "ETag": p.etag}
            for p in sorted(parts, key=lambda x: x.part_number)
        ]
    },
)
```

Abort multipart upload:

```python
s3_client.abort_multipart_upload(
    Bucket=bucket,
    Key=object_key,
    UploadId=upload_id,
)
```

---


## 16. Object Key Strategy

Object keys must be generated by the backend.

Recommended pattern:

```text
tenants/{tenant_slug_or_id}/projects/{project_id}/datasets/{dataset_id}/yyyy/mm/dd/{session_id}/{safe_filename}
```

Example:

```text
tenants/tnt_123/projects/prj_456/datasets/ds_789/2026/06/10/2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9/front_camera.hdf5
```

Rules:

- Never trust client-provided paths.
- Strip directory components from filename.
- Normalize Unicode if needed.
- Replace unsupported characters with `_`.
- Preserve useful extension when safe.
- Enforce maximum object key length.
- Include `project_id`, `dataset_id`, and `session_id` to avoid collisions and support audit/debug workflows.
- Prefix by tenant to enforce namespace isolation.

Recommended filename sanitizer behavior:

```text
"../../etc/passwd"        -> "passwd"
"front camera.mp4"        -> "front_camera.mp4"
"璁惧鏃ュ織 01.jsonl"       -> "璁惧鏃ュ織_01.jsonl" or ASCII-safe fallback
""                        -> "upload.bin"
```

---

