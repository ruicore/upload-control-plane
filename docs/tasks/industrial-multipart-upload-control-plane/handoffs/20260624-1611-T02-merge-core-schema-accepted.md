# Handoff: T02 merge core schema

Status: accepted
Agent type: Merge
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 16:10 +08:00
Finished: 2026-06-24 16:11 +08:00

## Scope

- Intended scope:
  - Stage and commit the accepted T02 core schema segment.
  - Preserve implementation and validation handoffs as part of the stable checkpoint.
  - Verify the committed checkpoint and record enough database evidence to confirm the core schema.
- Explicitly out of scope:
  - New business schema beyond `tenants`, `storage_policies`, `api_keys`, `projects`, and PRD enum types.
  - Seed data, datasets, tags, devices, `permission_grants`, upload lifecycle tables, upload APIs, auth logic, storage adapter behavior, MQTT, Go, or edge work.
  - Any business logic repair or next T02 segment implementation.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1605-T02-implementation-core-schema-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1609-T02-validation-core-schema-accepted.md`

## Changes

- Files changed:
  - Committed T02 core schema implementation, migration, tests, and implementation/validation handoffs in commit `7091001`.
  - Added this merge handoff.
- Behavior changed:
  - `main` now has Alembic head `20260624_0002` for the core schema segment.
  - SQLAlchemy metadata exposes only the four core schema tables for this segment.
- Compatibility notes:
  - Base persistence migration `20260624_0001` was not rewritten.
  - No out-of-scope schema, API, seed, auth, or storage behavior was added by the merge agent.

## Verification

- Commands run:
  - `git status --short --branch`
  - `git diff --name-status`
  - `git diff --check`
  - `rg -n "create_table\(|__tablename__|upload_batches|batch_id|permission_grants|datasets|devices|upload_tasks|upload_objects|upload_sessions|upload_parts|outbox_events|idempotency_records" src migrations tests docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1605-T02-implementation-core-schema-accepted.md docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1609-T02-validation-core-schema-accepted.md`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up -d postgres`
  - `make migrate`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select version_num from alembic_version;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name from information_schema.tables where table_schema = 'public' order by table_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select typname from pg_type t join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and t.typtype='e' order by typname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name, column_name, data_type, udt_name from information_schema.columns where table_schema='public' and table_name in ('tenants','storage_policies','api_keys','projects') order by table_name, ordinal_position;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tablename, indexname from pg_indexes where schemaname='public' and tablename in ('tenants','storage_policies','api_keys','projects') order by tablename, indexname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tc.table_name, tc.constraint_name, tc.constraint_type from information_schema.table_constraints tc where tc.table_schema='public' and tc.table_name in ('tenants','storage_policies','api_keys','projects') order by tc.table_name, tc.constraint_name;"`
  - `docker compose down`
- Results:
  - Merge precheck showed only accepted T02 core schema files before commit.
  - Commit created: `7091001 Add T02 core schema`.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 38 files already formatted.
  - `uv run mypy src tests`: passed; no issues found in 33 source files.
  - `uv run pytest`: passed; 79 tests passed with 1 existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; reran ruff, format check, mypy, and pytest with the same 79 passed / 1 warning result.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed; `upload-control-plane-postgres-1` reached `healthy`.
  - `make migrate`: passed; database remained/upgraded at Alembic head.
  - `alembic_version`: `20260624_0002`.
  - `public` tables: `alembic_version`, `api_keys`, `projects`, `storage_policies`, `tenants`.
  - `public` enum types: `dataset_status`, `device_status`, `outbox_status`, `permission_effect`, `recovery_status`, `upload_object_status`, `upload_part_status`, `upload_session_status`, `upload_task_status`, `validation_status`.
  - Column inspection confirmed UUID PK/FK columns, `api_keys.key_hash`, `api_keys.scopes` as `text[]`, `jsonb` metadata fields, and timestamp fields on the four core tables.
  - Index inspection confirmed `idx_api_keys_tenant_id`, `idx_projects_tenant_status`, `idx_storage_policies_tenant_status`, PK indexes, and unique indexes.
  - Constraint inspection confirmed PKs, FKs, unique constraints, and non-null checks for the four core tables.
  - `docker compose down`: passed.
- Commands not run and why:
  - None.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload API, file-byte endpoint, MQTT adapter, or storage proxy path was added.
- Clients receive no MinIO/S3 credentials: preserved. No client-facing storage credential behavior was added.
- Complete uses object storage ListParts as authority: preserved. Upload completion remains unimplemented.
- Authorization uses permission_grants: preserved for this segment. No auth shortcut was added; `permission_grants` remains absent for the next schema segment.
- Internal IDs remain UUIDs: satisfied for this segment. The four committed business tables use UUID primary keys and UUID foreign keys where applicable.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway code was added.

## Risks and Follow-up

- Remaining risks:
  - This is an accepted core schema segment, not full T02 persistence completion.
  - Downstream T02 dataset-governance schema must add `datasets`, tag tables, `devices`, and `permission_grants` in a later migration after `20260624_0002`.
- Known gaps:
  - Seed data and later persistence tables remain intentionally unimplemented.
- Suggested next agent:
  - T02 dataset-governance schema implementation agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The T02 dataset-governance schema agent can start from `main` at or after commit `7091001` and Alembic revision `20260624_0002`.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
