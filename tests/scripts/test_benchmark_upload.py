from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest


@pytest.fixture(scope="module")
def benchmark_upload() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_upload.py"
    spec = importlib.util.spec_from_file_location("benchmark_upload", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_size_bytes_supports_ci_tiny_and_default_units(benchmark_upload: ModuleType) -> None:
    parse_size_bytes = cast(Any, benchmark_upload).parse_size_bytes
    assert parse_size_bytes("1MiB") == 1024 * 1024
    assert parse_size_bytes("512MiB") == 512 * 1024 * 1024
    assert parse_size_bytes("2mb") == 2_000_000


def test_prepare_benchmark_file_can_create_tiny_sparse_file(
    benchmark_upload: ModuleType,
    tmp_path: Path,
) -> None:
    module = cast(Any, benchmark_upload)
    path = module.prepare_benchmark_file(
        tmp_path / "tiny.bin",
        size_bytes=module.parse_size_bytes("1MiB"),
    )

    assert path.stat().st_size == 1024 * 1024
