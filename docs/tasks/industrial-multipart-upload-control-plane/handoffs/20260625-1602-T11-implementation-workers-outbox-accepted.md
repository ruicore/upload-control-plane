# Handoff: T11 Workers Outbox

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T11-implementation-workers-outbox
Worktree: D:\upload-control-plane-T11-implementation-workers-outbox
Started: 2026-06-25 15:54 +08:00 Asia/Shanghai
Finished: 2026-06-25 16:02 +08:00 Asia/Shanghai

## Scope

- Intended scope:
  - Add a transactional outbox append helper.
  - Add an outbox dispatcher with claim, retry, and dead-letter behavior using the existing `outbox_events` schema and settings.
  - Integrate the dispatcher with the worker CLI/process while preserving T11 lifecycle commands.
  - Add tests for atomicity, successful delivery, retry scheduling, dead-lettering, idempotent repeated runs, and delivery failure not rolling back domain state.
- Explicitly out of scope:
  - Real MQTT publishing adapter or broker integration.
  - T12 dataset validation parsing.
  - T13 observability metrics/runbooks beyond minimal logging.
  - Go uploader, Go gateway, or edge work.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1530-master-handoff-after-T07-T10-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1553-T11-merge-workers-lifecycle-accepted.md`

## Changes

- Files changed:
  - `src/upload_control_plane/application/outbox.py`
  - `src/upload_control_plane/application/worker_lifecycle.py`
  - `src/upload_control_plane/worker/main.py`
  - `tests/application/test_outbox.py`
  - `tests/application/test_worker_lifecycle.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1602-T11-implementation-workers-outbox-accepted.md`
- Behavior changed:
  - `append_outbox_event()` adds outbox rows to the caller's current SQLAlchemy transaction and validates payloads against file bytes, credential-like keys, and presigned URL material.
  - Lifecycle upload events and dataset audit events now append outbox events in the same commit as their domain/audit writes.
  - `OutboxDispatcher` claims due `PENDING`/`FAILED` events, delivers through an `OutboxSink`, marks successes `DELIVERED`, schedules bounded retries as `FAILED`, and marks events `DEAD_LETTERED` after `outbox_max_attempts`.
  - `upload-worker dispatch-outbox` runs one dispatcher pass.
  - `upload-worker run` still runs lifecycle automation and additionally runs outbox dispatch only when `enable_outbox_dispatcher` is true.
- Compatibility notes:
  - No schema or migration changes were required; the existing `outbox_events` table and settings were used.
  - The real MQTT/webhook sink remains a later adapter; this slice ships a logging sink abstraction.
  - Existing lifecycle commands `run-once`, `reconcile`, and `run` are preserved.

## Verification

- Commands run:
  - `uv run ruff check src tests`: passed.
  - `uv run ruff format --check src tests`: passed, `80 files already formatted`.
  - `uv run mypy src tests`: passed, no issues in 80 source files.
  - `uv run pytest tests/application/test_outbox.py tests/application/test_worker_lifecycle.py -q`: passed, `10 passed`.
  - `uv run pytest tests/application/test_outbox.py tests/application/test_worker_lifecycle.py tests/api/test_upload_session_runtime_api.py tests/api/test_dataset_lifecycle_api.py tests/api/test_device_identity_api.py -q`: passed, `36 passed, 1 warning`.
  - `uv run pytest -q`: passed, `191 passed, 1 warning`.
  - `docker compose config --quiet`: passed.
  - `uv run upload-worker --help`: passed; commands include `run-once`, `dispatch-outbox`, `reconcile`, and `run`.
  - Backend file-byte route scan: `rg -n "UploadFile|File\(|Form\(|request\.body\(|request\.stream\(|Body\(.*bytes|bytes\s*=\s*Body|receive\(|StreamingResponse|FileResponse|/upload-bytes|/file-bytes|/upload-file" src\upload_control_plane\api src\upload_control_plane\main.py`; no matches, exit 1 expected.
  - URL/credential/outbox scan: `rg -n "s3_access_key|s3_secret_key|S3_ACCESS_KEY|S3_SECRET_KEY|aws_access_key_id|aws_secret_access_key|minioadmin|MINIO_ROOT_USER|MINIO_ROOT_PASSWORD|X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url" src\upload_control_plane tests\application\test_outbox.py tests\application\test_worker_lifecycle.py`; matches were limited to config/storage adapter, CLI manifest redaction constants, outbox validation constants, dataset download function names, and negative tests that prove rejection.
- Results:
  - Outbox helper and dispatcher tests passed.
  - Lifecycle worker regression tests passed after adding outbox appends.
  - Relevant dataset/upload/device API regressions passed.
  - Full test suite passed.
- Commands not run and why:
  - No live MQTT broker publishing was tested because real MQTT publishing is explicitly out of scope.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No backend file-byte route markers were found, and outbox payload validation rejects bytes.
- Clients receive no MinIO/S3 credentials: preserved. No new client/API credential exposure was added.
- Complete uses object storage ListParts as authority: preserved. No complete-path behavior was changed.
- Authorization uses permission_grants: preserved. No authorization path was changed.
- Internal IDs remain UUIDs: preserved. New outbox helper uses UUID identifiers and existing UUID schema.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go, or edge implementation was added.
- Presigned URLs are not persisted to outbox: preserved. Outbox payload validation rejects presigned URL-looking strings and URL/credential key names.

## Risks and Follow-up

- Remaining risks:
  - The dispatcher uses a logging sink stub; real MQTT/webhook delivery still needs a later adapter and its own failure tests.
  - `PROCESSING` events are not automatically reclaimed by this slice if a worker crashes after claim and before status update; the table has `locked_until`, but stale-processing recovery can be a T13/T15 hardening follow-up.
- Known gaps:
  - No outbox metrics were added; T13 still owns metrics and runbooks.
  - No operator replay command for dead letters was added.
- Suggested next agent:
  - T11 validation agent for the full lifecycle + outbox result. T12 must remain blocked until full T11 is validated, reviewed, and merged.

## Recovery Notes

- If accepted, next dependency unlocked: T11 validation can start from this branch.
- If partial, reusable pieces: not applicable.
- If blocked, unblock condition: not applicable.
- If rejected, do not repeat: do not persist presigned URL query strings, storage credentials, raw device credentials, or file bytes in outbox payloads.
