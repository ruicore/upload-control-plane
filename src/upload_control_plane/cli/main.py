"""Command-line entry point for uploadctl."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from upload_control_plane.cli.client import ControlPlaneClient
from upload_control_plane.cli.manifest import load_manifest, save_manifest, utc_now_iso
from upload_control_plane.cli.uploader import (
    DEFAULT_CONCURRENCY,
    MultipartUploader,
    UploadOptions,
)
from upload_control_plane.domain.parts import MIB

app = typer.Typer(help="HTTP-only multipart uploader for Upload Control Plane.")


def _client(api_url: str, api_key: str) -> ControlPlaneClient:
    return ControlPlaneClient(api_url=api_url, api_key=api_key)


@app.command()
def upload(
    file: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False)],
    api_url: Annotated[str, typer.Option("--api-url")],
    api_key: Annotated[str, typer.Option("--api-key", hide_input=True)],
    project_id: Annotated[str, typer.Option("--project-id")],
    tenant: Annotated[str | None, typer.Option("--tenant")] = None,
    device_id: Annotated[str | None, typer.Option("--device-id")] = None,
    source_device_id: Annotated[str | None, typer.Option("--source-device-id")] = None,
    task_name: Annotated[str | None, typer.Option("--task-name")] = None,
    dataset_name: Annotated[str | None, typer.Option("--dataset-name")] = None,
    object_name: Annotated[str | None, typer.Option("--object-name")] = None,
    content_type: Annotated[str | None, typer.Option("--content-type")] = None,
    part_size: Annotated[str | None, typer.Option("--part-size")] = None,
    concurrency: Annotated[int, typer.Option("--concurrency", min=1, max=64)] = DEFAULT_CONCURRENCY,
    manifest: Annotated[Path | None, typer.Option("--manifest")] = None,
    checksum_sha256: Annotated[str | None, typer.Option("--checksum-sha256")] = None,
    compute_sha256: Annotated[bool, typer.Option("--compute-sha256")] = False,
    presign_expires_seconds: Annotated[int, typer.Option("--presign-expires-seconds")] = 900,
) -> None:
    """Create an upload task, upload file parts directly to object storage, and complete."""
    uploader = MultipartUploader(_client(api_url, api_key), progress=typer.echo)
    outcome = uploader.upload(
        UploadOptions(
            api_url=api_url,
            api_key=api_key,
            project_id=project_id,
            file_path=file,
            manifest_path=manifest,
            task_name=task_name,
            dataset_name=dataset_name,
            object_name=object_name,
            content_type=content_type,
            part_size_bytes=parse_size_bytes(part_size),
            concurrency=concurrency,
            presign_expires_seconds=presign_expires_seconds,
            checksum_sha256=checksum_sha256,
            compute_sha256=compute_sha256,
            source_device_id=source_device_id,
            source_device_code=device_id,
            tenant=tenant,
        )
    )
    typer.echo(
        _format_outcome(
            outcome.status,
            outcome.session_id,
            outcome.uploaded_part_count,
            outcome.part_count,
        )
    )


@app.command()
def resume(
    manifest: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False)],
    api_key: Annotated[str, typer.Option("--api-key", hide_input=True)],
    concurrency: Annotated[int, typer.Option("--concurrency", min=1, max=64)] = DEFAULT_CONCURRENCY,
    presign_expires_seconds: Annotated[int, typer.Option("--presign-expires-seconds")] = 900,
    force_file_changed: Annotated[bool, typer.Option("--force-file-changed")] = False,
    no_complete: Annotated[bool, typer.Option("--no-complete")] = False,
) -> None:
    """Resume a local manifest and request fresh presigned URLs for missing parts."""
    saved = load_manifest(manifest)
    uploader = MultipartUploader(_client(saved.api_base_url, api_key), progress=typer.echo)
    outcome = uploader.resume_manifest(
        manifest_path=manifest,
        concurrency=concurrency,
        presign_expires_seconds=presign_expires_seconds,
        complete_when_done=not no_complete,
        force_file_changed=force_file_changed,
    )
    typer.echo(
        _format_outcome(
            outcome.status,
            outcome.session_id,
            outcome.uploaded_part_count,
            outcome.part_count,
        )
    )


@app.command()
def status(
    session_id: Annotated[str, typer.Argument()],
    api_url: Annotated[str, typer.Option("--api-url")],
    api_key: Annotated[str, typer.Option("--api-key", hide_input=True)],
) -> None:
    """Show server-side upload session status."""
    payload = _client(api_url, api_key).get_session(session_id)
    typer.echo(
        " ".join(
            [
                f"session={payload['session_id']}",
                f"status={payload['status']}",
                f"uploaded={payload['uploaded_part_count']}/{payload['part_count']}",
                f"missing={payload['missing_part_count']}",
            ]
        )
    )


@app.command()
def pause(
    session_id: Annotated[str, typer.Argument()],
    api_url: Annotated[str, typer.Option("--api-url")],
    api_key: Annotated[str, typer.Option("--api-key", hide_input=True)],
    reason: Annotated[str, typer.Option("--reason")] = "operator_requested",
    manifest: Annotated[Path | None, typer.Option("--manifest")] = None,
) -> None:
    """Pause server-side scheduling and optionally mark a local manifest paused."""
    payload = _client(api_url, api_key).pause(
        session_id=session_id,
        idempotency_key=f"uploadctl-pause-{session_id}",
        reason=reason,
    )
    if manifest is not None:
        saved = load_manifest(manifest)
        saved.local_status = "PAUSED"
        saved.paused_at = utc_now_iso()
        saved.updated_at = utc_now_iso()
        save_manifest(manifest, saved)
    typer.echo(f"session={payload['session_id']} status={payload['status']}")


@app.command("resume-session")
def resume_session(
    session_id: Annotated[str, typer.Argument()],
    api_url: Annotated[str, typer.Option("--api-url")],
    api_key: Annotated[str, typer.Option("--api-key", hide_input=True)],
    reason: Annotated[str, typer.Option("--reason")] = "operator_resumed",
) -> None:
    """Resume server-side scheduling; use uploadctl resume to upload missing parts."""
    payload = _client(api_url, api_key).resume(
        session_id=session_id,
        idempotency_key=f"uploadctl-resume-{session_id}",
        reason=reason,
    )
    typer.echo(f"session={payload['session_id']} status={payload['status']}")


@app.command()
def abort(
    session_id: Annotated[str, typer.Argument()],
    api_url: Annotated[str, typer.Option("--api-url")],
    api_key: Annotated[str, typer.Option("--api-key", hide_input=True)],
    reason: Annotated[str, typer.Option("--reason")] = "client_cancelled",
    manifest: Annotated[Path | None, typer.Option("--manifest")] = None,
) -> None:
    """Abort an unfinished multipart upload session."""
    payload = _client(api_url, api_key).abort(
        session_id=session_id,
        idempotency_key=f"uploadctl-abort-{session_id}",
        reason=reason,
    )
    if manifest is not None:
        saved = load_manifest(manifest)
        saved.local_status = "ABORTED"
        saved.updated_at = utc_now_iso()
        save_manifest(manifest, saved)
    typer.echo(f"session={payload['session_id']} status={payload['status']}")


def parse_size_bytes(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    suffixes = {
        "mib": MIB,
        "mi": MIB,
        "mb": 1000 * 1000,
        "gib": 1024 * MIB,
        "gi": 1024 * MIB,
        "gb": 1000 * 1000 * 1000,
    }
    for suffix, multiplier in suffixes.items():
        if normalized.endswith(suffix):
            number = normalized[: -len(suffix)]
            return int(float(number) * multiplier)
    return int(normalized)


def _format_outcome(status: str, session_id: str, uploaded_part_count: int, part_count: int) -> str:
    return f"session={session_id} status={status} uploaded={uploaded_part_count}/{part_count}"


if __name__ == "__main__":
    app()
