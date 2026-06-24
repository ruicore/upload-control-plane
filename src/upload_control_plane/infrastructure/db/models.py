from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from upload_control_plane.infrastructure.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class StoragePolicy(Base):
    __tablename__ = "storage_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        Index("idx_storage_policies_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'s3_compatible'"),
    )
    bucket_name: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    addressing_style: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'path'"),
    )
    object_key_template: Mapped[str] = mapped_column(Text, nullable=False)
    default_part_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    presign_expiry_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    upload_session_expiry_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'CLIENT_REPORTED'"),
    )
    encryption_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'NONE'")
    )
    kms_key_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_lock_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_lock_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    legal_hold_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    replication_policy_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    cors_policy_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("idx_api_keys_tenant_id", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("ARRAY[]::TEXT[]"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug"),
        Index("idx_projects_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    storage_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storage_policies.id"),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))
    metadata_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "device_code"),
        Index("idx_devices_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    device_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        ENUM(
            "ACTIVE",
            "DISABLED",
            "REVOKED",
            "DELETED",
            name="device_status",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'ACTIVE'"),
    )
    credential_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    credential_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (
        Index("idx_datasets_project_status", "project_id", "status"),
        Index("idx_datasets_tenant_status", "tenant_id", "status"),
        Index("idx_datasets_source_device", "tenant_id", "source_device_id"),
        Index("idx_datasets_source_device_code", "tenant_id", "source_device_code"),
        Index("idx_datasets_validation_status", "project_id", "validation_status"),
        Index("idx_datasets_recovery_status", "project_id", "recovery_status"),
        Index(
            "idx_datasets_object_unique",
            "bucket_name",
            "object_key",
            unique=True,
            postgresql_where=text("object_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        ENUM(
            "CREATED",
            "UPLOAD_PENDING",
            "UPLOADING",
            "PAUSED",
            "PROCESSING",
            "QUARANTINED",
            "READY",
            "REJECTED",
            "ARCHIVED",
            "DELETED",
            "PURGED",
            name="dataset_status",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'CREATED'"),
    )
    original_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    bucket_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    object_version_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id"),
        nullable=True,
    )
    source_device_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[str] = mapped_column(
        ENUM(
            "NOT_REQUIRED",
            "PENDING",
            "RUNNING",
            "PASSED",
            "FAILED",
            "SKIPPED",
            name="validation_status",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'NOT_REQUIRED'"),
    )
    recovery_status: Mapped[str] = mapped_column(
        ENUM(
            "NORMAL",
            "RECOVERY_PENDING",
            "RECOVERY_VERIFIED",
            "RECOVERY_MISSING_OBJECT",
            "RECOVERY_METADATA_ONLY",
            "RECOVERY_OBJECT_ONLY",
            name="recovery_status",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'NORMAL'"),
    )
    preview_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'NOT_AVAILABLE'"),
    )
    preview_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    labels: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("ARRAY[]::TEXT[]"),
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TagCategory(Base):
    __tablename__ = "tag_categories"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("project_id", "name"),
        Index("idx_tags_project_category", "project_id", "category_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tag_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class DatasetTag(Base):
    __tablename__ = "dataset_tags"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class PermissionGrant(Base):
    __tablename__ = "permission_grants"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "subject_type",
            "subject_id",
            "resource_type",
            "resource_id",
            "permission_code",
            "effect",
        ),
        CheckConstraint(
            "subject_type IN ('user', 'group', 'device', 'api_key')",
            name="permission_grants_subject_type_allowed",
        ),
        CheckConstraint(
            "resource_type IN ("
            "'tenant', 'project', 'dataset', 'upload_session', 'upload_task', "
            "'device', 'tag_category', 'tag', 'storage_policy'"
            ")",
            name="permission_grants_resource_type_allowed",
        ),
        Index("idx_permission_grants_subject", "tenant_id", "subject_type", "subject_id"),
        Index("idx_permission_grants_resource", "tenant_id", "resource_type", "resource_id"),
        Index("idx_permission_grants_permission", "tenant_id", "permission_code"),
        Index("idx_permission_grants_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    permission_code: Mapped[str] = mapped_column(Text, nullable=False)
    effect: Mapped[str] = mapped_column(
        ENUM("ALLOW", "DENY", name="permission_effect", create_type=False),
        nullable=False,
        server_default=text("'ALLOW'"),
    )
    conditions: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UploadTask(Base):
    __tablename__ = "upload_tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key"),
        Index("idx_upload_tasks_project_status", "project_id", "status"),
        Index("idx_upload_tasks_source_device", "tenant_id", "source_device_id"),
        Index("idx_upload_tasks_source_device_code", "tenant_id", "source_device_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    storage_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("storage_policies.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        ENUM(
            "CREATED",
            "PENDING",
            "PROCESSING",
            "PAUSED",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            name="upload_task_status",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'CREATED'"),
    )
    task_initiator: Mapped[str] = mapped_column(Text, nullable=False)
    source_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id"),
        nullable=True,
    )
    source_device_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completed_object_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    failed_object_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    total_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uploaded_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class UploadObject(Base):
    __tablename__ = "upload_objects"
    __table_args__ = (
        Index("idx_upload_objects_task_status", "upload_task_id", "status"),
        Index("idx_upload_objects_dataset_id", "dataset_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=False,
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id"),
        nullable=True,
    )
    upload_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("upload_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        ENUM(
            "CREATED",
            "PENDING",
            "UPLOADING",
            "PAUSED",
            "COMPLETING",
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "SKIPPED_INSTANT_UPLOAD",
            name="upload_object_status",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'CREATED'"),
    )
    object_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_instant_upload: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class UploadSession(Base):
    __tablename__ = "upload_sessions"
    __table_args__ = (
        CheckConstraint("file_size_bytes > 0", name="upload_sessions_file_size_positive"),
        CheckConstraint("part_size_bytes > 0", name="upload_sessions_part_size_positive"),
        CheckConstraint(
            "part_count >= 1 AND part_count <= 10000",
            name="upload_sessions_part_count_valid",
        ),
        UniqueConstraint("bucket_name", "object_key", name="upload_sessions_object_key_unique"),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="upload_sessions_idempotency_unique",
        ),
        Index("idx_upload_sessions_tenant_status", "tenant_id", "status"),
        Index("idx_upload_sessions_project_id", "project_id"),
        Index("idx_upload_sessions_dataset_id", "dataset_id"),
        Index("idx_upload_sessions_task_id", "upload_task_id"),
        Index("idx_upload_sessions_object_id", "upload_object_id"),
        Index("idx_upload_sessions_expires_at", "expires_at"),
        Index("idx_upload_sessions_storage_upload_id", "storage_upload_id"),
        Index("idx_upload_sessions_source_device", "tenant_id", "source_device_id"),
        Index("idx_upload_sessions_source_device_code", "tenant_id", "source_device_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        nullable=True,
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id"),
        nullable=True,
    )
    upload_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("upload_tasks.id"),
        nullable=True,
    )
    upload_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("upload_objects.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        ENUM(
            "INITIATING",
            "INITIATED",
            "UPLOADING",
            "PAUSED",
            "COMPLETING",
            "COMPLETED",
            "ABORTING",
            "ABORTED",
            "EXPIRED",
            "FAILED",
            name="upload_session_status",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'INITIATING'"),
    )
    bucket_name: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    storage_provider: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'minio'"),
    )
    storage_upload_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    part_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    part_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum_mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'CLIENT_REPORTED'"),
    )
    source_device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id"),
        nullable=True,
    )
    source_device_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_part_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    completed_part_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    object_etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    object_version_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    aborted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class UploadPart(Base):
    __tablename__ = "upload_parts"
    __table_args__ = (
        CheckConstraint(
            "part_number >= 1 AND part_number <= 10000",
            name="upload_parts_part_number_valid",
        ),
        CheckConstraint(
            "expected_size_bytes >= 0",
            name="upload_parts_expected_size_positive",
        ),
        Index("idx_upload_parts_session_status", "session_id", "status"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("upload_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    part_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(
        ENUM(
            "EXPECTED",
            "PRESIGNED",
            "UPLOADED",
            "MISSING",
            "FAILED",
            name="upload_part_status",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'EXPECTED'"),
    )
    offset_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    offset_end_exclusive: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    etag: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_presigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    presign_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'db'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
