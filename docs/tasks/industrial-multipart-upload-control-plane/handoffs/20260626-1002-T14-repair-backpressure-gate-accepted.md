# Handoff: T14 repair backpressure gate

Status: accepted
Agent type: Repair
Branch: codex/industrial-upload/T14-repair-backpressure-gate-wt
Worktree: D:\upload-control-plane-T14-repair-backpressure-gate
Started: 2026-06-26 09:50 Asia/Shanghai
Finished: 2026-06-26 10:02 Asia/Shanghai

## Scope

- Intended scope: close the T14 remaining backpressure rejection gate gap for upload creation and part presign paths.
- Explicitly out of scope: KMS unavailable rejection, completed dataset restore/rebuild, MQTT, Go uploader/gateway, file-byte proxying, storage-authoritative complete changes.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-0939-master-handoff-after-T12-T13-T14-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T13/T14 sections
  - `tests/test_phase13_capability_gaps.py`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`

## Changes

- Files changed:
  - `src/upload_control_plane/observability.py`
  - `src/upload_control_plane/application/upload_tasks.py`
  - `src/upload_control_plane/application/upload_sessions.py`
  - `tests/api/test_upload_task_api_foundation.py`
  - `tests/api/test_upload_session_runtime_api.py`
  - `tests/test_phase13_capability_gaps.py`
- Behavior changed:
  - Upload task creation now rejects with `503 storage.backpressure` before idempotency allocation and before storage multipart initiation when storage metrics exceed configured backpressure thresholds.
  - Part presign now rejects with `503 storage.backpressure` before generating presigned URLs when storage metrics exceed configured backpressure thresholds.
  - Rejections increment `storage_backpressure_rejects_total{reason=...}` with stable reasons `storage_error_rate` or `storage_p95_latency`.
  - Phase 13 capability gap list no longer xfails backpressure; only KMS unavailable and restore/rebuild remain xfailed.
- Compatibility notes:
  - No file bytes are accepted or proxied by the backend.
  - Existing successful upload create/presign behavior remains unchanged when storage metrics are below thresholds or absent.

## Verification

- Commands run:
  - `uv run pytest tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_storage_backpressure_before_storage tests/api/test_upload_session_runtime_api.py::test_presign_rejects_storage_backpressure_before_signing_parts tests/test_phase13_capability_gaps.py`
  - `uv run ruff check src/upload_control_plane/observability.py src/upload_control_plane/application/upload_tasks.py src/upload_control_plane/application/upload_sessions.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/test_phase13_capability_gaps.py`
  - `uv run ruff format --check src/upload_control_plane/observability.py src/upload_control_plane/application/upload_tasks.py src/upload_control_plane/application/upload_sessions.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/test_phase13_capability_gaps.py`
  - `uv run pytest tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/api/test_observability.py tests/test_phase13_capability_gaps.py`
- Results:
  - Focused pytest: `2 passed, 2 xfailed, 1 warning`.
  - Ruff check: `All checks passed!`
  - Ruff format check: `6 files already formatted`.
  - Wider API/observability pytest: `37 passed, 2 xfailed, 1 warning`.
- Commands not run and why:
  - Full pytest was not run to keep this repair scoped; focused and adjacent API/observability suites covered the changed behavior.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved; no upload byte route or proxy added.
- Clients receive no MinIO/S3 credentials: preserved; presign path rejects before URL generation under backpressure and never returns credentials.
- Complete uses object storage ListParts as authority: unchanged.
- Authorization uses permission_grants: unchanged.
- Internal IDs remain UUIDs: unchanged.
- MQTT/Go/edge remain optional and dependency-gated: unchanged.

## Risks and Follow-up

- Remaining risks:
  - Backpressure state is derived from the in-process metrics registry. Multi-process deployments need shared metrics/health aggregation before this becomes a full production-wide circuit breaker.
  - The response includes `retry_after_seconds` in the stable error details, not an HTTP `Retry-After` header.
- Known gaps:
  - KMS unavailable rejection remains xfailed.
  - Completed dataset automated restore/rebuild remains xfailed.
- Suggested next agent:
  - Validation agent should re-run T14 focused failure suite and decide whether the in-process metrics gate is sufficient for this phase.

## Recovery Notes

- If accepted, next dependency unlocked: T14 backpressure gap validation.
- If partial, reusable pieces: not applicable.
- If blocked, unblock condition: not applicable.
- If rejected, do not repeat: do not implement backpressure by proxying file bytes through the API or bypassing storage-authoritative complete.
