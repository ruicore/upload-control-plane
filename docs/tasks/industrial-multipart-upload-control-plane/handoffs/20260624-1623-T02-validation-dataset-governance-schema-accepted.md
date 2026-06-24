# Handoff: T02 dataset-governance schema validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 16:19 +08:00
Finished: 2026-06-24 16:23 +08:00

## Scope

- Intended scope:
  - Independently validate the uncommitted dataset-governance schema implementation.
  - Verify Alembic order, SQLAlchemy metadata, PostgreSQL catalog state, and PRD hard constraints for `datasets`, `tag_categories`, `tags`, `dataset_tags`, `devices`, and `permission_grants`.
- Explicitly out of scope:
  - Any implementation, test, migration, config, README, or PRD edits.
  - Upload lifecycle schema, validation/audit/outbox/idempotency schema, API routes, file-byte endpoints, MinIO multipart behavior, MQTT, Go, or seed data.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T02 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1619-T02-implementation-dataset-governance-schema-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md` sections 14.6-14.9
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `migrations/versions/20260624_0003_dataset_governance_schema.py`
  - `tests/infrastructure/test_dataset_governance_schema.py`

## Validation Findings

- Migration ordering accepted:
  - `20260624_0003_dataset_governance_schema.py` declares `revision = "20260624_0003"` and `down_revision = "20260624_0002"`.
  - `migrations/versions` contains `20260624_0001_persistence_base.py`, `20260624_0002_core_schema.py`, and `20260624_0003_dataset_governance_schema.py`.
  - Current git status/diff did not show older migration rewrites.
- Scoped tables accepted:
  - The new migration creates only `devices`, `datasets`, `tag_categories`, `tags`, `dataset_tags`, and `permission_grants`.
  - Metadata now contains the existing core tables plus these six governance tables.
- UUID strategy accepted:
  - Internal primary keys are UUIDs.
  - `dataset_tags` uses a UUID composite PK of `dataset_id` and `tag_id`.
  - New FKs use UUID columns.
- Device identity accepted:
  - `datasets.source_device_id` is a UUID FK to `devices.id`.
  - `datasets.source_device_code` is `text` metadata.
  - `permission_grants` has no `source_device_code` column, so authorization subjects remain registered UUID-backed subjects.
- `permission_grants` accepted:
  - Supports `subject_type`, `subject_id`, `resource_type`, `resource_id`, `permission_code`, `effect`, `conditions`, and `expires_at`.
  - `effect` uses the existing `permission_effect` enum with `ALLOW`/`DENY`.
  - Subject/resource type check constraints are present.
  - Indexes are present for subject, resource, permission code, and expiry.
  - Uniqueness covers tenant, subject, resource, permission code, and effect.
- Scope guardrails accepted:
  - No upload task/object/session/part tables were added in this segment.
  - No validation result, audit, upload event, outbox table, or idempotency table was added in this segment.
  - No upload API, FastAPI upload route, file-byte endpoint, storage adapter, MinIO multipart behavior, MQTT adapter, Go uploader, or gateway behavior was added.

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
  - `docker compose exec -T postgres psql -U upload -d upload -c "select table_name, column_name, data_type, udt_name from information_schema.columns where table_schema='public' and table_name in ('datasets','devices','permission_grants') and column_name in ('id','tenant_id','project_id','status','source_device_id','source_device_code','subject_id','resource_id','permission_code','effect','expires_at') order by table_name, ordinal_position;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select conrelid::regclass as table_name, conname, pg_get_constraintdef(oid) as definition from pg_constraint where conrelid::regclass::text in ('datasets','permission_grants') and (conname like '%source_device%' or conname like '%permission_grants%') order by conrelid::regclass::text, conname;"`
  - `docker compose down`
  - `rg` checks for upload lifecycle tables, validation/audit/outbox/idempotency tables, upload routes, file-byte endpoints, and MinIO multipart behavior.
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 40 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 34 source files.
  - `uv run pytest`: passed, 86 tests passed with 1 existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed, rerunning ruff, format check, mypy, and pytest with the same 86 passed / 1 warning result.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed; local database was already at or migrated to head.
  - `alembic_version`: `20260624_0003`.
  - Public tables: `alembic_version`, `api_keys`, `dataset_tags`, `datasets`, `devices`, `permission_grants`, `projects`, `storage_policies`, `tag_categories`, `tags`, `tenants`.
  - Catalog indexes confirmed for datasets, devices, tags, and permission grants, including `idx_datasets_object_unique`, `idx_datasets_source_device`, `idx_permission_grants_subject`, `idx_permission_grants_resource`, `idx_permission_grants_permission`, and `idx_permission_grants_expires_at`.
  - Catalog constraints confirmed, including `fk_datasets_source_device_id_devices`, permission grant subject/resource checks, primary keys, foreign keys, and unique constraints.
  - Column inspection confirmed UUID IDs/FKs, enum-backed status/effect columns, `source_device_code` as `text`, and `expires_at` as `timestamptz`.
  - `docker compose down`: passed.
- Commands not run and why:
  - None.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No file-byte route, upload API, storage proxy, or MQTT adapter was added.
- Clients receive no MinIO/S3 credentials: preserved. No client credential behavior was added.
- Complete uses object storage ListParts as authority: preserved. Upload completion remains out of scope.
- Authorization uses permission_grants: accepted for this schema segment. `permission_grants` is present as the resource-scoped permission-code source of truth.
- Internal IDs remain UUIDs: accepted.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway code was added.

## Risks and Follow-up

- Remaining risks:
  - T02 is not globally complete yet; upload lifecycle schema, validation/audit/outbox/idempotency schema, and seed data remain separate downstream segments.
  - `make migrate` did not show transition output in this run because the local Postgres state was already at head, but `alembic_version` and catalog checks confirmed the expected schema.
- Known gaps:
  - No runtime repository/service consumes these models yet.
  - No seed data in this segment.
- Suggested next agent:
  - The next T02 upload lifecycle schema agent can start from Alembic head `20260624_0003`.
  - That agent should add `upload_tasks`, `upload_objects`, `upload_sessions`, and `upload_parts` only, preserving `source_device_id` as the UUID registered device reference and `source_device_code` as external trace metadata.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Dataset-governance schema segment can be merged.
  - Next upload lifecycle schema agent can start after merge/master review.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
