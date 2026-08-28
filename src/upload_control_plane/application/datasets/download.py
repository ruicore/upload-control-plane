from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.datasets.audit import DatasetAuditWriter
from upload_control_plane.application.datasets.queries import DatasetQueryService
from upload_control_plane.application.errors import ApiError
from upload_control_plane.config import Settings
from upload_control_plane.domain.datasets import (
    DatasetStatus,
    RecoveryStatus,
    ValidationStatus,
    dataset_allows_exposure,
)
from upload_control_plane.domain.storage import (
    ObjectStorage,
    PresignDownloadObjectRequest,
    StorageError,
)


@dataclass(frozen=True, slots=True)
class DownloadUrlResult:
    dataset_id: uuid.UUID
    method: str
    url: str
    expires_at: datetime


class DatasetDownloadService:
    """Own dataset exposure policy, download presigning, and download audit."""

    def __init__(
        self,
        *,
        session: Session,
        storage: ObjectStorage,
        settings: Settings,
        queries: DatasetQueryService,
        audit: DatasetAuditWriter,
    ) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._queries = queries
        self._audit = audit

    def create_download_url(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        expires_in_seconds: int,
    ) -> DownloadUrlResult:
        dataset = self._queries.get_dataset_model(
            tenant_id=tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
        if not dataset_allows_exposure(
            DatasetStatus(dataset.status),
            ValidationStatus(dataset.validation_status),
            RecoveryStatus(dataset.recovery_status),
        ):
            self._audit.add(
                dataset,
                actor=actor,
                action="dataset.download_url",
                result="DENIED",
                request_id=request_id,
                metadata={"reason": "exposure_policy"},
            )
            self._session.commit()
            raise ApiError(
                status_code=409,
                code="dataset.exposure_denied",
                message="Dataset is not available for download in its current exposure state.",
                details={
                    "dataset_status": dataset.status,
                    "validation_status": dataset.validation_status,
                    "recovery_status": dataset.recovery_status,
                },
            )
        if dataset.bucket_name is None or dataset.object_key is None:
            self._audit.add(
                dataset,
                actor=actor,
                action="dataset.download_url",
                result="DENIED",
                request_id=request_id,
                metadata={"reason": "object_missing"},
            )
            self._session.commit()
            raise ApiError(
                status_code=409,
                code="dataset.object_missing",
                message="Dataset has no completed storage object.",
            )
        bounded_expiry = min(expires_in_seconds, self._settings.max_download_url_expiry_seconds)
        try:
            presigned = self._storage.presign_download_object(
                PresignDownloadObjectRequest(
                    bucket=dataset.bucket_name,
                    object_key=dataset.object_key,
                    expires_in_seconds=bounded_expiry,
                )
            )
        except StorageError as exc:
            raise ApiError(
                status_code=502,
                code="storage.download_presign_failed",
                message="Storage download URL presign failed.",
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc
        self._audit.add(
            dataset,
            actor=actor,
            action="dataset.download_url",
            result="SUCCESS",
            request_id=request_id,
            metadata={"expires_at": presigned.expires_at.isoformat()},
        )
        self._session.commit()
        return DownloadUrlResult(
            dataset_id=dataset.id,
            method=presigned.method,
            url=presigned.url,
            expires_at=presigned.expires_at,
        )
