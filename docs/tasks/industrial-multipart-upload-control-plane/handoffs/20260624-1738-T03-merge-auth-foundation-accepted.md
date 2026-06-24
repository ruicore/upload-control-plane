# Handoff: T03 auth foundation merge

Status: accepted
Agent type: Merge
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 17:35 +08:00
Finished: 2026-06-24 17:38 +08:00

## Scope

- Intended scope:
  - Commit the already accepted T03 auth foundation implementation, repair, tests, and related handoffs on `main`.
  - Run the required post-commit validation suite.
  - Record merge handoff evidence for the next T03 permission/project agent.
- Explicitly out of scope:
  - Adding project list/detail endpoints.
  - Adding `permission_grants` authorization filtering or `effective_permissions`.
  - Adding upload task/session/storage routes.
  - Changing business logic beyond preserving the accepted auth foundation checkpoint.
  - Pushing to any remote.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1723-T03-implementation-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1727-T03-validation-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1731-T03-repair-auth-header-contract-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1734-T03-validation-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`

## Changes

- Files committed in auth foundation checkpoint:
  - `src/upload_control_plane/main.py`
  - `src/upload_control_plane/api/__init__.py`
  - `src/upload_control_plane/api/auth.py`
  - `src/upload_control_plane/api/errors.py`
  - `src/upload_control_plane/api/middleware.py`
  - `src/upload_control_plane/api/request_context.py`
  - `tests/api/test_auth_foundation.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1723-T03-implementation-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1727-T03-validation-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1731-T03-repair-auth-header-contract-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1734-T03-validation-auth-foundation-accepted.md`
- Commits:
  - `283a05a T03 auth foundation accepted`
- Behavior changed:
  - No new merge-time behavior changes beyond the accepted T03 auth foundation checkpoint.
  - Public auth contract remains `Authorization: Bearer <api_key>`.
  - Legacy `X-API-Key` is rejected as not being the public auth contract.
- Compatibility notes:
  - `GET /internal/auth-smoke` remains an internal smoke route only.
  - Permission/project behavior remains intentionally unimplemented for the next T03 slice.

## Verification

- Commands run:
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
  - DB-backed Bearer auth smoke against `/internal/auth-smoke`
  - DB-backed legacy `X-API-Key` rejection smoke against `/internal/auth-smoke`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 52 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 44 source files.
  - `uv run pytest`: passed, 112 passed with 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed, repeating ruff, format check, mypy, and pytest with 112 passed and the same warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - Postgres health wait: passed, status `healthy`.
  - `make migrate`: passed.
  - `make seed-dev`: passed with counts `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - DB-backed Bearer auth smoke: returned `200`, `authenticated=True`, request ID `req-merge-bearer`, tenant/API key/subject UUIDs from seeded DB, and `scopes=["dev"]`.
  - DB-backed legacy `X-API-Key` rejection smoke: returned `401 auth.api_key_missing` with request ID `req-merge-x-api-key`.
  - `docker compose down`: passed and removed the Postgres container/network.
- Commands not run and why:
  - None from the requested validation list.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload, file-byte, storage proxy, MQTT, Go, or edge route was added.
- Clients receive no MinIO/S3 credentials: preserved. Auth smoke only returns actor identifiers and scopes.
- Complete uses object storage ListParts as authority: preserved. Complete remains unimplemented.
- Authorization uses permission_grants: preserved as the next T03 slice; this merge only commits the AuthN/request foundation.
- Internal IDs remain UUIDs: preserved. Auth actor IDs are UUIDs from T02 persistence.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No optional component was added.

## Risks and Follow-up

- Remaining risks:
  - `last_used_at` is not updated in this foundation slice; later audit/usage tracking should define the write behavior explicitly.
  - Request ID middleware preserves any non-empty ASGI-accepted request ID value; stricter validation needs a separate PRD/task decision.
- Known gaps:
  - Project list/detail endpoints are not implemented.
  - Central `permission_grants` authorization service/gate is not implemented.
  - `effective_permissions` API response is not implemented.
  - Upload permission gates are not implemented because upload product routes do not exist yet.
- Suggested next agent:
  - T03 AuthZ permission/project Implementation Agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The next T03 permission/project agent can start from commit `283a05a` plus this merge handoff after the handoff commit is created.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not reintroduce `X-API-Key` as a public auth alias unless the PRD is explicitly changed.
