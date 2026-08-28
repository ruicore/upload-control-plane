"""dataset governance schema

Revision ID: 20260624_0003
Revises: 20260624_0002
Create Date: 2026-06-24 16:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260624_0003"
down_revision: str | None = "20260624_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

dataset_status = postgresql.ENUM(name="dataset_status", create_type=False)
device_status = postgresql.ENUM(name="device_status", create_type=False)
validation_status = postgresql.ENUM(name="validation_status", create_type=False)
recovery_status = postgresql.ENUM(name="recovery_status", create_type=False)
permission_effect = postgresql.ENUM(name="permission_effect", create_type=False)


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("device_code", sa.Text(), nullable=True),
        sa.Column("device_type", sa.Text(), nullable=False),
        sa.Column("status", device_status, server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("credential_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("credential_hash", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ip", sa.Text(), nullable=True),
        sa.Column("client_version", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "device_code"),
    )
    op.create_index("idx_devices_tenant_status", "devices", ["tenant_id", "status"])

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", dataset_status, server_default=sa.text("'CREATED'"), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("content_type", sa.Text(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.Text(), nullable=True),
        sa.Column("bucket_name", sa.Text(), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("object_etag", sa.Text(), nullable=True),
        sa.Column("object_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("object_version_id", sa.Text(), nullable=True),
        sa.Column("source_device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_device_code", sa.Text(), nullable=True),
        sa.Column(
            "validation_status",
            validation_status,
            server_default=sa.text("'NOT_REQUIRED'"),
            nullable=False,
        ),
        sa.Column(
            "recovery_status",
            recovery_status,
            server_default=sa.text("'NORMAL'"),
            nullable=False,
        ),
        sa.Column(
            "preview_status",
            sa.Text(),
            server_default=sa.text("'NOT_AVAILABLE'"),
            nullable=False,
        ),
        sa.Column(
            "preview_metadata",
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
        sa.Column(
            "labels",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("ARRAY[]::TEXT[]"),
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
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["source_device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_datasets_project_status", "datasets", ["project_id", "status"])
    op.create_index("idx_datasets_tenant_status", "datasets", ["tenant_id", "status"])
    op.create_index(
        "idx_datasets_source_device",
        "datasets",
        ["tenant_id", "source_device_id"],
    )
    op.create_index(
        "idx_datasets_source_device_code",
        "datasets",
        ["tenant_id", "source_device_code"],
    )
    op.create_index(
        "idx_datasets_validation_status",
        "datasets",
        ["project_id", "validation_status"],
    )
    op.create_index(
        "idx_datasets_recovery_status",
        "datasets",
        ["project_id", "recovery_status"],
    )
    op.create_index(
        "idx_datasets_object_unique",
        "datasets",
        ["bucket_name", "object_key"],
        unique=True,
        postgresql_where=sa.text("object_key IS NOT NULL"),
    )

    op.create_table(
        "tag_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name"),
    )

    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["category_id"], ["tag_categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name"),
    )
    op.create_index("idx_tags_project_category", "tags", ["project_id", "category_id"])

    op.create_table(
        "dataset_tags",
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("dataset_id", "tag_id"),
    )

    op.create_table(
        "permission_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.Text(), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_code", sa.Text(), nullable=False),
        sa.Column("effect", permission_effect, server_default=sa.text("'ALLOW'"), nullable=False),
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "subject_type IN ('user', 'group', 'device', 'api_key')",
            name=op.f("ck_permission_grants_permission_grants_subject_type_allowed"),
        ),
        sa.CheckConstraint(
            "resource_type IN ("
            "'tenant', 'project', 'dataset', 'upload_session', 'upload_task', "
            "'device', 'tag_category', 'tag', 'storage_policy'"
            ")",
            name=op.f("ck_permission_grants_permission_grants_resource_type_allowed"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "subject_type",
            "subject_id",
            "resource_type",
            "resource_id",
            "permission_code",
            "effect",
        ),
    )
    op.create_index(
        "idx_permission_grants_subject",
        "permission_grants",
        ["tenant_id", "subject_type", "subject_id"],
    )
    op.create_index(
        "idx_permission_grants_resource",
        "permission_grants",
        ["tenant_id", "resource_type", "resource_id"],
    )
    op.create_index(
        "idx_permission_grants_permission",
        "permission_grants",
        ["tenant_id", "permission_code"],
    )
    op.create_index(
        "idx_permission_grants_expires_at",
        "permission_grants",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_permission_grants_expires_at", table_name="permission_grants")
    op.drop_index("idx_permission_grants_permission", table_name="permission_grants")
    op.drop_index("idx_permission_grants_resource", table_name="permission_grants")
    op.drop_index("idx_permission_grants_subject", table_name="permission_grants")
    op.drop_table("permission_grants")
    op.drop_table("dataset_tags")
    op.drop_index("idx_tags_project_category", table_name="tags")
    op.drop_table("tags")
    op.drop_table("tag_categories")
    op.drop_index("idx_datasets_object_unique", table_name="datasets")
    op.drop_index("idx_datasets_recovery_status", table_name="datasets")
    op.drop_index("idx_datasets_validation_status", table_name="datasets")
    op.drop_index("idx_datasets_source_device_code", table_name="datasets")
    op.drop_index("idx_datasets_source_device", table_name="datasets")
    op.drop_index("idx_datasets_tenant_status", table_name="datasets")
    op.drop_index("idx_datasets_project_status", table_name="datasets")
    op.drop_table("datasets")
    op.drop_index("idx_devices_tenant_status", table_name="devices")
    op.drop_table("devices")
