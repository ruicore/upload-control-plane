from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.api.auth import get_db_session
from upload_control_plane.api.request_context import REQUEST_ID_HEADER
from upload_control_plane.api.upload_tasks import get_object_storage
from upload_control_plane.config import Settings, get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompletedObject,
    CompleteMultipartUploadRequest,
    CreateMultipartUploadRequest,
    CreateMultipartUploadResult,
    HeadObjectRequest,
    HeadObjectResult,
    ListedPart,
    ListedPartsPage,
    ListPartsRequest,
    PresignedPartUrl,
    PresignUploadPartRequest,
    StorageCapabilities,
    StorageChecksumMismatchError,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    IdempotencyRecord,
    OutboxEvent,
    PermissionGrant,
    Tenant,
    UploadEvent,
    UploadObject,
    UploadPart,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import (
    DEV_API_KEY_VALUE,
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app
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


def test_complete_re_evaluates_current_permissions_after_part_upload() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag-1"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-complete-permission-revoked"
    deny_grant = dev_seed_uuid("test-grant:runtime-deny-upload-complete")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        with _session_scope(session_factory) as session:
            _upsert_grant(
                session,
                grant_id=deny_grant,
                resource_id=uuid.UUID(_created_object(created)["dataset_id"]),
                resource_type="dataset",
                permission_code="upload.complete",
                effect="DENY",
            )

        response = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={
                **_auth_headers("req-complete-permission-revoked"),
                "Idempotency-Key": "idem-complete-permission-revoked",
            },
            json={},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization.permission_denied"
        assert storage.complete_calls == []
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-complete-permission-revoked",
        )
        _delete_test_grants(session_factory, deny_grant)


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


def test_pause_resume_idempotency_and_presign_guard() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-lifecycle-pause"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        first_pause = client.post(
            f"/v1/uploads/{session_id}/pause",
            headers={**_auth_headers("req-pause-1"), "Idempotency-Key": "idem-pause"},
            json={"reason": "operator_requested", "client_inflight_behavior": "allow_finish"},
        )
        assert first_pause.status_code == 200
        assert first_pause.json()["status"] == "PAUSED"
        second_pause = client.post(
            f"/v1/uploads/{session_id}/pause",
            headers={**_auth_headers("req-pause-2"), "Idempotency-Key": "idem-pause"},
            json={"reason": "operator_requested", "client_inflight_behavior": "allow_finish"},
        )
        assert second_pause.status_code == 200
        assert second_pause.json() == first_pause.json()

        paused_presign = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-while-paused"),
            json={"part_numbers": [1]},
        )
        assert paused_presign.status_code == 409
        assert paused_presign.json()["error"]["code"] == "upload.invalid_state"

        resume = client.post(
            f"/v1/uploads/{session_id}/resume",
            headers={**_auth_headers("req-resume"), "Idempotency-Key": "idem-resume"},
            json={"reason": "operator_resumed"},
        )
        assert resume.status_code == 200
        assert resume.json()["status"] == "UPLOADING"

        fresh_presign = client.post(
            f"/v1/uploads/{session_id}/parts/presign",
            headers=_auth_headers("req-presign-after-resume"),
            json={"part_numbers": [1]},
        )
        assert fresh_presign.status_code == 200
        assert storage.abort_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key, "idem-pause", "idem-resume")


def test_complete_uses_storage_list_parts_not_db_ack_rows_for_missing_parts() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag-1"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-complete-missing"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(
            client,
            seed.project_id,
            idempotency_key,
            file_size_bytes=DEFAULT_PART_SIZE * 2,
            part_size_bytes=DEFAULT_PART_SIZE,
        )
        session_id = uuid.UUID(_created_object(created)["session_id"])
        ack = client.post(
            f"/v1/uploads/{session_id}/parts/ack",
            headers=_auth_headers("req-ack-two-db-only"),
            json={
                "parts": [
                    {"part_number": 1, "etag": '"db-etag-1"', "size_bytes": DEFAULT_PART_SIZE},
                    {"part_number": 2, "etag": '"db-etag-2"', "size_bytes": DEFAULT_PART_SIZE},
                ]
            },
        )
        assert ack.status_code == 200

        complete = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={**_auth_headers("req-complete-missing"), "Idempotency-Key": "idem-missing"},
            json={},
        )

        assert complete.status_code == 409
        error = complete.json()["error"]
        assert error["code"] == "upload.missing_parts"
        assert error["details"]["missing_part_count"] == 1
        assert error["details"]["missing_part_numbers"] == [2]
        assert storage.list_calls
        assert storage.complete_calls == []
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            assert upload_session.status == "UPLOADING"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key, "idem-missing")


