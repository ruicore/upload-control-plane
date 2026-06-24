# Handoff: T06 runtime status/presign/ack/parts implementation

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 05:30 +08:00
Finished: 2026-06-25 05:45 +08:00

## Scope

- Intended scope:
  - Implement the first T06 Upload Session Runtime API segment:
    - `GET /v1/uploads/{session_id}`
    - `POST /v1/uploads/{session_id}/parts/presign`
    - `POST /v1/uploads/{session_id}/parts/ack`
    - `GET /v1/uploads/{session_id}/parts`
  - Re-evaluate Bearer API-key authentication and permission grants on every request.
  - Use DB-backed upload sessions created through T05 upload task creation in API tests.
  - Use fake `ObjectStorage` for runtime API tests.
- Explicitly out of scope and not implemented:
  - `complete`, `abort`, `pause`, `resume`, and extend-expiry runtime actions.
  - Browser/CLI uploader behavior.
  - Worker cleanup.
  - File-byte proxy routes or FastAPI file/form upload routes.
  - Completion from DB ack state.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T06 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0530-T05-merge-upload-task-creation-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md` upload session / upload part sections
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md` sections 12.1-12.4 and part sizing rules
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md` upload_sessions / upload_parts sections
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - Current T05 upload task API/application service, storage adapter, DB models, and authorization helpers.

## Changes

- Added `src/upload_control_plane/application/upload_sessions.py`.
  - Loads tenant-owned upload sessions.
  - Computes DB status progress from `upload_parts`.
  - Presigns requested part numbers through `ObjectStorage.presign_upload_part`.
  - Upserts `upload_parts` rows with `last_presigned_at` and `presign_expires_at` without persisting presigned URLs.
  - Rejects presign for non-presignable states, including `PAUSED`, `COMPLETING`, `COMPLETED`, `ABORTING`, `ABORTED`, and `FAILED`.
  - Acknowledges uploaded parts with idempotent upsert/update semantics.
  - Keeps ack as progress only; it does not mark sessions completed or set final object metadata.
  - Implements `source=db`, `source=storage`, and `source=reconcile` list-parts behavior. `storage` returns observed parts without DB writes; `reconcile` writes storage-observed uploaded parts back to DB.
- Added `src/upload_control_plane/api/upload_sessions.py`.
  - Exposes the four T06 first-segment routes.
  - Uses Bearer auth via existing `require_api_key`.
  - Re-resolves the upload session and re-checks permission grants on each request.
  - Sets `Cache-Control: no-store` on presign responses.
  - Accepts part-number list or range presign requests.
- Updated `src/upload_control_plane/main.py`.
  - Registers the upload session runtime router.
- Added `tests/api/test_upload_session_runtime_api.py`.
  - Creates sessions through the T05 upload task API before exercising runtime endpoints.
  - Covers status, presign metadata, ack idempotency, DB list, paused presign rejection, permission re-evaluation, tenant isolation, storage list, and reconcile list.

## Authorization Choices

- Current dev seed and existing permission grants include:
  - `project.view`
  - `dataset.upload`
  - `upload.create`
- This segment therefore uses the current executable permission model:
  - `GET /v1/uploads/{session_id}` requires `project.view` on the dataset/project authorization target.
  - `GET /v1/uploads/{session_id}/parts` requires `project.view` on the dataset/project authorization target.
  - `POST /v1/uploads/{session_id}/parts/presign` requires `dataset.upload` or `upload.create`.
  - `POST /v1/uploads/{session_id}/parts/ack` requires `dataset.upload` or `upload.create`.
- PRD `09-security-governance.md` recommends a dedicated `upload.presign`; this code does not pretend that seed/migrations already grant it. A later authorization hardening segment can add seeded `upload.presign` and switch presign to that dedicated permission.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose up -d postgres`
  - `make migrate`
  - `make seed-dev`
  - `uv run pytest tests/api/test_upload_session_runtime_api.py -q`
  - `docker compose down`
  - `rg -n "UploadFile|\bFile\(|Form\(|/complete|/pause|/resume|/abort|parts/presign|parts/ack|/v1/uploads" src tests`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 68 files already formatted.
  - `uv run mypy src tests`: passed, no issues found in 60 source files.
  - `uv run pytest`: passed with 127 passed, 22 skipped, 1 existing Starlette TestClient warning.
  - `make test`: passed, including ruff, format check, mypy, and pytest with 127 passed, 22 skipped, 1 existing Starlette TestClient warning.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed.
  - `make seed-dev`: passed; seed still grants `project.view`, `dataset.upload`, and `upload.create`.
  - Targeted T06 DB-backed tests: passed with 5 passed, 1 existing Starlette TestClient warning.
  - `docker compose down`: passed and removed the postgres container and compose network.
  - Route/file-byte scan found only the intended `/v1/uploads`, `parts/presign`, and `parts/ack` matches. No `UploadFile`, FastAPI `File(...)`, `Form(...)`, `/complete`, `/pause`, `/resume`, or `/abort` matches were found in `src` or `tests`.

## PRD Hard Constraints Check

- Backend receives no file bytes:
  - Preserved. Runtime routes accept JSON metadata only and return presigned URLs for direct client-to-storage PUT.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Only scoped presigned PUT URLs are returned.
- Full presigned URLs are not logged or persisted:
  - Preserved. DB rows store part numbers and expiry timestamps only.
- Complete is not derived from DB ack:
  - Preserved. Ack updates progress rows only and does not mark session completion or final object metadata.
- Presign rejects paused and terminal/invalid states:
  - Implemented and tested for `PAUSED`; state guard also rejects the non-presignable states defined by the state machine.
- Parts list supports DB and storage reconciliation:
  - Implemented for `source=db`, `source=storage`, and `source=reconcile`.
- Authorization is re-evaluated on every request:
  - Implemented in the API layer and tested by revoking current effective upload permissions after T05 task creation.

## Remaining Lifecycle Work

- Not included in this first T06 segment:
  - `POST /v1/uploads/{session_id}/pause`
  - `POST /v1/uploads/{session_id}/resume`
  - `POST /v1/uploads/{session_id}/complete`
  - `POST /v1/uploads/{session_id}/abort`
  - Idempotency records for lifecycle actions.
  - Session-level locking for lifecycle transitions.
  - Storage-authoritative complete and `409 upload.missing_parts`.
- Suggested next segment:
  - Implement lifecycle actions using `SELECT ... FOR UPDATE` or an equivalent session lock.
  - Add dedicated `upload.presign` permission seeding/migration if the authorization contract is ready to move from the current T05-compatible permission set.
