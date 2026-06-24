# Handoff: T03 auth foundation

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 17:16 +08:00
Finished: 2026-06-24 17:23 +08:00

## Scope

- Intended scope:
  - Add request ID middleware that returns `X-Request-ID` and makes the value available to error responses.
  - Add stable PRD 10.2 error response shape.
  - Add API key authentication foundation using seeded `X-API-Key` values and hashed storage.
  - Verify API keys through the current dev seed `sha256:<hex>` hash format.
  - Enforce tenant active status for authenticated requests.
  - Add a minimal internal auth smoke route for tests without adding project/upload product routes.
- Explicitly out of scope:
  - Project list/detail endpoints.
  - Central authorization service over `permission_grants`.
  - Permission filtering and `effective_permissions`.
  - Upload task/session/storage routes and multipart operations.
  - File-byte endpoints.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1716-T02-merge-persistence-foundation-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - Current FastAPI app, settings, DB models/session helpers, seed script, and tests.

## Changes

- Files changed:
  - `src/upload_control_plane/main.py`
  - `src/upload_control_plane/api/__init__.py`
  - `src/upload_control_plane/api/auth.py`
  - `src/upload_control_plane/api/errors.py`
  - `src/upload_control_plane/api/middleware.py`
  - `src/upload_control_plane/api/request_context.py`
  - `tests/api/test_auth_foundation.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1723-T03-implementation-auth-foundation-accepted.md`
- Behavior changed:
  - Every FastAPI response now receives an `X-Request-ID` header. Caller-supplied `X-Request-ID` is preserved; otherwise a UUID is generated.
  - API, HTTP, and validation errors use `{ "error": { "code", "message", "details", "request_id" } }`.
  - `X-API-Key` auth hashes the presented key as `sha256:<hex>`, looks up `api_keys.key_hash`, verifies with constant-time comparison, checks API key status/expiry, and rejects inactive tenants.
  - Added `GET /internal/auth-smoke` as a minimal protected route for auth foundation smoke tests.
- Compatibility notes:
  - PRD 10.1 currently documents `Authorization: Bearer <api_key>`, while this implementation slice follows the task's explicit `X-API-Key` requirement and T02 dev seed. The next T03 agent should decide whether to add Bearer compatibility or update the contract before public product routes depend on it.
  - The smoke route is internal/test-friendly and should not be treated as a product API.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose up -d postgres`
  - Postgres health wait for `upload-control-plane-postgres-1`
  - `make migrate`
  - `make seed-dev`
  - Real DB auth smoke using `TestClient` against `/internal/auth-smoke` with seeded `X-API-Key`, then temporary tenant `INACTIVE` update and restore.
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 52 files already formatted.
  - `uv run mypy src tests`: passed; no issues in 44 source files.
  - `uv run pytest`: passed; 111 passed, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with 111 passed / 1 warning.
  - `docker compose up -d postgres`: passed.
  - Postgres health wait: passed, status `healthy`.
  - `make migrate`: passed.
  - `make seed-dev`: passed with counts `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - Real DB auth smoke: valid seeded key returned 200 with tenant/API-key/subject IDs and `req-db-valid`; temporary inactive tenant returned 403 `auth.tenant_inactive` with `req-db-inactive`; tenant status was restored to `ACTIVE`.
  - `docker compose down`: passed and removed the Postgres container and compose network.
- Commands not run and why:
  - None from the requested validation list.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload, storage proxy, MQTT, Go, or file-byte route was added.
- Clients receive no MinIO/S3 credentials: preserved. Auth smoke returns only control-plane actor IDs/scopes.
- Complete uses object storage ListParts as authority: preserved. Completion remains unimplemented and out of scope.
- Authorization uses permission_grants: preserved as the next T03 slice. This slice only establishes authenticated actors and tenant active enforcement.
- Internal IDs remain UUIDs: preserved. Auth actor IDs are UUIDs from T02 models.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No optional component was added.

## Risks and Follow-up

- Remaining risks:
  - Public auth header contract must be reconciled: task requested `X-API-Key`, PRD 10.1 says `Authorization: Bearer`.
  - DB session creation in the auth dependency is intentionally simple for this foundation slice; later app composition can centralize engine/session lifecycle if needed.
  - `last_used_at` is not updated in this slice to keep auth read-only and avoid hidden write behavior.
- Known gaps:
  - No project visibility filtering.
  - No central permission evaluator over `permission_grants`.
  - No `effective_permissions` response.
  - No upload permission gate because upload routes do not exist yet.
- Suggested next agent:
  - T03 AuthZ permission filtering Implementation Agent should follow. It should implement `permission_grants` evaluation, project list/detail filtering, `effective_permissions`, and the reusable permission gate that T05/T06 can call on every control-plane request.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The next T03 permission/project agent can start from this auth foundation after validation accepts it.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