def test_complete_succeeds_from_storage_parts_without_db_ack_and_is_idempotent() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag-1"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-complete-storage"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        first = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={**_auth_headers("req-complete-1"), "Idempotency-Key": "idem-complete"},
            json={},
        )
        assert first.status_code == 200
        body = first.json()
        assert body["status"] == "COMPLETED"
        assert body["etag"] == '"final-etag"'
        assert body["object_size_bytes"] == DEFAULT_PART_SIZE

        second = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={**_auth_headers("req-complete-2"), "Idempotency-Key": "idem-complete"},
            json={},
        )
        assert second.status_code == 200
        assert second.json() == body
        assert len(storage.complete_calls) == 1
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            dataset = session.get(Dataset, uuid.UUID(_created_object(created)["dataset_id"]))
            assert upload_session is not None
            assert dataset is not None
            assert upload_session.status == "COMPLETED"
            assert upload_session.object_etag == '"final-etag"'
            assert dataset.object_size_bytes == DEFAULT_PART_SIZE
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key, "idem-complete")


def test_storage_native_checksum_mismatch_does_not_mark_dataset_ready() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(
            part_number=1,
            etag='"storage-etag-1"',
            size_bytes=DEFAULT_PART_SIZE,
            checksum={"sha256": "a" * 64},
        ),
    )
    storage.complete_error = StorageChecksumMismatchError(
        "BadDigest",
        operation="complete_multipart_upload",
        provider_code="BadDigest",
    )
    idempotency_key = "idem-runtime-checksum-mismatch"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        created_object = _created_object(created)
        session_id = uuid.UUID(created_object["session_id"])
        dataset_id = uuid.UUID(created_object["dataset_id"])

        response = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={
                **_auth_headers("req-complete-checksum-mismatch"),
                "Idempotency-Key": "idem-complete-checksum-mismatch",
            },
            json={"checksum_sha256": "b" * 64},
        )

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "storage.complete_failed"
        assert response.json()["error"]["details"]["provider_code"] == "BadDigest"
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            dataset = session.get(Dataset, dataset_id)
            assert upload_session is not None
            assert dataset is not None
            assert upload_session.status == "INITIATED"
            assert upload_session.last_error_code == "storage.complete_failed"
            assert dataset.status == "UPLOAD_PENDING"
            assert dataset.object_etag is None
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-complete-checksum-mismatch",
        )


def test_abort_is_idempotent_and_completed_sessions_are_not_aborted() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-abort"
    completed_key = "idem-runtime-abort-completed"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        first_abort = client.post(
            f"/v1/uploads/{session_id}/abort",
            headers={**_auth_headers("req-abort-1"), "Idempotency-Key": "idem-abort"},
            json={"reason": "client_cancelled"},
        )
        assert first_abort.status_code == 200
        second_abort = client.post(
            f"/v1/uploads/{session_id}/abort",
            headers={**_auth_headers("req-abort-2"), "Idempotency-Key": "idem-abort"},
            json={"reason": "client_cancelled"},
        )
        assert second_abort.status_code == 200
        assert second_abort.json() == first_abort.json()
        assert len(storage.abort_calls) == 1

        completed_created = _create_upload_task(client, seed.project_id, completed_key)
        completed_session_id = uuid.UUID(_created_object(completed_created)["session_id"])
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, completed_session_id)
            assert upload_session is not None
            upload_session.status = "COMPLETED"
            upload_session.completed_at = datetime.now(UTC)
            upload_session.object_etag = '"already-final"'
            upload_session.object_size_bytes = DEFAULT_PART_SIZE

        abort_completed = client.post(
            f"/v1/uploads/{completed_session_id}/abort",
            headers={
                **_auth_headers("req-abort-completed"),
                "Idempotency-Key": "idem-abort-completed",
            },
            json={"reason": "operator_requested"},
        )
        assert abort_completed.status_code == 409
        assert abort_completed.json()["error"]["code"] == "upload.invalid_state"
        assert len(storage.abort_calls) == 1
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            completed_key,
            "idem-abort",
            "idem-abort-completed",
        )


