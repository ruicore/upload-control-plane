from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.config import Settings
from upload_control_plane.infrastructure.db.models import (
    ApiKey,
    Dataset,
    Device,
    PermissionGrant,
    Project,
    StoragePolicy,
    Tenant,
)

DEV_API_KEY_VALUE = "ucp_dev_api_key_local_only_20260624"
DEV_DEVICE_CREDENTIAL_VALUE = "ucp_dev_device_credential_local_only_20260624"
DEV_SEED_NAMESPACE = uuid.UUID("2b5bf9c4-50ce-47db-9348-6f31d5c8c239")


@dataclass(frozen=True)
class DevSeedResult:
    tenant_id: uuid.UUID
    api_key_id: uuid.UUID
    storage_policy_id: uuid.UUID
    project_id: uuid.UUID
    dataset_id: uuid.UUID
    device_id: uuid.UUID
    api_key_value: str
    api_key_hash: str
    permission_codes: tuple[str, ...]


def dev_seed_uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(DEV_SEED_NAMESPACE, name)


def hash_dev_secret(secret: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_dev_seed_result() -> DevSeedResult:
    return DevSeedResult(
        tenant_id=dev_seed_uuid("tenant:dev-industrial"),
        api_key_id=dev_seed_uuid("api-key:dev-automation"),
        storage_policy_id=dev_seed_uuid("storage-policy:local-minio"),
        project_id=dev_seed_uuid("project:robotics-line-3"),
        dataset_id=dev_seed_uuid("dataset:line-3-sample-hdf5"),
        device_id=dev_seed_uuid("device:robot-17"),
        api_key_value=DEV_API_KEY_VALUE,
        api_key_hash=hash_dev_secret(DEV_API_KEY_VALUE),
        permission_codes=(
            "project.view",
            "dataset.upload",
            "upload.create",
            "upload.pause",
            "upload.resume",
            "upload.complete",
            "upload.abort",
        ),
    )


def seed_dev_data(session: Session, settings: Settings) -> DevSeedResult:
    result = build_dev_seed_result()

    tenant = _get_or_create(session, Tenant, result.tenant_id)
    tenant.slug = "dev-industrial"
    tenant.name = "Dev Industrial Tenant"
    tenant.status = "ACTIVE"
    session.flush()

    api_key = _get_or_create(session, ApiKey, result.api_key_id)
    api_key.tenant_id = result.tenant_id
    api_key.key_hash = result.api_key_hash
    api_key.name = "Dev Automation API Key"
    api_key.subject_id = result.api_key_id
    api_key.scopes = ["dev"]
    api_key.status = "ACTIVE"
    api_key.expires_at = None

    storage_policy = _get_or_create(session, StoragePolicy, result.storage_policy_id)
    storage_policy.tenant_id = result.tenant_id
    storage_policy.name = "local-minio-default"
    storage_policy.provider = "s3_compatible"
    storage_policy.bucket_name = settings.s3_bucket
    storage_policy.region = settings.s3_region
    storage_policy.endpoint_ref = "local-minio"
    storage_policy.addressing_style = settings.s3_addressing_style
    storage_policy.object_key_template = (
        "tenants/{tenant_id}/projects/{project_id}/datasets/{dataset_id}/{object_name}"
    )
    storage_policy.default_part_size_bytes = settings.default_part_size_bytes
    storage_policy.presign_expiry_seconds = settings.default_presign_expiry_seconds
    storage_policy.upload_session_expiry_seconds = settings.default_upload_session_expiry_seconds
    storage_policy.retention_days = settings.default_dataset_retention_days
    storage_policy.checksum_mode = "CLIENT_REPORTED"
    storage_policy.encryption_mode = settings.s3_default_encryption_mode
    storage_policy.kms_key_ref = settings.s3_default_kms_key_ref or None
    storage_policy.object_lock_mode = settings.s3_default_object_lock_mode or None
    storage_policy.object_lock_retention_days = settings.s3_default_object_lock_retention_days
    storage_policy.legal_hold_default = False
    storage_policy.replication_policy_ref = None
    storage_policy.cors_policy_ref = "local-dev-cors"
    storage_policy.is_default = True
    storage_policy.status = "ACTIVE"
    storage_policy.metadata_ = {
        "seed": "dev",
        "s3_endpoint_url": settings.s3_endpoint_url,
        "s3_public_endpoint_url": settings.s3_public_endpoint_url,
    }
    session.flush()

    project = _get_or_create(session, Project, result.project_id)
    project.tenant_id = result.tenant_id
    project.storage_policy_id = result.storage_policy_id
    project.slug = "robotics-line-3"
    project.name = "Robotics Line 3"
    project.description = "Development project for industrial multipart upload control-plane flows."
    project.status = "ACTIVE"
    project.metadata_schema = {
        "required": ["source_device_code"],
        "properties": {"source_device_code": {"type": "string"}},
    }
    project.metadata_ = {"seed": "dev", "site": "shanghai-factory"}
    project.created_by = result.api_key_id

    device = _get_or_create(session, Device, result.device_id)
    device.tenant_id = result.tenant_id
    device.name = "Robot 17"
    device.device_code = "robot-17"
    device.device_type = "robot"
    device.status = "ACTIVE"
    device.credential_version = 1
    device.credential_hash = hash_dev_secret(DEV_DEVICE_CREDENTIAL_VALUE)
    device.last_ip = None
    device.client_version = "dev-seed"
    device.metadata_ = {"seed": "dev", "line": "3"}
    session.flush()

    dataset = _get_or_create(session, Dataset, result.dataset_id)
    dataset.tenant_id = result.tenant_id
    dataset.project_id = result.project_id
    dataset.name = "line-3-sample-hdf5"
    dataset.status = "UPLOAD_PENDING"
    dataset.original_filename = "line-3-sample.hdf5"
    dataset.content_type = "application/x-hdf5"
    dataset.file_size_bytes = None
    dataset.checksum_sha256 = None
    dataset.bucket_name = None
    dataset.object_key = None
    dataset.object_etag = None
    dataset.object_size_bytes = None
    dataset.object_version_id = None
    dataset.source_device_id = result.device_id
    dataset.source_device_code = "robot-17"
    dataset.validation_status = "NOT_REQUIRED"
    dataset.recovery_status = "NORMAL"
    dataset.preview_status = "NOT_AVAILABLE"
    dataset.preview_metadata = {}
    dataset.metadata_ = {"seed": "dev", "source": "seed_dev.py"}
    dataset.labels = ["dev", "robotics"]
    dataset.created_by = result.api_key_id

    for subject_type, subject_id in (
        ("api_key", result.api_key_id),
        ("device", result.device_id),
    ):
        for permission_code in result.permission_codes:
            grant_id = dev_seed_uuid(
                f"grant:{subject_type}:{subject_id}:project:{result.project_id}:{permission_code}"
            )
            grant = _get_or_create(session, PermissionGrant, grant_id)
            grant.tenant_id = result.tenant_id
            grant.subject_type = subject_type
            grant.subject_id = subject_id
            grant.resource_type = "project"
            grant.resource_id = result.project_id
            grant.permission_code = permission_code
            grant.effect = "ALLOW"
            grant.conditions = {}
            grant.source = "dev_seed"
            grant.created_by = result.api_key_id
            grant.expires_at = None

    session.flush()
    return result


def _get_or_create[T](session: Session, model: type[T], entity_id: uuid.UUID) -> T:
    instance = session.get(model, entity_id)
    if instance is not None:
        return instance

    instance = model(id=entity_id)  # type: ignore[call-arg]
    session.add(instance)
    return instance


def load_seeded_counts(session: Session, result: DevSeedResult) -> dict[str, int]:
    return {
        "tenants": int(session.get(Tenant, result.tenant_id) is not None),
        "api_keys": int(session.get(ApiKey, result.api_key_id) is not None),
        "storage_policies": int(session.get(StoragePolicy, result.storage_policy_id) is not None),
        "projects": int(session.get(Project, result.project_id) is not None),
        "datasets": int(session.get(Dataset, result.dataset_id) is not None),
        "devices": int(session.get(Device, result.device_id) is not None),
        "permission_grants": len(
            session.scalars(
                select(PermissionGrant).where(
                    PermissionGrant.tenant_id == result.tenant_id,
                    PermissionGrant.source == "dev_seed",
                )
            ).all()
        ),
    }
