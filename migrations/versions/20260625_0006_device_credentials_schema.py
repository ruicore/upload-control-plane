"""device credentials schema

Revision ID: 20260625_0006
Revises: 20260624_0005
Create Date: 2026-06-25 14:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260625_0006"
down_revision: str | None = "20260624_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("credential_hash", sa.Text(), nullable=False),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "credential_hash"),
        sa.UniqueConstraint("device_id", "credential_version"),
    )
    op.create_index(
        "idx_device_credentials_device",
        "device_credentials",
        ["device_id", "revoked_at", "expires_at"],
    )
    op.create_index(
        "idx_device_credentials_hash",
        "device_credentials",
        ["tenant_id", "credential_hash"],
    )


def downgrade() -> None:
    op.drop_index("idx_device_credentials_hash", table_name="device_credentials")
    op.drop_index("idx_device_credentials_device", table_name="device_credentials")
    op.drop_table("device_credentials")
