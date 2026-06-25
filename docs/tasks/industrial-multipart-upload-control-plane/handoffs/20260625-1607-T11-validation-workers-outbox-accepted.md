# Handoff: T11 Workers Outbox Validation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T11-validation-workers-outbox
Worktree: D:\upload-control-plane-T11-validation-workers-outbox
Started: 2026-06-25 16:02 +08:00 Asia/Shanghai
Finished: 2026-06-25 16:07 +08:00 Asia/Shanghai

## Scope

- Intended scope: independently validate implementation branch `codex/industrial-upload/T11-implementation-workers-outbox` at commit `41f1506a40cb0f3fa3d3c2557b4a3ad9416a8bd2` for the full T11 lifecycle plus workers outbox result.
- Explicitly out of scope: functional code edits, repair work, real MQTT publishing, Go uploader, edge gateway, T12 dataset validation parsing, and T13 metrics/runbooks.
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
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1545-T11-implementation-workers-lifecycle-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1550-T11-validation-workers-lifecycle-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1553-T11-merge-workers-lifecycle-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1602-T11-implementation-workers-outbox-accepted.md`

## Changes

- Files changed by this validation agent:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1607-T11-validation-workers-outbox-accepted.md`
- Behavior changed: none.
- Compatibility notes:
  - Validation was run in a dedicated worktree and branch created from implementation commit `41f1506`.
  - Implementation inspected includes `append_outbox_event`, `OutboxDispatcher`, lifecycle outbox appends, worker CLI integration, and outbox/lifecycle tests.

## Verification

- Commands run:
  - `git worktree add -b codex/industrial-upload/T11-validation-workers-outbox D:\upload-control-plane-T11-validation-workers-outbox 41f1506`: passed.
  - `uv run ruff check src tests`: passed; ruff emitted cache-write access warnings but returned success.
  - `uv run ruff format --check src tests`: passed, `80 files already formatted`.
  - `uv run mypy src tests`: passed, no issues in 80 source files.
  - `uv run pytest tests/application/test_outbox.py tests/application/test_worker_lifecycle.py -q`: passed, `10 passed`.
  - `uv run pytest tests/api/test_upload_session_runtime_api.py tests/api/test_dataset_lifecycle_api.py tests/api/test_device_identity_api.py -q`: passed, `26 passed, 1 warning`.
  - `uv run pytest -q`: passed, `191 passed, 1 warning`.
  - `docker compose config --quiet`: passed.
  - `uv run upload-worker --help`: passed; commands shown: `run-once`, `dispatch-outbox`, `reconcile`, and `run`.
  - `uv run upload-worker dispatch-outbox --help`: passed.
  - `rg -n "UploadFile|File\(|Form\(|request\.body\(|request\.stream\(|Body\(.*bytes|bytes\s*=\s*Body|receive\(|StreamingResponse|FileResponse|/upload-bytes|/file-bytes|/upload-file" src\upload_control_plane\api src\upload_control_plane\main.py`: no matches, exit 1 expected.
  - `rg -n "mqtt|emqx|paho|gmqtt|go/|golang|package main|func main" src tests pyproject.toml docker-compose.yml`: only existing MQTT configuration fields matched; no MQTT client/broker adapter or Go implementation was found.
  - `rg -n "s3_access_key|s3_secret_key|S3_ACCESS_KEY|S3_SECRET_KEY|aws_access_key_id|aws_secret_access_key|minioadmin|MINIO_ROOT_USER|MINIO_ROOT_PASSWORD|raw_credential|credential_secret|device_secret|device_token|X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url" src\upload_control_plane tests\application\test_outbox.py tests\application\test_worker_lifecycle.py`: matches were limited to settings/storage adapter credential use, storage presign calls, CLI redaction constants, dataset download function names, outbox validation constants, and negative outbox tests.
  - `rg -n "bytes|bytearray|memoryview|presigned|credential|credentials|password|secret|private_key|upload_url|download_url|X-Amz" src\upload_control_plane\application\outbox.py tests\application\test_outbox.py`: confirmed outbox rejects bytes, presigned URL material, and credential-like keys; tests cover representative rejection cases.
  - `rg -n "outbox|Outbox|append_outbox|OutboxAppend|OutboxDispatcher|dispatch-outbox|enable_outbox_dispatcher" src\upload_control_plane tests`: confirmed outbox code surface is confined to the helper, dispatcher, lifecycle appends, worker CLI integration, schema model/tests, and no hidden extra adapter.
  - `git diff --check`: passed.
