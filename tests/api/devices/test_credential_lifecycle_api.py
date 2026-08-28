from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Device,
    DeviceCredential,
    PermissionGrant,
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


def test_rotation_revokes_old_credential_without_overlap_and_new_credential_can_upload() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DeviceFakeObjectStorage()
    device_code = f"robot-device-rotate-{uuid.uuid4()}"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        registered = _register_device(client, seed.project_id, device_code).json()
        device_id = uuid.UUID(registered["device"]["device_id"])
        old_credential = registered["credential"]["credential_material"]
        rotated = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/credentials/rotate",
            headers=_api_headers("req-device-rotate"),
            json={"overlap_seconds": 0},
        )
        assert rotated.status_code == 200
        new_credential = rotated.json()["credential"]["credential_material"]
        assert new_credential != old_credential

        old_upload = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-old-revoked", old_credential),
                "Idempotency-Key": "idem-device-old-revoked",
            },
            json=_upload_payload(),
        )
        new_upload = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/upload",
            headers={
                **_device_headers("req-device-new-credential", new_credential),
                "Idempotency-Key": "idem-device-new-credential",
            },
            json=_upload_payload(),
        )

        assert old_upload.status_code == 401
        assert old_upload.json()["error"]["code"] == "device.credential_revoked"
        assert new_upload.status_code == 201
    finally:
        _delete_upload_artifacts(
            session_factory,
            "idem-device-old-revoked",
            "idem-device-new-credential",
        )
        _delete_devices_by_code(session_factory, device_code)


def test_device_credential_lifecycle_preserves_grants_overlap_revoke_and_audit() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    device_code = f"robot-device-lifecycle-{uuid.uuid4()}"
    expected_permission_codes = {
        "project.view",
        "dataset.view",
        "dataset.upload",
        "upload.create",
        "upload.pause",
        "upload.resume",
        "upload.complete",
        "upload.abort",
    }
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DeviceFakeObjectStorage())
        registered = _register_device(client, seed.project_id, device_code)
        assert registered.status_code == 201
        registration = registered.json()
        device_id = uuid.UUID(registration["device"]["device_id"])
        original_credential_id = uuid.UUID(registration["credential"]["credential_id"])

        with _session_scope(session_factory) as session:
            grants = list(
                session.scalars(
                    select(PermissionGrant)
                    .where(PermissionGrant.subject_type == "device")
                    .where(PermissionGrant.subject_id == device_id)
                    .where(PermissionGrant.resource_type == "project")
                    .where(PermissionGrant.resource_id == seed.project_id)
                )
            )
            registration_audit = session.scalar(
                select(AuditEvent)
                .where(AuditEvent.resource_type == "device")
                .where(AuditEvent.resource_id == str(device_id))
                .where(AuditEvent.action == "device.register")
            )
        assert len(grants) == 8
        assert {grant.permission_code for grant in grants} == expected_permission_codes
        assert {grant.effect for grant in grants} == {"ALLOW"}
        assert {grant.source for grant in grants} == {"device_registration"}
        assert registration_audit is not None
        assert registration_audit.request_id == "req-device-register"
        assert registration_audit.after_state == {
            "device_code": device_code,
            "credential_version": 1,
        }
        assert registration_audit.metadata_ == {"source": "device_service"}

        rotation_started_at = datetime.now(UTC)
        rotated = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/credentials/rotate",
            headers=_api_headers("req-device-overlap"),
            json={"overlap_seconds": 120},
        )
        assert rotated.status_code == 200
        rotation = rotated.json()
        assert rotation["device"]["credential_version"] == 2
        assert rotation["credential"]["credential_version"] == 2
        rotated_credential_id = uuid.UUID(rotation["credential"]["credential_id"])

        with _session_scope(session_factory) as session:
            original = session.get(DeviceCredential, original_credential_id)
            current = session.get(DeviceCredential, rotated_credential_id)
            device = session.get(Device, device_id)
            rotation_audit = session.scalar(
                select(AuditEvent)
                .where(AuditEvent.resource_type == "device")
                .where(AuditEvent.resource_id == str(device_id))
                .where(AuditEvent.action == "device.credentials.rotate")
            )
        assert original is not None
        assert original.revoked_at is None
        assert original.expires_at is not None
        assert rotation_started_at + timedelta(seconds=115) < original.expires_at
        assert original.expires_at <= datetime.now(UTC) + timedelta(seconds=120)
        assert current is not None
        assert device is not None
        assert device.credential_hash == current.credential_hash
        assert device.credential_version == 2
        assert rotation["credential"]["credential_material"] not in current.credential_hash
        assert rotation_audit is not None
        assert rotation_audit.request_id == "req-device-overlap"
        assert rotation_audit.after_state == {
            "credential_version": 2,
            "overlap_seconds": 120,
        }

        revoked = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/credentials/revoke",
            headers=_api_headers("req-device-revoke"),
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "REVOKED"

        enabled = client.post(
            f"/v1/projects/{seed.project_id}/devices/{device_id}/enable",
            headers=_api_headers("req-device-enable-revoked"),
        )
        assert enabled.status_code == 409
        assert enabled.json()["error"]["code"] == "device.revoked"

        with _session_scope(session_factory) as session:
            credentials = list(
                session.scalars(
                    select(DeviceCredential).where(DeviceCredential.device_id == device_id)
                )
            )
            revoke_audit = session.scalar(
                select(AuditEvent)
                .where(AuditEvent.resource_type == "device")
                .where(AuditEvent.resource_id == str(device_id))
                .where(AuditEvent.action == "device.credentials.revoke")
            )
        assert len(credentials) == 2
        assert all(credential.revoked_at is not None for credential in credentials)
        assert revoke_audit is not None
        assert revoke_audit.request_id == "req-device-revoke"
        assert revoke_audit.before_state is not None
        assert revoke_audit.before_state["status"] == "ACTIVE"
        assert revoke_audit.after_state is not None
        assert revoke_audit.after_state["status"] == "REVOKED"
    finally:
        _delete_devices_by_code(session_factory, device_code)
