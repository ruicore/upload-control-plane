from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.api.request_context import REQUEST_ID_HEADER
from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    PermissionGrant,
    Project,
    UploadEvent,
    UploadObject,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)
from upload_control_plane.main import create_app

from .support import (
    FakeObjectStorage,
    _auth_headers,
    _client,
    _db_session_factory_or_skip,
    _delete_upload_artifacts,
    _session_scope,
    _valid_payload,
)


def test_upload_task_create_requires_bearer_auth() -> None:
    client = TestClient(create_app())
    project_id = uuid.uuid4()

    response = client.post(
        f"/v1/projects/{project_id}/upload-tasks",
        headers={REQUEST_ID_HEADER: "req-upload-missing-auth"},
        json=_valid_payload(),
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "auth.api_key_missing",
            "message": "Missing API key.",
            "details": {},
            "request_id": "req-upload-missing-auth",
        }
    }


def test_upload_task_create_rejects_actor_without_upload_permission() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    denied_project_id = dev_seed_uuid("test-project:upload-create-denied")

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _upsert_project(session, denied_project_id, slug="upload-denied", name="Upload Denied")
        _upsert_grant(
            session,
            grant_id=dev_seed_uuid("test-grant:upload-denied-view"),
            resource_id=denied_project_id,
            permission_code="project.view",
        )

    try:
        client = _client(session_factory)
        response = client.post(
            f"/v1/projects/{denied_project_id}/upload-tasks",
            headers=_auth_headers("req-upload-denied"),
            json=_valid_payload(),
        )

        assert response.status_code == 403
        assert response.json() == {
            "error": {
                "code": "authorization.permission_denied",
                "message": "Permission denied.",
                "details": {
                    "permission_code": "dataset.upload or upload.create",
                    "resource_type": "project",
                },
                "request_id": "req-upload-denied",
            }
        }
    finally:
        _delete_test_projects(session_factory, denied_project_id)
        _delete_test_grants(session_factory, dev_seed_uuid("test-grant:upload-denied-view"))
        _ = seed


def test_upload_task_create_single_file_transactionally_creates_records() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    idempotency_key = "idem-upload-single"

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        before_count = session.scalar(select(func.count()).select_from(UploadTask))

    try:
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-create"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["project_id"] == str(seed.project_id)
        assert body["status"] == "PENDING"
        assert body["object_count"] == 1
        assert body["total_size_bytes"] == DEFAULT_PART_SIZE
        assert len(body["objects"]) == 1
        created = body["objects"][0]
        assert created["status"] == "PENDING"
        assert created["object_name"] == "front_camera.hdf5"
        assert created["bucket"] == get_settings().s3_bucket
        assert "/front_camera.hdf5" in created["object_key"]
        assert not created["object_key"].startswith("front_camera")
        assert storage.create_calls == [
            {
                "bucket": created["bucket"],
                "object_key": created["object_key"],
                "content_type": "application/x-hdf5",
            }
        ]

        with _session_scope(session_factory) as session:
            after_count = session.scalar(select(func.count()).select_from(UploadTask))
            task = session.get(UploadTask, uuid.UUID(body["task_id"]))
            upload_object = session.get(UploadObject, uuid.UUID(created["object_id"]))
            dataset = session.get(Dataset, uuid.UUID(created["dataset_id"]))
            upload_session = session.get(UploadSession, uuid.UUID(created["session_id"]))
            events = session.scalars(
                select(UploadEvent).where(UploadEvent.upload_task_id == uuid.UUID(body["task_id"]))
            ).all()
            audits = session.scalars(
                select(AuditEvent).where(AuditEvent.resource_id == body["task_id"])
            ).all()

        assert before_count is not None
        assert after_count == before_count + 1
        assert task is not None
        assert upload_object is not None
        assert dataset is not None
        assert upload_session is not None
        assert upload_session.storage_upload_id == "fake-upload-1"
        assert upload_session.status == "INITIATED"
        assert upload_object.upload_session_id == upload_session.id
        assert dataset.object_key == created["object_key"]
        assert {event.event_type for event in events} == {
            "upload_task.created",
            "upload_session.storage_initiated",
        }
        assert [audit.action for audit in audits] == ["upload_task.create"]
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_upload_task_create_multi_file_creates_one_object_and_session_per_item() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    idempotency_key = "idem-upload-multi"
    payload = _valid_payload(
        objects=[
            {
                "dataset_name": "front-camera",
                "object_name": "front_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
            },
            {
                "dataset_name": "rear-camera",
                "object_name": "rear_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
            },
        ]
    )
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-multi"), "Idempotency-Key": idempotency_key},
            json=payload,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["object_count"] == 2
        assert len(body["objects"]) == 2
        assert len({item["object_id"] for item in body["objects"]}) == 2
        assert len({item["session_id"] for item in body["objects"]}) == 2
        assert len(storage.create_calls) == 2
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_upload_task_create_idempotent_retry_returns_same_response_without_storage_call() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    idempotency_key = "idem-upload-retry"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        first = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-retry-1"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(),
        )
        second = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-retry-2"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(),
        )

        assert first.status_code == 201
        assert second.status_code == 201
        first_body = first.json()
        second_body = second.json()
        assert second_body == first_body
        assert len(storage.create_calls) == 1
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_upload_task_create_rejects_idempotency_key_reused_with_different_request() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    idempotency_key = "idem-upload-conflict"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        first = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-conflict-1"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(),
        )
        second = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-conflict-2"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(
                objects=[
                    {
                        "dataset_name": "rear",
                        "object_name": "rear.hdf5",
                        "file_size_bytes": DEFAULT_PART_SIZE,
                    }
                ]
            ),
        )

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "idempotency.key_reused_with_different_request"
        assert len(storage.create_calls) == 1
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def _upsert_project(session: Session, project_id: uuid.UUID, *, slug: str, name: str) -> None:
    seed = build_dev_seed_result()
    project = session.get(Project, project_id)
    if project is None:
        project = Project(id=project_id)
        session.add(project)
    project.tenant_id = seed.tenant_id
    project.storage_policy_id = seed.storage_policy_id
    project.slug = slug
    project.name = name
    project.description = None
    project.status = "ACTIVE"
    project.metadata_schema = {}
    project.metadata_ = {"seed": "test"}
    project.created_by = seed.api_key_id
    project.archived_at = None
    project.deleted_at = None


def _upsert_grant(
    session: Session,
    *,
    grant_id: uuid.UUID,
    resource_id: uuid.UUID,
    permission_code: str,
    effect: str = "ALLOW",
    expires_at: datetime | None = None,
) -> None:
    seed = build_dev_seed_result()
    grant = session.get(PermissionGrant, grant_id)
    if grant is None:
        grant = PermissionGrant(id=grant_id)
        session.add(grant)
    grant.tenant_id = seed.tenant_id
    grant.subject_type = "api_key"
    grant.subject_id = seed.api_key_id
    grant.resource_type = "project"
    grant.resource_id = resource_id
    grant.permission_code = permission_code
    grant.effect = effect
    grant.conditions = {}
    grant.source = "test"
    grant.created_by = seed.api_key_id
    grant.expires_at = expires_at or datetime.now(UTC) + timedelta(hours=1)


def _delete_test_projects(session_factory: sessionmaker[Session], *project_ids: uuid.UUID) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(PermissionGrant).where(PermissionGrant.resource_id.in_(project_ids)))
        session.execute(delete(Project).where(Project.id.in_(project_ids)))


def _delete_test_grants(session_factory: sessionmaker[Session], *grant_ids: uuid.UUID) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(PermissionGrant).where(PermissionGrant.id.in_(grant_ids)))