def test_lifecycle_actions_re_evaluate_current_permissions() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    idempotency_key = "idem-runtime-lifecycle-permission"
    deny_grant = dev_seed_uuid("test-grant:runtime-deny-upload-pause")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        with _session_scope(session_factory) as session:
            _upsert_grant(
                session,
                grant_id=deny_grant,
                resource_id=seed.project_id,
                permission_code="upload.pause",
                effect="DENY",
            )

        response = client.post(
            f"/v1/uploads/{session_id}/pause",
            headers={**_auth_headers("req-pause-denied"), "Idempotency-Key": "idem-pause-denied"},
            json={"reason": "operator_requested"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization.permission_denied"
        assert storage.abort_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key, "idem-pause-denied")
        _delete_test_grants(session_factory, deny_grant)


def test_lifecycle_session_tenant_isolation_returns_not_found_before_permission_check() -> None:
    session_factory = _db_session_factory_or_skip()
    foreign_tenant_id = dev_seed_uuid("test-tenant:runtime-lifecycle-foreign")
    foreign_session_id = dev_seed_uuid("test-session:runtime-lifecycle-foreign")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        tenant = session.get(Tenant, foreign_tenant_id)
        if tenant is None:
            tenant = Tenant(id=foreign_tenant_id)
            session.add(tenant)
        tenant.slug = "runtime-lifecycle-foreign"
        tenant.name = "Runtime Lifecycle Foreign"
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
        storage = RuntimeFakeObjectStorage()
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/uploads/{foreign_session_id}/pause",
            headers={**_auth_headers("req-foreign-pause"), "Idempotency-Key": "idem-foreign-pause"},
            json={"reason": "operator_requested"},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "upload_session.not_found"
        assert storage.abort_calls == []
        assert storage.complete_calls == []
    finally:
        with _session_scope(session_factory) as session:
            session.execute(delete(UploadSession).where(UploadSession.id == foreign_session_id))
            session.execute(delete(Tenant).where(Tenant.id == foreign_tenant_id))
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.key == "idem-foreign-pause")
            )


def _create_upload_task(
    client: TestClient,
    project_id: uuid.UUID,
    idempotency_key: str,
    *,
    file_size_bytes: int = DEFAULT_PART_SIZE,
    part_size_bytes: int = DEFAULT_PART_SIZE,
) -> dict[str, Any]:
    response = client.post(
        f"/v1/projects/{project_id}/upload-tasks",
        headers={
            **_auth_headers(f"req-create-{idempotency_key}"),
            "Idempotency-Key": idempotency_key,
        },
        json={
            "task_name": f"runtime-{idempotency_key}",
            "task_initiator": "api",
            "objects": [
                {
                    "dataset_name": f"runtime-{idempotency_key}",
                    "object_name": f"runtime-{idempotency_key}.bin",
                    "file_size_bytes": file_size_bytes,
                    "part_size_bytes": part_size_bytes,
                }
            ],
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def _created_object(created: dict[str, Any]) -> dict[str, Any]:
    objects = created["objects"]
    assert isinstance(objects, list)
    first = objects[0]
    assert isinstance(first, dict)
    return first


def _db_session_factory_or_skip() -> sessionmaker[Session]:
    settings = get_settings()
    url = make_url(settings.database_url)
    host = url.host or "localhost"
    port = url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1):
            pass
    except OSError as exc:
        pytest.skip(f"PostgreSQL integration database is not reachable at {host}:{port}: {exc}")

    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
    except (OperationalError, ProgrammingError) as exc:
        pytest.skip(f"PostgreSQL integration database is not available or migrated: {exc}")
    return build_session_factory(engine)


def _client(
    session_factory: sessionmaker[Session],
    *,
    storage: RuntimeFakeObjectStorage,
    settings: Settings | None = None,
) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_object_storage] = lambda: storage
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _auth_headers(request_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DEV_API_KEY_VALUE}",
        REQUEST_ID_HEADER: request_id,
    }


@contextmanager
def _session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _upsert_grant(
    session: Session,
    *,
    grant_id: uuid.UUID,
    resource_id: uuid.UUID,
    permission_code: str,
    resource_type: str = "project",
    effect: str = "ALLOW",
) -> None:
    seed = build_dev_seed_result()
    grant = session.get(PermissionGrant, grant_id)
    if grant is None:
        grant = PermissionGrant(id=grant_id)
        session.add(grant)
    grant.tenant_id = seed.tenant_id
    grant.subject_type = "api_key"
    grant.subject_id = seed.api_key_id
    grant.resource_type = resource_type
    grant.resource_id = resource_id
    grant.permission_code = permission_code
    grant.effect = effect
    grant.conditions = {}
    grant.source = "test"
    grant.created_by = seed.api_key_id
    grant.expires_at = datetime.now(UTC) + timedelta(hours=1)


