# Handoff: T03 repair auth header contract

Status: accepted
Agent type: Repair
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 17:27 +08:00
Finished: 2026-06-24 17:31 +08:00

## Scope

- Intended scope:
  - Reconcile the T03 auth foundation header contract with PRD 10.1.
  - Require `Authorization: Bearer <api_key>` for API key authentication.
  - Update auth foundation tests so Bearer is the primary and only public contract.
  - Preserve stable error shape, request ID behavior, hash verification, API key active/expiry checks, and tenant active enforcement.
- Explicitly out of scope:
  - Project endpoints.
  - Permission service or `permission_grants` evaluator.
  - Upload APIs.
  - Storage adapter or multipart operations.
  - Any file-byte route, MQTT, Go uploader, or edge gateway behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T03 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1723-T03-implementation-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1727-T03-validation-auth-foundation-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md` sections 10.1 and 10.2
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md` auth sections
  - `src/upload_control_plane/api/auth.py`
  - `tests/api/test_auth_foundation.py`

## Changes

- Files changed:
  - `src/upload_control_plane/api/auth.py`
  - `tests/api/test_auth_foundation.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1731-T03-repair-auth-header-contract-accepted.md`
- Behavior changed:
  - `require_api_key` now reads `Authorization` and extracts `Bearer <api_key>`.
  - Missing `Authorization` or an empty Bearer token returns the existing `401 auth.api_key_missing` error shape.
  - Non-Bearer authorization values return the existing `401 auth.api_key_invalid` error shape.
  - `X-API-Key` is no longer accepted as an authentication alias.
- Compatibility notes:
  - No temporary `X-API-Key` backwards-compatible dev alias was kept. The public contract is exactly PRD 10.1: `Authorization: Bearer <api_key>`.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run pytest tests/api/test_auth_foundation.py`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose up -d postgres`
  - Postgres health wait for `upload-control-plane-postgres-1`
  - `make migrate`
  - `make seed-dev`
  - DB-backed auth smoke using `Authorization: Bearer <seeded-dev-key>` against `/internal/auth-smoke`
  - DB-backed missing auth smoke against `/internal/auth-smoke`
  - DB-backed legacy `X-API-Key` smoke against `/internal/auth-smoke`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 52 files already formatted.
  - `uv run pytest tests/api/test_auth_foundation.py`: passed; 8 passed, 1 existing Starlette TestClient deprecation warning.
  - `uv run mypy src tests`: passed; no issues in 44 source files.
  - `uv run pytest`: passed; 112 passed, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with 112 passed / 1 warning.
  - `docker compose up -d postgres`: passed.
  - Postgres health wait: passed, status `healthy`.
  - `make migrate`: passed.
  - `make seed-dev`: passed with counts `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - DB-backed Bearer auth smoke: returned `200` with authenticated tenant/API-key/subject IDs and request ID `req-db-bearer`.
  - DB-backed missing auth smoke: returned `401 auth.api_key_missing` with request ID `req-db-missing`.
  - DB-backed legacy `X-API-Key` smoke: returned `401 auth.api_key_missing` with request ID `req-db-x-api-key`.
  - `docker compose down`: passed and removed the Postgres container and compose network.
- Commands not run and why:
  - None from the requested verification list.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload, storage proxy, MQTT, Go, or file-byte route was added.
- Clients receive no MinIO/S3 credentials: preserved. Auth smoke returns only control-plane actor IDs/scopes.
- Complete uses object storage ListParts as authority: preserved. Completion remains unimplemented and out of scope.
- Authorization uses permission_grants: preserved as the next T03 slice. This repair only corrects the auth header contract.
- Internal IDs remain UUIDs: preserved. Auth actor IDs remain UUIDs from T02 models.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No optional component was added.

## Risks and Follow-up

- Remaining risks:
  - No new risk identified for the header contract. Existing T03 foundation gaps still remain for the next T03 authorization slice.
- Known gaps:
  - Project list/detail endpoints are not implemented.
  - Central `permission_grants` authorization service/gate is not implemented.
  - `effective_permissions` API response is not implemented.
  - Upload permission gates are not implemented because upload product routes do not exist yet.
- Suggested next agent:
  - Revalidate T03 auth foundation after this repair, then continue with the T03 AuthZ permission/project Implementation Agent if accepted.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T03 auth foundation can be revalidated with the corrected Bearer contract.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not reintroduce `X-API-Key` as the public auth contract unless the PRD is explicitly changed.
