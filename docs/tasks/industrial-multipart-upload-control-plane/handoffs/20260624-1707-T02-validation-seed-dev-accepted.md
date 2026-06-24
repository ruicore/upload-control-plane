# Handoff: T02 dev seed validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 17:03 +08:00
Finished: 2026-06-24 17:07 +08:00

## Scope

- Intended scope:
  - Independently validate the uncommitted T02 dev seed implementation on `main`.
  - Confirm seed creates tenant, API key, storage policy, project, dataset, device, and permission grants.
  - Confirm seed is idempotent when run twice.
  - Confirm API key raw secret is not persisted and stored key value is hash-like.
  - Confirm seeded API key actor and device have `project.view` plus `dataset.upload` or `upload.create` grants.
  - Confirm no API/auth route, storage operation, upload route, MQTT, Go, or edge behavior was added.
- Explicitly out of scope:
  - Modifying implementation code, tests, configuration, README, or PRD.
  - Repairing or expanding seed behavior.
  - Implementing T03 auth, T04 storage, or upload API runtime behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T02 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1703-T02-implementation-seed-dev-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md` API key and permission sections
  - `scripts/seed_dev.py`
  - `src/upload_control_plane/infrastructure/db/seed.py`
  - `tests/infrastructure/test_seed_dev.py`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1707-T02-validation-seed-dev-accepted.md`
- Behavior changed:
  - None. This validation did not modify implementation, tests, configuration, README, or PRD.
- Compatibility notes:
  - Existing uncommitted implementation files were left untouched.
  - `docker compose down` was run after validation cleanup.

## Verification

- Commands run:
  - `git status --short --branch`
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
  - PostgreSQL inspection for table row counts.
  - PostgreSQL inspection for API key hash-only storage.
  - PostgreSQL inspection for permission grant codes.
  - PostgreSQL inspection for seeded tenant/storage policy/project/dataset/device state.
  - Static route/scope inspection with `rg` and direct reads of `src/upload_control_plane/main.py` and `src/upload_control_plane/worker/main.py`.
  - `docker compose down`
- Results:
  - `git status --short --branch`: `main` is ahead of `origin/main` and has uncommitted T02 seed implementation files; no unrelated files were reverted.
  - `uv run ruff check`: passed, `All checks passed!`.
  - `uv run ruff format --check`: passed, `46 files already formatted`.
  - `uv run mypy src tests`: passed, `Success: no issues found in 38 source files`.
  - `uv run pytest`: passed, `104 passed, 1 warning`.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with `104 passed, 1 warning`.
  - `docker compose config --quiet`: passed with no output.
  - `docker compose up -d postgres`: passed; Postgres container started.
  - `make migrate`: passed against local PostgreSQL.
  - First `make seed-dev`: passed with deterministic IDs and counts `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - Second `make seed-dev`: passed with the same IDs and same counts, confirming idempotency for the deterministic dev seed.
  - PostgreSQL row counts after two seed runs:
    - `tenants=1`
    - `api_keys=1`
    - `storage_policies=1`
    - `projects=1`
    - `datasets=1`
    - `devices=1`
    - `permission_grants=6`
  - API key inspection showed `key_hash = sha256:b05a2b9364e784271845832d9dfb602917c751c0af57d1322fb8f4313bb86a91`, `key_hash LIKE 'sha256:%' = true`, and raw key substring absent from `key_hash`.
  - Permission inspection showed both subjects have project-scoped `ALLOW` grants from `dev_seed`:
    - `api_key cd6c08e8-68a1-50e8-868e-b2b17a0231db`: `project.view`, `dataset.upload`, `upload.create`
    - `device e06d5e8b-3579-5efd-8a51-e89db11c6cc9`: `project.view`, `dataset.upload`, `upload.create`
  - Seeded entity inspection showed:
    - tenant `dev-industrial`
    - storage policy `local-minio-default`, bucket `robot-data`
    - project `robotics-line-3`
    - dataset `line-3-sample-hdf5`, `UPLOAD_PENDING`, `NOT_REQUIRED`, `NORMAL`
    - device `robot-17`, `ACTIVE`, credential hash is `sha256:`-like
  - Static route/scope inspection showed FastAPI still defines only `GET /healthz`; no API/auth route, storage operation, upload route, MQTT, Go, or edge behavior was added by this seed slice.
  - `docker compose down`: passed; Postgres container and compose network were removed.
- Commands not run and why:
  - None from the requested validation list.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. Seed implementation adds no API, upload, storage, MQTT, Go, or edge file-byte path.
- Clients receive no MinIO/S3 credentials: preserved. Seed prints a dev API key value for local use, not MinIO/S3 credentials; database inspection showed API key and device credential material are hash-like at rest.
- Complete uses object storage ListParts as authority: preserved. Complete behavior remains unimplemented and out of scope.
- Authorization uses permission_grants: satisfied for this seed slice. API key and device subjects receive project-scoped permission rows in `permission_grants`.
- Internal IDs remain UUIDs: satisfied. Seeded internal IDs are deterministic UUID values.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway work was added.

## Risks and Follow-up

- Remaining risks:
  - `make seed-dev` intentionally prints the dev-only API key value to stdout; this is not persisted in the database, but operators should treat console output as local dev-only material.
  - T03 still needs to define and validate the runtime API key verification contract.
  - T10 still needs production device credential lifecycle/provisioning semantics.
- Known gaps:
  - No endpoint consumes these permission grants yet; that remains T03 scope.
  - Upload tasks/sessions are intentionally not seeded because upload task creation is out of scope for T02 seed.
- Suggested next agent:
  - Full T02 final validation can start.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Full T02 validation can start from `main` with the current seed implementation and Alembic migrations.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
