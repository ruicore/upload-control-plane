# Handoff: T03 full authentication and authorization validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 04:09 +08:00
Finished: 2026-06-25 04:14 +08:00

## Scope

- Intended scope:
  - Independently validate complete T03 Authentication and Authorization after the auth foundation commit and the uncommitted permission/project implementation.
  - Verify API key authentication, tenant active enforcement, stable error shape, request ID preservation, DB-backed permission grants, project visibility filtering, deterministic effective permissions, DENY-over-ALLOW, expired grant handling, and reusable upload permission gate helpers.
  - Confirm T03 did not add upload task/session routes, multipart storage operations, file-byte endpoints, MQTT, Go, or edge behavior.
- Explicitly out of scope:
  - Editing implementation code, tests, config, README, or PRD.
  - Reverting or committing existing worktree changes.
  - Adding upload, storage, MQTT, Go, or edge behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1738-T03-merge-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0409-T03-implementation-permission-project-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
- Implementation/tests inspected:
  - `src/upload_control_plane/api/auth.py`
  - `src/upload_control_plane/api/authorization.py`
  - `src/upload_control_plane/api/projects.py`
  - `src/upload_control_plane/api/errors.py`
  - `src/upload_control_plane/api/middleware.py`
  - `src/upload_control_plane/api/request_context.py`
  - `src/upload_control_plane/domain/permissions.py`
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `src/upload_control_plane/main.py`
  - `tests/api/test_auth_foundation.py`
  - `tests/api/test_project_authorization.py`

## Validation Findings

- API key authentication:
  - Accepted. Public auth uses `Authorization: Bearer <api_key>` through `require_api_key`.
  - `X-API-Key` is not accepted as a public auth alias and returns `401 auth.api_key_missing`.
- Tenant active status:
  - Accepted. Authenticated requests check the mapped tenant and reject inactive tenant rows with `403 auth.tenant_inactive`.
- Stable error response and request ID:
  - Accepted. Errors use the PRD error envelope and preserve `X-Request-ID` in both response body and header.
- Authorization source of truth:
  - Accepted. `AuthorizationService` loads `permission_grants` for actor subjects and delegates permission calculation to the domain evaluator.
  - API key scopes are not used as the resource-level authorization source.
- Project list:
  - Accepted. `GET /v1/projects` enumerates tenant projects but returns only projects with effective `project.view`.
  - Deleted projects are excluded.
- Project detail:
  - Accepted. `GET /v1/projects/{project_id}` requires `project.view` and returns stable sorted `effective_permissions`.
- Effective permissions:
  - Accepted. Domain evaluator ignores expired grants, returns deterministic sorted codes, and applies DENY-over-ALLOW.
- Reusable gate/helper:
  - Accepted. `AuthorizationService.require_permission` and `AuthorizationService.require_any_permission` are reusable for later upload routes; DB-backed test covers later `dataset.upload` or `upload.create` gate usage.
- Scope boundaries:
  - Accepted. Runtime route scan shows only `/healthz`, `/internal/auth-smoke`, and `/v1/projects` list/detail.
  - No upload API, multipart storage operation, file-byte endpoint, MQTT runtime adapter, Go service, or edge behavior was added by T03.

## Verification

- `uv run ruff check`: passed.
- `uv run ruff format --check`: passed, 55 files already formatted.
- `uv run mypy src tests`: passed, no issues in 47 source files.
- `uv run pytest` before Postgres startup: passed, 112 passed, 4 skipped, 1 existing Starlette TestClient deprecation warning.
- `make test` before Postgres startup: passed, repeating ruff, format check, mypy, and pytest with 112 passed, 4 skipped, 1 existing warning.
- `docker compose config --quiet`: passed.
- `docker compose up -d postgres`: passed.
- Postgres health wait: passed, container reported `healthy`.
- `make migrate`: passed.
- `make seed-dev`: passed with deterministic seed IDs and counts:
  - `tenants=1`
  - `api_keys=1`
  - `storage_policies=1`
  - `projects=1`
  - `datasets=1`
  - `devices=1`
  - `permission_grants=6`
- `uv run pytest tests\api\test_project_authorization.py -q` with Postgres online: passed, 4 passed, 1 existing warning.
- `uv run pytest` with Postgres online: passed, 116 passed, 1 existing warning.
- DB-backed smoke calls:
  - Bearer auth `/internal/auth-smoke`: `200`, preserved `X-Request-ID=req-validation-smoke`, returned seeded tenant/API key/subject IDs and `scopes=["dev"]`.
  - Legacy `X-API-Key` `/internal/auth-smoke`: `401 auth.api_key_missing`, preserved `X-Request-ID=req-validation-x-api-key`.
  - Project list `/v1/projects`: `200`, returned only seeded project `020500f8-920c-5a49-bf01-0eca416b8ddf` with `effective_permissions=["dataset.upload", "project.view", "upload.create"]`.
  - Project detail `/v1/projects/020500f8-920c-5a49-bf01-0eca416b8ddf`: `200`, returned stable `effective_permissions=["dataset.upload", "project.view", "upload.create"]`.
  - Tenant inactive smoke: temporarily set seeded tenant to `INACTIVE`, `/internal/auth-smoke` returned `403 auth.tenant_inactive` with `X-Request-ID=req-validation-tenant-inactive`, then restored tenant status to `ACTIVE`.
- Scope scans:
  - Route scan found only `app.include_router(projects_router)`, `/healthz`, `/internal/auth-smoke`, `APIRouter(prefix="/v1/projects")`, `GET /v1/projects`, and `GET /v1/projects/{project_id}`.
  - Upload/MQTT/edge scan found no runtime upload routes or storage operations in T03 API code; hits were limited to existing config/domain/schema/tests/text references.
- `docker compose down`: passed and removed Postgres container/network.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved.
- Clients receive no MinIO/S3 credentials: preserved.
- Complete uses object storage ListParts as authority: preserved because complete remains unimplemented.
- Authorization uses `permission_grants`: implemented and validated for project APIs and reusable gates.
- API key scopes do not replace resource permissions: preserved.
- Internal IDs remain UUIDs: preserved.
- MQTT/Go/edge remain optional and dependency-gated: preserved.

## Risks and Follow-up

- Remaining risks:
  - Project visibility is currently evaluated in Python after loading tenant projects. This is acceptable for T03 but should become SQL-shaped before large-tenant scale.
  - Group subjects are not resolved because group membership is not modeled yet.
- Known gaps:
  - Upload route gates are reusable helpers only; no upload routes exist yet, so T05/T06 must apply them at every control-plane operation.
  - Device runtime authentication remains out of scope for T03.
- Suggested next agent:
  - T03 merge/finalization agent, then T04 MinIO/S3 Storage Adapter agent after T03 is merged.

## Decision

- T03 full Authentication and Authorization validation is accepted.
- T03 can merge/finalize after the current implementation and this validation handoff are committed.
- T04 can unlock after T03 is merged/finalized.
