# Handoff: T02 dev seed

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 17:00 +08:00
Finished: 2026-06-24 17:03 +08:00

## Scope

- Intended scope:
  - Implement deterministic local dev seed data for the accepted T02 schema at Alembic head `20260624_0005`.
  - Seed tenant, API key, storage policy, project, dataset, device, and resource-scoped permission grants.
  - Keep API key and device credential material hashed at rest; only print the dev API key value for local convenience.
  - Prove repeated seed runs are idempotent enough for local development.
- Explicitly out of scope:
  - Auth API implementation, API key verification dependency, project endpoints, upload task creation endpoint, storage multipart calls, worker/outbox behavior, and file-byte endpoints.
  - New migrations. No schema gap was found for this seed slice.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1656-T02-merge-records-schema-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `scripts/seed_dev.py`
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `src/upload_control_plane/infrastructure/db/session.py`

## Changes

- Files changed:
  - `src/upload_control_plane/infrastructure/db/seed.py`
  - `scripts/seed_dev.py`
  - `tests/infrastructure/test_seed_dev.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1703-T02-implementation-seed-dev-accepted.md`
- Behavior changed:
  - `make seed-dev` now writes deterministic dev rows for:
    - tenant `dev-industrial`
    - API key `cd6c08e8-68a1-50e8-868e-b2b17a0231db`
    - storage policy `local-minio-default`
    - project `robotics-line-3`
    - dataset `line-3-sample-hdf5`
    - device `robot-17`
    - permission grants for API key and device subjects.
  - Seeded API key actor receives `project.view`, `dataset.upload`, and `upload.create` on the seeded project.
  - API key raw value is printed as dev-only local convenience but only `sha256:*` hash is stored in `api_keys.key_hash`.
- Compatibility notes:
  - No migration was added.
  - Seed uses fixed UUIDv5 values and updates existing rows by primary key for repeated local runs.
  - The accepted schema has no `device_project_grants` table/model; device project access is represented through `permission_grants`.

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
  - `make seed-dev`
  - PostgreSQL inspection for seeded row counts.
  - PostgreSQL inspection for API key hash-only storage.
  - PostgreSQL inspection for permission grants and expected permission codes.
  - PostgreSQL inspection for seeded tenant/storage policy/project/dataset/device details.
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 46 files already formatted.
  - `uv run mypy src tests`: passed; no issues in 38 source files.
  - `uv run pytest`: passed; 104 passed, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with 104 passed / 1 warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed against local PostgreSQL.
  - First `make seed-dev`: passed; counts were `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - Second `make seed-dev`: passed with the same counts, proving no duplicate dev rows for the seeded IDs/source.
  - API key inspection showed `key_hash like 'sha256:%' = true` and raw key substring absent.
  - Permission inspection showed API key and device each have one `ALLOW` grant for `project.view`, `dataset.upload`, and `upload.create` on resource type `project`.
  - Seeded domain inspection showed tenant `dev-industrial`, storage policy `local-minio-default`, bucket `robot-data`, project `robotics-line-3`, dataset `line-3-sample-hdf5`, dataset status `UPLOAD_PENDING`, validation status `NOT_REQUIRED`, recovery status `NORMAL`, device `robot-17`, device status `ACTIVE`.
- Commands not run and why:
  - None. `docker compose down` is run after writing this handoff so the final response can include the cleanup result.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No API, MQTT, storage, or file-byte paths were added.
- Clients receive no MinIO/S3 credentials: preserved. Seed prints only a dev API key, not MinIO/S3 credentials.
- Complete uses object storage ListParts as authority: preserved. Completion behavior remains out of scope.
- Authorization uses permission_grants: satisfied for seed. Resource grants are written to `permission_grants`; API key scopes are only coarse dev metadata.
- Internal IDs remain UUIDs: satisfied. Seeded rows use deterministic UUID values.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway work added.

## Risks and Follow-up

- Remaining risks:
  - T03 must define the production API key hash verification contract; this seed currently uses deterministic `sha256:` hashing for local dev.
  - No endpoint consumes these grants yet; runtime authorization remains T03.
- Known gaps:
  - Device credential lifecycle and one-time provisioning behavior remain future T10 work.
  - Upload task/session rows are intentionally not seeded because upload task creation is out of scope.
- Suggested next agent:
  - T02 Persistence validation agent can run full T02 final validation.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Full T02 final validation can start from `main` with Alembic head `20260624_0005` and `make seed-dev`.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not persist raw API key or device credential material.
  - Do not add migrations for seed-only behavior unless validation finds an actual schema gap.
