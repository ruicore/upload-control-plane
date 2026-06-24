# Handoff: T02 validation/audit/outbox/idempotency records schema

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 16:50 +08:00
Finished: 2026-06-24 16:50 +08:00

## Scope

- Intended scope:
  - Add SQLAlchemy models and a new Alembic migration after `20260624_0004`.
  - Cover `dataset_validation_results`, `upload_events`, `audit_events`, `outbox_events`, and `idempotency_records`.
  - Preserve UUID internal PK/FK strategy, enum-backed `validation_status` and `outbox_status`, PRD indexes, idempotency uniqueness, and expiry/dispatch lookup indexes.
  - Add metadata/migration tests and inspect local PostgreSQL after migration.
- Explicitly out of scope:
  - Seed data.
  - Worker behavior, outbox dispatcher behavior, event publishing, validation parsing, MinIO multipart operations, API routes, auth dependencies, storage adapters, and upload/file-byte endpoints.
  - Rewriting migrations `20260624_0001` through `20260624_0004`.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T02 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1643-T02-merge-upload-lifecycle-schema-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md` validation/audit/outbox sections
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md` sections 14.14-14.18
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md` idempotency/outbox notes
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md` outbox/audit/validation testing and failure notes
  - Current infrastructure persistence models, migrations, and tests

## Changes

- Files changed:
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `src/upload_control_plane/infrastructure/db/__init__.py`
  - `migrations/versions/20260624_0005_validation_audit_outbox_idempotency_schema.py`
  - `tests/infrastructure/test_records_schema.py`
  - `tests/infrastructure/test_alembic_config.py`
  - `tests/infrastructure/test_upload_lifecycle_schema.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1650-T02-implementation-records-schema-accepted.md`
- Behavior changed:
  - Metadata now includes the five records tables.
  - Alembic head advances from `20260624_0004` to `20260624_0005`.
  - `upload_events` includes nullable FKs for project, dataset, upload task, upload object, and session traceability.
  - `outbox_events` keeps generic `aggregate_type`/`aggregate_id` without a polymorphic FK, as PRD makes domain tables the source of truth.
  - `audit_events.resource_id` remains text for unified audit across resource types.
- Compatibility notes:
  - Existing migrations were not modified.
  - Existing enum types are reused with `create_type=False`.
  - No seed data or runtime behavior was added.

## Verification

- Commands run:
  - `uv run ruff format src\upload_control_plane\infrastructure\db\models.py src\upload_control_plane\infrastructure\db\__init__.py migrations\versions\20260624_0005_validation_audit_outbox_idempotency_schema.py tests\infrastructure\test_upload_lifecycle_schema.py tests\infrastructure\test_records_schema.py`
  - `uv run ruff check --fix src\upload_control_plane\infrastructure\db\__init__.py tests\infrastructure\test_records_schema.py`
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
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name, column_name, data_type, udt_name from information_schema.columns where table_schema='public' and table_name in ('dataset_validation_results','upload_events','audit_events','outbox_events','idempotency_records') and column_name in ('id','tenant_id','project_id','dataset_id','upload_task_id','upload_object_id','session_id','aggregate_id','status','key','request_fingerprint','expires_at','next_attempt_at','payload','metadata','response_body') order by table_name, ordinal_position;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select typname, enumlabel from pg_type t join pg_enum e on t.oid=e.enumtypid join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and typname in ('validation_status','outbox_status') order by typname, enumsortorder;"`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 44 files already formatted.
  - `uv run mypy src tests`: passed; no issues in 36 source files.
  - `uv run pytest`: passed; 101 passed, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with 101 passed / 1 warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed; Alembic ran `20260624_0004 -> 20260624_0005`.
  - `alembic_version`: `20260624_0005`.
  - Target tables present: `audit_events`, `dataset_validation_results`, `idempotency_records`, `outbox_events`, `upload_events`.
  - Catalog inspection confirmed expected indexes, PK/FK/unique constraints, UUID internal IDs/FKs, JSONB payload/metadata columns, `validation_status` and `outbox_status` enum-backed status columns, outbox status/next-attempt and aggregate lookup indexes, and idempotency `(tenant_id, key)` uniqueness plus expiry index.
  - `docker compose down`: passed.
- Commands not run and why:
  - None.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. Schema-only change; no API, MQTT, storage proxy, or byte path added.
- Clients receive no MinIO/S3 credentials: preserved. No credential exposure behavior added.
- Complete uses object storage ListParts as authority: preserved. Complete behavior remains out of scope.
- Authorization uses permission_grants: preserved. No auth or permission logic changed.
- Internal IDs remain UUIDs: satisfied for new primary keys and FK columns; generic audit resource IDs remain text by unified audit design, and outbox aggregate IDs remain UUID without polymorphic FK.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or Go gateway work added.

## Risks and Follow-up

- Remaining risks:
  - Runtime services do not yet write these records; this is expected for this T02 schema segment.
  - `upload_events` intentionally extends PRD 14.15 with upload task/object FKs for lifecycle traceability requested in this scope.
- Known gaps:
  - Seed data is not included.
  - Idempotency conflict handling, outbox dispatch/retry, audit recording, and validation worker behavior remain future tasks.
- Suggested next agent:
  - Next T02 agent should be the dev seed script implementation agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T02 dev seed script can start from `main` at Alembic head `20260624_0005`.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not modify accepted migrations `20260624_0001` through `20260624_0004`.
  - Do not add upload file-byte handling, storage proxying, MinIO/S3 credential exposure, worker behavior, or API behavior in schema-only work.
