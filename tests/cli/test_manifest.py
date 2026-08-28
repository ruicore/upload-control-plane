from __future__ import annotations

import json
from pathlib import Path

import pytest

from upload_control_plane.cli.manifest import (
    UploadManifest,
    assert_manifest_payload_safe,
    load_manifest,
    redact_url,
    save_manifest,
    utc_now_iso,
)


def test_manifest_round_trip_does_not_store_presigned_urls(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    manifest.mark_uploaded(part_number=1, etag='"etag-1"', size_bytes=1024)
    path = tmp_path / "file.upload.json"

    save_manifest(path, manifest)
    raw = path.read_text(encoding="utf-8")
    loaded = load_manifest(path)

    assert "X-Amz-Signature" not in raw
    assert "presigned" not in raw.lower()
    assert loaded.session_id == "session-id"
    assert loaded.parts["1"].etag == '"etag-1"'


def test_manifest_rejects_presigned_url_keys_and_query_markers(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.upload.json"
    payload = _manifest(tmp_path).model_dump(mode="json")
    payload["parts"]["1"] = {
        "status": "UPLOADED",
        "etag": '"etag"',
        "size_bytes": 1024,
        "uploaded_at": utc_now_iso(),
        "url": "http://localhost:19000/bucket/key?partNumber=1&X-Amz-Signature=secret",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="presigned URL material"):
        load_manifest(path)

    with pytest.raises(ValueError, match="presigned URL material"):
        assert_manifest_payload_safe(
            {"safe_key": "http://localhost:19000/bucket/key?X-Amz-Signature=secret"}
        )


def test_redact_url_removes_presigned_query_string() -> None:
    assert (
        redact_url("http://localhost:19000/bucket/key?partNumber=1&X-Amz-Signature=secret")
        == "http://localhost:19000/bucket/key?[redacted]"
    )


def _manifest(tmp_path: Path) -> UploadManifest:
    file_path = tmp_path / "file.bin"
    file_path.write_bytes(b"content")
    stat = file_path.stat()
    now = utc_now_iso()
    return UploadManifest(
        api_base_url="http://localhost:18080",
        project_id="project-id",
        task_id="task-id",
        object_id="object-id",
        dataset_id="dataset-id",
        session_id="session-id",
        file_path=str(file_path),
        original_filename=file_path.name,
        file_size_bytes=stat.st_size,
        file_mtime_ns=stat.st_mtime_ns,
        part_size_bytes=1024,
        part_count=1,
        created_at=now,
        updated_at=now,
    )
