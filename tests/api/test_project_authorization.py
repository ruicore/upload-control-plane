from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.api.auth import AuthenticatedActor, get_db_session
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.config import get_settings
from upload_control_plane.domain.permissions import ResourceType
from upload_control_plane.infrastructure.db.models import PermissionGrant, Project
from upload_control_plane.infrastructure.db.seed import (
    DEV_API_KEY_VALUE,
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app


def test_project_list_filters_by_project_view_and_ignores_expired_grants() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    hidden_project_id = dev_seed_uuid("test-project:hidden-expired")

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _upsert_project(session, hidden_project_id, slug="hidden-expired", name="Hidden Expired")
        _upsert_grant(
            session,
            grant_id=dev_seed_uuid("test-grant:hidden-expired-project-view"),
            resource_id=hidden_project_id,
            permission_code="project.view",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )

    try:
        client = _client(session_factory)
        response = client.get("/v1/projects", headers=_auth_headers("req-project-list"))

        assert response.status_code == 200
        body = response.json()
        project_ids = {project["project_id"] for project in body["projects"]}
        assert str(seed.project_id) in project_ids
        assert str(hidden_project_id) not in project_ids
    finally:
        _delete_test_projects(session_factory, hidden_project_id)


def test_project_detail_returns_deterministic_effective_permissions_with_deny_winning() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _upsert_grant(
            session,
            grant_id=dev_seed_uuid("test-grant:seed-deny-upload-create"),
            resource_id=seed.project_id,
            permission_code="upload.create",
            effect="DENY",
        )
        _upsert_grant(
            session,
            grant_id=dev_seed_uuid("test-grant:seed-allow-dataset-download"),
            resource_id=seed.project_id,
            permission_code="dataset.download",
        )

    try:
        client = _client(session_factory)
        response = client.get(
            f"/v1/projects/{seed.project_id}",
            headers=_auth_headers("req-project-detail"),
        )

        assert response.status_code == 200
        permissions = response.json()["effective_permissions"]
        assert permissions == sorted(permissions)
        assert "project.view" in permissions
        assert "dataset.upload" in permissions
        assert "dataset.download" in permissions
        assert "upload.create" not in permissions
    finally:
        _delete_test_grants(
            session_factory,
            dev_seed_uuid("test-grant:seed-deny-upload-create"),
            dev_seed_uuid("test-grant:seed-allow-dataset-download"),
        )


def test_project_detail_rejects_project_without_project_view() -> None:
    session_factory = _db_session_factory_or_skip()
    denied_project_id = dev_seed_uuid("test-project:denied-detail")

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _upsert_project(session, denied_project_id, slug="denied-detail", name="Denied Detail")

    try:
        client = _client(session_factory)
        response = client.get(
            f"/v1/projects/{denied_project_id}",
            headers=_auth_headers("req-project-denied"),
        )

        assert response.status_code == 403
        assert response.json() == {
            "error": {
                "code": "authorization.permission_denied",
                "message": "Permission denied.",
                "details": {
                    "permission_code": "project.view",
                    "resource_type": "project",
                },
                "request_id": "req-project-denied",
            }
        }
    finally:
        _delete_test_projects(session_factory, denied_project_id)


def test_reusable_permission_gate_supports_later_upload_create_check() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        api_key_actor = _authenticated_actor_from_seed()
        authorization = AuthorizationService(session)

        permissions = authorization.require_any_permission(
            actor=api_key_actor,
            permission_codes=("dataset.upload", "upload.create"),
            resource_type=ResourceType.PROJECT,
            resource_id=seed.project_id,
        )

        assert "dataset.upload" in permissions
        assert "upload.create" in permissions


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


def _authenticated_actor_from_seed() -> AuthenticatedActor:
    seed = build_dev_seed_result()
    return AuthenticatedActor(
        tenant_id=seed.tenant_id,
        api_key_id=seed.api_key_id,
        subject_id=seed.api_key_id,
        scopes=("dev",),
    )


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
    grant.expires_at = expires_at


def _delete_test_projects(session_factory: sessionmaker[Session], *project_ids: uuid.UUID) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(PermissionGrant).where(PermissionGrant.resource_id.in_(project_ids)))
        session.execute(delete(Project).where(Project.id.in_(project_ids)))


def _delete_test_grants(session_factory: sessionmaker[Session], *grant_ids: uuid.UUID) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(PermissionGrant).where(PermissionGrant.id.in_(grant_ids)))
