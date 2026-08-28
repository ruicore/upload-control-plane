from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from upload_control_plane.application.upload_tasks.contracts import (
    CreatedUploadObject,
    CreateUploadObjectInput,
    CreateUploadTaskCommand,
)
from upload_control_plane.domain.object_keys import build_object_key
from upload_control_plane.domain.storage import CreateMultipartUploadRequest, ObjectStorage
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    StoragePolicy,
    UploadEvent,
    UploadObject,
    UploadSession,
    UploadTask,
)


class UploadObjectSessionProvisioner:
    """Private collaborator for provisioning one upload object and session."""

    def __init__(self, *, session: Session, storage: ObjectStorage) -> None:
        self._session = session
        self._storage = storage

    def provision(
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
