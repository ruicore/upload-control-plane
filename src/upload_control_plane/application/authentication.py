from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass


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
