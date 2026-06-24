# Handoff: T03 auth foundation validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 17:23 +08:00
Finished: 2026-06-24 17:27 +08:00

## Scope

- Intended scope:
  - Independently validate the uncommitted T03 auth foundation implementation.
  - Confirm request ID middleware, stable error body, `X-API-Key` auth, hashed-key verification, API key lifecycle checks, tenant active enforcement, and minimal internal smoke route.
  - Confirm this slice does not add project/upload/storage/MQTT/Go/edge product behavior.
- Explicitly out of scope:
  - Modifying implementation, tests, config, README, or PRD.
  - Implementing project list/detail, `effective_permissions`, or upload authorization gates.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T03 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1723-T03-implementation-auth-foundation-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md` sections 10.1 and 10.2
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md` tenants and api_keys sections
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md` auth sections
  - `src/upload_control_plane/api/*.py`
  - `src/upload_control_plane/main.py`
  - `tests/api/test_auth_foundation.py`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1727-T03-validation-auth-foundation-accepted.md`
- Behavior changed:
  - None. Validation was read-only except for this handoff.
- Compatibility notes:
  - The implementation intentionally follows the task's explicit `X-API-Key` requirement. PRD 10.1 still documents `Authorization: Bearer <api_key>`; this remains a contract reconciliation item before public product routes depend on auth.

## Verification

- Commands run:
  - `git status --short --branch`
  - Required document/code reads listed above.
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
  - DB-backed auth smoke with `TestClient` and real seeded DB rows.
  - Request ID smoke for incoming trace ID and generated UUID.
  - `rg` checks for prohibited endpoints/behavior and auth/header/hash surfaces.
  - `docker compose down`
- Results:
  - `git status --short --branch`: on `main...origin/main [ahead 17]` with uncommitted T03 implementation files present; no revert performed.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 52 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 44 source files.
  - `uv run pytest`: passed, 111 passed, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed, repeats ruff/format/mypy/pytest with 111 passed and the same warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - Postgres health wait: `healthy`.
  - `make migrate`: passed.
  - `make seed-dev`: passed with counts `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - DB-backed auth smoke:
    - DB `api_keys.key_hash` starts with `sha256:` and does not contain the dev raw key.
    - Valid seeded `X-API-Key`: `200`, `authenticated=True`, request ID propagated.
    - Missing key: `401 auth.api_key_missing`, request ID propagated.
    - Invalid key: `401 auth.api_key_invalid`, request ID propagated.
    - Inactive key: `401 auth.api_key_inactive`, request ID propagated.
    - Expired key: `401 auth.api_key_inactive`, request ID propagated.
    - Inactive tenant: `403 auth.tenant_inactive`, request ID propagated.
    - DB statuses were restored; valid key returned `200` after restore.
  - Request ID smoke:
    - Incoming `X-Request-ID: trace-abc-123` returned unchanged.
    - Missing request ID generated a valid UUID and returned it in `X-Request-ID`.
  - `rg` checks:
    - New FastAPI routes are only `/healthz` and `/internal/auth-smoke`.
    - No `/v1/projects`, project list/detail route, `effective_permissions` API response, upload task route, file-byte endpoint, storage multipart adapter/API, MQTT route, Go/edge behavior, `UploadFile`, `File(`, `boto3`, or `botocore` implementation was added in the T03 API surface.
    - Existing matches for upload/session/project/permission terms are from prior domain/schema/tests/config and not new product API behavior.
  - `docker compose down`: passed and removed the Postgres container/network.
- Commands not run and why:
  - None from the requested validation list.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No file-byte API, `UploadFile`, storage proxy, MQTT implementation, or Go/edge component was added.
- Clients receive no MinIO/S3 credentials: preserved. The internal auth smoke route returns only auth actor IDs and scopes.
- Complete uses object storage ListParts as authority: preserved. Complete remains unimplemented in this slice.
- Authorization uses permission_grants: preserved as the next T03 permission/project slice. This foundation only authenticates actors and enforces tenant/API-key active status.
- Internal IDs remain UUIDs: preserved. Smoke response IDs come from UUID model fields.
- MQTT/Go/edge remain optional and dependency-gated: preserved. Only pre-existing disabled config fields matched rg.

## Risks and Follow-up

- Remaining risks:
  - PRD 10.1 says `Authorization: Bearer <api_key>` while this task and implementation use `X-API-Key`. Reconcile before public product API exposure.
  - Request ID middleware preserves any non-empty incoming header value accepted by the ASGI stack; current validation confirms normal trace IDs and generated UUIDs. If stricter sanitization is desired, define the accepted trace-id format in PRD/task before hardening.
  - `last_used_at` is not updated by this foundation slice; acceptable for read-only auth validation, but later audit/usage tracking may need an explicit write path.
- Known gaps:
  - Project list/detail endpoints are not implemented.
  - `effective_permissions` API response is not implemented.
  - Central `permission_grants` authorization service/gate is not implemented in this slice.
  - Upload permission gates are not implemented because upload product routes do not exist yet.
- Suggested next agent:
  - T03 AuthZ permission/project Implementation Agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The next T03 permission/project agent can start. It should implement `permission_grants` evaluation, project list/detail filtering, `effective_permissions`, and reusable permission gates for later upload APIs.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
