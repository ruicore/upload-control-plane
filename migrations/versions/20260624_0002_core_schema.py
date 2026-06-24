"""core schema tenants policies api keys projects

Revision ID: 20260624_0002
Revises: 20260624_0001
Create Date: 2026-06-24 16:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0002"
down_revision: str | None = "20260624_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: tuple[postgresql.ENUM, ...] = (
    postgresql.ENUM(
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
    ),
    postgresql.ENUM(
        "EXPECTED",
        "PRESIGNED",
        "UPLOADED",
        "MISSING",
        "FAILED",
        name="upload_part_status",
    ),
    postgresql.ENUM(
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
    ),
    postgresql.ENUM(
        "CREATED",
        "PENDING",
        "PROCESSING",
        "PAUSED",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        name="upload_task_status",
    ),
    postgresql.ENUM(
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
    ),
    postgresql.ENUM(
        "ACTIVE",
        "DISABLED",
        "REVOKED",
        "DELETED",
        name="device_status",
    ),
    postgresql.ENUM(
        "NOT_REQUIRED",
        "PENDING",
        "RUNNING",
        "PASSED",
        "FAILED",
        "SKIPPED",
        name="validation_status",
    ),
    postgresql.ENUM(
        "NORMAL",
        "RECOVERY_PENDING",
        "RECOVERY_VERIFIED",
        "RECOVERY_MISSING_OBJECT",
        "RECOVERY_METADATA_ONLY",
        "RECOVERY_OBJECT_ONLY",
        name="recovery_status",
    ),
    postgresql.ENUM(
        "PENDING",
        "PROCESSING",
        "DELIVERED",
        "FAILED",
        "DEAD_LETTERED",
        name="outbox_status",
    ),
    postgresql.ENUM(
        "ALLOW",
        "DENY",
        name="permission_effect",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "storage_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), server_default=sa.text("'s3_compatible'"), nullable=False),
        sa.Column("bucket_name", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("endpoint_ref", sa.Text(), nullable=True),
        sa.Column("addressing_style", sa.Text(), server_default=sa.text("'path'"), nullable=False),
        sa.Column("object_key_template", sa.Text(), nullable=False),
        sa.Column("default_part_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("presign_expiry_seconds", sa.Integer(), nullable=False),
        sa.Column("upload_session_expiry_seconds", sa.Integer(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column(
            "checksum_mode",
            sa.Text(),
            server_default=sa.text("'CLIENT_REPORTED'"),
            nullable=False,
        ),
        sa.Column("encryption_mode", sa.Text(), server_default=sa.text("'NONE'"), nullable=False),
        sa.Column("kms_key_ref", sa.Text(), nullable=True),
        sa.Column("object_lock_mode", sa.Text(), nullable=True),
        sa.Column("object_lock_retention_days", sa.Integer(), nullable=True),
        sa.Column(
            "legal_hold_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("replication_policy_ref", sa.Text(), nullable=True),
        sa.Column("cors_policy_ref", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name"),
    )
    op.create_index(
        "idx_storage_policies_tenant_status",
        "storage_policies",
        ["tenant_id", "status"],
    )

    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("ARRAY[]::TEXT[]"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("idx_api_keys_tenant_id", "api_keys", ["tenant_id"])

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column(
            "metadata_schema",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["storage_policy_id"], ["storage_policies.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug"),
    )
    op.create_index("idx_projects_tenant_status", "projects", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_projects_tenant_status", table_name="projects")
    op.drop_table("projects")
    op.drop_index("idx_api_keys_tenant_id", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("idx_storage_policies_tenant_status", table_name="storage_policies")
    op.drop_table("storage_policies")
    op.drop_table("tenants")

    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=True)
