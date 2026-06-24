from pathlib import Path

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

from upload_control_plane.infrastructure.db import Base


def test_upload_lifecycle_tables_use_uuid_internal_keys() -> None:
    for table_name in ("upload_tasks", "upload_objects", "upload_sessions"):
        table = Base.metadata.tables[table_name]

        assert [column.name for column in table.primary_key.columns] == ["id"]
        assert isinstance(table.c.id.type, UUID)

    upload_parts = Base.metadata.tables["upload_parts"]

    assert [column.name for column in upload_parts.primary_key.columns] == [
        "session_id",
        "part_number",
    ]
    assert isinstance(upload_parts.c.session_id.type, UUID)


def test_upload_lifecycle_foreign_keys_match_prd_ownership_shape() -> None:
    upload_objects = Base.metadata.tables["upload_objects"]

    expected_targets = {
        "upload_tasks.tenant_id": {"tenants.id"},
        "upload_tasks.project_id": {"projects.id"},
        "upload_tasks.storage_policy_id": {"storage_policies.id"},
        "upload_tasks.source_device_id": {"devices.id"},
        "upload_objects.tenant_id": {"tenants.id"},
        "upload_objects.project_id": {"projects.id"},
        "upload_objects.dataset_id": {"datasets.id"},
        "upload_objects.upload_task_id": {"upload_tasks.id"},
        "upload_sessions.tenant_id": {"tenants.id"},
        "upload_sessions.project_id": {"projects.id"},
        "upload_sessions.dataset_id": {"datasets.id"},
        "upload_sessions.upload_task_id": {"upload_tasks.id"},
        "upload_sessions.upload_object_id": {"upload_objects.id"},
        "upload_sessions.source_device_id": {"devices.id"},
        "upload_parts.session_id": {"upload_sessions.id"},
    }

    for qualified_column, targets in expected_targets.items():
        table_name, column_name = qualified_column.split(".")
        table = Base.metadata.tables[table_name]

        assert {fk.target_fullname for fk in table.c[column_name].foreign_keys} == targets

    assert upload_objects.c.upload_session_id.foreign_keys == set()
    assert isinstance(upload_objects.c.upload_session_id.type, UUID)


def test_source_device_id_is_registered_device_uuid_and_code_is_metadata_text() -> None:
    upload_tasks = Base.metadata.tables["upload_tasks"]
    upload_sessions = Base.metadata.tables["upload_sessions"]

    for table in (upload_tasks, upload_sessions):
        assert isinstance(table.c.source_device_id.type, UUID)
        assert {fk.target_fullname for fk in table.c.source_device_id.foreign_keys} == {
            "devices.id"
        }
        assert isinstance(
            table.c.source_device_code.type,
            type(Base.metadata.tables["devices"].c.device_code.type),
        )


def test_upload_lifecycle_status_columns_use_existing_postgres_enums() -> None:
    expected_status_enums = {
        "upload_tasks": "upload_task_status",
        "upload_objects": "upload_object_status",
        "upload_sessions": "upload_session_status",
        "upload_parts": "upload_part_status",
    }

    for table_name, enum_name in expected_status_enums.items():
        status = Base.metadata.tables[table_name].c.status

        assert isinstance(status.type, ENUM)
        assert status.type.name == enum_name
        assert not status.type.create_type

    assert isinstance(Base.metadata.tables["upload_tasks"].c.metadata.type, JSONB)
    assert isinstance(Base.metadata.tables["upload_sessions"].c.metadata.type, JSONB)


def test_upload_lifecycle_prd_indexes() -> None:
    expected_indexes = {
        "upload_tasks": {
            ("idx_upload_tasks_project_status", ("project_id", "status"), False),
            ("idx_upload_tasks_source_device", ("tenant_id", "source_device_id"), False),
            (
                "idx_upload_tasks_source_device_code",
                ("tenant_id", "source_device_code"),
                False,
            ),
        },
        "upload_objects": {
            ("idx_upload_objects_task_status", ("upload_task_id", "status"), False),
            ("idx_upload_objects_dataset_id", ("dataset_id",), False),
        },
        "upload_sessions": {
            ("idx_upload_sessions_tenant_status", ("tenant_id", "status"), False),
            ("idx_upload_sessions_project_id", ("project_id",), False),
            ("idx_upload_sessions_dataset_id", ("dataset_id",), False),
            ("idx_upload_sessions_task_id", ("upload_task_id",), False),
            ("idx_upload_sessions_object_id", ("upload_object_id",), False),
            ("idx_upload_sessions_expires_at", ("expires_at",), False),
            ("idx_upload_sessions_storage_upload_id", ("storage_upload_id",), False),
            ("idx_upload_sessions_source_device", ("tenant_id", "source_device_id"), False),
            (
                "idx_upload_sessions_source_device_code",
                ("tenant_id", "source_device_code"),
                False,
            ),
        },
        "upload_parts": {
            ("idx_upload_parts_session_status", ("session_id", "status"), False),
        },
    }

    for table_name, indexes in expected_indexes.items():
        table = Base.metadata.tables[table_name]

        assert {
            (index.name, tuple(column.name for column in index.columns), index.unique)
            for index in table.indexes
        } == indexes


def test_upload_lifecycle_constraints_include_idempotency_and_part_bounds() -> None:
    expected_unique_constraints = {
        "upload_tasks": {("tenant_id", "idempotency_key")},
        "upload_sessions": {
            ("bucket_name", "object_key"),
            ("tenant_id", "idempotency_key"),
        },
    }

    for table_name, expected_columns in expected_unique_constraints.items():
        table = Base.metadata.tables[table_name]
        unique_columns = {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }

        assert expected_columns <= unique_columns

    upload_sessions_checks = {
        str(constraint.sqltext)
        for constraint in Base.metadata.tables["upload_sessions"].constraints
        if isinstance(constraint, CheckConstraint)
    }
    upload_parts_checks = {
        str(constraint.sqltext)
        for constraint in Base.metadata.tables["upload_parts"].constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "file_size_bytes > 0" in upload_sessions_checks
    assert "part_size_bytes > 0" in upload_sessions_checks
    assert "part_count >= 1 AND part_count <= 10000" in upload_sessions_checks
    assert "part_number >= 1 AND part_number <= 10000" in upload_parts_checks
    assert "expected_size_bytes >= 0" in upload_parts_checks


def test_upload_lifecycle_scope_excludes_batches_and_idempotency_records() -> None:
    assert "upload_batches" not in Base.metadata.tables
    assert "idempotency_records" not in Base.metadata.tables
    assert all("batch_id" not in table.c for table in Base.metadata.tables.values())


def test_upload_lifecycle_migration_follows_dataset_governance_revision() -> None:
    migration = Path("migrations/versions/20260624_0004_upload_lifecycle_schema.py").read_text()

    assert 'revision: str = "20260624_0004"' in migration
    assert 'down_revision: str | None = "20260624_0003"' in migration
    assert '"upload_tasks",' in migration
    assert '"upload_objects",' in migration
    assert '"upload_sessions",' in migration
    assert '"upload_parts",' in migration
    assert '"source_device_id", postgresql.UUID(as_uuid=True)' in migration
    assert '"source_device_code", sa.Text()' in migration
    assert '"upload_batches"' not in migration
    assert '"batch_id"' not in migration
    assert '"idempotency_records"' not in migration
