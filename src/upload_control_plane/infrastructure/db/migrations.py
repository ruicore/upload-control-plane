from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from upload_control_plane.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def build_alembic_config(settings: Settings) -> Config:
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config
