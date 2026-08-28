from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from upload_control_plane.config import get_settings
from upload_control_plane.domain.storage import DeleteObjectRequest, StorageError
from upload_control_plane.infrastructure.db.models import AuditEvent, Dataset, StoragePolicy
from upload_control_plane.infrastructure.db.seed import build_dev_seed_result, seed_dev_data

from .support import (
    DatasetFakeObjectStorage,
    _auth_headers,
    _client,
    _create_ready_dataset,
    _db_session_factory_or_skip,
    _delete_upload_artifacts,
    _session_scope,
)


class FailingDeleteObjectStorage(DatasetFakeObjectStorage):
    def __init__(self) -> None:
        super().__init__()
        self.delete_requests: list[DeleteObjectRequest] = []

    def delete_object(self, request: DeleteObjectRequest) -> None:
        self.delete_requests.append(request)
        raise StorageError(
            "storage delete failed",
            operation="delete_object",
            provider_code="SlowDown",
            retryable=True,
        )


def test_dataset_purge_requires_confirmation_and_retention_policy_approval() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = "idem-dataset-purge"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        deleted = client.delete(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-purge-delete"),
        )
        assert deleted.status_code == 200

        missing_confirmation = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-purge-no-confirm"),
            json={"confirm_purge": False},
        )
        assert missing_confirmation.status_code == 409
        assert missing_confirmation.json()["error"]["details"]["reason"] == "confirmation_required"
        assert storage.delete_calls == []

        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            assert policy is not None
            policy.retention_days = 30

        retention_denied = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-purge-retention"),
            json={"confirm_purge": True},
        )
        assert retention_denied.status_code == 409
        assert retention_denied.json()["error"]["details"]["reason"] == "retention_active"
        assert storage.delete_calls == []

        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            dataset = session.get(Dataset, dataset_id)
            assert policy is not None
            assert dataset is not None
            policy.retention_days = 0
            dataset.deleted_at = datetime.now(UTC) - timedelta(seconds=1)

        purged = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-purge-ok"),
            json={"confirm_purge": True},
        )
        assert purged.status_code == 200
        assert purged.json()["status"] == "PURGED"
        assert storage.delete_calls == [(created["bucket"], created["object_key"])]

        with _session_scope(session_factory) as session:
            denied_audits = session.scalars(
                select(AuditEvent).where(
                    AuditEvent.dataset_id == dataset_id,
                    AuditEvent.action == "dataset.purge",
                    AuditEvent.result == "DENIED",
                )
            ).all()
        assert {event.metadata_["reason"] for event in denied_audits} == {
            "confirmation_required",
            "retention_active",
        }
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_dataset_purge_storage_failure_preserves_versioned_object_state() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FailingDeleteObjectStorage()
    idempotency_key = "idem-dataset-purge-storage-failure"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        deleted = client.delete(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-purge-storage-failure-delete"),
        )
        assert deleted.status_code == 200

        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            dataset = session.get(Dataset, dataset_id)
            assert policy is not None
            assert dataset is not None
            policy.retention_days = 0
            dataset.deleted_at = datetime.now(UTC) - timedelta(seconds=1)
            dataset.object_version_id = "version-before-purge"
            before_state = (
                dataset.status,
                dataset.updated_at,
                dataset.bucket_name,
                dataset.object_key,
                dataset.object_etag,
                dataset.object_size_bytes,
                dataset.object_version_id,
                dict(dataset.metadata_),
            )

        response = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-purge-storage-failure"),
            json={"confirm_purge": True},
        )

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "storage.delete_object_failed"
        assert response.json()["error"]["details"] == {
            "operation": "delete_object",
            "provider_code": "SlowDown",
        }
        assert len(storage.delete_requests) == 1
        delete_request = storage.delete_requests[0]
        assert (
            delete_request.bucket,
            delete_request.object_key,
            delete_request.version_id,
        ) == (created["bucket"], created["object_key"], "version-before-purge")

        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            assert (
                dataset.status,
                dataset.updated_at,
                dataset.bucket_name,
                dataset.object_key,
                dataset.object_etag,
                dataset.object_size_bytes,
                dataset.object_version_id,
                dict(dataset.metadata_),
            ) == before_state
            assert (
                session.scalar(
                    select(AuditEvent).where(
                        AuditEvent.dataset_id == dataset_id,
                        AuditEvent.action == "dataset.purge",
                    )
                )
                is None
            )
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_dataset_purge_rejects_object_lock_and_legal_hold_policy() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = "idem-dataset-object-lock"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        assert (
            client.delete(
                f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
                headers=_auth_headers("req-lock-delete"),
            ).status_code
            == 200
        )
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            dataset = session.get(Dataset, dataset_id)
            assert policy is not None
            assert dataset is not None
            policy.retention_days = None
            policy.object_lock_mode = "GOVERNANCE"
            dataset.deleted_at = datetime.now(UTC) - timedelta(days=1)

        response = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-lock-purge"),
            json={"confirm_purge": True},
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"]["reason"] == "object_lock"

        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            assert policy is not None
            policy.object_lock_mode = None
            policy.legal_hold_default = True

        legal_hold = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-legal-hold-purge"),
            json={"confirm_purge": True},
        )
        assert legal_hold.status_code == 409
        assert legal_hold.json()["error"]["details"]["reason"] == "legal_hold"
    finally:
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            if policy is not None:
                policy.object_lock_mode = None
                policy.legal_hold_default = False
        _delete_upload_artifacts(session_factory, idempotency_key)
