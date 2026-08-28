from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from _upload_session_runtime_support import (
    RuntimeFakeObjectStorage,
    _auth_headers,
    _client,
    _create_upload_task,
    _created_object,
    _db_session_factory_or_skip,
    _delete_test_grants,
    _delete_upload_artifacts,
    _session_scope,
    _settings_override,
    _upsert_grant,
)
from sqlalchemy import delete

from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.domain.storage import ListedPart
from upload_control_plane.infrastructure.db.models import (
    Tenant,
    UploadPart,
    UploadSession,
)
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)
from upload_control_plane.observability import metrics_registry


def test_runtime_status_presign_ack_and_db_list_parts() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-happy"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        created_object = _created_object(created)
        session_id = uuid.UUID(created_object["session_id"])

        status = client.get(f"/v1/uploads/{session_id}", headers=_auth_headers("req-status"))
        assert status.status_code == 200
        assert status.json()["status"] == "INITIATED"
        assert status.json()["uploaded_part_count"] == 0

        presign = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign"),
            json={"part_numbers": [1], "expires_in_seconds": 600},
        )
        assert presign.status_code == 200
        presign_body = presign.json()
        assert presign_body["method"] == "PUT"
        assert presign_body["parts"][0]["part_number"] == 1
        assert "fake-signature" in presign_body["parts"][0]["url"]
        assert storage.presign_calls == [(created_object["bucket"], 1, 600)]

        with _session_scope(session_factory) as session:
            part = session.get(UploadPart, (session_id, 1))
            upload_session = session.get(UploadSession, session_id)
            assert part is not None
            assert upload_session is not None
            assert part.status == "PRESIGNED"
            assert part.last_presigned_at is not None
            assert part.presign_expires_at is not None
            assert upload_session.status == "UPLOADING"

        ack = client.post(
            f"/v1/uploads/{session_id}/parts/ack",
            headers=_auth_headers("req-ack"),
            json={
                "parts": [
                    {
                        "part_number": 1,
                        "etag": '"etag-1"',
                        "size_bytes": DEFAULT_PART_SIZE,
                    }
                ]
            },
        )
        assert ack.status_code == 200
        assert ack.json() == {
            "session_id": str(session_id),
            "acknowledged_part_count": 1,
            "uploaded_part_count": 1,
        }

        second_ack = client.post(
            f"/v1/uploads/{session_id}/parts/ack",
            headers=_auth_headers("req-ack-retry"),
            json={
                "parts": [
                    {
                        "part_number": 1,
                        "etag": '"etag-1"',
                        "size_bytes": DEFAULT_PART_SIZE,
                    }
                ]
            },
        )
        assert second_ack.status_code == 200
        assert second_ack.json()["uploaded_part_count"] == 1

        represign = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-represign-uploaded"),
            json={"part_numbers": [1], "expires_in_seconds": 600},
        )
        assert represign.status_code == 200
        with _session_scope(session_factory) as session:
            part = session.get(UploadPart, (session_id, 1))
            assert part is not None
            assert part.status == "UPLOADED"
            assert part.source == "db"

        parts = client.get(
            f"/v1/uploads/{session_id}/parts?source=db",
            headers=_auth_headers("req-list-db"),
        )
        assert parts.status_code == 200
        assert parts.json()["uploaded_part_count"] == 1
        assert parts.json()["missing_part_numbers"] == []
        assert parts.json()["parts"][0]["status"] == "UPLOADED"

        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            assert upload_session.status == "UPLOADING"
            assert upload_session.completed_at is None
            assert upload_session.object_etag is None
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_presign_rejects_paused_session() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-paused"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            upload_session.status = "PAUSED"

        response = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-paused"),
            json={"part_numbers": [1]},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "upload.invalid_state"
        assert storage.presign_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_presign_rejects_storage_backpressure_before_storage_presign() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    settings = _settings_override(
        storage_backpressure_forced_reason="error_rate",
        storage_backpressure_retry_after_seconds=45,
    )
    idempotency_key = "idem-runtime-backpressure-presign"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        storage.presign_calls.clear()
        backpressure_client = _client(session_factory, storage=storage, settings=settings)

        response = backpressure_client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-backpressure"),
            json={"part_numbers": [1], "expires_in_seconds": 600},
        )

        assert response.status_code == 503
        assert response.headers["Retry-After"] == "45"
        body = response.json()
        assert body["error"]["code"] == "storage.backpressure"
        assert body["error"]["details"] == {
            "source": "storage_health",
            "reason": "error_rate",
            "retry_after_seconds": 45,
        }
        assert storage.presign_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_presign_expiry_is_bounded_and_expired_sessions_are_gone() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-expiry-bounds"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        bounded = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-bounded"),
            json={"part_numbers": [1], "expires_in_seconds": 999_999},
        )
        assert bounded.status_code == 200
        assert storage.presign_calls == [
            (_created_object(created)["bucket"], 1, get_settings().max_presign_expiry_seconds)
        ]

        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            upload_session.status = "EXPIRED"
            upload_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        expired = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-expired"),
            json={"part_numbers": [1]},
        )
        assert expired.status_code == 409
        assert expired.json()["error"]["code"] == "upload.invalid_state"
        assert expired.json()["error"]["details"]["status"] == "EXPIRED"
        assert len(storage.presign_calls) == 1
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_presign_rejects_storage_backpressure_before_signing_parts() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-metrics-backpressure-presign"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    metrics_registry.reset_for_tests()
    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        metrics_registry.reset_for_tests()
        metrics_registry.observe(
            "storage_operation_duration_seconds",
            6.0,
            {"operation": "presign_upload_part"},
        )

        response = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-storage-backpressure"),
            json={"part_numbers": [1]},
        )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "storage.backpressure"
        assert response.json()["error"]["details"] == {
            "source": "storage_health",
            "reason": "storage_p95_latency",
            "retry_after_seconds": 30,
        }
        assert storage.presign_calls == []
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert 'storage_backpressure_rejects_total{reason="storage_p95_latency"} 1' in metrics.text
    finally:
        metrics_registry.reset_for_tests()
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_runtime_re_evaluates_current_permissions() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-permission"
    deny_grants = (
        dev_seed_uuid("test-grant:runtime-deny-dataset-upload"),
        dev_seed_uuid("test-grant:runtime-deny-upload-create"),
    )
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        with _session_scope(session_factory) as session:
            _upsert_grant(
                session,
                grant_id=deny_grants[0],
                resource_id=seed.project_id,
                permission_code="dataset.upload",
                effect="DENY",
            )
            _upsert_grant(
                session,
                grant_id=deny_grants[1],
                resource_id=seed.project_id,
                permission_code="upload.create",
                effect="DENY",
            )

        response = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-denied"),
            json={"part_numbers": [1]},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization.permission_denied"
        assert storage.presign_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
        _delete_test_grants(session_factory, *deny_grants)


