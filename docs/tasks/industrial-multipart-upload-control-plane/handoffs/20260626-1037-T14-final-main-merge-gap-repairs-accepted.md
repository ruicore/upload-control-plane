# T14 final main merge gap repairs - Accepted

Status: accepted
Agent type: final merge agent
Branch at handoff: main
Started: 2026-06-26 Asia/Shanghai
Finished: 2026-06-26 10:37 Asia/Shanghai

## Scope

- Merged accepted branch `codex/industrial-upload/T14-merge-gap-repairs` at `abd50a8` into local `main`.
- Main baseline before merge: `12fe967`, including the T15 backpressure line:
  - `39d785e`
  - `102acac`
  - `ba7bfc4`
  - `12fe967`
- T14 branch baseline: `0f30ba9`.
- No reset, checkout overwrite, or history rewrite was used.

## Integrated repairs

- KMS-unavailable upload initiation rejection:
  - rejects unsupported `SSE_KMS` capability before creating task/session rows
  - maps provider KMS initiation failure to `storage_policy.kms_unavailable`
  - does not expose `kms_key_ref` or provider message material in API response details
- Storage backpressure gate:
  - preserved T15 settings-driven gate behavior, `Retry-After`, and bounded error details
  - integrated T14 metrics-driven storage health signals through the same `storage_backpressure.py` gate
  - avoided duplicate gate calls and duplicate/conflicting reject metrics
- Restore/rebuild:
  - restores metadata for completed datasets when missing objects return
  - rebuilds object-only dataset metadata into operator-review quarantine without downloading file bytes
- Validation handoffs, merge handoff, and outbox test isolation handoffs were kept.
- Existing T15 handoffs were preserved.

## Conflict handling

- `tests/api/test_upload_task_api_foundation.py`
  - content conflict between T15 settings backpressure tests and T14 KMS/metrics backpressure tests
  - kept both accepted behavior sets and made metrics backpressure use the unified T15 error detail shape
- `tests/test_phase13_capability_gaps.py`
  - removed obsolete KMS and restore/rebuild xfail sentinels
  - kept the T15 backpressure evaluator regression as an active test
- `src/upload_control_plane/application/upload_tasks.py` and `src/upload_control_plane/application/upload_sessions.py`
  - auto-merge had duplicate private metrics gates plus the T15 gate
  - resolved by keeping one authoritative gate in `application/storage_backpressure.py`

## Hard constraints checked

- No backend/MQTT file-byte proxy behavior was added.
- No MinIO/S3 credentials or signed query material is exposed to clients by the merged paths.
- Completion remains storage-authoritative.
- Authorization remains permission-grants based.

## Verification

- `git diff --check`: passed.
- `uv run ruff check src tests`: passed.
- `uv run ruff format --check src tests`: passed, `88 files already formatted` after applying `uv run ruff format src tests`.
- `uv run mypy src tests`: passed, no issues in 88 source files.
- Focused tests:
  - `uv run pytest -q tests/test_phase13_capability_gaps.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/application/test_worker_lifecycle.py tests/application/test_outbox.py`
  - passed: 49 passed, 1 StarletteDeprecationWarning.
- Full tests:
  - `uv run pytest -q`
  - passed: 224 passed, 1 StarletteDeprecationWarning.

## Remaining risks

- The storage backpressure gate now accepts both deterministic settings input and in-process metrics input. This is intentional for the accepted T14/T15 merge, but production metric source wiring should remain controlled so stale process-local observations do not reject traffic unexpectedly.
- Existing FastAPI/Starlette `TestClient` deprecation warning remains unrelated to this merge.
- No push was performed.
