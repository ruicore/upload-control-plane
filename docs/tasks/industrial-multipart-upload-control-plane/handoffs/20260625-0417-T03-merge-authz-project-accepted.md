# Handoff: T03 authz project final merge

Status: accepted
Agent type: Merge
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 04:15 +08:00
Finished: 2026-06-25 04:17 +08:00

## Scope

- Intended scope:
  - Commit the accepted T03 permission/project implementation, tests, and implementation/validation handoffs on `main`.
  - Run the final post-commit validation suite.
  - Record the final merge handoff for unlocking T04.
- Explicitly out of scope:
  - Adding upload task creation routes.
  - Adding multipart storage operations or MinIO/S3 adapter behavior.
  - Adding dataset lifecycle, device runtime authentication, MQTT, Go, or edge behavior.
  - Changing accepted T03 business logic during merge finalization.
  - Pushing to any remote.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1738-T03-merge-auth-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0409-T03-implementation-permission-project-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0414-T03-validation-authz-project-accepted.md`

## Changes

- Files committed in permission/project checkpoint:
  - `src/upload_control_plane/main.py`
  - `src/upload_control_plane/api/authorization.py`
  - `src/upload_control_plane/api/projects.py`
  - `tests/api/test_project_authorization.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0409-T03-implementation-permission-project-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0414-T03-validation-authz-project-accepted.md`
- Commits:
  - `76a9a6e T03 permission project authorization accepted`
- Behavior changed:
  - No merge-time behavior changes beyond the accepted T03 permission/project checkpoint.
  - `GET /v1/projects` and `GET /v1/projects/{project_id}` are registered.
  - Authorization source remains DB-backed `permission_grants`; API key scopes do not replace resource authorization.
  - Reusable permission gate helpers are available for later upload routes, but no upload route exists yet.
- Compatibility notes:
  - Public auth remains `Authorization: Bearer <api_key>`.
  - T03 auth foundation commit `283a05a` and handoff commit `a768030` remain the base for this final checkpoint.

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
  - `uv run pytest tests\api\test_project_authorization.py -q`
  - `uv run pytest` with Postgres online
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 55 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 47 source files.
  - `uv run pytest` before Postgres startup: passed, 112 passed, 4 skipped, 1 existing Starlette TestClient deprecation warning.
  - `make test` before Postgres startup: passed, repeating ruff, format check, mypy, and pytest with 112 passed, 4 skipped, 1 existing warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - Postgres health wait: passed, status `healthy`.
  - `make migrate`: passed.
  - `make seed-dev`: passed with counts `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - `uv run pytest tests\api\test_project_authorization.py -q`: passed, 4 passed, 1 existing warning.
  - `uv run pytest` with Postgres online: passed, 116 passed, 1 existing warning.
  - `docker compose down`: passed and removed the Postgres container/network.
- Commands not run and why:
  - Manual HTTP smoke calls were not run because the required DB-backed auth/project targeted tests passed against the migrated seeded database.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload, file-byte, storage proxy, MQTT, Go, or edge route was added.
- Clients receive no MinIO/S3 credentials: preserved. Project APIs return metadata and permission codes only.
- Complete uses object storage ListParts as authority: preserved. Complete remains unimplemented.
- Authorization uses permission_grants: implemented and validated for project APIs and reusable gates.
- Internal IDs remain UUIDs: preserved. Project and authorization resource IDs are UUIDs.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No optional component was added.

## Risks and Follow-up

- Remaining risks:
  - Project visibility is evaluated in Python after loading tenant projects. This is accepted for T03; a future large-tenant path should move visibility filtering closer to SQL.
  - Group subjects are not resolved because group membership is not modeled yet.
- Known gaps:
  - Upload route gates are reusable helpers only; T05/T06 must apply them when those routes exist.
  - Device runtime authentication remains out of scope for T03.
- Suggested next agent:
  - T04 MinIO/S3 Storage Adapter implementation agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T04 is unlocked after this handoff is committed because T03 has accepted implementation, accepted validation, final merge commit, and final validation evidence.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not replace `permission_grants` with API key scopes for resource authorization.
  - Do not add upload/storage behavior in T03 finalization.
