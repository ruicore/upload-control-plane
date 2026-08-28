"""upload lifecycle schema

Revision ID: 20260624_0004
Revises: 20260624_0003
Create Date: 2026-06-24 17:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0004"
down_revision: str | None = "20260624_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

upload_task_status = postgresql.ENUM(name="upload_task_status", create_type=False)
upload_object_status = postgresql.ENUM(name="upload_object_status", create_type=False)
upload_session_status = postgresql.ENUM(name="upload_session_status", create_type=False)
upload_part_status = postgresql.ENUM(name="upload_part_status", create_type=False)


def upgrade() -> None:
    op.create_table(
        "upload_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status", upload_task_status, server_default=sa.text("'CREATED'"), nullable=False
        ),
        sa.Column("task_initiator", sa.Text(), nullable=False),
        sa.Column("source_device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_device_code", sa.Text(), nullable=True),
        sa.Column("object_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "completed_object_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "failed_object_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("total_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "uploaded_size_bytes",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["storage_policy_id"], ["storage_policies.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    op.create_index("idx_upload_tasks_project_status", "upload_tasks", ["project_id", "status"])
    op.create_index(
        "idx_upload_tasks_source_device",
        "upload_tasks",
        ["tenant_id", "source_device_id"],
    )
    op.create_index(
        "idx_upload_tasks_source_device_code",
        "upload_tasks",
        ["tenant_id", "source_device_code"],
    )

    op.create_table(
        "upload_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("upload_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status", upload_object_status, server_default=sa.text("'CREATED'"), nullable=False
        ),
        sa.Column("object_name", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("checksum_sha256", sa.Text(), nullable=True),
        sa.Column("upload_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "is_instant_upload", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["upload_task_id"], ["upload_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_upload_objects_task_status",
        "upload_objects",
        ["upload_task_id", "status"],
    )
    op.create_index("idx_upload_objects_dataset_id", "upload_objects", ["dataset_id"])

    op.create_table(
        "upload_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("upload_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("upload_object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            upload_session_status,
            server_default=sa.text("'INITIATING'"),
            nullable=False,
        ),
        sa.Column("bucket_name", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("storage_provider", sa.Text(), server_default=sa.text("'minio'"), nullable=False),
        sa.Column("storage_upload_id", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("part_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("part_count", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=True),
        sa.Column(
            "checksum_mode",
            sa.Text(),
            server_default=sa.text("'CLIENT_REPORTED'"),
            nullable=False,
        ),
        sa.Column("source_device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_device_code", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("request_fingerprint", sa.Text(), nullable=True),
        sa.Column("uploaded_part_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "completed_part_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("object_etag", sa.Text(), nullable=True),
        sa.Column("object_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("object_version_id", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aborted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.Text(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "file_size_bytes > 0",
            name=op.f("ck_upload_sessions_upload_sessions_file_size_positive"),
        ),
        sa.CheckConstraint(
            "part_size_bytes > 0",
            name=op.f("ck_upload_sessions_upload_sessions_part_size_positive"),
        ),
        sa.CheckConstraint(
            "part_count >= 1 AND part_count <= 10000",
            name=op.f("ck_upload_sessions_upload_sessions_part_count_valid"),
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["upload_object_id"], ["upload_objects.id"]),
        sa.ForeignKeyConstraint(["upload_task_id"], ["upload_tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bucket_name",
            "object_key",
            name=op.f("uq_upload_sessions_upload_sessions_object_key_unique"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name=op.f("uq_upload_sessions_upload_sessions_idempotency_unique"),
        ),
    )
    op.create_index(
        "idx_upload_sessions_tenant_status",
        "upload_sessions",
        ["tenant_id", "status"],
    )
    op.create_index("idx_upload_sessions_project_id", "upload_sessions", ["project_id"])
    op.create_index("idx_upload_sessions_dataset_id", "upload_sessions", ["dataset_id"])
    op.create_index("idx_upload_sessions_task_id", "upload_sessions", ["upload_task_id"])
    op.create_index("idx_upload_sessions_object_id", "upload_sessions", ["upload_object_id"])
    op.create_index("idx_upload_sessions_expires_at", "upload_sessions", ["expires_at"])
    op.create_index(
        "idx_upload_sessions_storage_upload_id",
        "upload_sessions",
        ["storage_upload_id"],
    )
    op.create_index(
        "idx_upload_sessions_source_device",
        "upload_sessions",
        ["tenant_id", "source_device_id"],
    )
    op.create_index(
        "idx_upload_sessions_source_device_code",
        "upload_sessions",
        ["tenant_id", "source_device_code"],
    )

    op.create_table(
        "upload_parts",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("part_number", sa.Integer(), nullable=False),
        sa.Column(
            "status", upload_part_status, server_default=sa.text("'EXPECTED'"), nullable=False
        ),
        sa.Column("offset_start", sa.BigInteger(), nullable=False),
        sa.Column("offset_end_exclusive", sa.BigInteger(), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.Text(), nullable=True),
        sa.Column("last_presigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("presign_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.Text(), server_default=sa.text("'db'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "part_number >= 1 AND part_number <= 10000",
            name=op.f("ck_upload_parts_upload_parts_part_number_valid"),
        ),
        sa.CheckConstraint(
            "expected_size_bytes >= 0",
            name=op.f("ck_upload_parts_upload_parts_expected_size_positive"),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["upload_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id", "part_number"),
    )
    op.create_index("idx_upload_parts_session_status", "upload_parts", ["session_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_upload_parts_session_status", table_name="upload_parts")
    op.drop_table("upload_parts")
    op.drop_index("idx_upload_sessions_source_device_code", table_name="upload_sessions")
    op.drop_index("idx_upload_sessions_source_device", table_name="upload_sessions")
    op.drop_index("idx_upload_sessions_storage_upload_id", table_name="upload_sessions")
    op.drop_index("idx_upload_sessions_expires_at", table_name="upload_sessions")
    op.drop_index("idx_upload_sessions_object_id", table_name="upload_sessions")
    op.drop_index("idx_upload_sessions_task_id", table_name="upload_sessions")
    op.drop_index("idx_upload_sessions_dataset_id", table_name="upload_sessions")
    op.drop_index("idx_upload_sessions_project_id", table_name="upload_sessions")
    op.drop_index("idx_upload_sessions_tenant_status", table_name="upload_sessions")
    op.drop_table("upload_sessions")
    op.drop_index("idx_upload_objects_dataset_id", table_name="upload_objects")
    op.drop_index("idx_upload_objects_task_status", table_name="upload_objects")
    op.drop_table("upload_objects")
    op.drop_index("idx_upload_tasks_source_device_code", table_name="upload_tasks")
    op.drop_index("idx_upload_tasks_source_device", table_name="upload_tasks")
    op.drop_index("idx_upload_tasks_project_status", table_name="upload_tasks")
    op.drop_table("upload_tasks")
