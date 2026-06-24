# Handoff: T02 dataset-governance schema

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 16:11 +08:00
Finished: 2026-06-24 16:19 +08:00

## Scope

- Intended scope:
  - Add the next T02 persistence schema segment after Alembic revision `20260624_0002`.
  - Add SQLAlchemy models and Alembic migration for `datasets`, `tag_categories`, `tags`, `dataset_tags`, `devices`, and `permission_grants`.
  - Preserve UUID primary/foreign key strategy and PRD section 14 indexes/constraints for these tables.
  - Verify metadata, migration structure, and local PostgreSQL migration result.
- Explicitly out of scope:
  - Editing existing migrations `20260624_0001` or `20260624_0002`.
  - Upload tasks, upload objects, upload sessions, upload parts, validation results, audit events, upload events, outbox events, idempotency records.
  - Seed data, API routes, auth dependencies, storage adapter behavior, MQTT, Go, or byte-upload endpoints.
  - `device_project_grants`; this segment uses `permission_grants` as the authorization source of truth. A future agent may add a dedicated join table only if Master explicitly expands scope.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T02 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1611-T02-merge-core-schema-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md` sections 14.6-14.9
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - Current `src/upload_control_plane/infrastructure/db/` models/base/session/migration code and existing Alembic revisions.

## Changes

- Files changed:
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `src/upload_control_plane/infrastructure/db/__init__.py`
  - `migrations/versions/20260624_0003_dataset_governance_schema.py`
  - `tests/infrastructure/test_alembic_config.py`
  - `tests/infrastructure/test_dataset_governance_schema.py`
  - This handoff.
- Behavior changed:
  - Alembic head is now `20260624_0003`.
  - SQLAlchemy metadata now exposes dataset governance tables in addition to the core schema.
  - `datasets.source_device_id` is a UUID FK to `devices.id`.
  - `datasets.source_device_code` is retained as text trace metadata only; it is not present in `permission_grants` and is not an authorization subject.
  - `permission_grants` supports resource-scoped authorization with UUID subject/resource IDs, `permission_code`, `ALLOW`/`DENY`, `expires_at`, PRD subject/resource/permission/expiry indexes, and uniqueness across tenant/subject/resource/permission/effect.
- Compatibility notes:
  - Existing migrations `20260624_0001` and `20260624_0002` were not rewritten.
  - The `device_status`, `dataset_status`, `validation_status`, `recovery_status`, and `permission_effect` enum types created by `20260624_0002` are reused.
  - Upload-specific `source_device_id/source_device_code` columns for upload tasks remain for the later upload lifecycle schema segment.

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
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name from information_schema.tables where table_schema = 'public' order by table_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tablename, indexname from pg_indexes where schemaname='public' and tablename in ('datasets','tag_categories','tags','dataset_tags','devices','permission_grants') order by tablename, indexname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select tc.table_name, tc.constraint_name, tc.constraint_type from information_schema.table_constraints tc where tc.table_schema='public' and tc.table_name in ('datasets','tag_categories','tags','dataset_tags','devices','permission_grants') order by tc.table_name, tc.constraint_name;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name, column_name, data_type, udt_name from information_schema.columns where table_schema='public' and table_name in ('datasets','devices','permission_grants') and column_name in ('id','tenant_id','project_id','status','source_device_id','source_device_code','validation_status','recovery_status','effect','expires_at') order by table_name, ordinal_position;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select typname from pg_type t join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and t.typtype='e' order by typname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select conrelid::regclass as table_name, conname, pg_get_constraintdef(oid) as definition from pg_constraint where conrelid::regclass::text in ('datasets','permission_grants') and (conname like 'fk_datasets_source_device%' or conname like 'ck_permission_grants%') order by conrelid::regclass::text, conname;"`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 40 files already formatted.
  - `uv run mypy src tests`: passed; no issues found in 34 source files.
  - `uv run pytest`: passed; 86 tests passed with 1 existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; reran ruff, format check, mypy, and pytest with the same 86 passed / 1 warning result.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed; `upload-control-plane-postgres-1` started.
  - `make migrate`: passed; Alembic ran `20260624_0002 -> 20260624_0003`.
  - `alembic_version`: `20260624_0003`.
  - Public tables: `alembic_version`, `api_keys`, `dataset_tags`, `datasets`, `devices`, `permission_grants`, `projects`, `storage_policies`, `tag_categories`, `tags`, `tenants`.
  - New indexes confirmed for datasets, devices, tags, and permission grants, including `idx_datasets_object_unique`, `idx_datasets_source_device`, `idx_permission_grants_subject`, `idx_permission_grants_resource`, `idx_permission_grants_permission`, and `idx_permission_grants_expires_at`.
  - Constraints confirmed, including `fk_datasets_source_device_id_devices`, permission-grant subject/resource type checks, PKs, FKs, and unique constraints.
  - Column inspection confirmed UUID internal IDs/FKs, enum-backed dataset/device/permission status/effect columns, `source_device_code` as `text`, and `expires_at` as `timestamptz`.
  - Enum inspection confirmed the expected PRD enum types remain present.
  - `docker compose down`: passed.
- Commands not run and why:
  - None.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload API, byte endpoint, storage proxy, or MQTT adapter was added.
- Clients receive no MinIO/S3 credentials: preserved. No client credential behavior was added.
- Complete uses object storage ListParts as authority: preserved. Upload completion remains out of scope.
- Authorization uses permission_grants: satisfied for this segment. `permission_grants` is now the durable source of truth for resource-scoped permission codes.
- Internal IDs remain UUIDs: satisfied. New tables use UUID primary keys and UUID foreign keys; `device_code` and `source_device_code` remain external text fields.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway code was added.

## Risks and Follow-up

- Remaining risks:
  - This is still not full T02 completion because upload lifecycle, validation/audit/outbox/idempotency tables and seed data remain intentionally unimplemented.
  - `device_project_grants` from PRD 14.8 was not added because this agent's explicit scope listed only the six dataset-governance tables and required `permission_grants` for resource-scoped auth.
- Known gaps:
  - No seed rows or seed script changes.
  - No runtime services or repositories consume the new models yet.
- Suggested next agent:
  - Next T02 schema agent should implement the upload lifecycle schema segment after `20260624_0003`: `upload_tasks`, `upload_objects`, `upload_sessions`, and `upload_parts`.
  - That next agent must preserve `source_device_id UUID REFERENCES devices(id)` for upload-task source identity and keep `source_device_code` as external trace metadata only.
  - The next agent should not add validation results, audit/upload events, outbox, idempotency, seed data, API routes, auth dependencies, or storage behavior unless Master explicitly expands its scope.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T02 upload lifecycle schema implementation can start from Alembic head `20260624_0003`.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not rewrite earlier migrations; repair by adding a follow-up migration or correcting this segment.
