from __future__ import annotations

import tempfile
from pathlib import Path

from mypy import api

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "static_typing" / "fixtures"
EXPECTED_MISSING_STORAGE = (
    'Cannot instantiate abstract class "MissingStorageFacade" with abstract attribute "_storage"'
)


def _run_fixture(name: str) -> tuple[str, str, int]:
    source = (FIXTURES / name).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="upload-session-facade-contract-") as directory:
        fixture = Path(directory) / name.removesuffix(".txt")
        fixture.write_text(source, encoding="utf-8")
        return api.run(["--config-file", str(ROOT / "pyproject.toml"), str(fixture)])


def _error_records(stdout: str, stderr: str) -> list[str]:
    lines = f"{stdout}\n{stderr}".splitlines()
    starts = [index for index, line in enumerate(lines) if ": error:" in line]
    return [
        "\n".join(lines[start : starts[index + 1] if index + 1 < len(starts) else None])
        for index, start in enumerate(starts)
    ]


def _matches_missing_storage(record: str) -> bool:
    return " ".join(EXPECTED_MISSING_STORAGE.split()) in " ".join(record.split())


def main() -> int:
    valid_stdout, valid_stderr, valid_status = _run_fixture(
        "upload_session_facade_contract_valid.py.txt"
    )
    if valid_status != 0 or _error_records(valid_stdout, valid_stderr):
        return 1

    missing_stdout, missing_stderr, missing_status = _run_fixture(
        "upload_session_facade_contract_missing_storage.py.txt"
    )
    errors = _error_records(missing_stdout, missing_stderr)
    if missing_status == 0 or len(errors) != 1 or not _matches_missing_storage(errors[0]):
        return 1

    print("valid fixture: PASS")
    print("missing-storage fixture: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
