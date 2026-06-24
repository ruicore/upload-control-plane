from pathlib import Path

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

from upload_control_plane.infrastructure.db import Base

RECORD_TABLES = (
    "dataset_validation_results",
    "upload_events",
    "audit_events",
    "outbox_events",
    "idempotency_records",
)


def test_record_tables_use_uuid_internal_primary_keys() -> None:
    for table_name in RECORD_TABLES:
        table = Base.metadata.tables[table_name]

        assert [column.name for column in table.primary_key.columns] == ["id"]
        assert isinstance(table.c.id.type, UUID)


def test_record_tables_foreign_keys_match_prd_traceability_shape() -> None:
    expected_targets = {
        "dataset_validation_results.tenant_id": {"tenants.id"},
        "dataset_validation_results.project_id": {"projects.id"},
        "dataset_validation_results.dataset_id": {"datasets.id"},
        "upload_events.tenant_id": {"tenants.id"},
        "upload_events.project_id": {"projects.id"},
        "upload_events.dataset_id": {"datasets.id"},
        "upload_events.upload_task_id": {"upload_tasks.id"},
        "upload_events.upload_object_id": {"upload_objects.id"},
        "upload_events.session_id": {"upload_sessions.id"},
        "audit_events.tenant_id": {"tenants.id"},
        "audit_events.project_id": {"projects.id"},
        "audit_events.dataset_id": {"datasets.id"},
        "outbox_events.tenant_id": {"tenants.id"},
        "idempotency_records.tenant_id": {"tenants.id"},
    }

    for qualified_column, targets in expected_targets.items():
        table_name, column_name = qualified_column.split(".")
        table = Base.metadata.tables[table_name]

        assert {fk.target_fullname for fk in table.c[column_name].foreign_keys} == targets

    outbox = Base.metadata.tables["outbox_events"]
    audit = Base.metadata.tables["audit_events"]

    assert isinstance(outbox.c.aggregate_id.type, UUID)
    assert outbox.c.aggregate_id.foreign_keys == set()
    assert isinstance(audit.c.resource_id.type, type(audit.c.action.type))
    assert audit.c.resource_id.foreign_keys == set()


def test_record_status_columns_use_existing_postgres_enums() -> None:
    validation_status = Base.metadata.tables["dataset_validation_results"].c.status
    outbox_status = Base.metadata.tables["outbox_events"].c.status

    assert isinstance(validation_status.type, ENUM)
    assert validation_status.type.name == "validation_status"
    assert not validation_status.type.create_type

    assert isinstance(outbox_status.type, ENUM)
    assert outbox_status.type.name == "outbox_status"
    assert not outbox_status.type.create_type


def test_record_json_payload_columns_use_jsonb() -> None:
    expected_jsonb_columns = {
        "dataset_validation_results": {"extracted_metadata", "errors"},
        "upload_events": {"payload"},
        "audit_events": {"before_state", "after_state", "metadata"},
        "outbox_events": {"payload"},
        "idempotency_records": {"response_body"},
    }

    for table_name, column_names in expected_jsonb_columns.items():
        table = Base.metadata.tables[table_name]
        for column_name in column_names:
            assert isinstance(table.c[column_name].type, JSONB)


def test_record_prd_indexes() -> None:
    expected_indexes = {
        "dataset_validation_results": {
            ("idx_dataset_validation_dataset", ("dataset_id", "created_at"), False),
            ("idx_dataset_validation_status", ("project_id", "status"), False),
        },
        "upload_events": {
            ("idx_upload_events_project_id", ("project_id", "created_at"), False),
            ("idx_upload_events_dataset_id", ("dataset_id", "created_at"), False),
            ("idx_upload_events_task_id", ("upload_task_id", "created_at"), False),
            ("idx_upload_events_object_id", ("upload_object_id", "created_at"), False),
            ("idx_upload_events_session_id", ("session_id", "created_at"), False),
            ("idx_upload_events_tenant_type", ("tenant_id", "event_type", "created_at"), False),
        },
        "audit_events": {
            (
                "idx_audit_events_resource",
                ("tenant_id", "resource_type", "resource_id", "created_at"),
                False,
            ),
            (
                "idx_audit_events_actor",
                ("tenant_id", "actor_type", "actor_id", "created_at"),
                False,
            ),
            ("idx_audit_events_action", ("tenant_id", "action", "created_at"), False),
        },
        "outbox_events": {
            ("idx_outbox_events_status_next_attempt", ("status", "next_attempt_at"), False),
            (
                "idx_outbox_events_aggregate",
                ("aggregate_type", "aggregate_id", "created_at"),
                False,
            ),
        },
        "idempotency_records": {
            ("idx_idempotency_records_expires_at", ("expires_at",), False),
        },
    }

    for table_name, indexes in expected_indexes.items():
        table = Base.metadata.tables[table_name]

        assert {
            (index.name, tuple(column.name for column in index.columns), index.unique)
            for index in table.indexes
        } == indexes


def test_idempotency_records_key_fingerprint_and_expiry_semantics() -> None:
    table = Base.metadata.tables["idempotency_records"]

    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("tenant_id", "key") in unique_columns
    assert table.c.key.nullable is False
    assert table.c.request_fingerprint.nullable is False
    assert table.c.expires_at.nullable is False


def test_records_migration_follows_upload_lifecycle_revision() -> None:
    migration = Path(
        "migrations/versions/20260624_0005_validation_audit_outbox_idempotency_schema.py"
    ).read_text()

    assert 'revision: str = "20260624_0005"' in migration
    assert 'down_revision: str | None = "20260624_0004"' in migration
    for table_name in RECORD_TABLES:
        assert f'"{table_name}",' in migration
    assert 'postgresql.ENUM(name="validation_status", create_type=False)' in migration
    assert 'postgresql.ENUM(name="outbox_status", create_type=False)' in migration
    assert '"idx_outbox_events_status_next_attempt"' in migration
    assert '"idx_outbox_events_aggregate"' in migration
    assert '"idx_idempotency_records_expires_at"' in migration
    assert '"tenant_id", "key"' in migration
    assert '"upload_batches"' not in migration
    assert '"batch_id"' not in migration
