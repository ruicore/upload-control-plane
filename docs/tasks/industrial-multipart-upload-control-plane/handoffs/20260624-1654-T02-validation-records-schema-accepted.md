# Handoff: T02 records schema validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 16:50 +08:00
Finished: 2026-06-24 16:54 +08:00

## Scope

- Intended scope:
  - Independently validate the uncommitted validation/audit/outbox/idempotency records schema implementation.
  - Confirm the new migration follows `20260624_0004` and does not rewrite older migrations.
  - Confirm the implementation is schema-only and limited to records persistence.
- Explicitly out of scope:
  - Implementation changes, tests changes, migration edits, config edits, README/PRD edits, seed data, API behavior, storage behavior, outbox dispatch behavior, and endpoint idempotency behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T02 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1650-T02-implementation-records-schema-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md` validation/audit/outbox sections
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md` sections 14.14-14.18
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md` idempotency/outbox notes
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `migrations/versions/20260624_0005_validation_audit_outbox_idempotency_schema.py`
  - `tests/infrastructure/test_records_schema.py`

## Validation Findings

- Migration chain:
  - `20260624_0005_validation_audit_outbox_idempotency_schema.py` declares `revision = 20260624_0005` and `down_revision = 20260624_0004`.
  - `git diff --name-only -- migrations/versions` returned no tracked old migration modifications.
- Scoped tables:
  - The new migration creates the expected records tables: `dataset_validation_results`, `upload_events`, `audit_events`, `outbox_events`, and `idempotency_records`.
  - No seed rows were present in the five records tables after migration.
- UUID PK/FK strategy:
  - All five records tables use UUID `id` primary keys.
  - Expected FKs exist to tenants/projects/datasets/upload tasks/upload objects/upload sessions where applicable.
  - `outbox_events.aggregate_id` is UUID without a polymorphic FK, matching the PRD statement that domain tables remain source of truth.
  - `audit_events.resource_id` remains text for unified cross-resource audit references.
- Status enums:
  - `dataset_validation_results.status` uses `validation_status`.
  - `outbox_events.status` uses `outbox_status`.
- Outbox schema:
  - `outbox_events` includes status, attempts, `next_attempt_at`, `locked_until`, `last_error`, `delivered_at`, JSONB payload, status/next-attempt index, and aggregate lookup index.
  - No dispatcher behavior was added.
- Idempotency schema:
  - `idempotency_records` includes key, request method/path, request fingerprint, response status/body, `locked_until`, timestamps, and `expires_at`.
  - `(tenant_id, key)` uniqueness and `expires_at` index are present.
  - No endpoint idempotency behavior was added.
- Negative scope checks:
  - `rg` checks found no new upload API/file-byte endpoint, MinIO multipart operation, storage proxying, or outbox dispatcher implementation in this slice.
  - Existing hits were prior domain/config/migration references or handoff text, not new runtime storage/API behavior.

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
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name from information_schema.tables where table_schema='public' and table_name in ('dataset_validation_results','upload_events','audit_events','outbox_events','idempotency_records') order by table_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tablename, indexname from pg_indexes where schemaname='public' and tablename in ('dataset_validation_results','upload_events','audit_events','outbox_events','idempotency_records') order by tablename, indexname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select conrelid::regclass as table_name, conname, contype from pg_constraint where conrelid::regclass::text in ('dataset_validation_results','upload_events','audit_events','outbox_events','idempotency_records') order by conrelid::regclass::text, conname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name, column_name, data_type, udt_name, is_nullable from information_schema.columns where table_schema='public' and table_name in ('dataset_validation_results','upload_events','audit_events','outbox_events','idempotency_records') and column_name in ('id','tenant_id','project_id','dataset_id','upload_task_id','upload_object_id','session_id','aggregate_id','status','key','request_fingerprint','expires_at','locked_until','next_attempt_at','payload','metadata','response_body') order by table_name, ordinal_position;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select typname, enumlabel from pg_type t join pg_enum e on t.oid=e.enumtypid join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and typname in ('validation_status','outbox_status') order by typname, enumsortorder;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tc.table_name, tc.constraint_name, string_agg(kcu.column_name, ',' order by kcu.ordinal_position) as columns from information_schema.table_constraints tc join information_schema.key_column_usage kcu on tc.constraint_schema=kcu.constraint_schema and tc.constraint_name=kcu.constraint_name where tc.table_schema='public' and tc.table_name='idempotency_records' and tc.constraint_type='UNIQUE' group by tc.table_name, tc.constraint_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select 'dataset_validation_results' as table_name, count(*) from dataset_validation_results union all select 'upload_events', count(*) from upload_events union all select 'audit_events', count(*) from audit_events union all select 'outbox_events', count(*) from outbox_events union all select 'idempotency_records', count(*) from idempotency_records order by table_name;"`
  - `docker compose down`
  - `rg` checks for forbidden batch/file-byte/storage behavior.
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 44 files already formatted.
  - `uv run mypy src tests`: passed; no issues in 36 source files.
  - `uv run pytest`: passed; 101 passed, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with 101 passed / 1 warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed.
  - `alembic_version`: `20260624_0005`.
  - Target tables present: `audit_events`, `dataset_validation_results`, `idempotency_records`, `outbox_events`, `upload_events`.
  - Target indexes present, including outbox status/next-attempt and aggregate indexes plus idempotency expiry index.
  - Target constraints present, including idempotency `(tenant_id,key)` unique constraint and expected FKs.
  - Target status enum labels present for `validation_status` and `outbox_status`.
  - Records table row counts were all zero.
  - `docker compose down`: passed.
- Commands not run and why:
  - None.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. This validation found schema-only records changes and no file-byte endpoint.
- Clients receive no MinIO/S3 credentials: preserved. No credential exposure was added.
- Complete uses object storage ListParts as authority: preserved. No complete behavior was added.
- Authorization uses permission_grants: preserved. No auth behavior was changed.
- Internal IDs remain UUIDs: accepted for the new tables' internal PK/FK strategy; unified audit `resource_id` remains text by PRD shape and outbox `aggregate_id` remains UUID without polymorphic FK.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway behavior was added.

## Risks and Follow-up

- Remaining risks:
  - Runtime writers for validation results, audit events, upload events, outbox events, and idempotency responses are not implemented yet; this is expected for this schema-only slice.
- Known gaps:
  - Dev seed data remains the next T02 slice.
  - Outbox dispatcher, endpoint idempotency conflict handling, audit recording, and validation worker behavior remain future tasks.
- Suggested next agent:
  - T02 seed implementation agent after this records schema segment is merged.

## Recovery Notes

- If accepted, next dependency unlocked:
  - This records schema segment can be merged.
  - After merge, the T02 seed agent can start from Alembic head `20260624_0005`.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
