from sqlalchemy import DateTime, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from upload_control_plane.infrastructure.db import models as _models  # noqa: F401
from upload_control_plane.infrastructure.db.base import Base


def test_device_credentials_schema_tracks_lifecycle_without_raw_material() -> None:
    table = Base.metadata.tables["device_credentials"]

    assert isinstance(table.c.id.type, UUID)
    assert isinstance(table.c.tenant_id.type, UUID)
    assert isinstance(table.c.device_id.type, UUID)
    assert isinstance(table.c.credential_version.type, Integer)
    assert isinstance(table.c.credential_hash.type, Text)
    assert isinstance(table.c.issued_at.type, DateTime)
    assert isinstance(table.c.expires_at.type, DateTime)
    assert isinstance(table.c.revoked_at.type, DateTime)
    assert isinstance(table.c.last_used_at.type, DateTime)
    assert isinstance(table.c.metadata.type, JSONB)
    assert "credential_material" not in table.c
    assert "raw_credential" not in table.c


def test_device_credentials_schema_keeps_uuid_foreign_keys_and_indexes() -> None:
    table = Base.metadata.tables["device_credentials"]
    foreign_keys = {
        f"{foreign_key.column.table.name}.{foreign_key.column.name}"
        for column in table.c
        for foreign_key in column.foreign_keys
    }
    indexes = {
        (index.name, tuple(column.name for column in index.columns)) for index in table.indexes
    }
    uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert foreign_keys == {"tenants.id", "devices.id"}
    assert ("idx_device_credentials_device", ("device_id", "revoked_at", "expires_at")) in indexes
    assert ("idx_device_credentials_hash", ("tenant_id", "credential_hash")) in indexes
    assert ("tenant_id", "credential_hash") in uniques
    assert ("device_id", "credential_version") in uniques
