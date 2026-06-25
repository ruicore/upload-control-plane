# Handoff: T09 Dataset Lifecycle API

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T09-implementation-dataset-lifecycle-api
Worktree: D:\upload-control-plane-T09-implementation-dataset-lifecycle-api
Started: 2026-06-25 11:47 +08:00
Finished: 2026-06-25 12:37 +08:00

## Scope

- Intended scope:
  - Project-scoped dataset list/search/filter/detail/update APIs.
  - Dataset download URL endpoint using a presigned object URL only.
  - Dataset archive, soft delete, restore, and purge APIs.
  - Tag category and tag CRUD APIs using the existing schema.
  - Dataset exposure checks using dataset status, validation status, and recovery status.
  - Audit events for dataset update/download/archive/delete/restore/purge and purge/download policy denial.
  - Permission grants for dataset lifecycle and tag operations in dev seed.
- Explicitly out of scope:
  - Device credential lifecycle.
  - Validation worker implementation.
  - Dataset preview endpoint.
  - Product UI.
  - Backend file-byte proxying.
- PRD/task files read:
  - docs/tasks/industrial-multipart-upload-control-plane/README.md
  - docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1134-master-handoff-after-T06-lifecycle-accepted.md
  - docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md
  - docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md
  - docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md
  - docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md
  - docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md
  - docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md
  - docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md
  - docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md

## Changes

- Files changed:
  - src/upload_control_plane/api/datasets.py
  - src/upload_control_plane/application/datasets.py
  - src/upload_control_plane/domain/storage.py
  - src/upload_control_plane/infrastructure/storage/s3_minio.py
  - src/upload_control_plane/infrastructure/db/seed.py
  - src/upload_control_plane/main.py
  - tests/api/test_dataset_lifecycle_api.py
  - tests/api/test_project_authorization.py
  - tests/domain/test_storage.py
  - tests/infrastructure/test_s3_storage.py
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1237-T09-implementation-dataset-lifecycle-api-accepted.md
- Behavior changed:
  - Adds `GET /v1/projects/{project_id}/datasets`.
  - Adds `GET/PATCH /v1/projects/{project_id}/datasets/{dataset_id}`.
  - Adds `POST /v1/projects/{project_id}/datasets/{dataset_id}/download-url`.
  - Adds `POST /v1/projects/{project_id}/datasets/{dataset_id}/archive`.
  - Adds `DELETE /v1/projects/{project_id}/datasets/{dataset_id}` for soft delete.
  - Adds `POST /v1/projects/{project_id}/datasets/{dataset_id}/restore`.
  - Adds `DELETE /v1/projects/{project_id}/datasets/{dataset_id}/purge`.
  - Adds `GET/POST/PATCH/DELETE /v1/projects/{project_id}/tag-categories`.
  - Adds `GET/POST/PATCH/DELETE /v1/projects/{project_id}/tags`.
  - Extends the storage adapter with `presign_download_object` and `delete_object`.
  - Extends dev seed permission grants with dataset lifecycle and tag permission codes.
- Compatibility notes:
  - No database migration was needed; current schema already has datasets, tags, audit events, storage policy retention/object-lock fields, and permission grants.
  - `dataset.download` is now in the dev seed, so one existing authorization test was updated to avoid inserting a duplicate allow grant.

## Verification

- Commands run:
  - `git fetch origin`: passed.
  - `git worktree add -b codex/industrial-upload/T09-implementation-dataset-lifecycle-api D:\upload-control-plane-T09-implementation-dataset-lifecycle-api origin/main`: passed.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed.
  - `uv run mypy src tests`: passed.
  - `docker compose config --quiet`: passed.
  - `git diff --check`: passed.
  - `docker compose up -d postgres`: passed.
  - `uv run python scripts/migrate.py`: passed, upgraded through Alembic head `20260624_0005`.
  - `uv run python scripts/seed_dev.py`: passed after rerun; first parallel seed attempt raced before migration completed.
  - `uv run pytest tests/api/test_dataset_lifecycle_api.py -q`: passed, `9 passed`.
  - `uv run pytest tests/domain/test_storage.py tests/infrastructure/test_s3_storage.py tests/infrastructure/test_seed_dev.py -q`: passed, `17 passed`.
  - `uv run pytest`: passed, `163 passed, 1 skipped, 1 warning`.
  - `rg -n "UploadFile|File\(|Form\(|request\.body\(|request\.stream\(" src\upload_control_plane`: no matches, exit code 1.
- Results:
  - Full test suite passes with local Postgres available.
  - The only skipped test is the pre-existing real MinIO integration test because MinIO was not started for this implementation validation.
  - Warning is the pre-existing Starlette `TestClient` deprecation warning.
- Commands not run and why:
  - `docker compose up -d minio minio-init`: not required for T09 API behavior because storage calls are tested through adapter unit tests and API fake storage; full pytest skipped only the existing live MinIO integration.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. No `UploadFile`, `File(...)`, `Form(...)`, `request.body()`, or `request.stream()` route markers in `src/upload_control_plane`.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Download returns only a short-lived presigned GET URL, not storage credentials.
- Complete uses object storage ListParts as authority:
  - Preserved. T09 did not change T06 complete behavior.
- Authorization uses permission_grants:
  - Preserved. All new dataset/tag endpoints use `AuthorizationService` and permission codes backed by `permission_grants`.
- Internal IDs remain UUIDs:
  - Preserved. New route schemas expose UUID IDs and use existing UUID schema columns.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go uploader, or gateway changes.

## Risks and Follow-up

- Remaining risks:
  - The current schema can represent storage-policy legal-hold defaults and object-lock modes, but it has no per-dataset legal hold field. T09 enforces the current storage-policy gates and documents the missing per-dataset control.
  - Purge deletes the storage object via the adapter and clears object metadata, but no outbox event is inserted yet. Outbox automation remains T11 scope.
  - Dataset restore uses `metadata.deleted_from_status` to recover READY vs ARCHIVED because the schema has no dedicated previous-status column.
- Known gaps:
  - No dataset preview API.
  - No batch rename/metadata/tags APIs.
  - Tag delete has no audit event because T09 only required audit for download/delete/restore/purge/policy denial where supported.
- Suggested next agent:
  - Validation agent for T09 dataset lifecycle API.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T10 Device Identity and Device Upload Authorization can start after validation acceptance.
- If partial, reusable pieces:
  - Dataset service/router, storage download/delete protocol, dev seed permissions, and tests are reusable.
- If blocked, unblock condition:
  - None.
- If rejected, do not repeat:
  - Do not add backend file-byte download/proxy routes; download must remain a presigned object URL response.
