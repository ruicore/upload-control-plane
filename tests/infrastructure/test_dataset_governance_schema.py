from pathlib import Path

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID

from upload_control_plane.infrastructure.db import Base


def test_dataset_governance_tables_use_uuid_internal_keys() -> None:
    for table_name in (
        "datasets",
        "tag_categories",
        "tags",
        "devices",
        "permission_grants",
    ):
        table = Base.metadata.tables[table_name]

        assert [column.name for column in table.primary_key.columns] == ["id"]
        assert isinstance(table.c.id.type, UUID)

    dataset_tags = Base.metadata.tables["dataset_tags"]

    assert [column.name for column in dataset_tags.primary_key.columns] == ["dataset_id", "tag_id"]
    assert isinstance(dataset_tags.c.dataset_id.type, UUID)
    assert isinstance(dataset_tags.c.tag_id.type, UUID)


def test_dataset_device_identity_columns_match_prd_authorization_shape() -> None:
    datasets = Base.metadata.tables["datasets"]
    devices = Base.metadata.tables["devices"]

    assert isinstance(datasets.c.source_device_id.type, UUID)
    assert isinstance(datasets.c.source_device_code.type, type(devices.c.device_code.type))
    assert "source_device_code" not in Base.metadata.tables["permission_grants"].c

    source_device_foreign_keys = {
        foreign_key.target_fullname for foreign_key in datasets.c.source_device_id.foreign_keys
    }
    assert source_device_foreign_keys == {"devices.id"}


def test_dataset_status_columns_remain_separate_enums() -> None:
    datasets = Base.metadata.tables["datasets"]

    assert isinstance(datasets.c.status.type, ENUM)
    assert datasets.c.status.type.name == "dataset_status"
    assert isinstance(datasets.c.validation_status.type, ENUM)
    assert datasets.c.validation_status.type.name == "validation_status"
    assert isinstance(datasets.c.recovery_status.type, ENUM)
    assert datasets.c.recovery_status.type.name == "recovery_status"
    assert isinstance(datasets.c.preview_metadata.type, JSONB)
    assert isinstance(datasets.c.metadata.type, JSONB)
    assert isinstance(datasets.c.labels.type, ARRAY)


def test_dataset_governance_prd_indexes() -> None:
    expected_indexes = {
        "datasets": {
            ("idx_datasets_project_status", ("project_id", "status"), False),
            ("idx_datasets_tenant_status", ("tenant_id", "status"), False),
            ("idx_datasets_source_device", ("tenant_id", "source_device_id"), False),
            ("idx_datasets_source_device_code", ("tenant_id", "source_device_code"), False),
            ("idx_datasets_validation_status", ("project_id", "validation_status"), False),
            ("idx_datasets_recovery_status", ("project_id", "recovery_status"), False),
            ("idx_datasets_object_unique", ("bucket_name", "object_key"), True),
        },
        "devices": {("idx_devices_tenant_status", ("tenant_id", "status"), False)},
        "tags": {("idx_tags_project_category", ("project_id", "category_id"), False)},
        "permission_grants": {
            ("idx_permission_grants_subject", ("tenant_id", "subject_type", "subject_id"), False),
            (
                "idx_permission_grants_resource",
                ("tenant_id", "resource_type", "resource_id"),
                False,
            ),
            ("idx_permission_grants_permission", ("tenant_id", "permission_code"), False),
            ("idx_permission_grants_expires_at", ("expires_at",), False),
        },
    }

    for table_name, indexes in expected_indexes.items():
        table = Base.metadata.tables[table_name]

        assert {
            (index.name, tuple(column.name for column in index.columns), index.unique)
            for index in table.indexes
        } == indexes


def test_dataset_governance_unique_constraints() -> None:
    expected_constraints: dict[str, set[tuple[str, ...]]] = {
        "tag_categories": {("project_id", "name")},
        "tags": {("project_id", "name")},
        "devices": {("tenant_id", "device_code")},
        "permission_grants": {
            (
                "tenant_id",
                "subject_type",
                "subject_id",
                "resource_type",
                "resource_id",
                "permission_code",
                "effect",
            )
        },
    }

    for table_name, expected_columns in expected_constraints.items():
        table = Base.metadata.tables[table_name]
        unique_columns = {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }

        assert expected_columns <= unique_columns


def test_permission_grants_support_resource_scoped_allow_deny_with_expiry() -> None:
    permission_grants = Base.metadata.tables["permission_grants"]

    assert isinstance(permission_grants.c.subject_id.type, UUID)
    assert isinstance(permission_grants.c.resource_id.type, UUID)
    assert isinstance(permission_grants.c.effect.type, ENUM)
    assert permission_grants.c.effect.type.name == "permission_effect"
    assert "expires_at" in permission_grants.c
    assert isinstance(permission_grants.c.conditions.type, JSONB)

    check_constraint_sql = {
        str(constraint.sqltext)
        for constraint in permission_grants.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "subject_type IN ('user', 'group', 'device', 'api_key')" in check_constraint_sql
    assert "'dataset'" in next(
        constraint_sql
        for constraint_sql in check_constraint_sql
        if "resource_type IN" in constraint_sql
    )


def test_dataset_governance_migration_follows_core_schema_revision() -> None:
    migration = Path("migrations/versions/20260624_0003_dataset_governance_schema.py").read_text()

    assert 'revision: str = "20260624_0003"' in migration
    assert 'down_revision: str | None = "20260624_0002"' in migration
    assert '"devices",' in migration
    assert '"datasets",' in migration
    assert '"permission_grants",' in migration
    assert '"source_device_id", postgresql.UUID(as_uuid=True)' in migration
    assert '"source_device_code", sa.Text()' in migration
