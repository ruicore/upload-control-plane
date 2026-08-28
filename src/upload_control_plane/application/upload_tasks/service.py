from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from upload_control_plane.application.errors import ApiError
from upload_control_plane.application.storage_backpressure import reject_if_storage_backpressure
from upload_control_plane.application.upload_tasks.contracts import (
    CreatedUploadObject,
    CreatedUploadTask,
    CreateUploadTaskCommand,
)
from upload_control_plane.application.upload_tasks.idempotency import UploadTaskIdempotency
from upload_control_plane.application.upload_tasks.provisioning import (
    UploadObjectSessionProvisioner,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.storage import (
    ObjectStorage,
    StorageCapabilities,
    StorageError,
)
from upload_control_plane.infrastructure.db.models import (
    Project,
    StoragePolicy,
    UploadTask,
)


class UploadTaskCreationService:
    """Application boundary for transactional upload task creation."""

    def __init__(self, *, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._idempotency = UploadTaskIdempotency(session)
        self._provisioner = UploadObjectSessionProvisioner(session=session, storage=storage)

    def create_upload_task(self, command: CreateUploadTaskCommand) -> CreatedUploadTask:
        fingerprint = self._idempotency.fingerprint(command)
        existing = self._idempotency.resolve(command, fingerprint)
        if existing is not None:
            return existing

        reject_if_storage_backpressure(self._settings)

        now = datetime.now(UTC)
        storage_policy = self._select_storage_policy(command)
        self._validate_quota_before_storage(command)
        _validate_storage_policy_capabilities(storage_policy, self._storage.capabilities)

        task = UploadTask(
            id=uuid.uuid4(),
            tenant_id=command.tenant_id,
            project_id=command.project_id,
            storage_policy_id=storage_policy.id,
            status="PENDING",
            task_initiator=command.task_initiator,
            source_device_id=command.source_device_id,
            source_device_code=command.source_device_code,
            object_count=len(command.objects),
            completed_object_count=0,
            failed_object_count=0,
            total_size_bytes=sum(item.file_size_bytes for item in command.objects),
            uploaded_size_bytes=0,
            idempotency_key=command.idempotency_key,
            metadata_=dict(command.metadata),
            created_by=command.actor.subject_id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(task)
        self._session.flush()

        created_objects: list[CreatedUploadObject] = []
        try:
            for item in command.objects:
                created_objects.append(
                    self._provisioner.provision(
                        command=command,
                        storage_policy=storage_policy,
                        task=task,
                        item=item,
                        now=now,
                        fingerprint=fingerprint,
                    )
                )
        except StorageError as exc:
            if _is_kms_initiation_failure(storage_policy, exc):
                raise ApiError(
                    status_code=503,
                    code="storage_policy.kms_unavailable",
                    message="Storage policy requires KMS, but KMS is unavailable.",
                    details={"reason": "kms_provider_unavailable"},
                ) from exc
            raise ApiError(
                status_code=502,
                code="storage.multipart_initiation_failed",
                message="Storage multipart upload initiation failed.",
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc

        result = CreatedUploadTask(
            task_id=task.id,
            project_id=task.project_id,
            status=task.status,
            object_count=task.object_count,
            total_size_bytes=task.total_size_bytes or 0,
            objects=tuple(created_objects),
            created_at=task.created_at,
        )
        self._idempotency.store_response(command, fingerprint, result)
        self._session.commit()
        return result

    def _select_storage_policy(self, command: CreateUploadTaskCommand) -> StoragePolicy:
        project = self._session.get(Project, command.project_id)
        if (
            project is None
            or project.tenant_id != command.tenant_id
            or project.deleted_at is not None
        ):
            raise ApiError(status_code=404, code="project.not_found", message="Project not found.")

        policy_id = command.storage_policy_id or project.storage_policy_id
        if policy_id is None:
            raise ApiError(
                status_code=409,
                code="storage_policy.missing_default",
                message="Project has no default storage policy.",
            )
        policy = self._session.get(StoragePolicy, policy_id)
        if policy is None or policy.tenant_id != command.tenant_id or policy.status != "ACTIVE":
            raise ApiError(
                status_code=404,
                code="storage_policy.not_found",
                message="Storage policy not found.",
            )
        return policy

    def _validate_quota_before_storage(self, command: CreateUploadTaskCommand) -> None:
        if len(command.objects) > self._settings.max_open_upload_tasks_per_project:
            raise ApiError(
                status_code=413,
                code="upload_task.too_many_objects",
                message="Upload task contains too many objects.",
            )

        open_tasks = self._count(
            select(func.count())
            .select_from(UploadTask)
            .where(UploadTask.tenant_id == command.tenant_id)
            .where(UploadTask.project_id == command.project_id)
            .where(UploadTask.status.in_(("CREATED", "PENDING", "PROCESSING", "PAUSED")))
        )
        if open_tasks >= self._settings.max_open_upload_tasks_per_project:
            raise ApiError(
                status_code=429,
                code="quota.open_upload_tasks_exceeded",
                message="Project has too many open upload tasks.",
            )

        requested_bytes = sum(item.file_size_bytes for item in command.objects)
        if (
            self._settings.max_bytes_per_project is not None
            and requested_bytes > self._settings.max_bytes_per_project
        ):
            raise ApiError(
                status_code=413,
                code="quota.project_bytes_exceeded",
                message="Requested upload exceeds project byte quota.",
            )
        if (
            self._settings.max_bytes_per_tenant is not None
            and requested_bytes > self._settings.max_bytes_per_tenant
        ):
            raise ApiError(
                status_code=413,
                code="quota.tenant_bytes_exceeded",
                message="Requested upload exceeds tenant byte quota.",
            )

    def _count(self, statement: Select[tuple[int]]) -> int:
        return int(self._session.execute(statement).scalar_one())


def _validate_storage_policy_capabilities(
    storage_policy: StoragePolicy,
    capabilities: StorageCapabilities,
) -> None:
    if storage_policy.encryption_mode != "SSE_KMS":
        return

    if not storage_policy.kms_key_ref:
        raise ApiError(
            status_code=503,
            code="storage_policy.kms_unavailable",
            message="Storage policy requires KMS, but KMS configuration is unavailable.",
            details={"reason": "missing_kms_key_ref"},
        )
    if "SSE_KMS" not in capabilities.supported_encryption_modes:
        raise ApiError(
            status_code=503,
            code="storage_policy.kms_unavailable",
            message="Storage policy requires KMS, but the storage adapter cannot provide it.",
            details={"reason": "unsupported_encryption_mode"},
        )


def _is_kms_initiation_failure(storage_policy: StoragePolicy, exc: StorageError) -> bool:
    if storage_policy.encryption_mode != "SSE_KMS":
        return False
    if exc.operation != "create_multipart_upload":
        return False
    provider_code = (exc.provider_code or "").lower()
    return "kms" in provider_code
