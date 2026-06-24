# Handoff: T02 upload lifecycle schema

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 16:28 +08:00
Finished: 2026-06-24 16:36 +08:00

## Scope

- Intended scope:
  - Add SQLAlchemy models and a follow-up Alembic migration after `20260624_0003` for `upload_tasks`, `upload_objects`, `upload_sessions`, and `upload_parts`.
  - Preserve UUID internal PK/FK strategy.
  - Add PRD-required FKs to tenants, projects, datasets, devices, storage policies, upload tasks, upload objects, and upload sessions.
  - Keep `source_device_id` as registered device UUID FK and `source_device_code` as text trace metadata.
  - Add PRD section 14 indexes, constraints, and upload task/session idempotency uniqueness.
  - Use existing enum types for upload task/object/session/part status columns.
- Explicitly out of scope:
  - Rewriting migrations `20260624_0001`, `20260624_0002`, or `20260624_0003`.
  - `upload_batches` or any `batch_id` ownership path.
  - `validation_results`, `upload_events`, `audit_events`, `outbox_events`, or `idempotency_records`.
  - Seed data.
  - API routes, auth dependencies, storage adapter, upload/file-byte endpoints, or MinIO multipart operations.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1627-T02-merge-dataset-governance-schema-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - Current infrastructure persistence models and migrations.

## Changes

- Files changed:
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `src/upload_control_plane/infrastructure/db/__init__.py`
  - `migrations/versions/20260624_0004_upload_lifecycle_schema.py`
  - `tests/infrastructure/test_alembic_config.py`
  - `tests/infrastructure/test_upload_lifecycle_schema.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1636-T02-implementation-upload-lifecycle-schema-accepted.md`
- Behavior changed:
  - Alembic head is now `20260624_0004`.
  - SQLAlchemy metadata now includes the four upload lifecycle schema tables.
  - Upload task/session status columns use existing enum-backed PostgreSQL types.
  - Upload task/session idempotency uniqueness is represented on the rows as specified in PRD section 14; no standalone idempotency table was added.
- Compatibility notes:
  - Earlier migrations were not modified.
  - `upload_objects.upload_session_id` is retained as a UUID column without an FK because PRD 14.11 does not declare that FK; the authoritative link declared in PRD 14.12 is `upload_sessions.upload_object_id REFERENCES upload_objects(id)`.

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
  - `docker compose exec -T postgres psql -U upload -d upload -c "select version_num from alembic_version;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name from information_schema.tables where table_schema = 'public' and table_name in ('upload_tasks','upload_objects','upload_sessions','upload_parts') order by table_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tablename, indexname from pg_indexes where schemaname='public' and tablename in ('upload_tasks','upload_objects','upload_sessions','upload_parts') order by tablename, indexname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select conrelid::regclass as table_name, conname, contype, pg_get_constraintdef(oid) as definition from pg_constraint where conrelid::regclass::text in ('upload_tasks','upload_objects','upload_sessions','upload_parts') order by conrelid::regclass::text, conname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name, column_name, data_type, udt_name from information_schema.columns where table_schema='public' and table_name in ('upload_tasks','upload_objects','upload_sessions','upload_parts') and column_name in ('id','tenant_id','project_id','dataset_id','upload_task_id','upload_object_id','session_id','storage_policy_id','source_device_id','source_device_code','status','idempotency_key','metadata','file_size_bytes','part_size_bytes','part_count','part_number') order by table_name, ordinal_position;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select typname from pg_type t join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and t.typtype='e' and typname in ('upload_task_status','upload_object_status','upload_session_status','upload_part_status') order by typname;"`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 42 files already formatted.
  - `uv run mypy src tests`: passed; no issues found in 35 source files.
  - `uv run pytest`: passed; 94 tests passed with 1 existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with the same 94 passed / 1 warning result.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed; ran `20260624_0003 -> 20260624_0004`.
  - `alembic_version`: `20260624_0004`.
  - Public tables confirmed: `upload_objects`, `upload_parts`, `upload_sessions`, `upload_tasks`.
  - Indexes confirmed for all four target tables, including PRD indexes and unique-backed indexes for upload task/session idempotency and session object key uniqueness.
  - Constraints confirmed, including UUID PK/FK constraints, `upload_tasks` idempotency uniqueness, `upload_sessions` idempotency/object-key uniqueness, session size/count checks, and upload part number/expected-size checks.
  - Column inspection confirmed UUID internal IDs/FKs, enum-backed status columns, `source_device_id` UUID, `source_device_code` text, `metadata` JSONB, and idempotency keys as text.
  - Enum inspection confirmed existing public enum types: `upload_task_status`, `upload_object_status`, `upload_session_status`, and `upload_part_status`.
  - `docker compose down`: passed.
- Commands not run and why:
  - None.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No route, byte endpoint, storage proxy, or MQTT adapter was added.
- Clients receive no MinIO/S3 credentials: preserved. No credential exposure behavior was added.
- Complete uses object storage ListParts as authority: preserved. Completion remains out of scope; schema does not make DB part rows authoritative for completion.
- Authorization uses permission_grants: preserved. This segment consumes existing project/device/resource FK shape and does not alter authorization.
- Internal IDs remain UUIDs: satisfied. New primary keys and foreign keys use UUID; storage upload ID, object key, device code, and idempotency key remain text metadata/transport fields.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway work was added.

## Risks and Follow-up

- Remaining risks:
  - Runtime services do not use these models yet.
  - This migration follows PRD 14 exactly for `upload_objects.upload_session_id` as a plain UUID column; if a later design wants a reverse FK, add it explicitly in a future migration after resolving circular ownership semantics.
- Known gaps:
  - No seed rows or seed script in this checkpoint.
  - No validation/audit/outbox/idempotency_records schema in this checkpoint.
- Suggested next agent:
  - Next T02 schema agent should start `Persistence seed` after this implementation is validated and accepted by a T02 Validation Agent.
  - The validation agent should independently verify migration from an empty Postgres database to head `20260624_0004`, metadata parity, absence of `upload_batches`/`batch_id`/`idempotency_records`, and catalog evidence for FKs/indexes/constraints.
  - The seed agent should not start until validation accepts this upload lifecycle schema checkpoint.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T02 validation for upload lifecycle schema can start from Alembic head `20260624_0004`.
  - After validation acceptance, T02 Persistence seed can start.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not rewrite earlier migrations; repair by adding a follow-up migration or correcting this segment before validation acceptance.
  - Do not introduce `upload_batches`, `batch_id`, seed data, API endpoints, storage byte paths, or standalone idempotency records in this schema segment.
