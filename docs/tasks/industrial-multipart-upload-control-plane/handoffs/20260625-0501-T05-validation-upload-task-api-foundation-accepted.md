# Handoff: T05 upload task API foundation validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 04:57 +08:00
Finished: 2026-06-25 05:01 +08:00

## Scope

- Intended scope:
  - Independently validate the uncommitted T05 upload task API contract foundation implementation on `main`.
  - Verify route/authz/request-validation/error-shape behavior and confirm this segment is intentionally not full T05 transactional creation.
  - Run the requested quality, test, compose, migration, seed, targeted-test, static `rg`, and cleanup commands.
- Explicitly out of scope:
  - Any implementation, test, config, README, or PRD changes.
  - Repairing issues or expanding the T05 feature scope.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T05 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0456-T05-implementation-upload-task-api-foundation-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md` sections 10, 11, and 13
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `src/upload_control_plane/api/upload_tasks.py`
  - `src/upload_control_plane/application/upload_tasks.py`
  - `tests/api/test_upload_task_api_foundation.py`

## Validation Findings

- Accepted foundation behavior:
  - `src/upload_control_plane/api/upload_tasks.py` registers `POST /v1/projects/{project_id}/upload-tasks`.
  - The route uses existing Bearer API key auth through `require_api_key`.
  - The route enforces `dataset.upload` or `upload.create` on project resources through `AuthorizationService.require_any_permission`.
  - Request schemas are JSON/Pydantic-only and reject extra client-controlled fields.
  - Request validation covers empty object lists, non-positive file sizes, invalid part sizes, unsafe path-traversal names, invalid checksums, and multipart/form-data file-byte attempts.
  - Valid authorized JSON requests reach `UploadTaskCreationService.create_upload_task`, which returns stable `501 upload_task.not_implemented`.
  - Existing error envelope and `X-Request-ID` propagation remain intact in tested auth, validation, authorization, and 501 paths.
- Not full T05:
  - This segment does not create UploadTask, UploadObject, Dataset, UploadSession, UploadPart, idempotency, audit, upload event, or outbox rows.
  - This segment does not initiate MinIO/S3 multipart uploads.
  - This segment does not implement quota checks, storage policy resolution, idempotency persistence, server object-key creation, or response mapping.
- Static hard-constraint checks:
  - `rg -n "UploadFile|\bFile\(|Form\(|multipart|form-data|create_multipart|initiate_multipart|presign|put_object|upload_part|ObjectStorage|storage\." src/upload_control_plane/api src/upload_control_plane/application src/upload_control_plane/main.py tests/api/test_upload_task_api_foundation.py`
    - Only hit: the multipart rejection test in `tests/api/test_upload_task_api_foundation.py`.
  - `rg -n "session\.(add|flush|commit|execute|merge|delete)|insert\(|update\(|delete\(|storage|ObjectStorage|create_multipart|multipart|presign|UploadFile|\bFile\(|Form\(" src/upload_control_plane/api/upload_tasks.py src/upload_control_plane/application/upload_tasks.py`
    - Only hits: `storage_policy_id` field/command plumbing, not storage calls or DB writes.

## Verification

- Commands run:
  - `uv run pytest tests/api/test_upload_task_api_foundation.py -q`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `docker compose config --quiet`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `docker compose up -d postgres`
  - `make migrate`
  - `make seed-dev`
  - `uv run pytest tests/api/test_upload_task_api_foundation.py -q`
  - `make test`
  - `docker compose down`
  - Static `rg` checks listed above.
- Results:
  - Initial targeted test before PostgreSQL: `1 passed, 8 skipped, 1 warning`.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, `65 files already formatted`.
  - `docker compose config --quiet`: passed.
  - `uv run mypy src tests`: passed, `Success: no issues found in 57 source files`.
  - Initial `uv run pytest` before PostgreSQL: `127 passed, 13 skipped, 1 warning`.
  - `docker compose up -d postgres`: passed; postgres became healthy before DB-backed targeted tests.
  - `make migrate`: passed.
  - `make seed-dev`: passed; seeded `project.view`, `dataset.upload`, and `upload.create`.
  - DB-backed targeted upload task API foundation tests: `9 passed, 1 warning`.
  - `make test`: passed, including ruff, format check, mypy, and pytest with `139 passed, 1 skipped, 1 warning`.
  - `docker compose down`: passed and removed postgres container/network.
- Commands not run and why:
  - No MinIO-specific integration command was added beyond the requested commands. The one skipped `make test` item is the existing MinIO integration test because the requested service startup was only `docker compose up -d postgres`.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. The route is JSON/Pydantic-only; multipart/form-data input is rejected and tested. No MQTT behavior exists in this segment.
- Clients receive no MinIO/S3 credentials:
  - Preserved. The endpoint currently returns only stable error envelopes and exposes no storage credentials or presigned URLs.
- Complete uses object storage ListParts as authority:
  - Preserved. No complete behavior was added.
- Authorization uses permission_grants:
  - Preserved. Route authorization uses the existing permission-grant-backed `AuthorizationService` and requires `dataset.upload` or `upload.create`.
- Internal IDs remain UUIDs:
  - Preserved. Path and optional request IDs use UUID types; no human-readable key replaces internal IDs.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go, edge, browser, or CLI behavior was added.

## Risks and Follow-up

- Remaining risks:
  - This is an accepted foundation segment, not a complete T05 implementation.
  - The route currently returns `501 upload_task.not_implemented` for valid authorized requests.
  - Idempotency key, source device, storage policy, quota, object-key generation, audit/events, DB transactionality, and storage multipart initiation remain for the next T05 segment.
- Known gaps:
  - No successful `201 Created` contract yet.
  - No transactional persistence or rollback behavior yet.
  - No storage-side multipart initiation/no-leak proof beyond the current no-call foundation.
- Suggested next agent:
  - T05 transactional creation implementation agent after this foundation segment is merged.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Merge of this foundation can proceed.
  - After merge, the next T05 transactional creation agent can start from `UploadTaskCreationService.create_upload_task` and replace the explicit 501 with DB transaction, idempotency, quota-before-storage, policy selection, server object keys, storage multipart initiation, audit/events, and response mapping.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