- Results:
  - Full T11 lifecycle plus outbox acceptance is satisfied by the implementation branch.
  - `append_outbox_event()` adds the outbox row to the caller's current SQLAlchemy session without committing, so domain writes and outbox inserts share the surrounding transaction. The atomicity test proves forced rollback removes both rows and successful commit persists both.
  - Delivery failure does not roll back completed domain action. The dispatcher operates after the domain transaction has committed; the focused test proves a committed `Dataset` remains `READY` while the outbox event moves to `FAILED`.
  - Dispatcher safely claims due `PENDING`/`FAILED` events with `FOR UPDATE SKIP LOCKED`, marks them `PROCESSING`, delivers successes as `DELIVERED`, schedules retry failures as `FAILED` with `next_attempt_at` and `last_error`, and marks `DEAD_LETTERED` at `outbox_max_attempts`.
  - Repeated dispatcher runs are idempotent for delivered events; the success test proves a second run claims zero events and does not redeliver.
  - Outbox payload validation rejects file bytes, credential-like keys including raw device-credential-looking names, presigned URL key names, and URL strings containing signature/query material.
  - `upload-worker` exposes lifecycle commands and `dispatch-outbox`; periodic `run` executes dispatcher only when `enable_outbox_dispatcher` is true.
  - Existing lifecycle validation evidence remains intact: expired sessions transition through `EXPIRED -> ABORTING -> ABORTED`, cleanup is retry-safe, completed sessions are not aborted, recycle purge is retention-gated, and recovery reconciliation detects missing, metadata-only, verified, and operator-supplied object-only cases.
  - No real MQTT/Go/edge implementation was introduced. Only existing MQTT settings remain.
- Commands not run and why:
  - No live MQTT broker publishing was run because real MQTT publishing is explicitly out of scope for T11 and remains dependency-gated.
  - No separate live MinIO destructive lifecycle smoke was run; the full suite, focused lifecycle tests, storage/API regressions, and adapter-bound fake storage cover this validation without deleting real local objects.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: accepted. Backend file-byte route scan found no matches, and outbox validation rejects byte payloads.
- Clients receive no MinIO/S3 credentials: accepted. Credential scan found only settings/storage adapter internals and existing redaction/negative-test surfaces, not client-facing exposure.
- Complete uses object storage ListParts as authority: accepted. Completion code was not changed by this slice, and runtime API regression tests passed.
- Authorization uses permission_grants: accepted. Authorization paths were not changed, and upload/session/dataset/device API regressions passed.
- Internal IDs remain UUIDs: accepted. Outbox aggregate IDs use existing UUID model fields and schema tests preserve UUID metadata.
- MQTT/Go/edge remain optional and dependency-gated: accepted. No real MQTT client, Go module, edge gateway, or file-byte broker path was added.
- Presigned URLs are not persisted to outbox: accepted. Outbox helper rejects URL-looking keys and signed query material; hard scans found no outbox persistence of presigned URL material.
- Domain writes and outbox inserts commit atomically: accepted by implementation shape and focused rollback/commit test.
- Outbox delivery failure never rolls back completed domain action: accepted by dispatcher design and focused failure test.

## Risks and Follow-up

- Remaining risks:
  - The dispatcher ships with a logging sink stub; real MQTT/webhook delivery still needs its own adapter, redaction, and failure tests in a later dependency-gated task.
  - `PROCESSING` events are not reclaimed after a worker crash between claim and status update, even though `locked_until` is present. This is acceptable for T11 acceptance but should be tracked for T13/T15 operational hardening.
  - Outbox negative tests use representative payloads rather than an exhaustive table of every forbidden key/string variant; the shared recursive validator covers nested structures and the hard scan found no unsafe producer.
- Known gaps:
  - No outbox metrics or dead-letter replay command; T13 owns metrics/runbooks and replay can be a later operational feature.
- Suggested next agent:
  - Merge Agent can merge full T11 after Master review. T12 can be unlocked only after this full T11 result is accepted by Master and merged.

## Recovery Notes

- If accepted, next dependency unlocked: full T11 is acceptable for merge; T12 remains locked until full T11 is merged.
- If partial, reusable pieces: not applicable.
- If blocked, unblock condition: not applicable.
- If rejected, do not repeat: not applicable.