def _delete_test_grants(session_factory: sessionmaker[Session], *grant_ids: uuid.UUID) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(PermissionGrant).where(PermissionGrant.id.in_(grant_ids)))


def _delete_upload_artifacts(
    session_factory: sessionmaker[Session],
    idempotency_key: str,
    *extra_idempotency_keys: str,
) -> None:
    with _session_scope(session_factory) as session:
        idempotency_keys = (idempotency_key, *extra_idempotency_keys)
        task_ids = list(
            session.scalars(
                select(UploadTask.id).where(UploadTask.idempotency_key.in_(idempotency_keys))
            )
        )
        if not task_ids:
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.key.in_(idempotency_keys))
            )
            return
        object_ids = list(
            session.scalars(
                select(UploadObject.id).where(UploadObject.upload_task_id.in_(task_ids))
            )
        )
        dataset_ids = list(
            session.scalars(
                select(UploadObject.dataset_id).where(UploadObject.upload_task_id.in_(task_ids))
            )
        )
        session_ids = list(
            session.scalars(
                select(UploadSession.id).where(UploadSession.upload_task_id.in_(task_ids))
            )
        )
        if session_ids:
            session.execute(delete(UploadPart).where(UploadPart.session_id.in_(session_ids)))
        session.execute(delete(UploadEvent).where(UploadEvent.upload_task_id.in_(task_ids)))
        session.execute(
            delete(AuditEvent)
            .where(AuditEvent.resource_type == "upload_task")
            .where(AuditEvent.resource_id.in_(str(task_id) for task_id in task_ids))
        )
        aggregate_ids = [*task_ids, *object_ids, *dataset_ids, *session_ids]
        if aggregate_ids:
            session.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(aggregate_ids)))
        session.execute(delete(UploadSession).where(UploadSession.upload_task_id.in_(task_ids)))
        if object_ids:
            session.execute(delete(UploadObject).where(UploadObject.id.in_(object_ids)))
        session.execute(delete(UploadTask).where(UploadTask.id.in_(task_ids)))
        if dataset_ids:
            session.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
        session.execute(
            delete(IdempotencyRecord).where(IdempotencyRecord.key.in_(idempotency_keys))
        )


def _settings_override(**values: object) -> Settings:
    return get_settings().model_copy(update=values)


class RuntimeFakeObjectStorage:
    def __init__(self) -> None:
        self.create_calls: list[CreateMultipartUploadRequest] = []
        self.presign_calls: list[tuple[str, int, int]] = []
        self.list_calls: list[ListPartsRequest] = []
        self.complete_calls: list[CompleteMultipartUploadRequest] = []
        self.abort_calls: list[AbortMultipartUploadRequest] = []
        self.listed_parts: tuple[ListedPart, ...] = ()
        self.complete_error: Exception | None = None

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities()

    def create_multipart_upload(
        self,
        request: CreateMultipartUploadRequest,
    ) -> CreateMultipartUploadResult:
        self.create_calls.append(request)
        return CreateMultipartUploadResult(upload_id=f"fake-upload-{len(self.create_calls)}")

    def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
        self.presign_calls.append((request.bucket, request.part_number, request.expires_in_seconds))
        return PresignedPartUrl(
            part_number=request.part_number,
            url=(
                f"http://storage.local/{request.bucket}/{request.object_key}"
                f"?partNumber={request.part_number}&uploadId={request.upload_id}&fake-signature=1"
            ),
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
            required_headers={},
        )

    def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
        self.list_calls.append(request)
        return ListedPartsPage(parts=self.listed_parts)

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        self.complete_calls.append(request)
        if self.complete_error is not None:
            raise self.complete_error
        return CompletedObject(
            bucket=request.bucket,
            object_key=request.object_key,
            etag='"final-etag"',
            size_bytes=sum(
                part.size_bytes
                for part in self.listed_parts
                if part.part_number in {item.part_number for item in request.parts}
            ),
        )

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        self.abort_calls.append(request)

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        return HeadObjectResult(
            bucket=request.bucket,
            object_key=request.object_key,
            etag='"final-etag"',
            size_bytes=sum(part.size_bytes for part in self.listed_parts),
        )
