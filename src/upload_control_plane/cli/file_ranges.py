"""Local file helpers for bounded-memory multipart uploads."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

DEFAULT_READ_CHUNK_BYTES = 1024 * 1024


def iter_file_range(
    file_path: Path,
    *,
    offset_start: int,
    offset_end_exclusive: int,
    chunk_size: int = DEFAULT_READ_CHUNK_BYTES,
) -> Iterator[bytes]:
    """Yield one file byte range without loading the full part into memory."""
    remaining = offset_end_exclusive - offset_start
    if remaining < 0:
        raise ValueError("offset_end_exclusive must be greater than or equal to offset_start")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    with file_path.open("rb") as file_obj:
        file_obj.seek(offset_start)
        while remaining > 0:
            chunk = file_obj.read(min(chunk_size, remaining))
            if not chunk:
                raise OSError("file ended before the expected byte range was read")
            remaining -= len(chunk)
            yield chunk
