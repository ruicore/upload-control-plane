# Handoff: T05 upload task creation validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 05:20 +08:00
Finished: 2026-06-25 05:24 +08:00

## Scope

- Intended scope:
  - Independently validate complete T05 Upload Task Creation currently present as uncommitted work on `main`.
  - Verify the former 501 foundation stub is replaced for valid seeded actors.
  - Verify authz, transactional DB creation, storage multipart initiation, idempotency, validation/quota-before-storage, generated object keys, event/audit rows, and absence of forbidden runtime/file-byte endpoints.
- Explicitly out of scope:
  - Any implementation, test, config, README, or PRD edits.
  - Presign, ack, complete, pause, resume, abort, browser, CLI, MQTT, Go, worker, lifecycle, and outbox dispatch implementation.
  - Real MinIO T05 test authoring.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0504-T05-merge-upload-task-api-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0519-T05-implementation-upload-task-transactional-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `src/upload_control_plane/api/upload_tasks.py`
  - `src/upload_control_plane/application/upload_tasks.py`
  - `tests/api/test_upload_task_api_foundation.py`

## Validation Findings

- `POST /v1/projects/{project_id}/upload-tasks` no longer returns the 501 stub for a valid seeded actor. DB-backed targeted tests return `201 Created`.
- Bearer auth is required, and the route uses permission-grant-backed `AuthorizationService.require_any_permission` for `dataset.upload` or `upload.create`.
- Single-file creation persists UploadTask, UploadObject, Dataset, and UploadSession rows.
- Multi-file creation creates one UploadObject and one UploadSession per object.
- Storage multipart initiation is called once per object through `ObjectStorage.create_multipart_upload`, and returned storage upload IDs are persisted on upload_sessions.
- Same idempotency key plus same fingerprint returns the stored task response without another storage call; same key plus different fingerprint returns `409 idempotency.key_reused_with_different_request`.
- Pydantic validation rejects invalid request shapes before storage calls. The service also performs minimal quota checks before storage calls: object count, open task count, requested project bytes, and requested tenant bytes.
- Object keys are server-generated with tenant/project/dataset/date/session namespace and do not start with raw client object names. Client storage keys are rejected as extra JSON fields.
- No bare public UploadSession creation route exists.
- No T06 runtime endpoint was added for presign, ack, complete, pause, resume, or abort.
- No endpoint accepts file bytes. The upload task route remains JSON metadata only; multipart file-byte input is rejected.
- Audit/upload events are implemented for T05 creation: `upload_task.created`, `upload_session.storage_initiated`, and `upload_task.create` audit rows are asserted in DB-backed tests.

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
  - `rg -n "@router\.(get|post|put|patch|delete)|add_api_route|APIRouter|UploadFile|\bFile\(|Form\(|files=|multipart|form-data|/v1/uploads|parts/presign|parts/ack|/complete|/pause|/resume|/abort" src tests`
  - `rg -n "upload_session|UploadSession|/v1/uploads|parts/presign|parts/ack|complete|pause|resume|abort|UploadFile|\bFile\(|Form\(" src\upload_control_plane\api src\upload_control_plane\application`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 65 files already formatted.
  - `uv run mypy src tests`: passed, no issues found in 57 source files.
  - `uv run pytest` before PostgreSQL startup: passed with 127 passed, 17 skipped, 1 Starlette TestClient warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed.
  - `make seed-dev`: passed; seed includes `project.view`, `dataset.upload`, and `upload.create`.
  - `uv run pytest tests/api/test_upload_task_api_foundation.py -q`: passed with 13 passed, 1 Starlette TestClient warning.
  - One parallel full-pytest attempt run at the same time as targeted T05 tests failed because the tests share deterministic idempotency keys and cleanup affected `before_count`/`after_count`. The same full suite was rerun serially immediately afterward and passed.
  - Serial `uv run pytest` after PostgreSQL startup: passed with 143 passed, 1 skipped, 1 Starlette TestClient warning.
  - `make test`: passed, including ruff, format check, mypy, and pytest with 143 passed, 1 skipped, 1 Starlette TestClient warning.
  - Static route/file-byte scans found only expected adapter/domain/test symbols and the one `POST /v1/projects/{project_id}/upload-tasks` API route; no public `/v1/uploads/*` runtime routes and no FastAPI `UploadFile`, `File`, or `Form` endpoint parameters were found.
  - `docker compose down`: run as final cleanup.
- Commands not run and why:
  - No T05 real MinIO task-creation integration was run. T04 already validates the adapter against MinIO, and T05 tests use fake `ObjectStorage` to verify application transaction semantics without adding tests or code.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. T05 accepts JSON metadata only and rejects multipart form file input.
- Clients receive no MinIO/S3 credentials:
  - Preserved. T05 returns task/object/dataset/session identifiers, bucket, object key, part sizing, and expiry only; no credentials or presigned URLs.
- Complete uses object storage ListParts as authority:
  - Preserved by absence. T05 does not implement complete.
- Authorization uses permission_grants:
  - Preserved. The route delegates to the existing permission-grant-backed authorization service and requires `dataset.upload` or `upload.create`.
- Internal IDs remain UUIDs:
  - Preserved. Task/object/dataset/session IDs are UUIDs; storage upload ID, object key, and idempotency key are not used as internal primary keys.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go, edge, browser, or CLI behavior was added.

## Risks and Follow-up

- Remaining risks:
  - Storage multipart creation and PostgreSQL commit are not strictly atomic across systems. A storage upload can theoretically be created before a later DB commit failure; T11 recovery/cleanup should reconcile and abort abandoned multipart uploads.
  - Quota protection is intentionally minimal. It is acceptable for T05 because it runs before storage initiation and covers object count, open task count, and configured requested-byte caps. It does not yet compute historical tenant/project storage usage.
  - T05 has no real MinIO upload-task integration test. This is acceptable for the current segment because T04 already validates the MinIO adapter, T05 depends on the `ObjectStorage` interface, and the T05 acceptance target is creation semantics. A future integration smoke can combine T05 with MinIO before production hardening.
  - Outbox event rows are not written by this T05 segment. This is acceptable because T11 owns workers/outbox automation; T05 writes upload_events and audit_events as required for the current creation segment.
- Known gaps:
  - No T06 runtime APIs exist yet, so clients still cannot presign/ack/complete created sessions.
  - No storage cleanup path exists yet for post-storage/pre-commit failure or abandoned T05 sessions.
- Suggested next agent:
  - T05 Merge Agent can commit this accepted T05 transactional creation segment and this validation handoff.
  - After T05 merge/final review, T06 Upload Session Runtime API can unlock.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T05 can merge/finalize. T06 can start after merge and final review.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not add presign/ack/complete/pause/resume/abort while merging T05.
  - Do not add file-byte routes or backend upload proxy behavior.
  - Do not expose bare UploadSession creation.
  - Do not replace permission-grant authorization with API key scopes.
