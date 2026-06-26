# T15 implementation backpressure gate handoff

Status: accepted
Agent type: implementation
Branch: `codex/industrial-upload/T15-implementation-backpressure-gate`
Worktree: `D:\upload-control-plane-T15-implementation-backpressure-gate`
Base: local `main` at `0f30ba9`
Started: 2026-06-26 Asia/Shanghai
Finished: 2026-06-26 10:03 Asia/Shanghai

## Scope

- Closed the T14 remaining backpressure rejection gap.
- Added a narrow Settings-driven storage health backpressure gate for:
  - upload task creation before upload task/object/session persistence and before multipart initiation;
  - upload part presign before presigned URL generation.
- Did not touch MQTT, Go, gateway, or backend byte proxy behavior.
- Did not expose storage credentials or new signed URL examples.

## Implementation

- Added `src/upload_control_plane/application/storage_backpressure.py`.
  - Evaluates deterministic local/test settings:
    - `storage_backpressure_forced_reason`
    - `storage_backpressure_observed_error_rate`
    - `storage_backpressure_observed_p95_latency_ms`
    - `storage_backpressure_retry_after_seconds`
  - Uses existing thresholds:
    - `backpressure_storage_error_rate_threshold`
    - `backpressure_storage_p95_latency_ms`
  - Rejects with stable code `storage.backpressure`.
  - Includes safe details only: `source=storage_health`, bounded `reason`, optional `retry_after_seconds`.
  - Increments `storage_backpressure_rejects_total{reason}` with bounded labels.
- Extended `ApiError` with optional response headers so the gate can return `Retry-After`.
- Kept idempotent upload-task replay behavior: an already completed idempotency response can still return before the new-request backpressure gate.
- Converted `tests/test_phase13_capability_gaps.py::test_backpressure_rejection_gate_gap` into a real passing contract test.
- Kept KMS unavailable and completed dataset restore/rebuild xfails intact.

## Validation

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `88 files already formatted`
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 88 source files`
- Focused tests:
  - `uv run pytest -q tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/api/test_observability.py tests/test_phase13_capability_gaps.py`
  - Passed: `39 passed, 2 xfailed, 1 warning`
- `uv run pytest -q`
  - First run failed in `tests/application/test_outbox.py::test_successful_delivery_and_repeated_runs_are_idempotent` because the shared local test DB had 37 due outbox events; this branch did not modify outbox code or tests.
  - Isolated rerun of that test passed.
  - Full rerun passed: `218 passed, 2 xfailed, 1 warning`
- `docker compose config --quiet`
  - Passed with no output.
- `git diff --check`
  - Passed with no output.
- Backend file-byte/proxy scan:
  - Passed. Matches were expected benchmark/docs statements, CLI local file reads, storage integration read, and negative API file-upload test coverage.
- Signed URL/credential leakage scan:
  - Passed. Matches were expected redaction constants/tests, storage implementation/config fields, PRD examples, and fake test URLs.

## Remaining gaps

- KMS unavailable rejection remains an xfail and was intentionally not implemented in this slice.
- Completed dataset automated restore/rebuild remains an xfail and was intentionally not implemented in this slice.
- The backpressure gate is local/config-driven and deterministic for tests; it does not claim live production storage-health monitoring.
