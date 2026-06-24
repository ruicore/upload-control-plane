from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.api.auth import get_db_session
from upload_control_plane.api.request_context import REQUEST_ID_HEADER
from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE, MIN_PART_SIZE
from upload_control_plane.infrastructure.db.models import PermissionGrant, Project, UploadTask
from upload_control_plane.infrastructure.db.seed import (
    DEV_API_KEY_VALUE,
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app


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


def test_upload_task_create_valid_contract_reaches_stable_not_implemented_entrypoint() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        before_count = session.scalar(select(func.count()).select_from(UploadTask))

    client = _client(session_factory)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers={**_auth_headers("req-upload-501"), "Idempotency-Key": "idem-upload-501"},
        json=_valid_payload(),
    )

    with _session_scope(session_factory) as session:
        after_count = session.scalar(select(func.count()).select_from(UploadTask))

    assert response.status_code == 501
    assert response.json() == {
        "error": {
            "code": "upload_task.not_implemented",
            "message": "Upload task transactional creation is not implemented yet.",
            "details": {},
            "request_id": "req-upload-501",
        }
    }
    assert after_count == before_count


@pytest.mark.parametrize(
    ("case", "expected_message"),
    [
        ("empty_objects", "List should have at least 1 item"),
        ("zero_file_size", "Input should be greater than 0"),
        ("part_too_small", "part size must be at least 5 MiB"),
        ("unsafe_object_name", "object name must not contain path separators"),
        ("client_storage_key", "Extra inputs are not permitted"),
    ],
)
def test_upload_task_create_rejects_invalid_request_shape(
    case: str,
    expected_message: str,
) -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    client = _client(session_factory)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers=_auth_headers("req-upload-validation"),
        json=_invalid_payload(case),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "request.validation_failed"
    assert body["error"]["request_id"] == "req-upload-validation"
    assert expected_message in str(body["error"]["details"]["errors"])


def _invalid_payload(case: str) -> dict[str, object]:
    if case == "empty_objects":
        return {**_valid_payload(), "objects": []}
    if case == "zero_file_size":
        return _valid_payload(
            objects=[
                {
                    "dataset_name": "front-camera",
                    "object_name": "front_camera.hdf5",
                    "file_size_bytes": 0,
                }
            ]
        )
    if case == "part_too_small":
        return _valid_payload(
            objects=[
                {
                    "dataset_name": "front-camera",
                    "object_name": "front_camera.hdf5",
                    "file_size_bytes": 1024,
                    "part_size_bytes": MIN_PART_SIZE - 1,
                }
            ]
        )
    if case == "unsafe_object_name":
        return _valid_payload(
            objects=[
                {
                    "dataset_name": "front-camera",
                    "object_name": "../front_camera.hdf5",
                    "file_size_bytes": DEFAULT_PART_SIZE,
                }
            ]
        )
    if case == "client_storage_key":
        return {**_valid_payload(), "storage_key": "client-controlled-key"}
    raise AssertionError(f"Unknown invalid payload case: {case}")


def test_upload_task_create_rejects_multipart_file_byte_input() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    client = _client(session_factory)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers=_auth_headers("req-upload-file-bytes"),
        files={"file": ("front_camera.hdf5", b"file-bytes", "application/x-hdf5")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request.validation_failed"


def _valid_payload(
    *,
    objects: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "task_name": "robot-run-2026-06-10-line-3",
        "task_initiator": "cli",
        "source_device_code": "robot-17",
        "objects": objects
        or [
            {
                "dataset_name": "front-camera-2026-06-10",
                "object_name": "front_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
                "content_type": "application/x-hdf5",
                "part_size_bytes": DEFAULT_PART_SIZE,
                "checksum_sha256": "a" * 64,
                "metadata": {"camera": "front"},
            }
        ],
        "metadata": {"site": "factory-shanghai"},
    }


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


def _client(session_factory: sessionmaker[Session]) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app)


def _auth_headers(request_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DEV_API_KEY_VALUE}",
        "X-Request-ID": request_id,
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
