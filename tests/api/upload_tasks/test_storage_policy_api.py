from __future__ import annotations

from sqlalchemy import func, select

from upload_control_plane.config import get_settings
from upload_control_plane.domain.storage import StorageCapabilities, StorageOperationError
from upload_control_plane.infrastructure.db.models import StoragePolicy, UploadSession, UploadTask
from upload_control_plane.infrastructure.db.seed import build_dev_seed_result, seed_dev_data

from .support import (
    FakeObjectStorage,
    _auth_headers,
    _client,
    _db_session_factory_or_skip,
    _delete_upload_artifacts,
    _session_scope,
    _valid_payload,
)


def test_upload_task_create_rejects_kms_policy_when_adapter_cannot_provide_kms() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage(capabilities=StorageCapabilities())
    idempotency_key = "idem-kms-unavailable"
    kms_key_ref = "arn:aws:kms:local-dev:111122223333:key/non-secret-key-ref"

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        policy = session.get(StoragePolicy, seed.storage_policy_id)
        assert policy is not None
        policy.encryption_mode = "SSE_KMS"
        policy.kms_key_ref = kms_key_ref
        before_task_count = session.scalar(select(func.count()).select_from(UploadTask))
        before_session_count = session.scalar(select(func.count()).select_from(UploadSession))

    try:
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={
                **_auth_headers("req-upload-kms-unavailable"),
                "Idempotency-Key": idempotency_key,
            },
            json=_valid_payload(),
        )

        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "storage_policy.kms_unavailable"
        assert body["error"]["details"] == {"reason": "unsupported_encryption_mode"}
        assert kms_key_ref not in response.text
        assert storage.create_calls == []

        with _session_scope(session_factory) as session:
            after_task_count = session.scalar(select(func.count()).select_from(UploadTask))
            after_session_count = session.scalar(select(func.count()).select_from(UploadSession))

        assert before_task_count is not None
        assert before_session_count is not None
        assert after_task_count == before_task_count
        assert after_session_count == before_session_count
    finally:
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            assert policy is not None
            policy.encryption_mode = get_settings().s3_default_encryption_mode
            policy.kms_key_ref = get_settings().s3_default_kms_key_ref or None
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_upload_task_create_rejects_kms_provider_failure_without_persisting_session() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    kms_key_ref = "arn:aws:kms:local-dev:111122223333:key/non-secret-key-ref"
    storage = FakeObjectStorage(
        capabilities=StorageCapabilities(supported_encryption_modes=frozenset({"SSE_KMS"})),
        create_error=StorageOperationError(
            "provider KMS failure for hidden key material",
            operation="create_multipart_upload",
            provider_code="KMSUnavailableException",
            retryable=True,
        ),
    )
    idempotency_key = "idem-kms-provider-unavailable"

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        policy = session.get(StoragePolicy, seed.storage_policy_id)
        assert policy is not None
        policy.encryption_mode = "SSE_KMS"
        policy.kms_key_ref = kms_key_ref
        before_task_count = session.scalar(select(func.count()).select_from(UploadTask))
        before_session_count = session.scalar(select(func.count()).select_from(UploadSession))

    try:
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={
                **_auth_headers("req-upload-kms-provider-unavailable"),
                "Idempotency-Key": idempotency_key,
            },
            json=_valid_payload(),
        )

        assert response.status_code == 503
        body = response.json()
        assert body["error"]["code"] == "storage_policy.kms_unavailable"
        assert body["error"]["details"] == {"reason": "kms_provider_unavailable"}
        assert kms_key_ref not in response.text
        assert "hidden key material" not in response.text
        assert len(storage.create_calls) == 1
        assert storage.create_calls[0]["encryption_mode"] == "SSE_KMS"

        with _session_scope(session_factory) as session:
            after_task_count = session.scalar(select(func.count()).select_from(UploadTask))
            after_session_count = session.scalar(select(func.count()).select_from(UploadSession))

        assert before_task_count is not None
        assert before_session_count is not None
        assert after_task_count == before_task_count
        assert after_session_count == before_session_count
    finally:
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            assert policy is not None
            policy.encryption_mode = get_settings().s3_default_encryption_mode
            policy.kms_key_ref = get_settings().s3_default_kms_key_ref or None
        _delete_upload_artifacts(session_factory, idempotency_key)
