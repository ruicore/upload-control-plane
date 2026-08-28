from alembic.config import Config
from alembic.script import ScriptDirectory

from upload_control_plane.config import Settings
from upload_control_plane.infrastructure.db import Base
from upload_control_plane.infrastructure.db.migrations import build_alembic_config


def test_alembic_config_points_at_migrations_directory() -> None:
    config = build_alembic_config(Settings())
    script_location = config.get_main_option("script_location")

    assert isinstance(config, Config)
    assert script_location is not None
    assert script_location.endswith("migrations")
    assert config.get_main_option("sqlalchemy.url") == Settings().database_url


def test_alembic_has_device_credentials_schema_head_revision() -> None:
    script = ScriptDirectory.from_config(build_alembic_config(Settings()))

    assert script.get_current_head() == "20260625_0006"


def test_migration_target_metadata_has_records_schema_tables() -> None:
    assert set(Base.metadata.tables) == {
        "api_keys",
        "audit_events",
        "dataset_validation_results",
        "dataset_tags",
        "datasets",
        "device_credentials",
        "devices",
        "idempotency_records",
        "outbox_events",
        "permission_grants",
        "projects",
        "storage_policies",
        "tag_categories",
        "tags",
        "tenants",
        "upload_events",
        "upload_objects",
        "upload_parts",
        "upload_sessions",
        "upload_tasks",
    }
