from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db.models import AuditEvent, Dataset
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


def test_dataset_list_detail_update_download_and_lifecycle_controls() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = "idem-dataset-lifecycle"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])

        listed = client.get(
            f"/v1/projects/{seed.project_id}/datasets?search=dataset-lifecycle",
            headers=_auth_headers("req-dataset-list"),
        )
        assert listed.status_code == 200
        assert str(dataset_id) in {item["dataset_id"] for item in listed.json()["datasets"]}

        updated = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-dataset-update"),
            json={"name": "dataset-lifecycle-renamed", "labels": ["ready", "robotics"]},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "dataset-lifecycle-renamed"
        assert updated.json()["labels"] == ["ready", "robotics"]

        download = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/download-url",
            headers=_auth_headers("req-dataset-download"),
            json={"expires_in_seconds": 600, "purpose": "test"},
        )
        assert download.status_code == 200
        assert download.json()["method"] == "GET"
        assert "download-signature=1" in download.json()["url"]
        assert storage.download_calls == [(created["bucket"], created["object_key"], 600)]

        archived = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/archive",
            headers=_auth_headers("req-dataset-archive"),
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "ARCHIVED"

        deleted = client.delete(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-dataset-delete"),
        )
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "DELETED"

        normal_list = client.get(
            f"/v1/projects/{seed.project_id}/datasets",
            headers=_auth_headers("req-dataset-list-hidden"),
        )
        assert str(dataset_id) not in {
            item["dataset_id"] for item in normal_list.json()["datasets"]
        }
        recycle_list = client.get(
            f"/v1/projects/{seed.project_id}/datasets?include_deleted=true",
            headers=_auth_headers("req-dataset-list-deleted"),
        )
        assert str(dataset_id) in {item["dataset_id"] for item in recycle_list.json()["datasets"]}

        restored = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/restore",
            headers=_auth_headers("req-dataset-restore"),
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "ARCHIVED"

        with _session_scope(session_factory) as session:
            actions = set(
                session.scalars(
                    select(AuditEvent.action).where(AuditEvent.dataset_id == dataset_id)
                )
            )
        assert {
            "dataset.update",
            "dataset.download_url",
            "dataset.archive",
            "dataset.delete",
            "dataset.restore",
        }.issubset(actions)
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


@pytest.mark.parametrize("status", ["DELETED", "PURGED"])
def test_dataset_update_rejects_deleted_or_purged_datasets(status: str) -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = f"idem-dataset-update-invalid-{status.lower()}"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            dataset.status = status

        response = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers(f"req-dataset-update-invalid-{status.lower()}"),
            json={"name": "must-not-update"},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "dataset.invalid_state"
        assert (
            response.json()["error"]["message"]
            == "Dataset cannot be updated in its current lifecycle state."
        )
        assert response.json()["error"]["details"] == {"status": status}
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
