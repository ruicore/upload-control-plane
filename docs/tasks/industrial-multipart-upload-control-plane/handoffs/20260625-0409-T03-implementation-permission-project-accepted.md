# Handoff: T03 permission/project authorization

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 03:45 +08:00
Finished: 2026-06-25 04:09 +08:00

## Scope

- Intended scope:
  - Implement DB-backed `permission_grants` authorization service.
  - Add reusable permission gate helpers for later upload routes.
  - Add `GET /v1/projects` and `GET /v1/projects/{project_id}`.
  - Return deterministic `effective_permissions`.
  - Add DB-backed tests for project visibility, detail permissions, DENY handling, expired grants, and later upload gate reuse.
- Explicitly out of scope:
  - Upload task creation route.
  - Multipart storage operations.
  - Dataset product lifecycle APIs.
  - Device credential runtime auth.
  - File-byte endpoints, MQTT, Go, or edge behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1738-T03-merge-auth-foundation-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`

## Changes

- Files changed:
  - `src/upload_control_plane/api/authorization.py`
  - `src/upload_control_plane/api/projects.py`
  - `src/upload_control_plane/main.py`
  - `tests/api/test_project_authorization.py`
- Behavior changed:
  - `AuthorizationService` loads grants for API key actors, ignores expired grants through the existing domain evaluator, supports DENY-over-ALLOW, and resolves tenant/project/dataset parent scopes.
  - `require_permission` and `require_any_permission` provide reusable gates for later upload APIs.
  - `GET /v1/projects` returns only non-deleted tenant projects where caller has `project.view`.
  - `GET /v1/projects/{project_id}` requires `project.view` and returns stable sorted `effective_permissions`.
- Compatibility notes:
  - Public auth remains `Authorization: Bearer <api_key>`.
  - Device subject grant rows are supported by the domain model and seed, but device runtime authentication remains out of scope.

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
  - `uv run pytest tests\api\test_project_authorization.py -q`
  - `uv run pytest`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 55 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 47 source files.
  - `uv run pytest` without Postgres: passed, 112 passed, 4 project DB tests skipped, 1 existing Starlette TestClient warning.
  - `make test` without Postgres: passed, 112 passed, 4 project DB tests skipped, same warning.
  - `docker compose up -d postgres`: passed; Postgres became healthy on `25432`.
  - `make migrate`: passed.
  - `make seed-dev`: passed; seed counts included `permission_grants=6`.
  - `uv run pytest tests\api\test_project_authorization.py -q`: passed, 4 passed, 1 warning.
  - `uv run pytest` with Postgres online: passed, 116 passed, 1 warning.
  - `docker compose down`: passed.
- Commands not run and why:
  - No upload-route smoke was run because upload routes are explicitly out of scope.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload, file-byte, storage proxy, MQTT, Go, or edge route was added.
- Clients receive no MinIO/S3 credentials: preserved. Project APIs return only project metadata and permission codes.
- Complete uses object storage ListParts as authority: preserved. Complete remains unimplemented.
- Authorization uses permission_grants: implemented for project list/detail and reusable gates.
- Internal IDs remain UUIDs: preserved. Project IDs and subject/resource IDs are UUIDs.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No optional component was added.

## Risks and Follow-up

- Remaining risks:
  - Project listing currently evaluates visible projects in Python after loading tenant projects and matching subject grants. This is acceptable for the current slice; larger tenants may need a SQL-level visibility query later.
  - Group subjects are not resolved because group membership is not modeled yet.
- Known gaps:
  - Upload route gates are implemented as reusable helpers but are not applied to real upload routes because those routes do not exist yet.
  - Device runtime auth remains out of scope.
- Suggested next agent:
  - T03 AuthZ validation agent can start full T03 validation.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Full T03 validation can start from this worktree.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not replace `permission_grants` with API key scopes for resource authorization.
