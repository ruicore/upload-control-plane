"""Durable local upload manifest without presigned URLs."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field

MANIFEST_VERSION = 1
FORBIDDEN_MANIFEST_KEYS = {
    "url",
    "urls",
    "presigned_url",
    "presigned_urls",
    "signed_url",
    "signed_urls",
}
PRESIGNED_QUERY_MARKERS = {
    "X-Amz-Signature",
    "X-Amz-Credential",
    "X-Amz-Security-Token",
    "X-Amz-Algorithm",
    "uploadId",
    "partNumber",
}


class ManifestPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PENDING", "UPLOADED", "FAILED"] = "PENDING"
    etag: str | None = None
    size_bytes: int | None = None
    checksum_sha256: str | None = None
    uploaded_at: str | None = None
    retry_count: int = 0
    last_error: str | None = None


class UploadManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: int = MANIFEST_VERSION
    api_base_url: str
    project_id: str
    task_id: str
    object_id: str
    dataset_id: str
    session_id: str
    file_path: str
    original_filename: str
    file_size_bytes: int
    file_mtime_ns: int
    part_size_bytes: int
    part_count: int
    checksum_sha256: str | None = None
    local_status: Literal["UPLOADING", "PAUSED", "COMPLETED", "ABORTED", "FAILED"] = "UPLOADING"
    paused_at: str | None = None
    parts: dict[str, ManifestPart] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    def uploaded_part_numbers(self) -> set[int]:
        return {
            int(part_number)
            for part_number, part in self.parts.items()
            if part.status == "UPLOADED"
        }

    def mark_uploaded(
        self,
        *,
        part_number: int,
        etag: str,
        size_bytes: int,
        uploaded_at: str | None = None,
    ) -> None:
        timestamp = uploaded_at or utc_now_iso()
        self.parts[str(part_number)] = ManifestPart(
            status="UPLOADED",
            etag=etag,
            size_bytes=size_bytes,
            uploaded_at=timestamp,
        )
        self.updated_at = timestamp

    def mark_failed(self, *, part_number: int, error: str) -> None:
        existing = self.parts.get(str(part_number), ManifestPart())
        self.parts[str(part_number)] = existing.model_copy(
            update={
                "status": "FAILED",
                "retry_count": existing.retry_count + 1,
                "last_error": error,
            }
        )
        self.updated_at = utc_now_iso()


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def default_manifest_path(file_path: Path) -> Path:
    return file_path.parent / ".uploadctl" / f"{file_path.name}.upload.json"


def load_manifest(path: Path) -> UploadManifest:
    with path.open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)
    assert_manifest_payload_safe(payload)
    return UploadManifest.model_validate(payload)


def save_manifest(path: Path, manifest: UploadManifest) -> None:
    payload = manifest.model_dump(mode="json")
    assert_manifest_payload_safe(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
        newline="\n",
    ) as file_obj:
        json.dump(payload, file_obj, indent=2, sort_keys=True)
        file_obj.write("\n")
        temp_path = Path(file_obj.name)
    temp_path.replace(path)


def assert_manifest_payload_safe(payload: Any) -> None:
    offenders: list[str] = []
    _collect_manifest_safety_offenders(payload, path="$", offenders=offenders)
    if offenders:
        raise ValueError("manifest contains presigned URL material: " + ", ".join(offenders))


def redact_url(value: str) -> str:
    split = urlsplit(value)
    if not split.query:
        return value
    query_keys = {key for key, _value in parse_qsl(split.query, keep_blank_values=True)}
    if query_keys & PRESIGNED_QUERY_MARKERS:
        return split._replace(query="[redacted]").geturl()
    return value


def _collect_manifest_safety_offenders(payload: Any, *, path: str, offenders: list[str]) -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text.lower() in FORBIDDEN_MANIFEST_KEYS:
                offenders.append(child_path)
            _collect_manifest_safety_offenders(value, path=child_path, offenders=offenders)
        return
    if isinstance(payload, list):
        for index, item in enumerate(payload):
            _collect_manifest_safety_offenders(item, path=f"{path}[{index}]", offenders=offenders)
        return
    if isinstance(payload, str):
        split = urlsplit(payload)
        if split.scheme in {"http", "https"} and split.query:
            query_keys = {key for key, _value in parse_qsl(split.query, keep_blank_values=True)}
            if query_keys & PRESIGNED_QUERY_MARKERS:
                offenders.append(path)
