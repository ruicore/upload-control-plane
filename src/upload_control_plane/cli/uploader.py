"""Multipart upload orchestration for uploadctl."""

from __future__ import annotations

import concurrent.futures
import hashlib
import random
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from upload_control_plane.cli.client import (
    ControlPlaneClient,
    UploadApiError,
    is_expired_presigned_response,
)
from upload_control_plane.cli.file_ranges import iter_file_range
from upload_control_plane.cli.manifest import (
    UploadManifest,
    default_manifest_path,
    load_manifest,
    save_manifest,
    utc_now_iso,
)
from upload_control_plane.domain.parts import choose_part_size

DEFAULT_CONCURRENCY = 8
MAX_CONCURRENCY = 64
RETRYABLE_STORAGE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class UploadOptions:
    api_url: str
    api_key: str
    project_id: str
    file_path: Path
    manifest_path: Path | None
    task_name: str | None
    dataset_name: str | None
    object_name: str | None
    content_type: str | None
    part_size_bytes: int | None
    concurrency: int
    presign_expires_seconds: int
    checksum_sha256: str | None
    compute_sha256: bool
    source_device_id: str | None
    source_device_code: str | None
    tenant: str | None


@dataclass(frozen=True, slots=True)
class UploadOutcome:
    status: str
    manifest_path: Path
    session_id: str
    uploaded_part_count: int
    part_count: int


ProgressCallback = Callable[[str], None]


