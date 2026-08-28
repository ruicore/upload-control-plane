from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE, MIN_PART_SIZE
from upload_control_plane.infrastructure.db.models import UploadTask
from upload_control_plane.infrastructure.db.seed import build_dev_seed_result, seed_dev_data
from upload_control_plane.observability import metrics_registry

from .support import (
    FakeObjectStorage,
    _auth_headers,
    _client,
    _db_session_factory_or_skip,
    _delete_upload_artifacts,
    _session_scope,
    _settings_override,
    _valid_payload,
)


@pytest.mark.parametrize(
    ("case", "expected_message"),
    [
        ("empty_objects", "List should have at least 1 item"),
        ("zero_file_size", "Input should be greater than 0"),
        ("part_too_small", "part size must be at least 5 MiB"),
        ("unsafe_object_name", "object name must not contain path separators"),
        ("client_storage_key", "Extra inputs are not permitted"),
    ],
)
def test_upload_task_create_rejects_invalid_request_shape(
    case: str,
    expected_message: str,
) -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    client = _client(session_factory)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers=_auth_headers("req-upload-validation"),
        json=_invalid_payload(case),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "request.validation_failed"
    assert body["error"]["request_id"] == "req-upload-validation"
    assert expected_message in str(body["error"]["details"]["errors"])


def test_upload_task_create_validation_happens_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    client = _client(session_factory, storage=storage)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers={
            **_auth_headers("req-upload-invalid-no-storage"),
            "Idempotency-Key": "idem-invalid-no-storage",
        },
        json=_invalid_payload("zero_file_size"),
    )

    assert response.status_code == 422
    assert storage.create_calls == []


def test_upload_task_create_rejects_too_many_objects_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    settings = _settings_override(max_open_upload_tasks_per_project=1)
    payload = _valid_payload(
        objects=[
            {
                "dataset_name": "front-camera",
                "object_name": "front_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
            },
            {
                "dataset_name": "rear-camera",
                "object_name": "rear_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
            },
        ]
    )
    with _session_scope(session_factory) as session:
        seed_dev_data(session, settings)

    client = _client(session_factory, storage=storage, settings=settings)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers={
            **_auth_headers("req-upload-too-many-objects"),
            "Idempotency-Key": "idem-quota-too-many-objects",
        },
        json=payload,
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_task.too_many_objects"
    assert storage.create_calls == []


def test_upload_task_create_rejects_open_task_quota_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    settings = _settings_override(max_open_upload_tasks_per_project=1)
    existing_task_idempotency_key = "idem-quota-existing-open-task"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, settings)
        _insert_open_upload_task(session, idempotency_key=existing_task_idempotency_key)

    try:
        client = _client(session_factory, storage=storage, settings=settings)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={
                **_auth_headers("req-upload-open-quota"),
                "Idempotency-Key": "idem-quota-open",
            },
            json=_valid_payload(),
        )

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "quota.open_upload_tasks_exceeded"
        assert storage.create_calls == []
    finally:
        _delete_upload_artifacts(session_factory, existing_task_idempotency_key)


def test_upload_task_create_rejects_project_byte_quota_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    settings = _settings_override(max_bytes_per_project=DEFAULT_PART_SIZE - 1)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, settings)

    client = _client(session_factory, storage=storage, settings=settings)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers={
            **_auth_headers("req-upload-project-bytes"),
            "Idempotency-Key": "idem-quota-project-bytes",
        },
        json=_valid_payload(),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "quota.project_bytes_exceeded"
    assert storage.create_calls == []


def test_upload_task_create_rejects_storage_backpressure_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    settings = _settings_override(
        storage_backpressure_observed_p95_latency_ms=5_000,
        storage_backpressure_retry_after_seconds=30,
    )
    with _session_scope(session_factory) as session:
        seed_dev_data(session, settings)

    client = _client(session_factory, storage=storage, settings=settings)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers={
            **_auth_headers("req-upload-storage-backpressure"),
            "Idempotency-Key": "idem-storage-backpressure-create",
        },
        json=_valid_payload(),
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    body = response.json()
    assert body["error"]["code"] == "storage.backpressure"
    assert body["error"]["details"] == {
        "source": "storage_health",
        "reason": "latency",
        "retry_after_seconds": 30,
    }
    assert storage.create_calls == []


def test_upload_task_create_rejects_metrics_backpressure_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    idempotency_key = "idem-metrics-backpressure-create"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    metrics_registry.reset_for_tests()
    try:
        metrics_registry.observe(
            "storage_operation_duration_seconds",
            0.1,
            {"operation": "create_multipart_upload"},
        )
        metrics_registry.increment(
            "storage_operation_errors_total",
            {"operation": "create_multipart_upload", "error_code": "StorageOperationError"},
        )
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={
                **_auth_headers("req-upload-storage-backpressure"),
                "Idempotency-Key": idempotency_key,
            },
            json=_valid_payload(),
        )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "storage.backpressure"
        assert response.json()["error"]["details"] == {
            "source": "storage_health",
            "reason": "storage_error_rate",
            "retry_after_seconds": 30,
        }
        assert storage.create_calls == []
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert 'storage_backpressure_rejects_total{reason="storage_error_rate"} 1' in metrics.text
    finally:
        metrics_registry.reset_for_tests()
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_upload_task_create_rejects_multipart_file_byte_input() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    client = _client(session_factory)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers=_auth_headers("req-upload-file-bytes"),
        files={"file": ("front_camera.hdf5", b"file-bytes", "application/x-hdf5")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request.validation_failed"


def _invalid_payload(case: str) -> dict[str, object]:
    if case == "empty_objects":
        return {**_valid_payload(), "objects": []}
    if case == "zero_file_size":
        return _valid_payload(
            objects=[
                {
                    "dataset_name": "front-camera",
                    "object_name": "front_camera.hdf5",
                    "file_size_bytes": 0,
                }
            ]
        )
    if case == "part_too_small":
        return _valid_payload(
            objects=[
                {
                    "dataset_name": "front-camera",
                    "object_name": "front_camera.hdf5",
                    "file_size_bytes": 1024,
                    "part_size_bytes": MIN_PART_SIZE - 1,
                }
            ]
        )
    if case == "unsafe_object_name":
        return _valid_payload(
            objects=[
                {
                    "dataset_name": "front-camera",
                    "object_name": "../front_camera.hdf5",
                    "file_size_bytes": DEFAULT_PART_SIZE,
                }
            ]
        )
    if case == "client_storage_key":
        return {**_valid_payload(), "storage_key": "client-controlled-key"}
    raise AssertionError(f"Unknown invalid payload case: {case}")


def _insert_open_upload_task(session: Session, *, idempotency_key: str) -> None:
    seed = build_dev_seed_result()
    now = datetime.now(UTC)
    session.add(
        UploadTask(
            id=uuid.uuid4(),
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            storage_policy_id=seed.storage_policy_id,
            status="PENDING",
            task_initiator="cli",
            source_device_id=None,
            source_device_code=None,
            object_count=1,
            completed_object_count=0,
            failed_object_count=0,
            total_size_bytes=DEFAULT_PART_SIZE,
            uploaded_size_bytes=0,
            idempotency_key=idempotency_key,
            metadata_={"seed": "quota-test"},
            created_by=seed.api_key_id,
            created_at=now,
            updated_at=now,
        )
    )
