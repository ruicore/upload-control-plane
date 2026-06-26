# Handoff: T14 validation backpressure gate

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T14-validation-backpressure-gate
Validated branch: codex/industrial-upload/T14-repair-backpressure-gate-wt
Validated commit: c2342e2f32ad97a68cb353d4b54aa08202c96900
Worktree: D:\upload-control-plane-T14-repair-backpressure-gate
Started: 2026-06-26 10:04 Asia/Shanghai
Finished: 2026-06-26 10:08 Asia/Shanghai

## Scope

- Intended scope: independently validate the T14 repair for storage backpressure rejection on upload task creation and part presign.
- Explicitly out of scope: implementation changes, KMS unavailable handling, automated completed-dataset restore/rebuild, MQTT, Go uploader/gateway, and production-wide distributed backpressure aggregation.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1002-T14-repair-backpressure-gate-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`

## Changes

- Files changed: this validation handoff only.
- Behavior changed: none.
- Compatibility notes:
  - Validation reviewed the repair diff at `c2342e2`.
  - Upload task creation calls the storage backpressure gate before fingerprint/idempotency allocation and before storage multipart initiation.
  - Part presign calls the storage backpressure gate before expiry calculation and before storage presign URL generation.

## Verification

- Commands run:
  - `git rev-parse HEAD`
  - `git show --stat --oneline c2342e2`
  - `git show -- src/upload_control_plane/observability.py src/upload_control_plane/application/upload_tasks.py src/upload_control_plane/application/upload_sessions.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/test_phase13_capability_gaps.py`
  - `uv run pytest tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_storage_backpressure_before_storage tests/api/test_upload_session_runtime_api.py::test_presign_rejects_storage_backpressure_before_signing_parts tests/test_phase13_capability_gaps.py -q`
  - `uv run ruff check src/upload_control_plane/observability.py src/upload_control_plane/application/upload_tasks.py src/upload_control_plane/application/upload_sessions.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/test_phase13_capability_gaps.py`
  - `uv run ruff format --check src/upload_control_plane/observability.py src/upload_control_plane/application/upload_tasks.py src/upload_control_plane/application/upload_sessions.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/test_phase13_capability_gaps.py`
  - `uv run pytest tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/api/test_observability.py tests/test_phase13_capability_gaps.py -q`
  - `git diff --check c2342e2^..c2342e2`
  - `rg -n "UploadFile|File\(|bytes\s*=|request\.body\(|stream\(|iter_bytes|put_object|upload_file|upload_fileobj|proxy|X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\benchmarks.md scripts\benchmark_upload.py`
  - `rg -n "def test_|xfail|backpressure|KMS|restore|rebuild|reconciliation" tests\test_phase13_capability_gaps.py src\upload_control_plane\observability.py src\upload_control_plane\application\upload_tasks.py src\upload_control_plane\application\upload_sessions.py`
- Results:
  - Validated HEAD: `c2342e2f32ad97a68cb353d4b54aa08202c96900` before creating this validation handoff branch.
  - Focused pytest: `2 passed, 2 xfailed, 1 warning in 1.71s`.
  - Ruff check: `All checks passed!`
  - Ruff format check: `6 files already formatted`.
  - Wider adjacent pytest: `37 passed, 2 xfailed, 1 warning in 8.57s`.
  - `git diff --check c2342e2^..c2342e2`: no whitespace errors.
  - Static scan reviewed expected matches only: existing benchmark no-proxy note, storage/MinIO internal config and presign implementation, dataset download URL API names, device one-time credential tests/API shape, redaction deny-lists/tests, CLI manifest presigned URL rejection, and size-byte metadata fields.
- Commands not run and why:
  - Full repository pytest was not run; the focused repair suite plus adjacent upload API, session runtime, observability, and phase capability tests cover the changed surface.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. The repair adds only control-plane rejection checks and tests; no route accepting `UploadFile`, request streams, or data-plane proxying was added.
- Clients receive no MinIO/S3 credentials: preserved. Existing internal S3 settings and storage adapter remain server-side; response tests only expose stable 503 details.
- Complete uses object storage ListParts as authority: unchanged by the repair.
- Authorization uses permission_grants: unchanged by the repair.
- Internal IDs remain UUIDs: unchanged by the repair.
- MQTT/Go/edge remain optional and dependency-gated: unchanged by the repair.
- Presigned URLs are not persisted: preserved. Presign rejection happens before `storage.presign_upload_part`, and static scan showed only expected redaction/manifest-deny-list/storage implementation matches.

## Validation Findings

- Accepted: upload task creation returns `503 storage.backpressure` under storage error-rate backpressure before calling `storage.create_multipart_upload`; focused test asserts no storage create calls.
- Accepted: part presign returns `503 storage.backpressure` under storage p95-latency backpressure before calling `storage.presign_upload_part`; focused test asserts no presign calls.
- Accepted: `storage_backpressure_rejects_total` uses a single low-cardinality `reason` label. Current reasons are stable constants: `storage_error_rate` and `storage_p95_latency`.
- Accepted: `tests/test_phase13_capability_gaps.py` now contains only non-backpressure xfails for KMS unavailable rejection and completed dataset automated restore/rebuild.

## Risks and Follow-up

- Remaining risks:
  - Backpressure is derived from the in-process metrics registry. This is acceptable for the current phase validation, but production multi-worker deployments still need shared health aggregation or a deployment-level circuit breaker.
  - The retry hint is returned in error details as `retry_after_seconds`; no HTTP `Retry-After` header is set.
- Known gaps:
  - KMS unavailable rejection remains xfailed and outside this repair scope.
  - Completed dataset automated restore/rebuild remains xfailed and outside this repair scope.
- Suggested next agent:
  - Master review can treat the T14 backpressure gate repair as accepted, with the above production aggregation caveat recorded.

## Recovery Notes

- If accepted, next dependency unlocked: Master review of `codex/industrial-upload/T14-repair-backpressure-gate-wt` / `c2342e2`.
- If partial, reusable pieces: not applicable.
- If blocked, unblock condition: not applicable.
- If rejected, do not repeat: not applicable.
