from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError

import pytest

from upload_control_plane.api.auth import (
    AuthenticatedActor as ApiAuthenticatedActor,
)
from upload_control_plane.api.auth import (
    hash_api_key as api_hash_api_key,
)
from upload_control_plane.api.auth import (
    verify_api_key_hash as api_verify_api_key_hash,
)
from upload_control_plane.api.errors import ApiError as ApiCompatibilityError
from upload_control_plane.application.authentication import (
    AuthenticatedActor,
    hash_api_key,
    verify_api_key_hash,
)
from upload_control_plane.application.errors import ApiError


def test_api_compatibility_imports_reexport_neutral_contract_objects() -> None:
    assert ApiAuthenticatedActor is AuthenticatedActor
    assert ApiCompatibilityError is ApiError
    assert api_hash_api_key is hash_api_key
    assert api_verify_api_key_hash is verify_api_key_hash


def test_authenticated_actor_preserves_frozen_value_behavior_and_defaults() -> None:
    actor = AuthenticatedActor(
        tenant_id=uuid.UUID(int=1),
        subject_id=uuid.UUID(int=2),
    )

    assert actor == AuthenticatedActor(
        tenant_id=uuid.UUID(int=1),
        subject_id=uuid.UUID(int=2),
    )
    assert actor.api_key_id is None
    assert actor.scopes == ()
    assert actor.actor_type == "api_key"
    assert actor.device_id is None
    assert actor.device_credential_id is None
    assert actor.credential_version is None
    with pytest.raises(FrozenInstanceError):
        actor.actor_type = "device"  # type: ignore[misc]


def test_api_error_preserves_exception_fields_and_copies_mappings() -> None:
    details = {"field": "value"}
    headers = {"Retry-After": "5"}

    error = ApiError(
        status_code=409,
        code="example.conflict",
        message="Example conflict.",
        details=details,
        headers=headers,
    )
    details["field"] = "changed"
    headers["Retry-After"] = "10"

    assert str(error) == "Example conflict."
    assert error.status_code == 409
    assert error.code == "example.conflict"
    assert error.message == "Example conflict."
    assert error.details == {"field": "value"}
    assert error.headers == {"Retry-After": "5"}


def test_credential_hashing_preserves_format_and_verification_behavior() -> None:
    stored_hash = hash_api_key("credential-value")

    assert stored_hash == (
        "sha256:875ee88fbea14a3e7cbffc22ca68e8a21a2486ce2c8379504beef7d5e87e25f0"
    )
    assert verify_api_key_hash("credential-value", stored_hash) is True
    assert verify_api_key_hash("wrong-value", stored_hash) is False
    assert verify_api_key_hash("credential-value", "credential-value") is False
