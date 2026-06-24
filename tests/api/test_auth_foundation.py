from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.sql import Select

from upload_control_plane.api.auth import get_db_session, hash_api_key, verify_api_key_hash
from upload_control_plane.api.request_context import REQUEST_ID_HEADER
from upload_control_plane.infrastructure.db.models import ApiKey, Tenant
from upload_control_plane.infrastructure.db.seed import DEV_API_KEY_VALUE
from upload_control_plane.main import create_app


@dataclass
class FakeScalarResult:
    value: ApiKey | None

    def one_or_none(self) -> ApiKey | None:
        return self.value


class FakeSession:
    def __init__(self, *, api_key: ApiKey | None, tenant: Tenant | None) -> None:
        self.api_key = api_key
        self.tenant = tenant

    def scalars(self, statement: Select[tuple[ApiKey]]) -> FakeScalarResult:
        _ = statement
        return FakeScalarResult(self.api_key)

    def get(self, model: type[Tenant], entity_id: uuid.UUID) -> Tenant | None:
        _ = model
        if self.tenant is not None and self.tenant.id == entity_id:
            return self.tenant
        return None


def test_dev_seed_sha256_hash_format_verifies_without_raw_storage() -> None:
    stored_hash = hash_api_key(DEV_API_KEY_VALUE)

    assert stored_hash.startswith("sha256:")
    assert DEV_API_KEY_VALUE not in stored_hash
    assert verify_api_key_hash(DEV_API_KEY_VALUE, stored_hash) is True
    assert verify_api_key_hash("wrong-key", stored_hash) is False
    assert verify_api_key_hash(DEV_API_KEY_VALUE, DEV_API_KEY_VALUE) is False


def test_request_id_header_is_returned_and_used_in_error_shape() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/missing-route", headers={REQUEST_ID_HEADER: "req-test-123"})

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == "req-test-123"
    assert response.json() == {
        "error": {
            "code": "request.not_found",
            "message": "Not Found",
            "details": {},
            "request_id": "req-test-123",
        }
    }


def test_missing_api_key_returns_stable_error_response() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/internal/auth-smoke", headers={REQUEST_ID_HEADER: "req-missing"})

    assert response.status_code == 401
    assert response.headers[REQUEST_ID_HEADER] == "req-missing"
    assert response.json() == {
        "error": {
            "code": "auth.api_key_missing",
            "message": "Missing API key.",
            "details": {},
            "request_id": "req-missing",
        }
    }


def test_invalid_api_key_returns_stable_error_response() -> None:
    app = create_app()
    app.dependency_overrides[get_db_session] = _override_session(
        FakeSession(api_key=None, tenant=None)
    )
    client = TestClient(app)

    response = client.get(
        "/internal/auth-smoke",
        headers={REQUEST_ID_HEADER: "req-invalid", "Authorization": "Bearer bad-key"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.api_key_invalid"
    assert response.json()["error"]["request_id"] == "req-invalid"


def test_valid_api_key_authenticates_actor() -> None:
    api_key = _api_key(status="ACTIVE", expires_at=None)
    tenant = _tenant(api_key.tenant_id, status="ACTIVE")
    app = create_app()
    app.dependency_overrides[get_db_session] = _override_session(
        FakeSession(api_key=api_key, tenant=tenant)
    )
    client = TestClient(app)

    response = client.get(
        "/internal/auth-smoke",
        headers={"Authorization": f"Bearer {DEV_API_KEY_VALUE}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "tenant_id": str(api_key.tenant_id),
        "api_key_id": str(api_key.id),
        "subject_id": str(api_key.subject_id),
        "scopes": ["dev"],
    }


def test_inactive_tenant_rejects_authenticated_request() -> None:
    api_key = _api_key(status="ACTIVE", expires_at=None)
    tenant = _tenant(api_key.tenant_id, status="INACTIVE")
    app = create_app()
    app.dependency_overrides[get_db_session] = _override_session(
        FakeSession(api_key=api_key, tenant=tenant)
    )
    client = TestClient(app)

    response = client.get(
        "/internal/auth-smoke",
        headers={
            REQUEST_ID_HEADER: "req-inactive-tenant",
            "Authorization": f"Bearer {DEV_API_KEY_VALUE}",
        },
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "auth.tenant_inactive",
            "message": "Tenant is inactive.",
            "details": {},
            "request_id": "req-inactive-tenant",
        }
    }


def test_expired_or_inactive_api_key_is_rejected_before_tenant_check() -> None:
    api_key = _api_key(status="ACTIVE", expires_at=datetime.now(UTC) - timedelta(seconds=1))
    tenant = _tenant(api_key.tenant_id, status="ACTIVE")
    app = create_app()
    app.dependency_overrides[get_db_session] = _override_session(
        FakeSession(api_key=api_key, tenant=tenant)
    )
    client = TestClient(app)

    response = client.get(
        "/internal/auth-smoke",
        headers={"Authorization": f"Bearer {DEV_API_KEY_VALUE}"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth.api_key_inactive"


def test_x_api_key_header_is_not_public_auth_contract() -> None:
    api_key = _api_key(status="ACTIVE", expires_at=None)
    tenant = _tenant(api_key.tenant_id, status="ACTIVE")
    app = create_app()
    app.dependency_overrides[get_db_session] = _override_session(
        FakeSession(api_key=api_key, tenant=tenant)
    )
    client = TestClient(app)

    response = client.get(
        "/internal/auth-smoke",
        headers={REQUEST_ID_HEADER: "req-x-api-key", "X-API-Key": DEV_API_KEY_VALUE},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "auth.api_key_missing",
            "message": "Missing API key.",
            "details": {},
            "request_id": "req-x-api-key",
        }
    }


def _override_session(fake_session: FakeSession) -> Any:
    def override() -> Iterator[FakeSession]:
        yield fake_session

    return override


def _api_key(*, status: str, expires_at: datetime | None) -> ApiKey:
    api_key = ApiKey(id=uuid.uuid4())
    api_key.tenant_id = uuid.uuid4()
    api_key.key_hash = hash_api_key(DEV_API_KEY_VALUE)
    api_key.name = "Test API key"
    api_key.subject_id = api_key.id
    api_key.scopes = ["dev"]
    api_key.status = status
    api_key.expires_at = expires_at
    return api_key


def _tenant(tenant_id: uuid.UUID, *, status: str) -> Tenant:
    tenant = Tenant(id=tenant_id)
    tenant.slug = "test"
    tenant.name = "Test"
    tenant.status = status
    return tenant
