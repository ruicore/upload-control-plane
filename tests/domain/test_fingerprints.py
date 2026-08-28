from uuid import UUID

import pytest

from upload_control_plane.domain.fingerprints import (
    JSONValue,
    assert_json_value,
    canonical_json,
    generate_request_fingerprint,
)


def test_canonical_json_is_deterministic_for_object_key_order() -> None:
    first: JSONValue = {"b": [2, {"z": True, "a": None}], "a": "value"}
    second: JSONValue = {"a": "value", "b": [2, {"a": None, "z": True}]}

    assert canonical_json(first) == canonical_json(second)


def test_request_fingerprint_normalizes_method_and_body_order() -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000001")

    first = generate_request_fingerprint(
        method="post",
        path="/v1/projects/00000000-0000-4000-8000-000000000002/upload-tasks",
        tenant_id=tenant_id,
        body={"objects": [{"file_size_bytes": 10, "object_name": "a.hdf5"}], "task_name": "t"},
    )
    second = generate_request_fingerprint(
        method="POST",
        path="/v1/projects/00000000-0000-4000-8000-000000000002/upload-tasks",
        tenant_id=tenant_id,
        body={"task_name": "t", "objects": [{"object_name": "a.hdf5", "file_size_bytes": 10}]},
    )

    assert first == second


def test_request_fingerprint_changes_for_different_body_or_tenant() -> None:
    tenant_id = UUID("00000000-0000-4000-8000-000000000001")
    other_tenant_id = UUID("00000000-0000-4000-8000-000000000002")

    original = generate_request_fingerprint(
        method="POST",
        path="/v1/projects/project/upload-tasks",
        tenant_id=tenant_id,
        body={"task_name": "a"},
    )

    assert original != generate_request_fingerprint(
        method="POST",
        path="/v1/projects/project/upload-tasks",
        tenant_id=tenant_id,
        body={"task_name": "b"},
    )
    assert original != generate_request_fingerprint(
        method="POST",
        path="/v1/projects/project/upload-tasks",
        tenant_id=other_tenant_id,
        body={"task_name": "a"},
    )


def test_assert_json_value_rejects_non_json_values() -> None:
    with pytest.raises(TypeError):
        assert_json_value(object())
