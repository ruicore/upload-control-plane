from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from upload_control_plane.cli import main
from upload_control_plane.cli.manifest import UploadManifest, save_manifest, utc_now_iso


def test_status_command_uses_public_api_client(monkeypatch: Any) -> None:
    class FakeClient:
        def get_session(self, session_id: str) -> dict[str, Any]:
            assert session_id == "session-1"
            return {
                "session_id": "session-1",
                "status": "UPLOADING",
                "uploaded_part_count": 2,
                "part_count": 4,
                "missing_part_count": 2,
            }

    monkeypatch.setattr(main, "_client", lambda _api_url, _api_key: FakeClient())

    result = CliRunner().invoke(
        main.app,
        ["status", "session-1", "--api-url", "http://api", "--api-key", "secret"],
    )

    assert result.exit_code == 0
    assert "session=session-1 status=UPLOADING uploaded=2/4 missing=2" in result.stdout


def test_pause_command_flushes_manifest_without_presigned_url(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    class FakeClient:
        def pause(
            self,
            *,
            session_id: str,
            idempotency_key: str,
            reason: str,
        ) -> dict[str, str]:
            assert session_id == "session-1"
            assert idempotency_key == "uploadctl-pause-session-1"
            assert reason == "operator_requested"
            return {"session_id": session_id, "status": "PAUSED"}

    manifest_path = tmp_path / "manifest.json"
    save_manifest(manifest_path, _manifest(tmp_path))
    monkeypatch.setattr(main, "_client", lambda _api_url, _api_key: FakeClient())

    result = CliRunner().invoke(
        main.app,
        [
            "pause",
            "session-1",
            "--api-url",
            "http://api",
            "--api-key",
            "secret",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 0
    raw = manifest_path.read_text(encoding="utf-8")
    assert "status=PAUSED" in result.stdout
    assert "X-Amz-Signature" not in raw
    assert UploadManifest.model_validate_json(raw).local_status == "PAUSED"


def test_parse_size_bytes_supports_mib_suffix() -> None:
    assert main.parse_size_bytes("64MiB") == 64 * 1024 * 1024


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
        session_id="session-1",
        file_path=str(file_path),
        original_filename=file_path.name,
        file_size_bytes=stat.st_size,
        file_mtime_ns=stat.st_mtime_ns,
        part_size_bytes=1024,
        part_count=1,
        created_at=now,
        updated_at=now,
    )
