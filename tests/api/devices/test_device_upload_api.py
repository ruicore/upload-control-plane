from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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
    _device_headers,
    _register_device,
    _session_scope,
    _upload_payload,
)


def test_device_upload_creates_ordinary_upload_task_session_and_uuid_source_device() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DeviceFakeObjectStorage()
    device_code = f"robot-device-upload-{uuid.uuid4()}"
    idempotency_key = "idem-device-upload"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        registered = _register_device(client, seed.project_id, device_code).json()
        device_id = uuid.UUID(registered["device"]["device_id"])
        credential = registered["credential"]["credential_material"]

        response = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-upload", credential),
                "Idempotency-Key": idempotency_key,
            },
            json=_upload_payload(source_device_code="spoofed-code"),
        )

        assert response.status_code == 201
        body = response.json()
        created = body["objects"][0]
        assert storage.create_calls
        with _session_scope(session_factory) as session:
            task = session.get(UploadTask, uuid.UUID(body["task_id"]))
            upload_session = session.get(UploadSession, uuid.UUID(created["session_id"]))
            dataset = session.get(Dataset, uuid.UUID(created["dataset_id"]))
        assert task is not None
        assert upload_session is not None
        assert dataset is not None
        assert task.source_device_id == device_id
        assert upload_session.source_device_id == device_id
        assert dataset.source_device_id == device_id
        assert task.source_device_code == device_code
        assert upload_session.source_device_code == device_code
        assert dataset.source_device_code == device_code
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
        _delete_devices_by_code(session_factory, device_code)


def test_disabled_device_credential_cannot_create_upload_or_presign() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DeviceFakeObjectStorage()
    device_code = f"robot-device-disabled-{uuid.uuid4()}"
    idempotency_key = "idem-device-disabled-before"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        registered = _register_device(client, seed.project_id, device_code).json()
        device_id = uuid.UUID(registered["device"]["device_id"])
        credential = registered["credential"]["credential_material"]
        created = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-upload-before-disable", credential),
                "Idempotency-Key": idempotency_key,
            },
            json=_upload_payload(),
        )
        assert created.status_code == 201
        session_id = created.json()["objects"][0]["session_id"]

        disabled = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/disable",
            headers=_api_headers("req-device-disable"),
        )
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "DISABLED"

        upload = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-upload-disabled", credential),
                "Idempotency-Key": "idem-device-disabled-after",
            },
            json=_upload_payload(),
        )
        presign = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_device_headers("req-device-presign-disabled", credential),
            json={"part_numbers": [1]},
        )

        assert upload.status_code == 403
        assert upload.json()["error"]["code"] == "device.inactive"
        assert presign.status_code == 403
        assert presign.json()["error"]["code"] == "device.inactive"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key, "idem-device-disabled-after")
        _delete_devices_by_code(session_factory, device_code)


def test_expired_device_credential_cannot_upload() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    device_code = f"robot-device-expired-{uuid.uuid4()}"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DeviceFakeObjectStorage())
        registered = _register_device(client, seed.project_id, device_code).json()
        credential = registered["credential"]["credential_material"]
        credential_id = uuid.UUID(registered["credential"]["credential_id"])
        device_id = registered["device"]["device_id"]
        with _session_scope(session_factory) as session:
            stored = session.get(DeviceCredential, credential_id)
            assert stored is not None
            stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        response = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-expired", credential),
                "Idempotency-Key": "idem-device-expired",
            },
            json=_upload_payload(),
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "device.credential_expired"
    finally:
        _delete_upload_artifacts(session_factory, "idem-device-expired")
        _delete_devices_by_code(session_factory, device_code)
