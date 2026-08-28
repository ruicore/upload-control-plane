from __future__ import annotations

import uuid

import pytest

from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db.models import Dataset
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


@pytest.mark.parametrize(
    ("dataset_status", "validation_status", "recovery_status"),
    [
        ("QUARANTINED", "PASSED", "NORMAL"),
        ("REJECTED", "PASSED", "NORMAL"),
        ("READY", "FAILED", "NORMAL"),
        ("READY", "PASSED", "RECOVERY_MISSING_OBJECT"),
    ],
)
def test_dataset_download_rejects_blocked_exposure_states(
    dataset_status: str,
    validation_status: str,
    recovery_status: str,
) -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = f"idem-download-blocked-{dataset_status.lower()}-{validation_status.lower()}"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            dataset.status = dataset_status
            dataset.validation_status = validation_status
            dataset.recovery_status = recovery_status

        response = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/download-url",
            headers=_auth_headers("req-download-blocked"),
            json={},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "dataset.exposure_denied"
        assert storage.download_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_dataset_download_requires_current_dataset_download_permission() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = "idem-dataset-download-denied"
    deny_grant_id = dev_seed_uuid("test-grant:deny-dataset-download-authorization")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        with _session_scope(session_factory) as session:
            _upsert_grant(
                session,
                grant_id=deny_grant_id,
                resource_id=seed.project_id,
                permission_code="dataset.download",
                effect="DENY",
            )

        response = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{created['dataset_id']}/download-url",
            headers=_auth_headers("req-download-denied"),
            json={},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization.permission_denied"
        assert storage.download_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
        _delete_test_grants(session_factory, deny_grant_id)
