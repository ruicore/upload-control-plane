from upload_control_plane.application.datasets import (
    DatasetDetail,
    DatasetSummary,
    DatasetValidationResultItem,
    DatasetValidationStatusResult,
    DownloadUrlResult,
    RetryValidationResult,
    TagCategoryResult,
    TagResult,
)

from .schemas import (
    DatasetDetailResponse,
    DatasetSummaryResponse,
    DatasetValidationResponse,
    DatasetValidationResultResponse,
    DownloadUrlResponse,
    RetryValidationResponse,
    TagCategoryResponse,
    TagResponse,
)


def summary_response(item: DatasetSummary) -> DatasetSummaryResponse:
    return DatasetSummaryResponse(
        dataset_id=item.dataset_id,
        project_id=item.project_id,
        name=item.name,
        status=item.status,
        original_filename=item.original_filename,
        content_type=item.content_type,
        file_size_bytes=item.file_size_bytes,
        validation_status=item.validation_status,
        recovery_status=item.recovery_status,
        labels=list(item.labels),
        tag_ids=list(item.tag_ids),
        created_at=item.created_at,
        updated_at=item.updated_at,
        ready_at=item.ready_at,
        archived_at=item.archived_at,
        deleted_at=item.deleted_at,
    )


def detail_response(item: DatasetDetail) -> DatasetDetailResponse:
    return DatasetDetailResponse(
        **summary_response(item).model_dump(),
        bucket=item.bucket,
        object_key=item.object_key,
        object_etag=item.object_etag,
        object_size_bytes=item.object_size_bytes,
        object_version_id=item.object_version_id,
        checksum_sha256=item.checksum_sha256,
        source_device_id=item.source_device_id,
        source_device_code=item.source_device_code,
        preview_status=item.preview_status,
        preview_metadata=item.preview_metadata,
        metadata=item.metadata,
    )


def download_response(item: DownloadUrlResult) -> DownloadUrlResponse:
    return DownloadUrlResponse(
        dataset_id=item.dataset_id,
        method="GET",
        url=item.url,
        expires_at=item.expires_at,
    )


def validation_result_response(
    item: DatasetValidationResultItem,
) -> DatasetValidationResultResponse:
    return DatasetValidationResultResponse(
        validation_result_id=item.validation_result_id,
        status=item.status,
        validator_name=item.validator_name,
        validator_version=item.validator_version,
        extracted_metadata=item.extracted_metadata,
        errors=item.errors,
        started_at=item.started_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
    )


def validation_response(item: DatasetValidationStatusResult) -> DatasetValidationResponse:
    return DatasetValidationResponse(
        dataset_id=item.dataset_id,
        project_id=item.project_id,
        dataset_status=item.dataset_status,
        validation_status=item.validation_status,
        preview_status=item.preview_status,
        preview_metadata=item.preview_metadata,
        extracted_metadata=item.extracted_metadata,
        latest_result=validation_result_response(item.latest_result)
        if item.latest_result is not None
        else None,
        results=[validation_result_response(result) for result in item.results],
    )


def retry_validation_response(item: RetryValidationResult) -> RetryValidationResponse:
    return RetryValidationResponse(
        dataset_id=item.dataset_id,
        project_id=item.project_id,
        dataset_status=item.dataset_status,
        validation_status=item.validation_status,
        retry_queued=item.retry_queued,
    )


def category_response(item: TagCategoryResult) -> TagCategoryResponse:
    return TagCategoryResponse(
        category_id=item.category_id,
        project_id=item.project_id,
        name=item.name,
        color=item.color,
        sort_order=item.sort_order,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def tag_response(item: TagResult) -> TagResponse:
    return TagResponse(
        tag_id=item.tag_id,
        project_id=item.project_id,
        category_id=item.category_id,
        name=item.name,
        color=item.color,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
