"""Local multipart upload benchmark helper.

The benchmark creates a local file, creates an upload task through the public API,
then uploads file ranges directly to presigned storage URLs through the existing
CLI uploader. It never sends file bytes to the backend API.
"""

from __future__ import annotations

import argparse
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from upload_control_plane.cli.client import ControlPlaneClient
from upload_control_plane.cli.uploader import DEFAULT_CONCURRENCY, MultipartUploader, UploadOptions
from upload_control_plane.domain.parts import MIB

DEFAULT_SIZE_BYTES = 512 * MIB
DEFAULT_FILE_NAME = "upload-control-plane-benchmark.bin"


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    file_path: Path
    size_bytes: int
    elapsed_seconds: float
    throughput_mib_per_second: float
    session_id: str | None
    status: str


def main() -> None:
    args = parse_args()
    file_path = prepare_benchmark_file(
        args.file,
        size_bytes=parse_size_bytes(args.size),
        materialize=args.materialize,
    )
    if args.dry_run:
        print(
            "dry-run "
            f"file={file_path} size_bytes={file_path.stat().st_size} "
            "upload_path=api-presign-direct-storage-put"
        )
        return

    result = run_benchmark(
        file_path=file_path,
        api_url=args.api_url,
        api_key=args.api_key,
        project_id=args.project_id,
        part_size_bytes=parse_size_bytes(args.part_size) if args.part_size else None,
        concurrency=args.concurrency,
        presign_expires_seconds=args.presign_expires_seconds,
        manifest_path=args.manifest,
    )
    print(
        "benchmark-complete "
        f"session={result.session_id} status={result.status} "
        f"size_mib={result.size_bytes / MIB:.2f} "
        f"elapsed_seconds={result.elapsed_seconds:.3f} "
        f"throughput_mib_per_second={result.throughput_mib_per_second:.2f}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local direct-to-storage upload benchmark.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--size", default="512MiB")
    parser.add_argument("--file", type=Path, default=Path(".benchmarks") / DEFAULT_FILE_NAME)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--part-size", default=None)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--presign-expires-seconds", type=int, default=900)
    parser.add_argument(
        "--materialize",
        action="store_true",
        help="Write deterministic bytes instead of creating a sparse file.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and (not args.api_key or not args.project_id):
        parser.error("--api-key and --project-id are required unless --dry-run is set")
    return args


def parse_size_bytes(value: str) -> int:
    normalized = value.strip().lower()
    suffixes = {
        "mib": MIB,
        "mi": MIB,
        "mb": 1000 * 1000,
        "gib": 1024 * MIB,
        "gi": 1024 * MIB,
        "gb": 1000 * 1000 * 1000,
        "b": 1,
    }
    for suffix, multiplier in suffixes.items():
        if normalized.endswith(suffix):
            number = normalized[: -len(suffix)]
            return int(float(number) * multiplier)
    return int(normalized)


def prepare_benchmark_file(path: Path, *, size_bytes: int, materialize: bool = False) -> Path:
    if size_bytes <= 0:
        raise ValueError("size_bytes must be positive")
    path.parent.mkdir(parents=True, exist_ok=True)
    if materialize:
        write_deterministic_file(path, size_bytes=size_bytes)
    else:
        with path.open("wb") as file_obj:
            file_obj.truncate(size_bytes)
    return path.resolve()


def write_deterministic_file(path: Path, *, size_bytes: int) -> None:
    block = bytes(range(256)) * 4096
    remaining = size_bytes
    with path.open("wb") as file_obj:
        while remaining:
            chunk = block[: min(len(block), remaining)]
            file_obj.write(chunk)
            remaining -= len(chunk)


def run_benchmark(
    *,
    file_path: Path,
    api_url: str,
    api_key: str,
    project_id: str,
    part_size_bytes: int | None,
    concurrency: int,
    presign_expires_seconds: int,
    manifest_path: Path | None,
) -> BenchmarkResult:
    client = ControlPlaneClient(api_url=api_url, api_key=api_key)
    uploader = MultipartUploader(client, progress=print)
    started = time.perf_counter()
    outcome = uploader.upload(
        UploadOptions(
            api_url=api_url,
            api_key=api_key,
            project_id=project_id,
            file_path=file_path,
            manifest_path=manifest_path,
            task_name=f"benchmark-{uuid.uuid4()}",
            dataset_name=f"benchmark-{file_path.stem}",
            object_name=file_path.name,
            content_type="application/octet-stream",
            part_size_bytes=part_size_bytes,
            concurrency=concurrency,
            presign_expires_seconds=presign_expires_seconds,
            checksum_sha256=None,
            compute_sha256=False,
            source_device_id=None,
            source_device_code=None,
            tenant=None,
        )
    )
    elapsed = time.perf_counter() - started
    size_bytes = file_path.stat().st_size
    throughput = (size_bytes / MIB) / elapsed if elapsed > 0 else 0.0
    return BenchmarkResult(
        file_path=file_path,
        size_bytes=size_bytes,
        elapsed_seconds=elapsed,
        throughput_mib_per_second=throughput,
        session_id=outcome.session_id,
        status=outcome.status,
    )


if __name__ == "__main__":
    main()
