from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, cast

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from upload_control_plane.config import Settings
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompletedObject,
    CompleteMultipartUploadRequest,
    CreateMultipartUploadRequest,
    CreateMultipartUploadResult,
    DeleteObjectRequest,
    HeadObjectRequest,
    HeadObjectResult,
    ListedPart,
    ListedPartsPage,
    ListPartsRequest,
    PresignDownloadObjectRequest,
    PresignedDownloadUrl,
    PresignedPartUrl,
    PresignUploadPartRequest,
    StorageAccessDeniedError,
    StorageCapabilities,
    StorageChecksumMismatchError,
    StorageConflictError,
    StorageError,
    StorageNotFoundError,
    StorageOperationError,
    StoragePreconditionFailedError,
)
from upload_control_plane.observability import record_storage_operation, storage_operation_started

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client
else:
    S3Client = Any


_RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_RETRYABLE_PROVIDER_CODES = {
    "InternalError",
    "OperationAborted",
    "RequestTimeout",
    "ServiceUnavailable",
    "SlowDown",
    "Throttling",
}


def build_s3_clients(settings: Settings) -> tuple[S3Client, S3Client]:
    """Build separate clients for internal control calls and public presigning."""

    return (
        _build_s3_client(settings, endpoint_url=settings.s3_endpoint_url),
        _build_s3_client(settings, endpoint_url=settings.s3_public_endpoint_url),
    )


def build_s3_object_storage(settings: Settings) -> S3ObjectStorage:
    internal_client, presign_client = build_s3_clients(settings)
    return S3ObjectStorage(
        internal_client=internal_client,
        presign_client=presign_client,
        capabilities=_capabilities_from_settings(settings),
    )


def _build_s3_client(settings: Settings, *, endpoint_url: str) -> S3Client:
    service_name: Literal["s3"] = "s3"
    config = Config(
        signature_version="s3v4",
        s3=cast(Any, {"addressing_style": settings.s3_addressing_style}),
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=3,
        read_timeout=10,
    )
    client = boto3.client(
        service_name,
        endpoint_url=endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=config,
    )
    return client


def _capabilities_from_settings(settings: Settings) -> StorageCapabilities:
    encryption_modes: set[str] = set()
    if settings.s3_default_encryption_mode and settings.s3_default_encryption_mode != "NONE":
        encryption_modes.add(settings.s3_default_encryption_mode)

    return StorageCapabilities(
        supports_native_checksums=settings.enable_storage_native_checksum,
        supports_conditional_complete=settings.s3_enable_conditional_complete,
        supported_encryption_modes=frozenset(encryption_modes),
        supports_object_lock=settings.s3_enable_object_lock,
        supports_legal_hold=settings.s3_enable_object_lock,
        exposes_replication_metadata=True,
        supports_incomplete_multipart_listing=True,
        supports_cors_inspection=True,
    )


