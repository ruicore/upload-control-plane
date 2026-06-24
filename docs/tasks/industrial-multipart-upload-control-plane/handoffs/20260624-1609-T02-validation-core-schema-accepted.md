# Handoff: T02 validation core schema

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 16:06 +08:00
Finished: 2026-06-24 16:09 +08:00

## Scope

- Intended scope:
  - Independently validate the T02 core schema implementation for tenants, storage policies, API keys, projects, and PRD enum types.
  - Verify migration order, UUID PK/FK strategy, API key hash-only storage, scoped table/index/constraint coverage, and absence of out-of-scope schema/API/storage behavior.
- Explicitly out of scope:
  - Any implementation repair or modification.
  - Datasets, tags, devices, permission grants, upload lifecycle tables, outbox, idempotency, seed data, upload API routes, file-byte handling, and MinIO multipart behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T02 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1605-T02-implementation-core-schema-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md` sections 14.0-14.5 and enum section 14.1
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `migrations/versions/20260624_0002_core_schema.py`
  - `tests/infrastructure/test_core_schema.py`

## Changes

- Files changed:
  - Added this validation handoff only.
- Behavior changed:
  - None.
- Compatibility notes:
  - Validation treated the existing uncommitted T02 implementation as the candidate under review.
  - No implementation, test, migration, configuration, README, or PRD file was modified.

## Verification

- Commands run:
  - `git status --short --branch`
  - `git diff --name-only -- migrations/versions/20260624_0001_persistence_base.py`
  - `rg -n "upload_batches|batch_id|datasets|tag_categories|tags|devices|permission_grants|upload_tasks|upload_objects|upload_sessions|upload_parts|dataset_validation_results|upload_events|audit_events|outbox_events|idempotency_records" src migrations tests docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1605-T02-implementation-core-schema-accepted.md`
  - `rg -n "UploadFile|File\(|multipart|MinIO|boto3|botocore|presign|create_multipart|complete_multipart|put_object|/upload|upload-tasks|file bytes|file-byte" src tests migrations`
  - `rg -n "create_table\(|CREATE TABLE|op\.create_table|__tablename__" src/upload_control_plane/infrastructure/db migrations/versions/20260624_0002_core_schema.py tests/infrastructure/test_core_schema.py`
  - `rg -n "key_hash|api_key|raw_key|secret|secret_key" src/upload_control_plane/infrastructure/db/models.py migrations/versions/20260624_0002_core_schema.py tests/infrastructure/test_core_schema.py`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up -d postgres`
  - Waited for `upload-control-plane-postgres-1` health status `healthy`
  - `make migrate`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select version_num from alembic_version;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name from information_schema.tables where table_schema = 'public' order by table_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select typname from pg_type t join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and t.typtype='e' order by typname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name, column_name, data_type, udt_name, is_nullable, column_default from information_schema.columns where table_schema='public' and table_name in ('tenants','storage_policies','api_keys','projects') order by table_name, ordinal_position;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tablename, indexname, indexdef from pg_indexes where schemaname='public' and tablename in ('tenants','storage_policies','api_keys','projects') order by tablename, indexname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tc.table_name, tc.constraint_name, tc.constraint_type from information_schema.table_constraints tc where tc.table_schema='public' and tc.table_name in ('tenants','storage_policies','api_keys','projects') order by tc.table_name, tc.constraint_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select e.enumtypid::regtype::text as enum_name, e.enumlabel from pg_enum e join pg_type t on t.oid=e.enumtypid join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' order by enum_name, e.enumsortorder;"`
  - `docker compose down`
- Results:
  - `git status --short --branch`: on `main...origin/main [ahead 7]` with uncommitted T02 implementation files present.
  - Base migration rewrite check: no diff for `migrations/versions/20260624_0001_persistence_base.py`.
  - Migration order: `20260624_0002_core_schema.py` has `down_revision = "20260624_0001"`.
  - Scoped schema search: implementation creates only `tenants`, `storage_policies`, `api_keys`, and `projects`; no dataset/tag/device/permission_grant/upload/outbox/idempotency tables are introduced in the T02 core schema implementation.
  - Upload/storage behavior search: no `UploadFile`, FastAPI `File(...)`, boto3/botocore/MinIO adapter, multipart storage operation, or file-byte endpoint was added under `src`, `tests`, or migrations. Existing `presign` hits are configuration/domain references and the schema field `presign_expiry_seconds`.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 38 files already formatted.
  - `uv run mypy src tests`: passed; no issues found in 33 source files.
  - `uv run pytest`: passed; 79 tests passed, 1 existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; reran ruff, format check, mypy, and pytest with 79 tests passed and the same warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed; container reached `healthy`.
  - `make migrate`: passed; local database was at Alembic head after migration command.
  - `alembic_version`: `20260624_0002`.
  - `public` tables: `alembic_version`, `api_keys`, `projects`, `storage_policies`, `tenants`.
  - `public` enum types: `dataset_status`, `device_status`, `outbox_status`, `permission_effect`, `recovery_status`, `upload_object_status`, `upload_part_status`, `upload_session_status`, `upload_task_status`, `validation_status`.
  - Enum labels matched PRD 14.1.
  - Column inspection confirmed UUID internal PK/FK columns, `timestamptz` timestamps, `jsonb` metadata fields, `api_keys.key_hash`, `api_keys.scopes` as `text[]`, and no raw secret/API-key column.
  - Index inspection confirmed `idx_storage_policies_tenant_status`, `idx_api_keys_tenant_id`, `idx_projects_tenant_status`, plus PK/unique indexes for PRD uniqueness.
  - Constraint inspection confirmed PKs, FKs, and unique constraints for scoped tables.
  - `docker compose down`: passed.
- Commands not run and why:
  - No seed command was run because this validation scope is core schema only and seed data is explicitly out of scope for this segment.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload API, file-byte endpoint, MQTT adapter, or storage proxy path was added.
- Clients receive no MinIO/S3 credentials: preserved. No client-facing storage credential behavior was added.
- Complete uses object storage ListParts as authority: preserved. Upload completion remains unimplemented.
- Authorization uses permission_grants: preserved for this segment. No auth shortcut was added; `permission_grants` remains absent and should be added in the next schema segment before T03 authorization work depends on it.
- Internal IDs remain UUIDs: satisfied for this segment. Four scoped business tables use UUID primary keys and UUID foreign keys where applicable.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway code was added.

## Risks and Follow-up

- Remaining risks:
  - The current local Postgres volume was already at Alembic head when `make migrate` ran, so the validation confirms head state and schema contents rather than showing a fresh upgrade log in this run.
  - The broader T02 README deliverables mention more persistence tables and seed data, but this implementation handoff intentionally split T02 into a core schema segment. This validation accepts that split only for the core segment.
- Known gaps:
  - No datasets, tag tables, devices, permission grants, upload lifecycle tables, validation/audit/outbox/idempotency tables, or seed data exist yet.
- Suggested next agent:
  - Start the next T02 schema segment for dataset governance: `datasets`, tag tables, `devices`, and `permission_grants`, with a migration after `20260624_0002`.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T02 core schema can be merged.
  - The next T02 schema segment can start from Alembic revision `20260624_0002`.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
