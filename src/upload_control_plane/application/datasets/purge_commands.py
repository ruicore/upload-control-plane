from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.datasets.audit import DatasetAuditWriter
from upload_control_plane.application.datasets.contracts import DatasetDetail
from upload_control_plane.application.datasets.queries import DatasetQueryService
from upload_control_plane.application.errors import ApiError
from upload_control_plane.domain.datasets import DatasetStatus
from upload_control_plane.domain.storage import DeleteObjectRequest, ObjectStorage, StorageError
from upload_control_plane.infrastructure.db.models import Dataset, StoragePolicy


class DatasetPurgeCommandService:
    """Own interactive dataset purge policy, storage deletion, and metadata clearing."""

    def __init__(
        self,
        *,
        session: Session,
        storage: ObjectStorage,
        queries: DatasetQueryService,
        audit: DatasetAuditWriter,
    ) -> None:
        self._session = session
        self._storage = storage
        self._queries = queries
        self._audit = audit

    def purge_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        confirm_purge: bool,
    ) -> DatasetDetail:
        dataset = self._queries.get_dataset_model(
            tenant_id=tenant_id, project_id=project_id, dataset_id=dataset_id
        )
        if dataset.status != DatasetStatus.DELETED.value:
            raise self._invalid_state(dataset, "purge")
        policy = self._storage_policy_for_project(tenant_id=tenant_id, project_id=project_id)
        denial = self._purge_policy_denial(
            dataset,
            policy=policy,
            confirm_purge=confirm_purge,
        )
        if denial is not None:
            self._audit.add(
                dataset,
                actor=actor,
                action="dataset.purge",
                result="DENIED",
                request_id=request_id,
                metadata=denial,
            )
            self._session.commit()
            raise ApiError(
                status_code=409,
                code="dataset.purge_policy_denied",
                message="Dataset purge is denied by retention or storage governance policy.",
                details=denial,
            )
        before = self._audit.snapshot(dataset)
        if dataset.bucket_name and dataset.object_key:
            try:
                self._storage.delete_object(
                    DeleteObjectRequest(
                        bucket=dataset.bucket_name,
                        object_key=dataset.object_key,
                        version_id=dataset.object_version_id,
                    )
                )
            except StorageError as exc:
                raise ApiError(
                    status_code=502,
                    code="storage.delete_object_failed",
                    message="Storage object delete failed.",
                    details={"operation": exc.operation, "provider_code": exc.provider_code},
                ) from exc
        now = datetime.now(UTC)
        dataset.status = DatasetStatus.PURGED.value
        dataset.updated_at = now
        dataset.bucket_name = None
        dataset.object_key = None
        dataset.object_etag = None
        dataset.object_size_bytes = None
        dataset.object_version_id = None
        self._audit.add(
            dataset,
            actor=actor,
            action="dataset.purge",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit.snapshot(dataset),
        )
        self._session.commit()
        return self._queries.detail(dataset)

    def _storage_policy_for_project(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> StoragePolicy | None:
        project = self._queries.require_project(tenant_id=tenant_id, project_id=project_id)
        if project.storage_policy_id is None:
            return None
        policy = self._session.get(StoragePolicy, project.storage_policy_id)
        if policy is None or policy.tenant_id != tenant_id:
            return None
        return policy

    def _purge_policy_denial(
        self,
        dataset: Dataset,
        *,
        policy: StoragePolicy | None,
        confirm_purge: bool,
    ) -> dict[str, Any] | None:
        if not confirm_purge:
            return {"reason": "confirmation_required"}
        if dataset.deleted_at is None:
            return {"reason": "deleted_timestamp_missing"}
        if policy is None:
            return None
        if policy.legal_hold_default:
            return {"reason": "legal_hold", "storage_policy_id": str(policy.id)}
        if policy.object_lock_mode:
            return {
                "reason": "object_lock",
                "storage_policy_id": str(policy.id),
                "object_lock_mode": policy.object_lock_mode,
            }
        if policy.retention_days is not None:
            purge_after = dataset.deleted_at + timedelta(days=policy.retention_days)
            if datetime.now(UTC) < purge_after:
                return {
                    "reason": "retention_active",
                    "storage_policy_id": str(policy.id),
                    "purge_after": purge_after.isoformat(),
                    "retention_days": policy.retention_days,
                }
        return None

    def _invalid_state(self, dataset: Dataset, action: str) -> ApiError:
        return ApiError(
            status_code=409,
            code="dataset.invalid_state",
            message=f"Dataset is not in a state that allows {action}.",
            details={"dataset_status": dataset.status},
        )