def test_runtime_session_tenant_isolation_returns_not_found_before_permission_check() -> None:
    session_factory = _db_session_factory_or_skip()
    foreign_tenant_id = dev_seed_uuid("test-tenant:runtime-foreign")
    foreign_session_id = dev_seed_uuid("test-session:runtime-foreign")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        tenant = session.get(Tenant, foreign_tenant_id)
        if tenant is None:
            tenant = Tenant(id=foreign_tenant_id)
            session.add(tenant)
        tenant.slug = "runtime-foreign"
        tenant.name = "Runtime Foreign"
        tenant.status = "ACTIVE"
        session.add(
            UploadSession(
                id=foreign_session_id,
                tenant_id=foreign_tenant_id,
                status="INITIATED",
                bucket_name="foreign-bucket",
                object_key=f"foreign/{foreign_session_id}",
                storage_provider="minio",
                storage_upload_id="foreign-upload",
                original_filename="foreign.bin",
                file_size_bytes=DEFAULT_PART_SIZE,
                part_size_bytes=DEFAULT_PART_SIZE,
                part_count=1,
                checksum_mode="CLIENT_REPORTED",
                metadata_={},
                uploaded_part_count=0,
                completed_part_count=0,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )

    try:
        client = _client(session_factory, storage=RuntimeFakeObjectStorage())
        response = client.get(
            f"/v1/uploads/{foreign_session_id}",
            headers=_auth_headers("req-foreign-session"),
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "upload_session.not_found"
    finally:
        with _session_scope(session_factory) as session:
            session.execute(delete(UploadSession).where(UploadSession.id == foreign_session_id))
            session.execute(delete(Tenant).where(Tenant.id == foreign_tenant_id))


def test_storage_and_reconcile_sources_use_object_storage_list_parts() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-reconcile"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        storage_only = client.get(
            f"/v1/uploads/{session_id}/parts?source=storage",
            headers=_auth_headers("req-list-storage"),
        )
        assert storage_only.status_code == 200
        assert storage_only.json()["uploaded_part_count"] == 1
        with _session_scope(session_factory) as session:
            assert session.get(UploadPart, (session_id, 1)) is None

        reconciled = client.get(
            f"/v1/uploads/{session_id}/parts?source=reconcile",
            headers=_auth_headers("req-list-reconcile"),
        )
        assert reconciled.status_code == 200
        assert reconciled.json()["uploaded_part_count"] == 1
        with _session_scope(session_factory) as session:
            part = session.get(UploadPart, (session_id, 1))
            assert part is not None
            assert part.etag == '"storage-etag"'
            assert part.source == "storage"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_reconcile_completed_session_uses_db_parts_without_storage_list() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-reconcile-completed"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        storage.listed_parts = (
            ListedPart(part_number=1, etag='"storage-etag"', size_bytes=DEFAULT_PART_SIZE),
        )

        reconciled = client.get(
            f"/v1/uploads/{session_id}/parts?source=reconcile",
            headers=_auth_headers("req-list-reconcile-before-complete"),
        )
        assert reconciled.status_code == 200
        assert len(storage.list_calls) == 1

        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            upload_session.status = "COMPLETED"
            upload_session.uploaded_part_count = 1
            upload_session.completed_at = datetime.now(UTC)
            session.commit()

        storage.listed_parts = ()
        completed_reconcile = client.get(
            f"/v1/uploads/{session_id}/parts?source=reconcile",
            headers=_auth_headers("req-list-reconcile-after-complete"),
        )

        assert completed_reconcile.status_code == 200
        body = completed_reconcile.json()
        assert body["uploaded_part_count"] == 1
        assert body["missing_part_numbers"] == []
        assert len(storage.list_calls) == 1
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
