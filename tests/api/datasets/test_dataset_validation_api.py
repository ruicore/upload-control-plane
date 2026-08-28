from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    DatasetValidationResult,
    OutboxEvent,
)
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)

from .support import (
    DatasetFakeObjectStorage,
    _auth_headers,
    _client,
    _create_ready_dataset,
    _db_session_factory_or_skip,
    _delete_test_grants,
    _delete_upload_artifacts,
    _session_scope,
    _upsert_grant,
)


def test_dataset_validation_result_api_returns_metadata_and_errors_without_storage_secrets() -> (
    None
):
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = "idem-validation-result"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            dataset.status = "REJECTED"
            dataset.validation_status = "FAILED"
            dataset.preview_status = "AVAILABLE"
            dataset.preview_metadata = {"format": "HDF5", "sample_count": 2}
            dataset.metadata_ = {
                "extracted_metadata": {
                    "format": "HDF5",
                    "topic_count": 3,
                    "safe_storage_ref": {"bucket": created["bucket"]},
                }
            }
            now = datetime.now(UTC)
            session.add(
                DatasetValidationResult(
                    id=uuid.uuid4(),
                    tenant_id=seed.tenant_id,
                    project_id=seed.project_id,
                    dataset_id=dataset_id,
                    status="FAILED",
                    validator_name="hdf5_metadata_stub",
                    validator_version="1",
                    extracted_metadata={"format": "HDF5"},
                    errors=[
                        {
                            "code": "storage.head_failed",
                            "message": "metadata unavailable",
                            "retryable": True,
                        }
                    ],
                    started_at=now,
                    completed_at=now,
                    created_at=now,
                )
            )

        response = client.get(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/validation",
            headers=_auth_headers("req-validation-result"),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["dataset_status"] == "REJECTED"
        assert body["validation_status"] == "FAILED"
        assert body["preview_metadata"] == {"format": "HDF5", "sample_count": 2}
        assert body["extracted_metadata"]["topic_count"] == 3
        assert body["latest_result"]["errors"][0]["code"] == "storage.head_failed"
        serialized = str(body).lower()
        assert "presigned" not in serialized
        assert "download-signature" not in serialized
        assert "access_key" not in serialized
        assert "secret_key" not in serialized
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_dataset_validation_result_requires_dataset_view_permission() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = "idem-validation-result-denied"
    deny_grant_id = dev_seed_uuid("test-grant:deny-validation-result-view")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        with _session_scope(session_factory) as session:
            _upsert_grant(
                session,
                grant_id=deny_grant_id,
                resource_id=seed.project_id,
                permission_code="dataset.view",
                effect="DENY",
            )

        response = client.get(
            f"/v1/projects/{seed.project_id}/datasets/{created['dataset_id']}/validation",
            headers=_auth_headers("req-validation-result-denied"),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization.permission_denied"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
        _delete_test_grants(session_factory, deny_grant_id)


def test_retry_validation_resets_failed_dataset_and_preserves_object_metadata() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = "idem-validation-retry"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            dataset.status = "REJECTED"
            dataset.validation_status = "FAILED"
            dataset.preview_status = "NOT_AVAILABLE"
            dataset.metadata_ = {"extracted_metadata": {"previous": "kept"}}
            dataset.object_version_id = "version-before-retry"
            original_object = (
                dataset.bucket_name,
                dataset.object_key,
                dataset.object_etag,
                dataset.object_size_bytes,
                dataset.object_version_id,
                dataset.metadata_,
            )

        response = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/validation/retry",
            headers=_auth_headers("req-validation-retry"),
        )

        assert response.status_code == 200
        assert response.json()["dataset_status"] == "PROCESSING"
        assert response.json()["validation_status"] == "PENDING"
        assert response.json()["retry_queued"] is True
        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            assert dataset.status == "PROCESSING"
            assert dataset.validation_status == "PENDING"
            assert (
                dataset.bucket_name,
                dataset.object_key,
                dataset.object_etag,
                dataset.object_size_bytes,
                dataset.object_version_id,
                dataset.metadata_,
            ) == original_object
            assert session.scalar(
                select(AuditEvent).where(
                    AuditEvent.dataset_id == dataset_id,
                    AuditEvent.action == "dataset.validation_retry",
                )
            )
            assert session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id == dataset_id,
                    OutboxEvent.event_type == "dataset.validation_retry",
                )
            )
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_retry_validation_is_idempotent_when_already_pending() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = "idem-validation-retry-pending"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            dataset.status = "PROCESSING"
            dataset.validation_status = "PENDING"

        first = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/validation/retry",
            headers=_auth_headers("req-validation-retry-pending-1"),
        )
        second = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/validation/retry",
            headers=_auth_headers("req-validation-retry-pending-2"),
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()
        assert first.json()["retry_queued"] is False
        with _session_scope(session_factory) as session:
            assert (
                session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.dataset_id == dataset_id,
                        AuditEvent.action == "dataset.validation_retry",
                    )
                )
                is None
            )
            assert (
                session.scalar(
                    select(OutboxEvent).where(
                        OutboxEvent.aggregate_id == dataset_id,
                        OutboxEvent.event_type == "dataset.validation_retry",
                    )
                )
                is None
            )
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_retry_validation_rejects_non_eligible_passed_dataset() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = "idem-validation-retry-passed"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)

        response = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{created['dataset_id']}/validation/retry",
            headers=_auth_headers("req-validation-retry-passed"),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "dataset.validation_retry_not_eligible"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_retry_validation_requires_dataset_validate_permission() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = "idem-validation-retry-denied"
    deny_grant_id = dev_seed_uuid("test-grant:deny-validation-retry-validate")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            dataset.status = "REJECTED"
            dataset.validation_status = "FAILED"
            _upsert_grant(
                session,
                grant_id=deny_grant_id,
                resource_id=seed.project_id,
                permission_code="dataset.validate",
                effect="DENY",
            )

        response = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/validation/retry",
            headers=_auth_headers("req-validation-retry-denied"),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization.permission_denied"
        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            assert dataset.status == "REJECTED"
            assert dataset.validation_status == "FAILED"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
        _delete_test_grants(session_factory, deny_grant_id)