class MultipartUploader:
    def __init__(self, client: ControlPlaneClient, *, progress: ProgressCallback | None = None):
        self.client = client
        self.progress = progress or (lambda _message: None)

    def upload(self, options: UploadOptions) -> UploadOutcome:
        validate_concurrency(options.concurrency)
        file_path = options.file_path.resolve()
        stat = file_path.stat()
        part_size = choose_part_size(stat.st_size, options.part_size_bytes)
        checksum = options.checksum_sha256
        if options.compute_sha256:
            checksum = compute_file_sha256(file_path)
        created = self.client.create_upload_task(
            project_id=options.project_id,
            idempotency_key=f"uploadctl-create-{uuid.uuid4()}",
            payload=_create_task_payload(
                options,
                file_size=stat.st_size,
                part_size=part_size,
                checksum=checksum,
            ),
        )
        created_object = _single_created_object(created)
        manifest = UploadManifest(
            api_base_url=options.api_url,
            project_id=str(created["project_id"]),
            task_id=str(created["task_id"]),
            object_id=str(created_object["object_id"]),
            dataset_id=str(created_object["dataset_id"]),
            session_id=str(created_object["session_id"]),
            file_path=str(file_path),
            original_filename=file_path.name,
            file_size_bytes=stat.st_size,
            file_mtime_ns=stat.st_mtime_ns,
            part_size_bytes=int(created_object["part_size_bytes"]),
            part_count=int(created_object["part_count"]),
            checksum_sha256=checksum,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        manifest_path = options.manifest_path or default_manifest_path(file_path)
        save_manifest(manifest_path, manifest)
        self.progress(f"created session {manifest.session_id}; manifest {manifest_path}")
        return self.resume_manifest(
            manifest_path=manifest_path,
            concurrency=options.concurrency,
            presign_expires_seconds=options.presign_expires_seconds,
            complete_when_done=True,
        )

    def resume_manifest(
        self,
        *,
        manifest_path: Path,
        concurrency: int,
        presign_expires_seconds: int,
        complete_when_done: bool,
        force_file_changed: bool = False,
    ) -> UploadOutcome:
        validate_concurrency(concurrency)
        manifest = load_manifest(manifest_path)
        file_path = Path(manifest.file_path)
        _validate_file_unchanged(manifest, file_path, force=force_file_changed)
        status = self.client.get_session(manifest.session_id)
        remote_status = str(status["status"])
        if remote_status == "COMPLETED":
            manifest.local_status = "COMPLETED"
            manifest.updated_at = utc_now_iso()
            save_manifest(manifest_path, manifest)
            return _outcome(manifest, manifest_path)
        if remote_status in {"ABORTED", "FAILED", "EXPIRED"}:
            raise RuntimeError(f"cannot resume session in terminal state {remote_status}")
        if remote_status == "PAUSED":
            raise RuntimeError("session is paused; run uploadctl resume-session before resume")

        self._reconcile_manifest(manifest, manifest_path)
        missing = _missing_part_numbers(manifest)
        self.progress(_progress_line(manifest, "resume"))
        try:
            self._upload_missing_parts(
                manifest=manifest,
                manifest_path=manifest_path,
                missing_part_numbers=missing,
                concurrency=concurrency,
                presign_expires_seconds=presign_expires_seconds,
            )
        except KeyboardInterrupt:
            manifest.local_status = "PAUSED"
            manifest.paused_at = utc_now_iso()
            save_manifest(manifest_path, manifest)
            raise

        if complete_when_done:
            self._complete(manifest, manifest_path)
        return _outcome(manifest, manifest_path)

    def _upload_missing_parts(
        self,
        *,
        manifest: UploadManifest,
        manifest_path: Path,
        missing_part_numbers: list[int],
        concurrency: int,
        presign_expires_seconds: int,
    ) -> None:
        batch_size = min(concurrency * 4, 100)
        pending = list(missing_part_numbers)
        while pending:
            batch = pending[:batch_size]
            pending = pending[batch_size:]
            presigned = self.client.presign_parts(
                session_id=manifest.session_id,
                part_numbers=batch,
                expires_in_seconds=presign_expires_seconds,
            )
            parts_by_number = {
                int(item["part_number"]): item
                for item in presigned["parts"]
                if isinstance(item, dict)
            }
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {
                    executor.submit(
                        self._upload_part_with_retry,
                        manifest=manifest,
                        presigned_part=parts_by_number[part_number],
                        presign_expires_seconds=presign_expires_seconds,
                    ): part_number
                    for part_number in batch
                }
                ack_batch: list[Mapping[str, Any]] = []
                for future in concurrent.futures.as_completed(futures):
                    part_number = futures[future]
                    try:
                        uploaded = future.result()
                    except Exception as exc:
                        manifest.mark_failed(part_number=part_number, error=str(exc))
                        save_manifest(manifest_path, manifest)
                        raise
                    manifest.mark_uploaded(
                        part_number=part_number,
                        etag=uploaded["etag"],
                        size_bytes=uploaded["size_bytes"],
                    )
                    ack_batch.append(
                        {
                            "part_number": part_number,
                            "etag": uploaded["etag"],
                            "size_bytes": uploaded["size_bytes"],
                        }
                    )
                    self.progress(_progress_line(manifest, f"uploaded part {part_number}"))
                    save_manifest(manifest_path, manifest)
                if ack_batch:
                    self.client.ack_parts(session_id=manifest.session_id, parts=ack_batch)
                    save_manifest(manifest_path, manifest)

    def _upload_part_with_retry(
        self,
        *,
        manifest: UploadManifest,
        presigned_part: Mapping[str, Any],
        presign_expires_seconds: int,
    ) -> dict[str, Any]:
        current_part = dict(presigned_part)
        part_number = int(current_part["part_number"])
        for attempt in range(1, 6):
            response = self.client.put_presigned_part(
                url=str(current_part["url"]),
                body=iter_file_range(
                    Path(manifest.file_path),
                    offset_start=int(current_part["offset_start"]),
                    offset_end_exclusive=int(current_part["offset_end_exclusive"]),
                ),
                size_bytes=int(current_part["expected_size_bytes"]),
                required_headers=_string_mapping(current_part.get("required_headers", {})),
                timeout_seconds=max(30.0, presign_expires_seconds + 30.0),
            )
            if response.is_success:
                etag = response.headers.get("ETag") or response.headers.get("etag")
                if not etag:
                    raise RuntimeError(
                        f"storage response for part {part_number} did not include ETag"
                    )
                return {"etag": etag, "size_bytes": int(current_part["expected_size_bytes"])}
            if is_expired_presigned_response(response):
                current_part = self._presign_one(
                    manifest.session_id,
                    part_number,
                    presign_expires_seconds,
                )
                continue
            if response.status_code not in RETRYABLE_STORAGE_STATUS_CODES or attempt == 5:
                raise RuntimeError(
                    f"part {part_number} upload failed with HTTP {response.status_code}"
                )
            time.sleep(_retry_delay_seconds(attempt))
        raise RuntimeError(f"part {part_number} upload failed after retries")

    def _presign_one(
        self,
        session_id: str,
        part_number: int,
        presign_expires_seconds: int,
    ) -> dict[str, Any]:
        response = self.client.presign_parts(
            session_id=session_id,
            part_numbers=[part_number],
            expires_in_seconds=presign_expires_seconds,
        )
        part = response["parts"][0]
        if not isinstance(part, dict):
            raise RuntimeError("presign response contained an invalid part")
        return part

    def _reconcile_manifest(self, manifest: UploadManifest, manifest_path: Path) -> None:
        parts = self.client.list_parts(session_id=manifest.session_id, source="reconcile")
        for item in parts.get("parts", []):
            if not isinstance(item, dict) or item.get("status") != "UPLOADED":
                continue
            etag = item.get("etag")
            size_bytes = item.get("size_bytes")
            if isinstance(etag, str) and isinstance(size_bytes, int):
                uploaded_at = item.get("uploaded_at")
                manifest.mark_uploaded(
                    part_number=int(item["part_number"]),
                    etag=etag,
                    size_bytes=size_bytes,
                    uploaded_at=uploaded_at if isinstance(uploaded_at, str) else None,
                )
        save_manifest(manifest_path, manifest)

    def _complete(self, manifest: UploadManifest, manifest_path: Path) -> None:
        reported_parts: list[Mapping[str, Any]] = [
            {"part_number": int(part_number), "etag": part.etag}
            for part_number, part in sorted(manifest.parts.items(), key=lambda item: int(item[0]))
            if part.status == "UPLOADED" and part.etag is not None
        ]
        try:
            self.client.complete(
                session_id=manifest.session_id,
                idempotency_key=f"uploadctl-complete-{manifest.session_id}",
                client_reported_parts=reported_parts,
                checksum_sha256=manifest.checksum_sha256,
            )
        except UploadApiError as exc:
            if exc.status_code == 409 and exc.code == "upload.missing_parts":
                self._reconcile_manifest(manifest, manifest_path)
                missing = _missing_part_numbers(manifest)
                raise RuntimeError(
                    f"complete rejected; missing parts remain: {missing[:20]}"
                ) from exc
            raise
        manifest.local_status = "COMPLETED"
        manifest.updated_at = utc_now_iso()
        save_manifest(manifest_path, manifest)
        self.progress(_progress_line(manifest, "completed"))


def validate_concurrency(value: int) -> None:
    if value < 1 or value > MAX_CONCURRENCY:
        raise ValueError("concurrency must be between 1 and 64")


def compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        while chunk := file_obj.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _create_task_payload(
    options: UploadOptions,
    *,
    file_size: int,
    part_size: int,
    checksum: str | None,
) -> dict[str, Any]:
    file_name = options.file_path.name
    metadata: dict[str, Any] = {}
    if options.tenant is not None:
        metadata["tenant"] = options.tenant
    return {
        "task_name": options.task_name or f"uploadctl-{file_name}",
        "task_initiator": "cli",
        "source_device_id": options.source_device_id,
        "source_device_code": options.source_device_code,
        "objects": [
            {
                "dataset_name": options.dataset_name or Path(file_name).stem,
                "object_name": options.object_name or file_name,
                "file_size_bytes": file_size,
                "content_type": options.content_type,
                "part_size_bytes": part_size,
                "checksum_sha256": checksum,
                "metadata": {},
            }
        ],
        "metadata": metadata,
    }


def _single_created_object(created: Mapping[str, Any]) -> Mapping[str, Any]:
    objects = created.get("objects")
    if not isinstance(objects, list) or len(objects) != 1 or not isinstance(objects[0], dict):
        raise RuntimeError("uploadctl currently expects exactly one object in create response")
    return objects[0]


def _validate_file_unchanged(manifest: UploadManifest, file_path: Path, *, force: bool) -> None:
    stat = file_path.stat()
    if stat.st_size != manifest.file_size_bytes:
        raise RuntimeError("local file size changed; start a new upload instead of resuming")
    if stat.st_mtime_ns != manifest.file_mtime_ns and not force:
        raise RuntimeError(
            "local file mtime changed; rerun with --force-file-changed to resume anyway"
        )


def _missing_part_numbers(manifest: UploadManifest) -> list[int]:
    uploaded = manifest.uploaded_part_numbers()
    return [
        part_number
        for part_number in range(1, manifest.part_count + 1)
        if part_number not in uploaded
    ]


def _progress_line(manifest: UploadManifest, prefix: str) -> str:
    uploaded = len(manifest.uploaded_part_numbers())
    return (
        f"{prefix}: session={manifest.session_id} uploaded={uploaded}/{manifest.part_count} "
        f"file_size={manifest.file_size_bytes} part_size={manifest.part_size_bytes}"
    )


def _outcome(manifest: UploadManifest, manifest_path: Path) -> UploadOutcome:
    return UploadOutcome(
        status=manifest.local_status,
        manifest_path=manifest_path,
        session_id=manifest.session_id,
        uploaded_part_count=len(manifest.uploaded_part_numbers()),
        part_count=manifest.part_count,
    )


def _retry_delay_seconds(attempt: int) -> float:
    return cast(float, min(30.0, 0.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.25))


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}
