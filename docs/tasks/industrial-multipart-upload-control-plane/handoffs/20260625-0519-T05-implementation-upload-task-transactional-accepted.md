# Handoff: T05 upload task transactional creation

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 05:07 +08:00
Finished: 2026-06-25 05:19 +08:00

## Scope

- Intended scope:
  - Replace the stable `501 upload_task.not_implemented` foundation stub with real create-upload-task behavior.
  - Transactionally create UploadTask, UploadObject, Dataset, and UploadSession records for single-file and multi-file requests.
  - Initiate one storage multipart upload per UploadObject through `ObjectStorage`.
  - Persist storage upload IDs, generated object keys, idempotency records, upload events, and audit events.
  - Keep the existing permission-grant-backed authorization gate for `dataset.upload` or `upload.create`.
- Explicitly out of scope:
  - Presign, ack, complete, pause, resume, abort, runtime status, browser uploader, CLI uploader, worker/outbox dispatching, MQTT, Go, or edge work.
  - FastAPI file-byte handling; the endpoint remains JSON metadata only.
  - Real MinIO upload task integration tests; this segment uses fake ObjectStorage for T05 API tests.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0504-T05-merge-upload-task-api-foundation-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`

## Changes

- Files changed:
  - `src/upload_control_plane/api/upload_tasks.py`
  - `src/upload_control_plane/application/upload_tasks.py`
  - `tests/api/test_upload_task_api_foundation.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0519-T05-implementation-upload-task-transactional-accepted.md`
- Behavior changed:
  - `POST /v1/projects/{project_id}/upload-tasks` returns `201 Created` for an authorized seeded actor.
  - Creates UploadTask, per-object Dataset, UploadObject, and UploadSession rows.
  - Calls `ObjectStorage.create_multipart_upload` once per object and stores the returned upload ID.
  - Uses project default storage policy unless an active same-tenant explicit policy is supplied.
  - Generates server-side object keys using tenant/project/dataset/date/session namespace.
  - Implements create idempotency through `idempotency_records`; same key/fingerprint returns the stored response, different fingerprint returns `409`.
  - Adds upload events for task creation and storage initiation plus audit events for creation.
- Compatibility notes:
  - The route still rejects multipart file-byte requests through JSON/Pydantic validation.
  - No public bare UploadSession creation route was added.
  - `get_object_storage` is a FastAPI dependency so tests can inject fake storage without MinIO.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest tests/api/test_upload_task_api_foundation.py -q`
  - `uv run pytest`
  - `make test`
  - `docker compose up -d postgres`
  - `make migrate`
  - `make seed-dev`
  - `uv run pytest tests/api/test_upload_task_api_foundation.py -q`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 65 files already formatted.
  - `uv run mypy src tests`: passed, no issues found in 57 source files.
  - Targeted T05 tests before PostgreSQL startup: 1 passed, 12 skipped, 1 existing Starlette warning.
  - `uv run pytest` before PostgreSQL startup: 127 passed, 17 skipped, 1 existing Starlette warning.
  - `docker compose up -d postgres`: passed; postgres became healthy on `localhost:25432`.
  - `make migrate`: passed.
  - `make seed-dev`: passed; seeded dev key has `project.view`, `dataset.upload`, and `upload.create`.
  - Targeted T05 tests after PostgreSQL startup: 13 passed, 1 existing Starlette warning.
  - `uv run pytest` after PostgreSQL startup: 143 passed, 1 skipped, 1 existing Starlette warning.
  - `make test`: passed, including ruff, format check, mypy, and pytest with 143 passed, 1 skipped, 1 existing Starlette warning.
- Commands not run and why:
  - No real MinIO upload task integration test was added or run. T05 API tests use fake ObjectStorage; existing MinIO storage integration remains separate and skipped unless MinIO is available.
  - `docker compose down` will be run after this handoff is written as the final DB cleanup step.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. The upload task endpoint accepts JSON metadata only and rejects multipart file-byte input.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Creation response returns IDs, bucket, object key, part sizing, and expiry, but no credentials or presigned URLs.
- Complete uses object storage ListParts as authority:
  - Preserved. No complete behavior was added.
- Authorization uses permission_grants:
  - Preserved. The route still re-evaluates `dataset.upload` or `upload.create` via `AuthorizationService`.
- Internal IDs remain UUIDs:
  - Preserved. New task/object/dataset/session IDs are UUIDs.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go, edge, browser, or CLI behavior was added.

## Risks and Follow-up

- Remaining risks:
  - Storage multipart creation and DB commit cannot be perfectly atomic across PostgreSQL and object storage. The implementation creates DB rows, initiates storage, then commits; a future recovery/sweeper agent should handle rare post-storage/pre-commit failures.
  - Quota guard is intentionally minimal: it checks open task count and requested bytes against configured caps before storage calls, but does not yet compute historical or existing storage usage.
  - Explicit storage policy selection validates active same-tenant policy. Fine-grained storage-policy permission checks should be added when storage policy APIs and grants are implemented.
- Known gaps:
  - No outbox event helper/dispatcher behavior; only upload_events and audit_events are written.
  - No real MinIO T05 integration test in this segment.
- Suggested next agent:
  - T05 validation agent should independently verify transactional creation, idempotency, quota no-storage behavior, object key generation, and event rows.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T05 validation can start from this handoff and the updated route/service/tests.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not reintroduce direct file-byte routes.
  - Do not bypass `permission_grants` with API-key scopes.
  - Do not expose a bare UploadSession creation endpoint.
  - Do not use client-supplied filenames as raw object keys.
