# Handoff: T06 runtime presign/ack validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 05:45 +08:00
Finished: 2026-06-25 05:52 +08:00

## Scope

- Intended scope:
  - Independently validate the first T06 runtime segment already present on `main`:
    - `GET /v1/uploads/{session_id}`
    - `POST /v1/uploads/{session_id}/parts/presign`
    - `POST /v1/uploads/{session_id}/parts/ack`
    - `GET /v1/uploads/{session_id}/parts`
  - Verify route boundary, auth, presign, ack, and list-parts behavior.
- Explicitly out of scope:
  - Modifying implementation, tests, config, README, or PRD.
  - Validating full T06 lifecycle actions as complete.
  - Adding pause/resume/complete/abort implementation.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T06 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0545-T06-implementation-runtime-presign-ack-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md` sections 12.1-12.4
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md` presigned URL/security sections
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md` resume/list-parts notes
  - `src/upload_control_plane/api/upload_sessions.py`
  - `src/upload_control_plane/application/upload_sessions.py`
  - `tests/api/test_upload_session_runtime_api.py`

## Validation Findings

- Route boundary:
  - Accepted. The runtime router exposes only:
    - `GET /v1/uploads/{session_id}`
    - `POST /v1/uploads/{session_id}/parts/presign`
    - `POST /v1/uploads/{session_id}/parts/ack`
    - `GET /v1/uploads/{session_id}/parts`
  - No runtime pause/resume/complete/abort route was added in this segment.
- Auth and permission re-evaluation:
  - Accepted. All runtime endpoints use Bearer auth through `require_api_key`.
  - Each request reloads the session, checks tenant ownership, and re-runs permission checks through `AuthorizationService`.
  - Current executable permission set remains `project.view`, `dataset.upload`, and `upload.create`; dedicated `upload.presign` remains a later hardening gap noted by the implementation handoff.
- Presign:
  - Accepted. Presign rejects `PAUSED` and other non-presignable states through `can_presign`.
  - It bounds expiry by settings, returns `Cache-Control: no-store`, stores only `last_presigned_at` and `presign_expires_at`, and does not persist full presigned URLs.
- Ack:
  - Accepted. Ack upserts part rows idempotently, updates progress, and does not mark the upload/session completed.
  - Tests verify repeated ack leaves `uploaded_part_count` stable and `completed_at`/`object_etag` unset.
- Parts list:
  - Accepted. `source=db` uses local ack state.
  - `source=storage` and `source=reconcile` call the `ObjectStorage.list_parts` boundary.
  - `source=storage` returns observed storage parts without DB writes; `source=reconcile` writes storage-observed uploaded parts back to DB.
  - DB ack is not used as completion proof in this segment.
- File bytes and credentials:
  - Accepted. Runtime endpoints accept JSON metadata only; no `UploadFile`, FastAPI `File(...)`, `Form(...)`, or multipart form endpoint was found.
  - Clients receive presigned PUT URLs only. No MinIO/S3 access key or secret key is exposed by the runtime API.

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
  - `uv run pytest tests/api/test_upload_session_runtime_api.py -q`
  - `docker compose down`
  - `rg -n "@router\\.(get|post|put|patch|delete)|APIRouter\\(|include_router|/pause|/resume|/complete|/abort|parts/presign|parts/ack|/v1/uploads" src/upload_control_plane tests/api/test_upload_session_runtime_api.py`
  - `rg -n "UploadFile|\\bFile\\(|Form\\(|bytes\\s*=|Body\\(|multipart/form-data|presigned_url|presigned_urls|presign_url|full_url|X-Amz|secret_key|access_key|MINIO|S3" src/upload_control_plane tests/api/test_upload_session_runtime_api.py docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0545-T06-implementation-runtime-presign-ack-accepted.md`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 68 files already formatted.
  - `uv run mypy src tests`: passed, no issues found in 60 source files.
  - `uv run pytest`: passed with 127 passed, 22 skipped, 1 Starlette TestClient deprecation warning.
  - `make test`: passed; includes ruff, format check, mypy, and pytest with 127 passed, 22 skipped, 1 Starlette TestClient deprecation warning.
  - `docker compose config --quiet`: passed with no output.
  - `docker compose up -d postgres`: passed, postgres container started.
  - `make migrate`: passed.
  - `make seed-dev`: passed; seeded deterministic dev data and permission codes `project.view`, `dataset.upload`, `upload.create`.
  - `uv run pytest tests/api/test_upload_session_runtime_api.py -q`: passed with 5 passed, 1 Starlette TestClient deprecation warning.
  - `docker compose down`: passed, postgres container and network removed.
  - Route scan: only the intended runtime routes were found in `src/upload_control_plane/api/upload_sessions.py`; no runtime `/pause`, `/resume`, `/complete`, or `/abort` route was found.
  - File-byte/presigned URL/credential scan: no FastAPI file-byte endpoint or persisted presigned URL field was found. S3 access/secret matches are limited to backend settings/storage client code, not API response models.
- Commands not run:
  - None from the requested list.

## PRD Hard Constraints Check

- Backend API receives no file bytes:
  - Preserved.
- Clients receive no MinIO/S3 credentials:
  - Preserved.
- Presigned URLs are not persisted:
  - Preserved for this segment.
- Authorization uses permission grants and is re-evaluated:
  - Preserved, with the known follow-up that `upload.presign` is not yet seeded/enforced.
- Complete uses object storage ListParts as authority:
  - Not implemented in this first segment; no DB-ack-based complete path was added.
- Ack does not complete sessions:
  - Preserved.
- Parts reconciliation uses object storage:
  - Preserved.
- Pause/resume/complete/abort:
  - Not added in this segment.

## Risks and Follow-up

- This first T06 segment can merge as a partial T06 slice for status, presign, ack, and parts list.
- Full T06 remains incomplete until the lifecycle segment implements:
  - `POST /v1/uploads/{session_id}/pause`
  - `POST /v1/uploads/{session_id}/resume`
  - `POST /v1/uploads/{session_id}/complete`
  - `POST /v1/uploads/{session_id}/abort`
  - lifecycle idempotency
  - session-level locking
  - storage-authoritative complete with `409 upload.missing_parts`
- Suggested next agent:
  - T06 Runtime lifecycle actions implementation agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Only the next T06 lifecycle segment is unblocked, not T07/T08/T09 as full T06 dependents.
- If partial:
  - Not applicable.
- If blocked:
  - Not applicable.
- If rejected:
  - Not applicable.
