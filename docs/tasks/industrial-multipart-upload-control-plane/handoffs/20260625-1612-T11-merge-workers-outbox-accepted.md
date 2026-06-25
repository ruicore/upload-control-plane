# Handoff: T11 Workers Outbox Merge

Status: accepted
Agent type: Merge
Branch: codex/industrial-upload/T11-merge-workers-outbox
Worktree: D:\upload-control-plane-T11-merge-workers-outbox
Started: 2026-06-25 16:07 +08:00
Finished: 2026-06-25 16:12 +08:00

## Scope

- Intended scope:
  - Create the T11 workers outbox merge branch from current `main` at `5682c4d`.
  - Merge `codex/industrial-upload/T11-validation-workers-outbox` at `bd065ed`.
  - Preserve accepted T07-T10 behavior and accepted T11 workers lifecycle behavior.
  - Record merge conflicts, verification evidence, and downstream unlock notes.
- Explicitly out of scope:
  - No new product behavior.
  - No semantic conflict resolution.
  - No opportunistic repair or cleanup.
  - No T12 work.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - Existing implementation and validation handoffs merged from the outbox branch.

## Changes

- Files changed:
  - Merged `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1602-T11-implementation-workers-outbox-accepted.md`.
  - Merged `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1607-T11-validation-workers-outbox-accepted.md`.
  - Merged `src/upload_control_plane/application/outbox.py`.
  - Merged T11 outbox hooks in `src/upload_control_plane/application/worker_lifecycle.py`.
  - Merged `dispatch-outbox` worker command wiring in `src/upload_control_plane/worker/main.py`.
  - Merged `tests/application/test_outbox.py`.
  - Merged T11 lifecycle outbox assertions in `tests/application/test_worker_lifecycle.py`.
- Behavior changed:
  - Accepted T11 lifecycle behavior from current `main` is retained.
  - Accepted T11 workers outbox implementation and validation result are now present on the merge branch.
- Compatibility notes:
  - No merge conflicts occurred.
  - No semantic decisions were made by this Merge Agent.

## Conflict Summary

- `git merge --no-ff codex/industrial-upload/T11-validation-workers-outbox`
  - Result: clean merge using the `ort` strategy.
  - Conflict files: none.
  - Manual conflict edits: none.

## Verification

- Commands run:
  - `git diff --check HEAD~1..HEAD`
    - Result: passed, no output.
  - `uv run ruff check src tests`
    - Result: passed, `All checks passed!`.
    - Note: first run in this worktree created `.venv`; ruff cache writes emitted access warnings but exit code was 0.
  - `uv run ruff format --check src tests`
    - Result: passed, `80 files already formatted`.
  - `uv run mypy src tests`
    - Result: passed, `Success: no issues found in 80 source files`.
  - `uv run pytest tests/application/test_outbox.py tests/application/test_worker_lifecycle.py -q`
    - Result: passed, `10 passed in 2.98s`.
  - `uv run pytest tests/api/test_upload_session_runtime_api.py tests/api/test_dataset_lifecycle_api.py tests/api/test_device_identity_api.py -q`
    - Result: passed, `26 passed, 1 warning in 8.34s`.
    - Warning: Starlette/TestClient dependency deprecation warning from FastAPI testclient import.
  - `docker compose config --quiet`
    - Result: passed, no output.
  - `uv run upload-worker --help`
    - Result: passed; commands include `run-once`, `dispatch-outbox`, `reconcile`, and `run`.
  - `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body" src/upload_control_plane/api src/upload_control_plane/application`
    - Result: passed, no backend API/application file-byte route hits.
  - `rg -n "MINIO|S3|AWS_ACCESS|AWS_SECRET|access_key|secret_key|presigned|presign|credential|credentials" src tools tests/application/test_outbox.py`
    - Result: reviewed expected hits only: server config/storage internals, CLI/browser presign flows, device credential APIs, and outbox rejection tests/guards.
  - `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|bytes\(|bytearray|memoryview" src/upload_control_plane/application/outbox.py src/upload_control_plane/application/worker_lifecycle.py tests/application/test_outbox.py`
    - Result: reviewed expected outbox guard and test hits; no unsafe payload persistence path found.
- Commands not run and why:
  - Full repository pytest suite was not requested for this Merge Agent and would exceed the defined merge validation scope.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. API/application scan found no `UploadFile`, FastAPI `File(...)`, multipart form-data, request stream, or request body handlers.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Scan hits are limited to server-side settings/storage internals, existing device credential API behavior, CLI/browser presign flow references, and tests/guards.
- Complete uses object storage ListParts as authority:
  - Preserved. This merge does not alter accepted runtime complete logic.
- Authorization uses permission_grants:
  - Preserved. This merge does not alter accepted authorization gates.
- Internal IDs remain UUIDs:
  - Preserved. Outbox aggregate/event IDs use UUIDs and do not introduce human-readable primary keys.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. This merge does not introduce MQTT, Go uploader, or Go gateway behavior.

## Risks and Follow-up

- Remaining risks:
  - Final acceptance still requires Master final review of this merge branch.
- Known gaps:
  - None found within Merge Agent scope.
- Suggested next agent:
  - Master final review on `codex/industrial-upload/T11-merge-workers-outbox`.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Full T11 lifecycle plus workers outbox are accepted and merged on this branch.
  - T12 is only unlocked after Master final review and root `main` fast-forward to this merge result.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
