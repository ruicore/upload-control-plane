# Handoff: T11 Workers Lifecycle Validation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T11-validation-workers-lifecycle
Worktree: D:\upload-control-plane-T11-validation-workers-lifecycle
Started: 2026-06-25 15:45 +08:00 Asia/Shanghai
Finished: 2026-06-25 15:50 +08:00 Asia/Shanghai

## Scope

- Intended scope: Independently validate implementation branch `codex/industrial-upload/T11-implementation-workers-lifecycle` at commit `795bf5ea568d10622a3b35206bb9d7e9ec45fdbb` for the T11 lifecycle slice.
- Explicitly out of scope: Functional code edits, repair work, outbox implementation, T12 validation worker implementation, MQTT, Go uploader, and edge gateway.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - T11 section in `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`
  - `D:\upload-control-plane-T11-implementation-workers-lifecycle\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1545-T11-implementation-workers-lifecycle-accepted.md`

## Changes

- Files changed by this validation agent:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1550-T11-validation-workers-lifecycle-accepted.md`
- Behavior changed: none.
- Compatibility notes:
  - Validation was run in a dedicated worktree and branch created from implementation commit `795bf5e`.
  - Implementation changes inspected include `WorkerLifecycleService`, `upload-worker` Typer commands, Docker worker command, settings additions, and lifecycle tests.

## Verification

- Commands run:
  - `git worktree add -b codex/industrial-upload/T11-validation-workers-lifecycle D:\upload-control-plane-T11-validation-workers-lifecycle 795bf5e`: passed.
  - `uv run ruff check src tests`: passed.
  - `uv run ruff format --check src tests`: passed, 78 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 78 source files.
  - `uv run pytest tests/application/test_worker_lifecycle.py -q`: passed, 4 passed.
  - `uv run pytest tests/api/test_upload_session_runtime_api.py tests/api/test_dataset_lifecycle_api.py tests/api/test_device_identity_api.py -q`: passed, 26 passed, 1 Starlette/httpx deprecation warning.
  - `uv run pytest -q`: passed, 185 passed, 1 Starlette/httpx deprecation warning.
  - `docker compose config --quiet`: passed.
  - `uv run upload-worker --help`: passed; commands shown: `run-once`, `reconcile`, `run`.
  - `uv run upload-worker reconcile --help`: passed; documents `--object-ref bucket:object/key`.
  - `uv run upload-worker run-once --help`: passed.
  - `rg -n "UploadFile|File\(|Form\(|request\.body\(|request\.stream\(|Body\(.*bytes|bytes\s*=\s*Body|receive\(|StreamingResponse|FileResponse|/upload-bytes|/file-bytes|/upload-file" src\upload_control_plane\api src\upload_control_plane\main.py`: no matches, exit 1 expected.
  - `rg -n "s3_access_key|s3_secret_key|S3_ACCESS_KEY|S3_SECRET_KEY|aws_access_key_id|aws_secret_access_key|minioadmin|MINIO_ROOT_USER|MINIO_ROOT_PASSWORD" src\upload_control_plane\api src\upload_control_plane\application src\upload_control_plane\cli tools\manual-uploader\src`: no matches, exit 1 expected.
  - `rg -n "outbox|Outbox|DEAD_LETTER|DEAD_LETTERED|PENDING|PROCESSING|DELIVERED|dispatch|dispatcher" src\upload_control_plane tests docs\tasks\industrial-multipart-upload-control-plane\handoffs`: confirms only schema/config/handoff references and explicit `WorkerLifecycleService` note that outbox dispatcher is not implemented.
  - `rg -n "mqtt|emqx|paho|gmqtt|go/|golang|permission_grants|PermissionGrant|grant" src tests pyproject.toml docker-compose.yml`: no added MQTT/Go implementation path found; permission grant code remains existing auth/schema/test surface.
  - `git diff --check HEAD^..HEAD`: passed.
- Results:
  - Worker process/CLI exists through `upload-worker = "upload_control_plane.worker.main:app"` and exposes sensible lifecycle commands.
  - Expired sessions in `INITIATED`/`UPLOADING`/`PAUSED` are selected for expiry; focused tests prove `PAUSED -> EXPIRED -> ABORTING -> ABORTED` with one storage abort call and safe rerun behavior.
  - Completed sessions are excluded from expiry cleanup; focused tests prove no abort or delete storage calls for completed sessions.
  - Recycle-bin retention enforcement only targets `DELETED` datasets; code checks retention, legal hold, and object lock before purge. Focused tests cover retention timing and storage delete/metadata clearing.
  - Purge deletes through `ObjectStorage.delete_object`, then marks dataset `PURGED` and clears object metadata.
  - Recovery reconciliation uses `recovery_status` and focused tests cover missing final object, metadata-only, verified, and operator-supplied object-only references.
  - Outbox dispatcher body is not implemented in this lifecycle slice; full T11 remains incomplete until the workers-outbox slice is implemented and validated.
- Commands not run and why:
  - Live MinIO destructive lifecycle smoke was not run; existing tests use the storage adapter boundary and fake storage to avoid deleting real local objects during validation.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: accepted. Hard scan found no backend file-byte route markers, and the worker uses metadata plus storage adapter calls.
- Clients receive no MinIO/S3 credentials: accepted. Hard scan found no client-facing S3/MinIO credential exposure markers.
- Complete uses object storage ListParts as authority: accepted. Completion code was not changed by this lifecycle slice, and runtime API regression tests passed.
- Authorization uses permission_grants: accepted. Permission grant/auth paths were not changed, and related API regressions passed.
- Internal IDs remain UUIDs: accepted. New worker logic uses existing UUID model identifiers.
- MQTT/Go/edge remain optional and dependency-gated: accepted. No MQTT, Go uploader, or edge gateway implementation was added.
- Completed sessions/final objects are not deleted by cleanup abort: accepted by focused test.
- Dataset recycle-bin retention auto-purge respects T09 governance/legal hold/object lock policy: accepted by code inspection for policy gates plus retention-focused test coverage; legal-hold/object-lock denial lacks a dedicated new T11 focused test.

## Risks and Follow-up

- Remaining risks:
  - Legal hold and object-lock denial are implemented in code but not directly covered by a new T11 worker-focused test; T09 API tests and schema coverage still protect the governance model.
  - Recovery object-only detection depends on operator-supplied `--object-ref` because the current storage adapter protocol does not list arbitrary final objects.
  - `enable_outbox_dispatcher`, `outbox_max_attempts`, and `outbox_batch_size` settings exist, but no dispatcher/helper behavior exists in this slice.
- Known gaps:
  - Outbox append helper, dispatcher retry, and dead-letter behavior are not implemented.
  - T12 must remain blocked until full T11, including outbox atomicity and dispatcher failure behavior, is implemented and validated.
- Suggested next agent:
  - T11 Workers outbox implementation agent, followed by T11 outbox validation.

## Recovery Notes

- If accepted, next dependency unlocked: T11 workers-outbox implementation slice can start.
- If partial, reusable pieces: not applicable.
- If blocked, unblock condition: not applicable for lifecycle slice.
- If rejected, do not repeat: not applicable.
