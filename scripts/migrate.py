from __future__ import annotations

from alembic import command

from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db.migrations import build_alembic_config


def main() -> None:
    command.upgrade(build_alembic_config(get_settings()), "head")


if __name__ == "__main__":
    main()
