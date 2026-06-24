"""Server-side object key generation without storage SDK dependencies."""

import re
from datetime import UTC, datetime
from uuid import UUID

from upload_control_plane.domain.errors import InvalidObjectNameError

MAX_OBJECT_NAME_LENGTH = 255
SAFE_OBJECT_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_object_name(raw_name: str) -> str:
    stripped = raw_name.strip()
    if not stripped:
        raise InvalidObjectNameError("object name must not be empty")
    if len(stripped) > MAX_OBJECT_NAME_LENGTH:
        raise InvalidObjectNameError("object name is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in stripped):
        raise InvalidObjectNameError("object name must not contain control characters")
    if "/" in stripped or "\\" in stripped:
        raise InvalidObjectNameError("object name must not contain path separators")
    if stripped in {".", ".."}:
        raise InvalidObjectNameError("object name must not be a relative path segment")

    sanitized = SAFE_OBJECT_NAME_RE.sub("_", stripped).strip("._-")
    if not sanitized or sanitized in {".", ".."}:
        raise InvalidObjectNameError("object name does not contain a safe filename stem")
    if sanitized != stripped and ".." in stripped:
        raise InvalidObjectNameError("object name must not contain path traversal")
    return sanitized


def build_object_key(
    *,
    tenant_id: UUID,
    project_id: UUID,
    dataset_id: UUID,
    session_id: UUID,
    raw_object_name: str,
    created_at: datetime,
) -> str:
    safe_name = sanitize_object_name(raw_object_name)
    timestamp = created_at.astimezone(UTC)
    date_prefix = timestamp.strftime("%Y/%m/%d")
    return (
        f"tenants/{tenant_id}/projects/{project_id}/datasets/{dataset_id}/"
        f"{date_prefix}/{session_id}/{safe_name}"
    )
