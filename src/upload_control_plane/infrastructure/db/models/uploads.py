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
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from upload_control_plane.infrastructure.db.base import Base


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