class S3ObjectStorage:
    """boto3/botocore-backed ObjectStorage implementation for S3-compatible storage."""

    def __init__(
        self,
        *,
        internal_client: S3Client,
        presign_client: S3Client,
        capabilities: StorageCapabilities | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._internal_client = internal_client
        self._presign_client = presign_client
        self._capabilities = capabilities or StorageCapabilities(
            supports_incomplete_multipart_listing=True,
            supports_cors_inspection=True,
        )
        self._now = now or (lambda: datetime.now(tz=UTC))

    @property
    def capabilities(self) -> StorageCapabilities:
        return self._capabilities

    def create_multipart_upload(
        self,
        request: CreateMultipartUploadRequest,
    ) -> CreateMultipartUploadResult:
        kwargs: dict[str, Any] = {
            "Bucket": request.bucket,
            "Key": request.object_key,
        }
        if request.content_type is not None:
            kwargs["ContentType"] = request.content_type
        if request.metadata:
            kwargs["Metadata"] = dict(request.metadata)
        if request.checksum_algorithm is not None:
            kwargs["ChecksumAlgorithm"] = request.checksum_algorithm
        kwargs.update(_encryption_kwargs(request.encryption))
        kwargs.update(_object_lock_kwargs(request.object_lock))

        response = self._call(
            "create_multipart_upload",
            lambda: self._internal_client.create_multipart_upload(**kwargs),
        )
        return CreateMultipartUploadResult(upload_id=response["UploadId"])

    def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
        params: dict[str, Any] = {
            "Bucket": request.bucket,
            "Key": request.object_key,
            "UploadId": request.upload_id,
            "PartNumber": request.part_number,
        }
        if request.checksum_algorithm is not None:
            params["ChecksumAlgorithm"] = request.checksum_algorithm

        url = self._call(
            "presign_upload_part",
            lambda: self._presign_client.generate_presigned_url(
                ClientMethod="upload_part",
                Params=params,
                ExpiresIn=request.expires_in_seconds,
                HttpMethod="PUT",
            ),
        )
        return PresignedPartUrl(
            part_number=request.part_number,
            url=url,
            expires_at=self._now() + timedelta(seconds=request.expires_in_seconds),
            required_headers=request.required_headers,
        )

    def presign_download_object(
        self,
        request: PresignDownloadObjectRequest,
    ) -> PresignedDownloadUrl:
        url = self._call(
            "presign_download_object",
            lambda: self._presign_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": request.bucket, "Key": request.object_key},
                ExpiresIn=request.expires_in_seconds,
                HttpMethod="GET",
            ),
        )
        return PresignedDownloadUrl(
            url=url,
            expires_at=self._now() + timedelta(seconds=request.expires_in_seconds),
        )

    def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
        kwargs: dict[str, Any] = {
            "Bucket": request.bucket,
            "Key": request.object_key,
            "UploadId": request.upload_id,
        }
        if request.part_number_marker is not None:
            kwargs["PartNumberMarker"] = request.part_number_marker
        if request.max_parts is not None:
            kwargs["MaxParts"] = request.max_parts

        response = self._call("list_parts", lambda: self._internal_client.list_parts(**kwargs))
        return ListedPartsPage(
            parts=tuple(_listed_part(item) for item in response.get("Parts", ())),
            is_truncated=bool(response.get("IsTruncated", False)),
            next_part_number_marker=response.get("NextPartNumberMarker"),
        )

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        multipart_upload = {
            "Parts": [{"PartNumber": part.part_number, "ETag": part.etag} for part in request.parts]
        }
        kwargs: dict[str, Any] = {
            "Bucket": request.bucket,
            "Key": request.object_key,
            "UploadId": request.upload_id,
            "MultipartUpload": multipart_upload,
        }
        kwargs.update(_completion_checksum_kwargs(request.checksum))
        kwargs.update(_precondition_kwargs(request.preconditions))

        response = self._call(
            "complete_multipart_upload",
            lambda: self._internal_client.complete_multipart_upload(**kwargs),
        )
        return CompletedObject(
            bucket=response.get("Bucket", request.bucket),
            object_key=response.get("Key", request.object_key),
            etag=response.get("ETag"),
            version_id=response.get("VersionId"),
            size_bytes=None,
        )

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        self._call(
            "abort_multipart_upload",
            lambda: self._internal_client.abort_multipart_upload(
                Bucket=request.bucket,
                Key=request.object_key,
                UploadId=request.upload_id,
            ),
        )

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        response = self._call(
            "head_object",
            lambda: self._internal_client.head_object(
                Bucket=request.bucket,
                Key=request.object_key,
            ),
        )
        return HeadObjectResult(
            bucket=request.bucket,
            object_key=request.object_key,
            etag=response.get("ETag"),
            size_bytes=response["ContentLength"],
            last_modified=response.get("LastModified"),
            version_id=response.get("VersionId"),
            metadata=response.get("Metadata", {}),
            checksum=_checksum_from_response(response),
            encryption=_encryption_from_response(response),
            object_lock=_object_lock_from_response(response),
            replication=_replication_from_response(response),
        )

    def delete_object(self, request: DeleteObjectRequest) -> None:
        kwargs: dict[str, Any] = {"Bucket": request.bucket, "Key": request.object_key}
        if request.version_id is not None:
            kwargs["VersionId"] = request.version_id
        self._call("delete_object", lambda: self._internal_client.delete_object(**kwargs))

    def _call[T](self, operation: str, call: Callable[[], T]) -> T:
        started_at = storage_operation_started()
        try:
            result = call()
            record_storage_operation(operation, started_at)
            return result
        except ClientError as exc:
            mapped = _map_client_error(operation, exc)
            record_storage_operation(
                operation,
                started_at,
                error_code=mapped.provider_code or mapped.__class__.__name__,
            )
            raise mapped from exc
        except BotoCoreError as exc:
            record_storage_operation(operation, started_at, error_code=exc.__class__.__name__)
            raise StorageOperationError(
                f"storage operation failed: {operation}",
                operation=operation,
                provider_code=exc.__class__.__name__,
                retryable=True,
            ) from exc


def _listed_part(item: Mapping[str, Any]) -> ListedPart:
    return ListedPart(
        part_number=item["PartNumber"],
        etag=item["ETag"],
        size_bytes=item["Size"],
        last_modified=item.get("LastModified"),
        checksum=_checksum_from_response(item),
    )


