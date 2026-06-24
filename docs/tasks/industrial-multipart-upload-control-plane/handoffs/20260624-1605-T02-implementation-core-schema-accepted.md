# Handoff: T02 implementation core schema

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 15:57 +08:00
Finished: 2026-06-24 16:05 +08:00

## Scope

- Intended scope:
  - Add SQLAlchemy 2.x models for `tenants`, `storage_policies`, `api_keys`, and `projects`.
  - Add a follow-up Alembic migration after `20260624_0001` for PRD enum types and these four tables.
  - Preserve UUID internal primary and foreign key strategy.
  - Store API key verification material as `key_hash`; do not store raw API keys.
  - Add metadata/migration structure tests where practical.
- Explicitly out of scope:
  - `datasets`, tags, devices, `permission_grants`, upload tasks, upload objects, upload sessions, upload parts, validation/audit/outbox/idempotency, seed data, routes, auth dependencies, storage adapter, and upload/file-byte endpoints.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1557-T02-merge-persistence-base-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - Current infrastructure persistence modules and migrations.

## Changes

- Files changed:
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `src/upload_control_plane/infrastructure/db/__init__.py`
  - `migrations/versions/20260624_0002_core_schema.py`
  - `tests/infrastructure/test_alembic_config.py`
  - `tests/infrastructure/test_core_schema.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1605-T02-implementation-core-schema-accepted.md`
- Behavior changed:
  - `Base.metadata` now contains the four core schema tables for Alembic autogenerate and model inspection.
  - Alembic head is now `20260624_0002`.
  - Migration creates 10 PRD enum types and only `tenants`, `storage_policies`, `api_keys`, and `projects`.
- Compatibility notes:
  - Base migration `20260624_0001` was not modified.
  - No seed rows or API behavior were added.
  - `permission_grants` remains absent by design for the next schema segment.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up -d postgres`
  - Wait for `upload-control-plane-postgres-1` health status `healthy`
  - `make migrate`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select version_num from alembic_version;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name from information_schema.tables where table_schema = 'public' order by table_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select typname from pg_type t join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and t.typtype='e' order by typname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name, column_name, data_type, udt_name from information_schema.columns where table_schema='public' and table_name in ('tenants','storage_policies','api_keys','projects') order by table_name, ordinal_position;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tablename, indexname from pg_indexes where schemaname='public' and tablename in ('tenants','storage_policies','api_keys','projects') order by tablename, indexname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tc.table_name, tc.constraint_name, tc.constraint_type from information_schema.table_constraints tc where tc.table_schema='public' and tc.table_name in ('tenants','storage_policies','api_keys','projects') order by tc.table_name, tc.constraint_name;"`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 38 files already formatted.
  - `uv run mypy src tests`: passed; no issues found in 33 source files.
  - `uv run pytest`: passed; 79 tests passed, 1 existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; reran ruff, format check, mypy, and pytest with 79 tests passed and the same warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed; container reached `healthy`.
  - `make migrate`: passed; ran upgrade `20260624_0001 -> 20260624_0002`.
  - `alembic_version`: `20260624_0002`.
  - `public` tables: `alembic_version`, `api_keys`, `projects`, `storage_policies`, `tenants`.
  - `public` enum types: `dataset_status`, `device_status`, `outbox_status`, `permission_effect`, `recovery_status`, `upload_object_status`, `upload_part_status`, `upload_session_status`, `upload_task_status`, `validation_status`.
  - Key column checks confirmed UUID PK/FKs, `jsonb` metadata fields, `api_keys.key_hash`, `api_keys.scopes` as text array, and no raw API key column.
  - Index checks confirmed PRD indexes plus PK/unique indexes.
  - `docker compose down`: passed.
- Commands not run and why:
  - No seed command was run because seed data is out of scope for this segment.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No API, upload handler, MQTT adapter, or file-byte path was added.
- Clients receive no MinIO/S3 credentials: preserved. No client-facing storage credential behavior was added.
- Complete uses object storage ListParts as authority: preserved. Upload completion remains unimplemented.
- Authorization uses permission_grants: preserved. No auth shortcut was added; `permission_grants` is intentionally left for the next schema segment.
- Internal IDs remain UUIDs: satisfied for this segment. Four business tables use UUID primary keys and UUID foreign keys.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway code was added.

## Risks and Follow-up

- Remaining risks:
  - Enum types are created before their later tables so downstream schema migrations can reuse them; current models do not yet map the future enum-backed tables.
  - `status` fields for this segment follow the PRD as `TEXT`; enforcement is left to service logic or later explicit checks if the PRD changes.
- Known gaps:
  - No datasets, tags, devices, permission grants, upload lifecycle tables, validation/audit/outbox/idempotency tables, or seed data exist yet.
- Suggested next agent:
  - T02 Persistence schema implementation agent for dataset-governance schema: `datasets`, tag tables, `devices`, and `permission_grants`.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The next T02 schema agent can start from Alembic revision `20260624_0002` and add a new migration after it.
  - Next schema agent should follow with `datasets`, tag tables, `devices`, and `permission_grants`, including UUID FKs to `tenants`, `projects`, and `storage_policies` where required.
  - Next schema agent must not implement upload task/object/session/part tables yet unless Master explicitly expands that segment.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
