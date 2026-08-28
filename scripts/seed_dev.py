from __future__ import annotations

from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db import (
    build_engine,
    build_session_factory,
    session_scope,
)
from upload_control_plane.infrastructure.db.seed import load_seeded_counts, seed_dev_data


def main() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)

    with session_scope(session_factory) as session:
        result = seed_dev_data(session, settings)
        counts = load_seeded_counts(session, result)

    print("Seeded deterministic dev persistence data.")
    print(f"Tenant ID: {result.tenant_id}")
    print(f"API key ID: {result.api_key_id}")
    print(f"Project ID: {result.project_id}")
    print(f"Dataset ID: {result.dataset_id}")
    print(f"Device ID: {result.device_id}")
    print(f"Permission codes: {', '.join(result.permission_codes)}")
    print(f"Seed counts: {counts}")
    print("Dev-only API key value, not persisted in the database:")
    print(result.api_key_value)


if __name__ == "__main__":
    main()
