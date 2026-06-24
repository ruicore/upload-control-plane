# Handoff: T02 upload lifecycle schema validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 16:38 +08:00
Finished: 2026-06-24 16:40 +08:00

## Scope

- Intended scope:
  - Independently validate the uncommitted T02 upload lifecycle schema implementation.
  - Verify SQLAlchemy models, Alembic migration, tests, migration order, schema scope, UUID FK strategy, PRD indexes/constraints, and absence of out-of-scope tables/API/storage behavior.
- Explicitly out of scope:
  - Modifying implementation code, tests, migrations, configuration, README, or PRD.
  - Repairing issues.
  - Adding seed data.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T02 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1636-T02-implementation-upload-lifecycle-schema-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md` sections 14.10-14.13
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `migrations/versions/20260624_0004_upload_lifecycle_schema.py`
  - `tests/infrastructure/test_upload_lifecycle_schema.py`

## Validation Findings

- Migration order is valid: `20260624_0004_upload_lifecycle_schema.py` has `down_revision = "20260624_0003"`.
- Older migrations were not rewritten; `git diff --name-only -- migrations/versions/20260624_0001* migrations/versions/20260624_0002* migrations/versions/20260624_0003*` returned no paths.
- New upload lifecycle schema scope is limited to `upload_tasks`, `upload_objects`, `upload_sessions`, and `upload_parts`.
- UUID internal PK/FK strategy is represented:
  - `upload_tasks`, `upload_objects`, and `upload_sessions` use UUID `id` primary keys.
  - `upload_parts` uses composite primary key `(session_id, part_number)` with UUID `session_id`.
  - FKs target `tenants`, `projects`, `datasets`, `devices`, `storage_policies`, and the upload lifecycle parent tables as required by PRD 14.10-14.13.
- `source_device_id` in `upload_tasks` and `upload_sessions` is UUID FK to `devices(id)`; `source_device_code` is plain text metadata.
- No `upload_batches` table and no `batch_id` ownership path were found in SQLAlchemy metadata or the migration.
- PRD indexes and constraints are represented:
  - Upload task project/status and source-device indexes.
  - Upload object task/status and dataset indexes.
  - Upload session tenant/status, project, dataset, task, object, expires, storage upload ID, source-device indexes.
  - Upload part session/status index.
  - Row-level idempotency uniqueness exists on `upload_tasks(tenant_id, idempotency_key)` and `upload_sessions(tenant_id, idempotency_key)`.
  - Session object key uniqueness and part/session bounds checks exist.
- Status columns use existing PostgreSQL enum types: `upload_task_status`, `upload_object_status`, `upload_session_status`, and `upload_part_status`.
- No `validation_results`, `dataset_validation_results`, `upload_events`, `audit_events`, `outbox_events`, or `idempotency_records` tables are present in this schema segment.
- No upload API/file-byte endpoint or MinIO multipart behavior was added by this segment.

## Verification

- Commands run:
  - `git status --short --branch`
  - `rg -n "upload_batches|batch_id|idempotency_records|validation_results|upload_events|audit_events|outbox_events|create_multipart|complete_multipart|presign|UploadFile|File\(|MinIO|boto3|botocore|/v1/uploads|upload-tasks" src tests migrations docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1636-T02-implementation-upload-lifecycle-schema-accepted.md`
  - `git diff --name-only -- migrations/versions/20260624_0001* migrations/versions/20260624_0002* migrations/versions/20260624_0003*`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up -d postgres`
  - `make migrate`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select version_num from alembic_version;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name from information_schema.tables where table_schema = 'public' and table_name like 'upload_%' order by table_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name from information_schema.tables where table_schema = 'public' and table_name in ('validation_results','dataset_validation_results','upload_events','audit_events','outbox_events','idempotency_records','upload_batches') order by table_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tablename, indexname, indexdef from pg_indexes where schemaname='public' and tablename in ('upload_tasks','upload_objects','upload_sessions','upload_parts') order by tablename, indexname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select conrelid::regclass as table_name, conname, contype, pg_get_constraintdef(oid) as definition from pg_constraint where conrelid::regclass::text in ('upload_tasks','upload_objects','upload_sessions','upload_parts') order by conrelid::regclass::text, contype, conname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name, column_name, data_type, udt_name, is_nullable, column_default from information_schema.columns where table_schema='public' and table_name in ('upload_tasks','upload_objects','upload_sessions','upload_parts') order by table_name, ordinal_position;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select typname, enumlabel from pg_type t join pg_enum e on t.oid=e.enumtypid where typname in ('upload_task_status','upload_object_status','upload_session_status','upload_part_status') order by typname, enumsortorder;"`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 42 files already formatted.
  - `uv run mypy src tests`: passed; no issues found in 35 source files.
  - `uv run pytest`: passed; 94 passed, 1 existing Starlette/httpx TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with 94 passed and the same warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed.
  - `alembic_version`: `20260624_0004`.
  - Upload tables present: `upload_objects`, `upload_parts`, `upload_sessions`, `upload_tasks`.
  - Excluded tables present: none.
  - Catalog inspection confirmed expected indexes, constraints, UUID/text/jsonb column types, and enum values.
  - `docker compose down`: passed.
- Commands not run and why:
  - None.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload API, byte endpoint, storage proxy, MQTT adapter, or multipart operation was added.
- Clients receive no MinIO/S3 credentials: preserved. No credential exposure behavior was added.
- Complete uses object storage ListParts as authority: preserved. Complete behavior remains out of scope for this schema-only segment.
- Authorization uses permission_grants: preserved. This segment does not alter auth logic or permission grants.
- Internal IDs remain UUIDs: satisfied for new primary and foreign key columns; device code, storage upload ID, object key, and idempotency key remain metadata/transport text.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or Go gateway implementation was added.

## Risks and Follow-up

- Remaining risks:
  - Runtime services do not consume these tables yet; that is expected for this schema segment.
  - `make migrate` was run against the local compose Postgres state available in this workspace; the implementation test suite and Alembic head checks also cover migration wiring.
- Known gaps:
  - Seed data is not present in this segment.
  - Validation/audit/outbox/idempotency record tables are not present in this segment.
- Suggested next agent:
  - Next T02 schema segment should be validation/audit/outbox/idempotency records, not seed yet.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Master review/merge can proceed for the upload lifecycle schema segment.
  - Continue T02 schema with validation/audit/outbox/idempotency records before seed.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
