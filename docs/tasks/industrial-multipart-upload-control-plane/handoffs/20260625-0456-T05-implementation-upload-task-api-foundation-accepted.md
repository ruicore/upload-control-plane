# Handoff: T05 upload task API foundation

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 04:50 +08:00
Finished: 2026-06-25 04:56 +08:00

## Scope

- Intended scope:
  - Establish the public `POST /v1/projects/{project_id}/upload-tasks` route contract.
  - Add Pydantic request/response schemas for the PRD upload task creation shape.
  - Reuse existing Bearer API key auth and `dataset.upload` or `upload.create` project permission gate.
  - Add an application service entrypoint for create upload task.
  - Validate metadata-only JSON request shape, object count, positive file size, part sizing, checksums, and unsafe/path-traversal names.
  - Keep the endpoint intentionally non-persistent by returning stable `501 upload_task.not_implemented`.
- Explicitly out of scope:
  - Transactional creation of UploadTask, UploadObject, Dataset, UploadSession, UploadPart, audit, upload events, outbox, or idempotency rows.
  - MinIO/S3 multipart initiation.
  - Quota checks beyond request-level validation.
  - Presign, ack, complete, pause, resume, abort, retry, status, browser, or CLI upload behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0449-T04-merge-storage-adapter-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - Current API auth/authorization/projects modules, domain part/object-key helpers, storage protocol, and DB models.

## Changes

- Files changed:
  - `src/upload_control_plane/application/__init__.py`
  - `src/upload_control_plane/application/upload_tasks.py`
  - `src/upload_control_plane/api/upload_tasks.py`
  - `src/upload_control_plane/api/errors.py`
  - `src/upload_control_plane/main.py`
  - `tests/api/test_upload_task_api_foundation.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0456-T05-implementation-upload-task-api-foundation-accepted.md`
- Behavior changed:
  - Registered `POST /v1/projects/{project_id}/upload-tasks`.
  - The route requires Bearer API key authentication.
  - The route requires `dataset.upload` or `upload.create` effective permission on the project.
  - Valid authorized metadata-only JSON requests reach `UploadTaskCreationService.create_upload_task` and currently return `501 upload_task.not_implemented`.
  - Invalid requests return the existing stable `request.validation_failed` error envelope.
  - Multipart/form-data file-byte input is rejected before the application service.
  - Error response details are now passed through `jsonable_encoder` so Pydantic validation details containing `ValueError` or raw bytes remain serializable.
- Compatibility notes:
  - No DB rows are created by the new route.
  - No storage adapter method is called by the new route.
  - No endpoint accepts `UploadFile`, `File`, request streams, or backend file-byte proxy behavior.

## Verification

- Commands run:
  - `uv run pytest tests\api\test_upload_task_api_foundation.py -q` before PostgreSQL startup
  - `docker compose up -d postgres`
  - `make migrate`
  - `make seed-dev`
  - `uv run pytest tests\api\test_upload_task_api_foundation.py -q`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
- Results:
  - Pre-DB target test: 1 passed, 8 skipped, 1 existing Starlette TestClient warning.
  - PostgreSQL startup: passed.
  - `make migrate`: passed.
  - `make seed-dev`: passed; dev seed includes `project.view`, `dataset.upload`, and `upload.create`.
  - DB-backed target test: 9 passed, 1 existing Starlette TestClient warning.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 65 files already formatted.
  - `uv run mypy src tests`: passed, no issues found in 57 source files.
  - `uv run pytest`: passed, 139 passed, 1 skipped, 1 existing Starlette TestClient warning. The skipped test is the existing MinIO integration test because only PostgreSQL was started for T05 permission tests.
  - `make test`: passed, repeating ruff, format check, mypy, and pytest with 139 passed, 1 skipped, 1 existing warning.
- Commands not run and why:
  - No MinIO-specific targeted integration run was required for this API foundation segment because it intentionally does not call storage multipart initiation.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. The new route accepts a Pydantic JSON body only; multipart file input is rejected and tested.
- Clients receive no MinIO/S3 credentials:
  - Preserved. The route returns only a 501 error for valid requests and exposes no storage credentials.
- Complete uses object storage ListParts as authority:
  - Preserved. No complete behavior was added.
- Authorization uses permission_grants:
  - Preserved. The route uses `AuthorizationService.require_any_permission` over permission grants.
- Internal IDs remain UUIDs:
  - Preserved. Path and schema IDs are UUIDs; no human-readable key is used as an internal primary key.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go, edge, browser, or CLI behavior was added.

## Risks and Follow-up

- Remaining risks:
  - This is not full T05. It only establishes route/schema/authz/request validation/application entrypoint.
  - Idempotency key is accepted and passed into the command but not persisted.
  - `source_device_id` is accepted as UUID shape but device existence/tenant visibility is not yet enforced.
  - `storage_policy_id` is accepted as UUID shape but policy selection/authorization is not yet enforced.
  - Maximum objects per task is only constrained to at least one object; no configured upper bound exists yet in settings.
- Known gaps:
  - No UploadTask, UploadObject, Dataset, UploadSession, UploadPart, idempotency, audit, upload event, or outbox writes.
  - No storage multipart upload creation or storage upload ID persistence.
  - No quota, retention, policy, device, or content-type policy enforcement beyond request shape.
- Suggested next agent:
  - T05 transactional creation agent: implement DB transaction, idempotency persistence/fingerprint, quota-before-storage, storage policy selection, server object keys, one multipart initiation per object, and response mapping.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The next T05 segment can start from `UploadTaskCreationService.create_upload_task` and replace the stable 501 with transactional behavior.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not bypass `permission_grants` with API key scopes.
  - Do not accept file bytes through FastAPI.
  - Do not create bare public UploadSession endpoints.
  - Do not let clients supply final object keys.
