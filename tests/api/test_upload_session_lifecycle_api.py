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
    _upsert_grant,
)
from sqlalchemy import delete

from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.domain.storage import StorageNotFoundError, StorageOperationError
from upload_control_plane.infrastructure.db.models import (
    IdempotencyRecord,
    Tenant,
    UploadSession,
)
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)


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


def test_abort_treats_missing_storage_upload_as_success() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.abort_error = StorageNotFoundError(
        "multipart upload not found",
        operation="abort_multipart_upload",
        provider_code="NoSuchUpload",
    )
    idempotency_key = "idem-runtime-abort-missing-storage"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        response = client.post(
            f"/v1/uploads/{session_id}/abort",
            headers={
                **_auth_headers("req-abort-missing-storage"),
                "Idempotency-Key": "idem-abort-missing-storage",
            },
            json={"reason": "client_cancelled"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ABORTED"
        assert len(storage.abort_calls) == 1
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-abort-missing-storage",
        )


def test_abort_storage_failure_restores_state_and_allows_retry() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.abort_error = StorageOperationError(
        "provider unavailable",
        operation="abort_multipart_upload",
        provider_code="ServiceUnavailable",
        retryable=True,
    )
    idempotency_key = "idem-runtime-abort-storage-failure"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        headers = {
            **_auth_headers("req-abort-storage-failure"),
            "Idempotency-Key": "idem-abort-storage-failure",
        }

        failed = client.post(
            f"/v1/uploads/{session_id}/abort",
            headers=headers,
            json={"reason": "client_cancelled"},
        )
        assert failed.status_code == 502
        assert failed.json()["error"]["code"] == "storage.abort_failed"

        status = client.get(
            f"/v1/uploads/{session_id}",
            headers=_auth_headers("req-status-after-abort-failure"),
        )
        assert status.status_code == 200
        assert status.json()["status"] == "INITIATED"

        storage.abort_error = None
        retried = client.post(
            f"/v1/uploads/{session_id}/abort",
            headers={
                **_auth_headers("req-abort-storage-retry"),
                "Idempotency-Key": "idem-abort-storage-failure",
            },
            json={"reason": "client_cancelled"},
        )
        assert retried.status_code == 200
        assert retried.json()["status"] == "ABORTED"
        assert len(storage.abort_calls) == 2
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-abort-storage-failure",
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
