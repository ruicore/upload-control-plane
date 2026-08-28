from __future__ import annotations

import uuid

from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db.models import (
    Dataset,
    DeviceCredential,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import build_dev_seed_result, seed_dev_data

from .support import (
    DeviceFakeObjectStorage,
    _api_headers,
    _client,
    _db_session_factory_or_skip,
    _delete_devices_by_code,
    _delete_upload_artifacts,
    _register_device,
    _session_scope,
    _upload_payload,
)


def test_device_register_returns_credential_once_and_get_does_not_reveal_secret() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    device_code = f"robot-device-{uuid.uuid4()}"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DeviceFakeObjectStorage())
        registered = _register_device(client, seed.project_id, device_code)

        assert registered.status_code == 201
        body = registered.json()
        device_id = uuid.UUID(body["device"]["device_id"])
        credential = body["credential"]
        assert credential["credential_material"].startswith("ucp_device_")
        assert credential["credential_version"] == 1

        fetched = client.get(
            f"/v1/projects/{seed.project_id}/devices/{device_id}",
            headers=_api_headers("req-device-get"),
        )
        assert fetched.status_code == 200
        assert "credential" not in fetched.json()
        assert "credential_material" not in str(fetched.json())

        with _session_scope(session_factory) as session:
            stored = session.get(DeviceCredential, uuid.UUID(credential["credential_id"]))
            assert stored is not None
            assert credential["credential_material"] not in stored.credential_hash
            assert stored.credential_hash.startswith("sha256:")
    finally:
        _delete_devices_by_code(session_factory, device_code)


def test_source_device_code_only_is_metadata_and_not_authorization_subject() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DeviceFakeObjectStorage()
    idempotency_key = "idem-source-code-only"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_api_headers("req-source-code-only"), "Idempotency-Key": idempotency_key},
            json=_upload_payload(source_device_code="unregistered-text-code"),
        )

        assert response.status_code == 201
        created = response.json()["objects"][0]
        with _session_scope(session_factory) as session:
            task = session.get(UploadTask, uuid.UUID(response.json()["task_id"]))
            upload_session = session.get(UploadSession, uuid.UUID(created["session_id"]))
            dataset = session.get(Dataset, uuid.UUID(created["dataset_id"]))
        assert task is not None
        assert upload_session is not None
        assert dataset is not None
        assert task.source_device_id is None
        assert upload_session.source_device_id is None
        assert dataset.source_device_id is None
        assert task.source_device_code == "unregistered-text-code"
        assert upload_session.source_device_code == "unregistered-text-code"
        assert dataset.source_device_code == "unregistered-text-code"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
