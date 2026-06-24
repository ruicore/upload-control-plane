# Handoff: T03 auth foundation re-validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 17:31 +08:00
Finished: 2026-06-24 17:34 +08:00

## Scope

- Intended scope:
  - Independently re-validate the repaired T03 auth foundation on `main`.
  - Confirm public auth now follows PRD 10.1: `Authorization: Bearer <api_key>`.
  - Confirm legacy `X-API-Key` is not accepted as auth.
  - Confirm request ID middleware, stable PRD 10.2 error shape, API key hash verification, active/expiry checks, and tenant active enforcement remain correct.
  - Confirm the internal auth smoke route remains minimal and no project/upload/storage/MQTT/Go/edge behavior was added.
- Explicitly out of scope:
  - Modifying implementation, tests, config, README, or PRD.
  - Reverting any uncommitted work.
  - Implementing project APIs, permission filtering, upload APIs, storage adapters, MQTT, Go, or edge behavior.
- PRD/task/code files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T03 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1723-T03-implementation-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1727-T03-validation-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1731-T03-repair-auth-header-contract-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md` sections 10.1 and 10.2
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md` auth sections
  - `src/upload_control_plane/api/*.py`
  - `src/upload_control_plane/main.py`
  - `tests/api/test_auth_foundation.py`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1734-T03-validation-auth-foundation-accepted.md`
- Behavior changed:
  - None. Validation was read-only except for this handoff.

## Verification

- Commands run:
  - `git status --short --branch`
  - Required document/code reads listed above.
  - `rg` route/header/storage/MQTT/Go/edge checks.
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up -d postgres`
  - Postgres health wait against `upload-control-plane-postgres-1`
  - `make migrate`
  - `make seed-dev`
  - DB-backed Bearer auth smoke and legacy `X-API-Key` rejection smoke.
  - `docker compose down`
- Results:
  - `git status --short --branch`: on `main...origin/main [ahead 17]` with uncommitted T03 files present; no revert performed.
  - `rg --files src/upload_control_plane/api`: API package contains only `__init__.py`, `request_context.py`, `middleware.py`, `errors.py`, and `auth.py`.
  - Route scan: FastAPI routes are only `/healthz` and `/internal/auth-smoke`.
  - Header scan: current implementation reads `Authorization` with `Bearer `; `X-API-Key` appears only in tests and historical handoff text, not in the auth dependency.
  - Prohibited behavior scan: no new project/upload API route, `UploadFile`, `File(`, storage multipart adapter/API, `boto3`, `botocore`, MQTT route, Go, or edge behavior was found in the T03 API surface. Existing multipart/permission/project matches are prior domain/schema/tests/config surfaces, not product API additions.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 52 files already formatted.
  - `uv run mypy src tests`: passed; no issues in 44 source files.
  - `uv run pytest`: passed; 112 passed, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with 112 passed and the same warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - Postgres health wait: passed, status `healthy`.
  - `make migrate`: passed.
  - `make seed-dev`: passed with counts `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - DB-backed smoke:
    - Seeded `api_keys.key_hash` starts with `sha256:` and does not contain the raw dev API key.
    - Valid `Authorization: Bearer <dev-key>`: `200`, `authenticated=True`, request ID `req-db-valid-bearer` propagated.
    - Legacy `X-API-Key` only: `401 auth.api_key_missing`, request ID `req-db-x-api-key` propagated.
    - Missing auth: `401 auth.api_key_missing`, request ID propagated.
    - Non-Bearer authorization: `401 auth.api_key_invalid`, request ID propagated.
    - Invalid Bearer key: `401 auth.api_key_invalid`, request ID propagated.
    - Inactive API key: `401 auth.api_key_inactive`, request ID propagated.
    - Expired API key: `401 auth.api_key_inactive`, request ID propagated.
    - Inactive tenant: `403 auth.tenant_inactive`, request ID propagated.
    - DB statuses/expiry were restored and a final valid Bearer request returned `200`.
  - `docker compose down`: passed and removed the Postgres container/network.
- Commands not run and why:
  - None from the requested validation list.

## PRD Hard Constraints Check

- Public auth contract uses `Authorization: Bearer <api_key>` per PRD 10.1: accepted.
- `X-API-Key` is not accepted as auth: accepted.
- Request ID middleware and PRD 10.2 error shape remain stable: accepted.
- API key hash verification, active/expiry checks, and tenant active enforcement remain correct: accepted.
- Internal auth smoke route is still minimal: accepted.
- No project/upload API was added: accepted.
- No file-byte endpoint, storage multipart implementation, MQTT, Go, or edge behavior was added: accepted.
- Clients receive no MinIO/S3 credentials: preserved.
- Storage-authoritative complete remains unimplemented in this slice: preserved.
- Authorization over `permission_grants` remains the next T03 slice, not part of this foundation re-validation.

## Risks and Follow-up

- Remaining risks:
  - `last_used_at` is still not updated by this foundation slice; acceptable for the current read-only auth foundation, but later audit/usage tracking should define this write behavior explicitly.
  - Request ID middleware still preserves any non-empty ASGI-accepted request ID value; stricter trace ID validation would need a PRD/task decision.
- Known gaps:
  - Project list/detail endpoints are not implemented.
  - Central `permission_grants` authorization service/gate is not implemented.
  - `effective_permissions` API response is not implemented.
  - Upload permission gates are not implemented because upload product routes do not exist yet.
- Suggested next agent:
  - T03 AuthZ permission/project Implementation Agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The T03 permission/project agent can start. It should implement `permission_grants` evaluation, project list/detail filtering, `effective_permissions`, and reusable permission gates for later upload APIs.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not reintroduce `X-API-Key` as a public auth alias unless the PRD is explicitly changed.
