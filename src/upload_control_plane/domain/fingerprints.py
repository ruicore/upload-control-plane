"""Canonical request fingerprint helpers for idempotency records."""

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any
from uuid import UUID

JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | Sequence["JSONValue"] | Mapping[str, "JSONValue"]


def _normalize_json(value: JSONValue) -> JSONValue:
    if isinstance(value, Mapping):
        return {key: _normalize_json(value[key]) for key in sorted(value)}
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return [_normalize_json(item) for item in value]


def canonical_json(value: JSONValue) -> str:
    return json.dumps(
        _normalize_json(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def generate_request_fingerprint(
    *,
    method: str,
    path: str,
    tenant_id: UUID,
    body: JSONValue,
) -> str:
    canonical = {
        "body": _normalize_json(body),
        "method": method.upper(),
        "path": path,
        "tenant_id": str(tenant_id),
    }
    return sha256(canonical_json(canonical).encode("utf-8")).hexdigest()


def assert_json_value(value: Any) -> JSONValue:
    """Type-narrow a decoded JSON value for strict callers."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [assert_json_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {key: assert_json_value(item) for key, item in value.items()}
    raise TypeError("value is not JSON-compatible")
