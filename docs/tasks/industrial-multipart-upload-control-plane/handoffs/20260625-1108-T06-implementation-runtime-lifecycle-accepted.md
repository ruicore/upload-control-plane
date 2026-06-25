# Handoff: T06 runtime lifecycle actions

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T06-implementation-runtime-lifecycle
Worktree: D:\upload-control-plane-T06-implementation-runtime-lifecycle
Started: 2026-06-25 10:00 +08:00
Finished: 2026-06-25 11:08 +08:00

## Scope

- Intended scope:
  - Implement `POST /v1/uploads/{session_id}/pause`.
  - Implement `POST /v1/uploads/{session_id}/resume`.
  - Implement `POST /v1/uploads/{session_id}/complete`.
  - Implement `POST /v1/uploads/{session_id}/abort`.
  - Add lifecycle idempotency through `Idempotency-Key`.
  - Add PostgreSQL row-lock based session-level lifecycle concurrency protection.
  - Complete multipart uploads from storage `ListParts`, not DB ack rows.
  - Return stable `409 upload.missing_parts` when storage parts are missing or invalid.
  - Test lifecycle permission re-evaluation and tenant isolation.
- Explicitly out of scope:
  - Browser uploader, Python CLI, dataset lifecycle APIs, workers, validation worker, observability, MQTT, Go uploader, Go gateway.
  - Any file-byte proxy endpoint.
  - Relaxing authorization or storage-authoritative completion.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T06 section.
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`.
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0948-master-handoff-after-T06-presign-ack.md`.
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0558-T06-merge-runtime-presign-ack-accepted.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`.

## Changes

- Files changed:
  - `src/upload_control_plane/application/upload_sessions.py`
  - `src/upload_control_plane/api/upload_sessions.py`
  - `src/upload_control_plane/infrastructure/db/seed.py`
  - `tests/api/test_upload_session_runtime_api.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1108-T06-implementation-runtime-lifecycle-accepted.md`
- Behavior changed:
  - Added pause/resume/complete/abort runtime routes under `/v1/uploads/{session_id}`.
  - Added lifecycle response models and strict request validation.
  - Lifecycle routes re-load the session under the actor tenant before permission checks and use action-specific permission codes:
    - `upload.pause`
    - `upload.resume`
    - `upload.complete`
    - `upload.abort`
  - Dev seed now grants these lifecycle permissions to the seeded API key and device subjects.
  - Lifecycle state changes use `SELECT ... FOR UPDATE` row locks for transition checks.
  - Pause stores `paused_at` and `pause_reason` in session metadata and blocks later presign through the existing state guard.
  - Resume clears pause metadata and returns clients to the normal reconcile/presign path.
  - Complete sets `COMPLETING`, calls storage `ListParts`, validates expected part numbers and sizes, then calls storage `complete_multipart_upload` with storage-observed ETags only.
  - Missing or invalid storage parts restore the session to `UPLOADING` or back to `PAUSED` when complete was attempted from paused state, reconcile observed parts, and return `409 upload.missing_parts`.
  - Complete marks session/object/task/dataset metadata after storage success without treating upload `COMPLETED` as dataset `READY`.
  - Abort transitions through `ABORTING`, calls storage abort, then marks `ABORTED`; already `ABORTED` is idempotent and already `COMPLETED` returns conflict without storage abort.
- Compatibility notes:
  - Existing status, presign, ack, and parts list response shapes are preserved except `paused_at`/`pause_reason` can now be non-null after pause.
  - Dev seed permission count increases because lifecycle permissions are now explicit.

## Verification

- Commands run:
  - `git fetch origin main`
  - `git worktree add -b codex/industrial-upload/T06-implementation-runtime-lifecycle ..\upload-control-plane-T06-implementation-runtime-lifecycle origin/main`
  - `uv run ruff check src/upload_control_plane/application/upload_sessions.py src/upload_control_plane/api/upload_sessions.py src/upload_control_plane/infrastructure/db/seed.py tests/api/test_upload_session_runtime_api.py`
  - `uv run ruff format --check src/upload_control_plane/application/upload_sessions.py src/upload_control_plane/api/upload_sessions.py src/upload_control_plane/infrastructure/db/seed.py tests/api/test_upload_session_runtime_api.py`
  - `uv run pytest tests/api/test_upload_session_runtime_api.py -q` before PostgreSQL was started
  - `docker compose up -d postgres`
  - `make migrate`
  - `make seed-dev`
  - `uv run pytest tests/api/test_upload_session_runtime_api.py -q`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `git diff --check`
  - Route surface scan:
    - `rg -n "@router\\.(get|post|put|patch|delete)|APIRouter\\(|include_router|/pause|/resume|/complete|/abort|parts/presign|parts/ack|/v1/uploads" src/upload_control_plane tests/api/test_upload_session_runtime_api.py`
  - File-byte endpoint marker scan:
    - `rg -n "UploadFile|File\\(|Form\\(|multipart/form-data|files=" src/upload_control_plane`
  - `docker compose down`
- Results:
  - Targeted API tests before PostgreSQL: `11 skipped`, confirming no DB was reachable yet.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed, Alembic applied through `20260624_0005`.
  - `make seed-dev`: passed; seeded permission codes include `project.view`, `dataset.upload`, `upload.create`, `upload.pause`, `upload.resume`, `upload.complete`, and `upload.abort`.
  - `uv run pytest tests/api/test_upload_session_runtime_api.py -q`: passed with `11 passed`, 1 existing Starlette TestClient deprecation warning.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 68 files formatted.
  - `uv run mypy src tests`: passed, no issues in 60 source files.
  - `uv run pytest`: passed with `154 passed, 1 skipped`, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed with ruff, format check, mypy, and pytest; pytest result `154 passed, 1 skipped`, 1 existing Starlette TestClient deprecation warning.
  - `docker compose config --quiet`: passed with no output.
  - `git diff --check`: passed with no output.
  - Route surface scan found the expected runtime routes:
    - `GET /v1/uploads/{session_id}`
    - `POST /v1/uploads/{session_id}/parts/presign`
    - `POST /v1/uploads/{session_id}/parts/ack`
    - `GET /v1/uploads/{session_id}/parts`
    - `POST /v1/uploads/{session_id}/pause`
    - `POST /v1/uploads/{session_id}/resume`
    - `POST /v1/uploads/{session_id}/complete`
    - `POST /v1/uploads/{session_id}/abort`
  - File-byte endpoint marker scan returned no matches.
  - `docker compose down`: passed and removed the PostgreSQL container and compose network.
- Commands not run and why:
  - Real MinIO complete/abort lifecycle integration was not run because this slice uses the existing fake storage API tests and existing MinIO adapter tests; a later Validation agent should decide whether to add full MinIO lifecycle E2E coverage.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. Added JSON control-plane lifecycle routes only. File-byte marker scan returned no matches.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Lifecycle responses return no storage credentials.
- Complete uses object storage ListParts as authority:
  - Implemented. Complete builds final completion parts from storage-observed `ListParts`; DB ack rows alone are rejected when storage lacks parts.
- Authorization uses permission_grants:
  - Preserved. Lifecycle routes require action-specific permission codes through `AuthorizationService` on every request.
- Internal IDs remain UUIDs:
  - Preserved. No schema migration or identifier type change.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go uploader, or gateway work added.

## Risks and Follow-up

- Remaining risks:
  - Full real MinIO API lifecycle E2E for complete/abort should be covered by the next T06 Validation agent or a later integration slice.
  - Storage-complete success followed by DB failure still needs the later repair/reconcile command described in PRD failure modes.
- Known gaps:
  - No browser/CLI UX behavior is implemented; this is intentionally out of scope.
  - No metrics or tracing for lifecycle counters yet; observability is a later task.
- Suggested next agent:
  - T06 Runtime validation agent to independently verify lifecycle behavior, including real storage where appropriate.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T06 lifecycle implementation can proceed to independent validation.
  - T07/T08/T09 should remain blocked until Validation and Master review accept full T06.
- If partial:
  - Not applicable.
- If blocked:
  - Not applicable.
- If rejected:
  - Do not replace storage `ListParts` with DB ack rows for complete; the current tests explicitly protect this constraint.
