import uuid

from upload_control_plane.infrastructure.db.seed import (
    DEV_API_KEY_VALUE,
    build_dev_seed_result,
    dev_seed_uuid,
    hash_dev_secret,
)


def test_dev_seed_uses_deterministic_uuid_values() -> None:
    first = build_dev_seed_result()
    second = build_dev_seed_result()

    assert first == second
    assert first.tenant_id == dev_seed_uuid("tenant:dev-industrial")
    assert isinstance(first.project_id, uuid.UUID)


def test_dev_api_key_seed_result_exposes_hash_separately_from_dev_only_value() -> None:
    result = build_dev_seed_result()

    assert result.api_key_value == DEV_API_KEY_VALUE
    assert result.api_key_hash == hash_dev_secret(DEV_API_KEY_VALUE)
    assert result.api_key_value not in result.api_key_hash
    assert result.api_key_hash.startswith("sha256:")


def test_dev_seed_permission_codes_unlock_t02_acceptance_path() -> None:
    result = build_dev_seed_result()

    assert "project.view" in result.permission_codes
    assert {"dataset.upload", "upload.create"} & set(result.permission_codes)
