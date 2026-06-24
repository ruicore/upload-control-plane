# Handoff: T05 upload task API foundation merge

Status: accepted
Agent type: Merge
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 05:02 +08:00
Finished: 2026-06-25 05:07 +08:00

## Scope

- Intended scope:
  - Commit the accepted T05 upload task API foundation implementation, tests, and implementation/validation handoffs on `main`.
  - Preserve the explicit boundary that this foundation segment registers and validates the API contract but does not implement transactional creation.
  - Run the requested post-commit validation commands and record results.
- Explicitly out of scope:
  - Transactional creation of UploadTask, UploadObject, Dataset, UploadSession, UploadPart, idempotency, audit, events, or outbox rows.
  - Storage multipart initiation, presigned URLs, complete/ack/pause/resume/abort behavior, browser upload, CLI upload, MQTT, Go, or edge work.
  - Any repair or semantic changes beyond committing the already accepted foundation segment and this merge handoff.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0456-T05-implementation-upload-task-api-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0501-T05-validation-upload-task-api-foundation-accepted.md`

## Changes

- Files changed:
  - `src/upload_control_plane/api/errors.py`
  - `src/upload_control_plane/main.py`
  - `src/upload_control_plane/api/upload_tasks.py`
  - `src/upload_control_plane/application/__init__.py`
  - `src/upload_control_plane/application/upload_tasks.py`
  - `tests/api/test_upload_task_api_foundation.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0456-T05-implementation-upload-task-api-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0501-T05-validation-upload-task-api-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0504-T05-merge-upload-task-api-foundation-accepted.md`
- Behavior changed:
  - `POST /v1/projects/{project_id}/upload-tasks` is registered.
  - The route requires Bearer API key authentication and `dataset.upload` or `upload.create` project permission.
  - Valid metadata-only JSON requests reach `UploadTaskCreationService.create_upload_task` and return stable `501 upload_task.not_implemented`.
  - Multipart/form-data file-byte requests are rejected by request validation.
  - Error response details are JSON-encoded before response construction.
- Compatibility notes:
  - No database writes are introduced by this T05 foundation segment.
  - No storage adapter or multipart operation is called by this T05 foundation segment.
  - No public UploadSession creation route is introduced.

## Merge Record

- Implementation/validation commit:
  - `b80ffd0 T05 upload task API foundation accepted`
- Merge handoff commit:
  - Recorded separately after validation evidence was added.
- Conflict handling:
  - No merge conflict handling was required. The accepted segment was already present as uncommitted work on `main`.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up -d postgres`
  - `make migrate`
  - `make seed-dev`
  - `uv run pytest tests/api/test_upload_task_api_foundation.py -q`
  - `docker compose down`
  - `rg -n "UploadFile|\bFile\(|Form\(|multipart|form-data|create_multipart|initiate_multipart|presign|put_object|upload_part|ObjectStorage|storage\." src/upload_control_plane/api src/upload_control_plane/application src/upload_control_plane/main.py tests/api/test_upload_task_api_foundation.py`
  - `rg -n "session\.(add|flush|commit|execute|merge|delete)|insert\(|update\(|delete\(|storage|ObjectStorage|create_multipart|multipart|presign|UploadFile|\bFile\(|Form\(" src/upload_control_plane/api/upload_tasks.py src/upload_control_plane/application/upload_tasks.py`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 65 files already formatted.
  - `uv run mypy src tests`: passed, no issues found in 57 source files.
  - `uv run pytest`: passed, 127 passed, 13 skipped, 1 existing Starlette TestClient warning before PostgreSQL startup.
  - `make test`: passed, including ruff, format check, mypy, and pytest with 127 passed, 13 skipped, 1 existing Starlette TestClient warning before PostgreSQL startup.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed.
  - `make seed-dev`: passed; dev seed includes `project.view`, `dataset.upload`, and `upload.create`.
  - DB-backed targeted upload task API tests: 9 passed, 1 existing Starlette TestClient warning.
  - `docker compose down`: passed and removed the postgres container and compose network.
  - Static `rg` file-byte/storage scan: only hit the multipart rejection test in `tests/api/test_upload_task_api_foundation.py`.
  - Static `rg` route/application DB-write/storage scan: only hit `storage_policy_id` field and command plumbing, not DB writes, storage adapter calls, multipart calls, presign calls, or FastAPI file/form parameters.
- Commands not run and why:
  - No additional MinIO-specific integration command was run. This foundation segment intentionally does not call MinIO/S3, and the requested service startup was PostgreSQL only.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. The new route uses Pydantic JSON request models and rejects multipart file-byte input.
- Clients receive no MinIO/S3 credentials:
  - Preserved. No storage credentials or presigned URLs are returned.
- Complete uses object storage ListParts as authority:
  - Preserved. No complete behavior was added.
- Authorization uses permission_grants:
  - Preserved. The route delegates authorization to the existing permission-grant-backed authorization service.
- Internal IDs remain UUIDs:
  - Preserved. Project and optional request identifiers are UUID-typed.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go, edge, browser, or CLI behavior was added.

## Risks and Follow-up

- Remaining risks:
  - This accepted checkpoint is intentionally not complete T05. Valid authorized requests still return `501 upload_task.not_implemented`.
  - Idempotency persistence, quota-before-storage, policy selection, server object key generation, transactional DB writes, storage multipart initiation, audit/events, and response mapping remain unimplemented.
- Known gaps:
  - No successful `201 Created` upload task response yet.
  - No rollback semantics or no-leak proof for storage initiation yet because storage is not called at all in this segment.
- Suggested next agent:
  - T05 transactional creation implementation agent after this merge handoff is committed and validation remains green.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The next T05 transactional creation agent can start from `UploadTaskCreationService.create_upload_task`.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not implement transactional creation inside this merge pass.
  - Do not bypass permission grants with API key scopes.
  - Do not accept file bytes through FastAPI.
  - Do not expose bare UploadSession creation.
