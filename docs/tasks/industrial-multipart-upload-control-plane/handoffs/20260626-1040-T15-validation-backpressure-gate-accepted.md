# T15 validation backpressure gate handoff

Status: accepted
Agent type: validation
Branch: `codex/industrial-upload/T15-validation-backpressure-gate`
Validated implementation branch: `codex/industrial-upload/T15-implementation-backpressure-gate`
Validated implementation HEAD: `39d785e`
Worktree: `D:\upload-control-plane-T15-implementation-backpressure-gate`
Started: 2026-06-26 Asia/Shanghai
Finished: 2026-06-26 10:40 Asia/Shanghai

## Scope

- Independently validated the T15 storage backpressure gate implementation.
- Did not modify implementation code.
- Did not push.

## Required context read

- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1003-T15-implementation-backpressure-gate-accepted.md`
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-0939-master-handoff-after-T12-T13-T14-accepted.md`
- `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - 27.2 required metric `storage_backpressure_rejects_total{reason}`
  - 28.4 storage latency/error spike failure behavior
  - 29.22 quota or backpressure rejection behavior

## Acceptance evidence

- Backpressure gate covers both required paths:
  - Upload task creation calls `reject_if_storage_backpressure()` after idempotent replay resolution and before storage policy selection, quota validation, upload task/object/session persistence, and `create_multipart_upload`.
  - Upload part presign calls `reject_if_storage_backpressure()` after session state/upload id validation and before `presign_upload_part`.
- Rejection happens before storage allocation/presign:
  - `tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_storage_backpressure_before_storage` asserts HTTP 503, stable response details, `Retry-After`, and `storage.create_calls == []`.
  - `tests/api/test_upload_session_runtime_api.py::test_presign_rejects_storage_backpressure_before_storage_presign` asserts HTTP 503, stable response details, `Retry-After`, and `storage.presign_calls == []`.
- Response contract is stable:
  - HTTP 503.
  - Error code `storage.backpressure`.
  - Details limited to `source=storage_health`, bounded `reason`, and optional `retry_after_seconds`.
  - `ApiError` now carries optional response headers, used for `Retry-After`.
- Metric behavior is bounded:
  - `storage_backpressure_rejects_total` increments with a single bounded `reason` label.
  - Allowed reasons are `error_rate`, `latency`, and `manual`; custom forced reasons are mapped to `manual`.
  - No tenant, session, object, URL, or secret material is used in the metric label.
- Idempotent replay is preserved:
  - Existing idempotency response resolution still returns before the new backpressure gate.
- Scope control:
  - No diff paths touched MQTT, Go, or gateway files.
  - No backend byte proxy was introduced.
  - `tests/test_phase13_capability_gaps.py` now has only the KMS unavailable rejection and completed dataset automated restore/rebuild xfails.

## Validation commands

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `88 files already formatted`
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 88 source files`
- Focused tests:
  - `uv run pytest -q tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/api/test_observability.py tests/test_phase13_capability_gaps.py`
  - Passed: `39 passed, 2 xfailed, 1 warning`
- Full tests:
  - `uv run pytest -q`
  - Passed: `218 passed, 2 xfailed, 1 warning`
- `docker compose config --quiet`
  - Passed with no output.
- `git diff --check`
  - Passed with no output.
- Hard scans:
  - Backend byte/proxy scan found only expected benchmark/docs statements, CLI local manifest/benchmark writes, storage integration reads, and negative coverage.
  - Signed URL/credential scan found only expected redaction constants/tests, fake test URLs, storage configuration fields, and storage implementation code.
  - Diff path scan found no MQTT, Go, or gateway file touches.

## Remaining gaps and risks

- KMS unavailable rejection remains an intentional xfail.
- Completed dataset automated restore/rebuild remains an intentional xfail.
- The gate is deterministic and settings-driven; it does not add live production storage-health collection.
- Existing test warning remains: Starlette `TestClient` deprecation warning from FastAPI/httpx integration.
