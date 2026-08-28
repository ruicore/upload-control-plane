from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_SENSITIVE_KEYS = {
    "access_key",
    "accesskey",
    "api_key",
    "authorization",
    "credential",
    "password",
    "presigned_url",
    "private_key",
    "secret",
    "secret_key",
    "signed_url",
    "token",
    "upload_url",
    "url",
    "x-amz-credential",
    "x-amz-signature",
}


def redact_url_query(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.query:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", parsed.fragment))
    return value


def sanitize_for_observability(value: Any) -> Any:
    if isinstance(value, str):
        return redact_url_query(value)
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                sanitized[key_text] = _redacted_sensitive_value(item)
            else:
                sanitized[key_text] = sanitize_for_observability(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_observability(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_for_observability(item) for item in value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or any(part in normalized for part in _SENSITIVE_KEYS)


def _redacted_sensitive_value(value: Any) -> str:
    if isinstance(value, str) and ("://" in value):
        return redact_url_query(value)
    return "[REDACTED]"
