from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import AuthenticatedActor
from upload_control_plane.api.errors import ApiError
from upload_control_plane.application.storage_backpressure import reject_if_storage_backpressure
from upload_control_plane.config import Settings
from upload_control_plane.domain.fingerprints import assert_json_value, generate_request_fingerprint
from upload_control_plane.domain.object_keys import build_object_key
from upload_control_plane.domain.storage import (
    CreateMultipartUploadRequest,
    ObjectStorage,
    StorageCapabilities,
    StorageError,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    IdempotencyRecord,
    Project,
    StoragePolicy,
    UploadEvent,
    UploadObject,
    UploadSession,
    UploadTask,
)


@dataclass(frozen=True, slots=True)
class CreateUploadObjectInput:
    dataset_name: str
    object_name: str
    file_size_bytes: int
    content_type: str | None
    part_size_bytes: int
    part_count: int
    checksum_sha256: str | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CreateUploadTaskCommand:
    tenant_id: uuid.UUID
    project_id: uuid.UUID
    actor: AuthenticatedActor
    request_path: str
    request_body: dict[str, Any]
    request_id: str | None
    task_name: str
    task_initiator: str
    source_device_id: uuid.UUID | None
    source_device_code: str | None
    storage_policy_id: uuid.UUID | None
    idempotency_key: str | None
    objects: tuple[CreateUploadObjectInput, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class CreatedUploadObject:
    object_id: uuid.UUID
    dataset_id: uuid.UUID
    session_id: uuid.UUID
    status: str
    object_name: str
    bucket: str
    object_key: str
    file_size_bytes: int
    part_size_bytes: int
    part_count: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CreatedUploadTask:
    task_id: uuid.UUID
    project_id: uuid.UUID
    status: str
    object_count: int
    total_size_bytes: int
    objects: tuple[CreatedUploadObject, ...]
    created_at: datetime


class UploadTaskCreationService:
    """Application boundary for T05 transactional upload task creation."""

    def __init__(self, *, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings

    def create_upload_task(self, command: CreateUploadTaskCommand) -> CreatedUploadTask:
        fingerprint = generate_request_fingerprint(
            method="POST",
            path=command.request_path,
            tenant_id=command.tenant_id,
            body=assert_json_value(command.request_body),
        )
        existing = self._resolve_idempotency(command, fingerprint)
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
                    self._create_object_session(
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
        self._store_idempotency_response(command, fingerprint, result)
        self._session.commit()
        return result

    def _resolve_idempotency(
        self,
        command: CreateUploadTaskCommand,
        fingerprint: str,
    ) -> CreatedUploadTask | None:
        if command.idempotency_key is None:
            return None
        record = self._session.scalars(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.tenant_id == command.tenant_id)
            .where(IdempotencyRecord.key == command.idempotency_key)
            .with_for_update()
        ).one_or_none()
        if record is None:
            self._session.add(
                IdempotencyRecord(
                    id=uuid.uuid4(),
                    tenant_id=command.tenant_id,
                    key=command.idempotency_key,
                    request_method="POST",
                    request_path=command.request_path,
                    request_fingerprint=fingerprint,
                    response_status=None,
                    response_body=None,
                    locked_until=datetime.now(UTC) + timedelta(seconds=30),
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
            self._session.flush()
            return None
        if record.request_fingerprint != fingerprint:
            raise ApiError(
                status_code=409,
                code="idempotency.key_reused_with_different_request",
                message="Idempotency key was reused with a different request.",
            )
        if record.response_status == 201 and record.response_body is not None:
            return _result_from_json(record.response_body)
        raise ApiError(
            status_code=409,
            code="idempotency.request_in_progress",
            message="An idempotent request with this key is still in progress.",
        )

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

    def _create_object_session(
        self,
        *,
        command: CreateUploadTaskCommand,
        storage_policy: StoragePolicy,
        task: UploadTask,
        item: CreateUploadObjectInput,
        now: datetime,
        fingerprint: str,
    ) -> CreatedUploadObject:
        dataset = Dataset(
            id=uuid.uuid4(),
            tenant_id=command.tenant_id,
            project_id=command.project_id,
            name=item.dataset_name,
            status="UPLOAD_PENDING",
            original_filename=item.object_name,
            content_type=item.content_type,
            file_size_bytes=item.file_size_bytes,
            checksum_sha256=item.checksum_sha256,
            bucket_name=storage_policy.bucket_name,
            source_device_id=command.source_device_id,
            source_device_code=command.source_device_code,
            validation_status="NOT_REQUIRED",
            recovery_status="NORMAL",
            preview_status="NOT_AVAILABLE",
            preview_metadata={},
            metadata_=dict(item.metadata),
            labels=[],
            created_by=command.actor.subject_id,
            created_at=now,
            updated_at=now,
        )
        upload_object = UploadObject(
            id=uuid.uuid4(),
            tenant_id=command.tenant_id,
            project_id=command.project_id,
            dataset_id=dataset.id,
            upload_task_id=task.id,
            status="PENDING",
            object_name=item.object_name,
            file_size_bytes=item.file_size_bytes,
            content_type=item.content_type,
            checksum_sha256=item.checksum_sha256,
            retry_count=0,
            is_instant_upload=False,
            created_at=now,
            updated_at=now,
        )
        session_id = uuid.uuid4()
        object_key = build_object_key(
            tenant_id=command.tenant_id,
            project_id=command.project_id,
            dataset_id=dataset.id,
            session_id=session_id,
            raw_object_name=item.object_name,
            created_at=now,
        )
        expires_at = now + timedelta(seconds=storage_policy.upload_session_expiry_seconds)
        upload_session = UploadSession(
            id=session_id,
            tenant_id=command.tenant_id,
            project_id=command.project_id,
            dataset_id=dataset.id,
            upload_task_id=task.id,
            upload_object_id=upload_object.id,
            status="INITIATING",
            bucket_name=storage_policy.bucket_name,
            object_key=object_key,
            storage_provider=storage_policy.provider,
            original_filename=item.object_name,
            content_type=item.content_type,
            file_size_bytes=item.file_size_bytes,
            part_size_bytes=item.part_size_bytes,
            part_count=item.part_count,
            checksum_sha256=item.checksum_sha256,
            checksum_mode=storage_policy.checksum_mode,
            source_device_id=command.source_device_id,
            source_device_code=command.source_device_code,
            metadata_=dict(item.metadata),
            idempotency_key=_session_idempotency_key(command.idempotency_key, upload_object.id),
            request_fingerprint=fingerprint,
            uploaded_part_count=0,
            completed_part_count=0,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        dataset.object_key = object_key
        upload_object.upload_session_id = upload_session.id
        self._session.add_all((dataset, upload_object))
        self._session.flush()
        self._session.add(upload_session)
        self._session.flush()

        storage_result = self._storage.create_multipart_upload(
            CreateMultipartUploadRequest(
                bucket=storage_policy.bucket_name,
                object_key=object_key,
                content_type=item.content_type,
                metadata={
                    "tenant_id": str(command.tenant_id),
                    "project_id": str(command.project_id),
                    "dataset_id": str(dataset.id),
                    "session_id": str(upload_session.id),
                    "upload_task_id": str(task.id),
                    "upload_object_id": str(upload_object.id),
                },
                encryption=_encryption_policy(storage_policy),
                object_lock=_object_lock_policy(storage_policy, expires_at),
            )
        )
        upload_session.storage_upload_id = storage_result.upload_id
        upload_session.status = "INITIATED"
        upload_session.updated_at = now
        self._add_events(command, task, upload_object, dataset, upload_session)
        return CreatedUploadObject(
            object_id=upload_object.id,
            dataset_id=dataset.id,
            session_id=upload_session.id,
            status=upload_object.status,
            object_name=upload_object.object_name,
            bucket=upload_session.bucket_name,
            object_key=upload_session.object_key,
            file_size_bytes=upload_session.file_size_bytes,
            part_size_bytes=upload_session.part_size_bytes,
            part_count=upload_session.part_count,
            expires_at=upload_session.expires_at,
        )

    def _add_events(
        self,
        command: CreateUploadTaskCommand,
        task: UploadTask,
        upload_object: UploadObject,
        dataset: Dataset,
        upload_session: UploadSession,
    ) -> None:
        actor_id = str(command.actor.subject_id)
        actor_type = command.actor.actor_type
        payload = {
            "task_id": str(task.id),
            "object_id": str(upload_object.id),
            "storage_upload_id": upload_session.storage_upload_id,
        }
        self._session.add_all(
            [
                UploadEvent(
                    tenant_id=command.tenant_id,
                    project_id=command.project_id,
                    dataset_id=dataset.id,
                    upload_task_id=task.id,
                    upload_object_id=upload_object.id,
                    session_id=upload_session.id,
                    event_type="upload_task.created",
                    actor_type=actor_type,
                    actor_id=actor_id,
                    request_id=command.request_id,
                    payload=payload,
                ),
                UploadEvent(
                    tenant_id=command.tenant_id,
                    project_id=command.project_id,
                    dataset_id=dataset.id,
                    upload_task_id=task.id,
                    upload_object_id=upload_object.id,
                    session_id=upload_session.id,
                    event_type="upload_session.storage_initiated",
                    actor_type=actor_type,
                    actor_id=actor_id,
                    request_id=command.request_id,
                    payload=payload,
                ),
                AuditEvent(
                    tenant_id=command.tenant_id,
                    project_id=command.project_id,
                    dataset_id=dataset.id,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    action="upload_task.create",
                    resource_type="upload_task",
                    resource_id=str(task.id),
                    result="SUCCESS",
                    request_id=command.request_id,
                    after_state=payload,
                    metadata_={"source": "upload_task_creation"},
                ),
            ]
        )

    def _store_idempotency_response(
        self,
        command: CreateUploadTaskCommand,
        fingerprint: str,
        result: CreatedUploadTask,
    ) -> None:
        if command.idempotency_key is None:
            return
        record = self._session.scalars(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.tenant_id == command.tenant_id)
            .where(IdempotencyRecord.key == command.idempotency_key)
        ).one()
        record.request_fingerprint = fingerprint
        record.response_status = 201
        record.response_body = _result_to_json(result)
        record.locked_until = None
        record.updated_at = datetime.now(UTC)

    def _count(self, statement: Select[tuple[int]]) -> int:
        return int(self._session.execute(statement).scalar_one())


def _session_idempotency_key(
    idempotency_key: str | None,
    upload_object_id: uuid.UUID,
) -> str | None:
    if idempotency_key is None:
        return None
    return f"{idempotency_key}:{upload_object_id}"


def _encryption_policy(storage_policy: StoragePolicy) -> dict[str, str] | None:
    if storage_policy.encryption_mode == "NONE":
        return None
    values = {"mode": storage_policy.encryption_mode}
    if storage_policy.kms_key_ref:
        values["kms_key_ref"] = storage_policy.kms_key_ref
    return values


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


def _object_lock_policy(
    storage_policy: StoragePolicy,
    expires_at: datetime,
) -> dict[str, str] | None:
    values: dict[str, str] = {}
    if storage_policy.object_lock_mode:
        values["mode"] = storage_policy.object_lock_mode
    if storage_policy.object_lock_retention_days is not None:
        retain_until = datetime.now(UTC) + timedelta(days=storage_policy.object_lock_retention_days)
        values["retain_until_date"] = retain_until.isoformat()
    if storage_policy.legal_hold_default:
        values["legal_hold"] = "ON"
    _ = expires_at
    return values or None


def _result_to_json(result: CreatedUploadTask) -> dict[str, Any]:
    return {
        "task_id": str(result.task_id),
        "project_id": str(result.project_id),
        "status": result.status,
        "object_count": result.object_count,
        "total_size_bytes": result.total_size_bytes,
        "objects": [
            {
                "object_id": str(item.object_id),
                "dataset_id": str(item.dataset_id),
                "session_id": str(item.session_id),
                "status": item.status,
                "object_name": item.object_name,
                "bucket": item.bucket,
                "object_key": item.object_key,
                "file_size_bytes": item.file_size_bytes,
                "part_size_bytes": item.part_size_bytes,
                "part_count": item.part_count,
                "expires_at": item.expires_at.isoformat(),
            }
            for item in result.objects
        ],
        "created_at": result.created_at.isoformat(),
    }


def _result_from_json(value: dict[str, Any]) -> CreatedUploadTask:
    return CreatedUploadTask(
        task_id=uuid.UUID(value["task_id"]),
        project_id=uuid.UUID(value["project_id"]),
        status=value["status"],
        object_count=value["object_count"],
        total_size_bytes=value["total_size_bytes"],
        objects=tuple(
            CreatedUploadObject(
                object_id=uuid.UUID(item["object_id"]),
                dataset_id=uuid.UUID(item["dataset_id"]),
                session_id=uuid.UUID(item["session_id"]),
                status=item["status"],
                object_name=item["object_name"],
                bucket=item["bucket"],
                object_key=item["object_key"],
                file_size_bytes=item["file_size_bytes"],
                part_size_bytes=item["part_size_bytes"],
                part_count=item["part_count"],
                expires_at=datetime.fromisoformat(item["expires_at"]),
            )
            for item in value["objects"]
        ),
        created_at=datetime.fromisoformat(value["created_at"]),
    )
