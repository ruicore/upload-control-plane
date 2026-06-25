from __future__ import annotations

import hashlib
import hmac
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.api.errors import ApiError
from upload_control_plane.config import get_settings
from upload_control_plane.infrastructure.db.models import ApiKey, Device, DeviceCredential, Tenant
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory


@dataclass(frozen=True)
class AuthenticatedActor:
    tenant_id: uuid.UUID
    subject_id: uuid.UUID
    api_key_id: uuid.UUID | None = None
    scopes: tuple[str, ...] = ()
    actor_type: str = "api_key"
    device_id: uuid.UUID | None = None
    device_credential_id: uuid.UUID | None = None
    credential_version: int | None = None


def hash_api_key(api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def verify_api_key_hash(api_key: str, stored_hash: str) -> bool:
    if not stored_hash.startswith("sha256:"):
        return False
    return hmac.compare_digest(hash_api_key(api_key), stored_hash)


def get_db_session() -> Iterator[Session]:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    with session_factory() as session:
        yield session


DB_SESSION = Depends(get_db_session)
AUTHORIZATION_SCHEME = "Bearer "


def extract_bearer_api_key(authorization: str | None) -> str:
    if not authorization:
        raise ApiError(
            status_code=401,
            code="auth.api_key_missing",
            message="Missing API key.",
        )
    if not authorization.startswith(AUTHORIZATION_SCHEME):
        raise ApiError(
            status_code=401,
            code="auth.api_key_invalid",
            message="Invalid API key.",
        )
    api_key = authorization[len(AUTHORIZATION_SCHEME) :].strip()
    if not api_key:
        raise ApiError(
            status_code=401,
            code="auth.api_key_missing",
            message="Missing API key.",
        )
    return api_key


def require_api_key(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = DB_SESSION,
) -> AuthenticatedActor:
    presented_api_key = extract_bearer_api_key(authorization)

    api_key = session.scalars(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(presented_api_key))
    ).one_or_none()
    if api_key is None or not verify_api_key_hash(presented_api_key, api_key.key_hash):
        return _require_device_credential(presented_api_key, session)

    return _authenticated_api_key_actor(api_key, session)


def require_platform_api_key(
    authorization: str | None = Header(default=None, alias="Authorization"),
    session: Session = DB_SESSION,
) -> AuthenticatedActor:
    presented_api_key = extract_bearer_api_key(authorization)
    api_key = session.scalars(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(presented_api_key))
    ).one_or_none()
    if api_key is None or not verify_api_key_hash(presented_api_key, api_key.key_hash):
        raise ApiError(
            status_code=401,
            code="auth.api_key_invalid",
            message="Invalid API key.",
        )
    return _authenticated_api_key_actor(api_key, session)


def _authenticated_api_key_actor(api_key: ApiKey, session: Session) -> AuthenticatedActor:
    now = datetime.now(UTC)
    if api_key.status != "ACTIVE" or (api_key.expires_at is not None and api_key.expires_at <= now):
        raise ApiError(
            status_code=401,
            code="auth.api_key_inactive",
            message="API key is inactive.",
        )

    tenant = session.get(Tenant, api_key.tenant_id)
    if tenant is None or tenant.status != "ACTIVE":
        raise ApiError(
            status_code=403,
            code="auth.tenant_inactive",
            message="Tenant is inactive.",
        )

    subject_id = api_key.subject_id or api_key.id
    return AuthenticatedActor(
        tenant_id=api_key.tenant_id,
        subject_id=subject_id,
        api_key_id=api_key.id,
        scopes=tuple(api_key.scopes),
        actor_type="api_key",
    )


def _require_device_credential(presented_credential: str, session: Session) -> AuthenticatedActor:
    credential = session.scalars(
        select(DeviceCredential).where(
            DeviceCredential.credential_hash == hash_api_key(presented_credential)
        )
    ).one_or_none()
    if credential is None or not verify_api_key_hash(
        presented_credential,
        credential.credential_hash,
    ):
        raise ApiError(
            status_code=401,
            code="auth.api_key_invalid",
            message="Invalid API key.",
        )

    now = datetime.now(UTC)
    device = session.get(Device, credential.device_id)
    if device is None or device.tenant_id != credential.tenant_id or device.status == "DELETED":
        raise ApiError(
            status_code=401,
            code="device.credential_invalid",
            message="Device credential is invalid.",
        )
    if device.status != "ACTIVE":
        raise ApiError(
            status_code=403,
            code="device.inactive",
            message="Device is not active.",
            details={"device_id": str(device.id), "status": device.status},
        )
    if credential.revoked_at is not None:
        raise ApiError(
            status_code=401,
            code="device.credential_revoked",
            message="Device credential is revoked.",
            details={
                "device_id": str(device.id),
                "credential_version": credential.credential_version,
            },
        )
    if credential.expires_at is not None and credential.expires_at <= now:
        raise ApiError(
            status_code=401,
            code="device.credential_expired",
            message="Device credential is expired.",
            details={
                "device_id": str(device.id),
                "credential_version": credential.credential_version,
            },
        )

    tenant = session.get(Tenant, device.tenant_id)
    if tenant is None or tenant.status != "ACTIVE":
        raise ApiError(
            status_code=403,
            code="auth.tenant_inactive",
            message="Tenant is inactive.",
        )

    credential.last_used_at = now
    device.last_seen_at = now
    session.flush()
    return AuthenticatedActor(
        tenant_id=device.tenant_id,
        subject_id=device.id,
        actor_type="device",
        device_id=device.id,
        device_credential_id=credential.id,
        credential_version=credential.credential_version,
    )