def _map_client_error(operation: str, exc: ClientError) -> StorageError:
    error = exc.response.get("Error", {})
    metadata = exc.response.get("ResponseMetadata", {})
    provider_code = str(error.get("Code", "Unknown"))
    status_code = int(metadata.get("HTTPStatusCode", 0) or 0)
    message = str(error.get("Message") or f"storage operation failed: {operation}")
    retryable = status_code in _RETRYABLE_STATUS_CODES or provider_code in _RETRYABLE_PROVIDER_CODES

    if status_code in {401, 403} or provider_code in {"AccessDenied", "InvalidAccessKeyId"}:
        return StorageAccessDeniedError(
            message, operation=operation, provider_code=provider_code, retryable=retryable
        )
    if status_code == 404 or provider_code in {"NoSuchBucket", "NoSuchKey", "NoSuchUpload"}:
        return StorageNotFoundError(
            message, operation=operation, provider_code=provider_code, retryable=retryable
        )
    if provider_code in {"PreconditionFailed", "ConditionalRequestConflict"}:
        return StoragePreconditionFailedError(
            message, operation=operation, provider_code=provider_code, retryable=retryable
        )
    if provider_code in {"BadDigest", "ChecksumMismatch"}:
        return StorageChecksumMismatchError(
            message, operation=operation, provider_code=provider_code, retryable=retryable
        )
    if status_code == 409 or provider_code in {"BucketAlreadyExists", "EntityTooSmall"}:
        return StorageConflictError(
            message, operation=operation, provider_code=provider_code, retryable=retryable
        )
    return StorageOperationError(
        message, operation=operation, provider_code=provider_code, retryable=retryable
    )


def _encryption_kwargs(encryption: Mapping[str, str] | None) -> dict[str, str]:
    if not encryption:
        return {}
    mode = encryption.get("mode", "")
    if mode == "SSE_S3":
        return {"ServerSideEncryption": "AES256"}
    if mode == "SSE_KMS":
        kwargs = {"ServerSideEncryption": "aws:kms"}
        if kms_key_ref := encryption.get("kms_key_ref"):
            kwargs["SSEKMSKeyId"] = kms_key_ref
        return kwargs
    return dict(encryption)


def _object_lock_kwargs(object_lock: Mapping[str, str] | None) -> dict[str, str]:
    if not object_lock:
        return {}
    kwargs: dict[str, str] = {}
    if mode := object_lock.get("mode"):
        kwargs["ObjectLockMode"] = mode
    if retain_until := object_lock.get("retain_until_date"):
        kwargs["ObjectLockRetainUntilDate"] = retain_until
    if legal_hold := object_lock.get("legal_hold"):
        kwargs["ObjectLockLegalHoldStatus"] = legal_hold
    return kwargs


def _completion_checksum_kwargs(checksum: Mapping[str, str]) -> dict[str, str]:
    supported = {
        "crc32": "ChecksumCRC32",
        "crc32c": "ChecksumCRC32C",
        "crc64nvme": "ChecksumCRC64NVME",
        "sha1": "ChecksumSHA1",
        "sha256": "ChecksumSHA256",
    }
    return {field: checksum[key] for key, field in supported.items() if key in checksum}


def _precondition_kwargs(preconditions: Mapping[str, str]) -> dict[str, str]:
    kwargs: dict[str, str] = {}
    if if_none_match := preconditions.get("if-none-match"):
        kwargs["IfNoneMatch"] = if_none_match
    if if_match := preconditions.get("if-match"):
        kwargs["IfMatch"] = if_match
    return kwargs


def _checksum_from_response(response: Mapping[str, Any]) -> dict[str, str]:
    fields = {
        "ChecksumCRC32": "crc32",
        "ChecksumCRC32C": "crc32c",
        "ChecksumCRC64NVME": "crc64nvme",
        "ChecksumSHA1": "sha1",
        "ChecksumSHA256": "sha256",
    }
    return {name: response[field] for field, name in fields.items() if field in response}


def _encryption_from_response(response: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    if mode := response.get("ServerSideEncryption"):
        values["mode"] = str(mode)
    if kms_key_id := response.get("SSEKMSKeyId"):
        values["kms_key_ref"] = str(kms_key_id)
    return values


def _object_lock_from_response(response: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    if mode := response.get("ObjectLockMode"):
        values["mode"] = str(mode)
    if retain_until := response.get("ObjectLockRetainUntilDate"):
        values["retain_until_date"] = str(retain_until)
    if legal_hold := response.get("ObjectLockLegalHoldStatus"):
        values["legal_hold"] = str(legal_hold)
    return values


def _replication_from_response(response: Mapping[str, Any]) -> dict[str, str]:
    if status := response.get("ReplicationStatus"):
        return {"status": str(status)}
    return {}
