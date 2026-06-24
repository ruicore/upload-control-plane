from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from upload_control_plane.infrastructure.db import Base


def test_core_schema_metadata_tables_and_uuid_keys() -> None:
    for table_name in ("tenants", "storage_policies", "api_keys", "projects"):
        table = Base.metadata.tables[table_name]

        assert [column.name for column in table.primary_key.columns] == ["id"]
        assert isinstance(table.c.id.type, UUID)

    assert isinstance(Base.metadata.tables["storage_policies"].c.tenant_id.type, UUID)
    assert isinstance(Base.metadata.tables["api_keys"].c.tenant_id.type, UUID)
    assert isinstance(Base.metadata.tables["projects"].c.tenant_id.type, UUID)
    assert isinstance(Base.metadata.tables["projects"].c.storage_policy_id.type, UUID)


def test_api_keys_store_hashes_not_raw_secrets() -> None:
    columns = set(Base.metadata.tables["api_keys"].c.keys())

    assert "key_hash" in columns
    assert "api_key" not in columns
    assert "raw_key" not in columns
    assert "secret" not in columns
    assert "secret_key" not in columns


def test_core_schema_prd_indexes_and_constraints() -> None:
    storage_policies = Base.metadata.tables["storage_policies"]
    api_keys = Base.metadata.tables["api_keys"]
    projects = Base.metadata.tables["projects"]

    assert {
        (index.name, tuple(column.name for column in index.columns))
        for index in storage_policies.indexes
    } == {
        ("idx_storage_policies_tenant_status", ("tenant_id", "status")),
    }
    assert {
        (index.name, tuple(column.name for column in index.columns)) for index in api_keys.indexes
    } == {
        ("idx_api_keys_tenant_id", ("tenant_id",)),
    }
    assert {
        (index.name, tuple(column.name for column in index.columns)) for index in projects.indexes
    } == {
        ("idx_projects_tenant_status", ("tenant_id", "status")),
    }

    storage_unique_constraints = [
        constraint
        for constraint in storage_policies.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    project_unique_constraints = [
        constraint
        for constraint in projects.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert any(
        constraint.name == "uq_storage_policies_tenant_id"
        and [column.name for column in constraint.columns] == ["tenant_id", "name"]
        for constraint in storage_unique_constraints
    )
    assert any(
        constraint.name == "uq_projects_tenant_id"
        and [column.name for column in constraint.columns] == ["tenant_id", "slug"]
        for constraint in project_unique_constraints
    )


def test_jsonb_and_array_columns_match_prd_shape() -> None:
    storage_policies = Base.metadata.tables["storage_policies"]
    api_keys = Base.metadata.tables["api_keys"]
    projects = Base.metadata.tables["projects"]

    assert isinstance(storage_policies.c.metadata.type, JSONB)
    assert isinstance(api_keys.c.scopes.type, ARRAY)
    assert isinstance(projects.c.metadata_schema.type, JSONB)
    assert isinstance(projects.c.metadata.type, JSONB)
