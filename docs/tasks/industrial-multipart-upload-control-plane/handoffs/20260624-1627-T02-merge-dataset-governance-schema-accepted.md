# Handoff: T02 dataset-governance schema merge

Status: accepted
Agent type: Merge
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 16:23 +08:00
Finished: 2026-06-24 16:27 +08:00

## Scope

- Intended scope:
  - Commit the implementation-accepted and validation-accepted dataset-governance schema checkpoint.
  - Preserve the schema segment exactly within the accepted scope: `datasets`, `tag_categories`, `tags`, `dataset_tags`, `devices`, and `permission_grants`.
  - Run the requested post-commit validation matrix and record database catalog evidence.
- Explicitly out of scope:
  - Upload lifecycle schema tables.
  - Validation, audit, upload event, outbox, idempotency, or seed schema.
  - API routes, auth dependencies, storage behavior, MQTT, Go, or any file-byte path.
  - Business-logic changes or schema expansion beyond the accepted segment.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1619-T02-implementation-dataset-governance-schema-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1623-T02-validation-dataset-governance-schema-accepted.md`

## Changes

- Files committed in implementation checkpoint `9b9cea8`:
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `src/upload_control_plane/infrastructure/db/__init__.py`
  - `migrations/versions/20260624_0003_dataset_governance_schema.py`
  - `tests/infrastructure/test_alembic_config.py`
  - `tests/infrastructure/test_dataset_governance_schema.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1619-T02-implementation-dataset-governance-schema-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1623-T02-validation-dataset-governance-schema-accepted.md`
- Files changed by this merge handoff:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1627-T02-merge-dataset-governance-schema-accepted.md`
- Behavior changed:
  - Alembic head for this checkpoint is `20260624_0003`.
  - SQLAlchemy metadata and migration now include the accepted dataset-governance tables.
- Compatibility notes:
  - No earlier migration was rewritten.
  - No upload lifecycle schema work was started.

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
  - `docker compose exec -T postgres psql -U upload -d upload -c "select typname from pg_type t join pg_namespace n on n.oid=t.typnamespace where n.nspname='public' and t.typtype='e' order by typname;"`
  - `docker compose exec -T postgres psql -U upload -d upload -c "select conrelid::regclass as table_name, conname, pg_get_constraintdef(oid) as definition from pg_constraint where conrelid::regclass::text in ('datasets','permission_grants') and (conname like '%source_device%' or conname like '%permission_grants%') order by conrelid::regclass::text, conname;"`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 40 files already formatted.
  - `uv run mypy src tests`: passed; no issues found in 34 source files.
  - `uv run pytest`: passed; 86 tests passed with 1 existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with the same 86 passed / 1 warning result.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - `make migrate`: passed; local database was already at the target head.
  - `alembic_version`: `20260624_0003`.
  - Public tables confirmed: `alembic_version`, `api_keys`, `dataset_tags`, `datasets`, `devices`, `permission_grants`, `projects`, `storage_policies`, `tag_categories`, `tags`, `tenants`.
  - Indexes confirmed for all six target tables, including `idx_datasets_object_unique`, `idx_datasets_source_device`, `idx_permission_grants_subject`, `idx_permission_grants_resource`, `idx_permission_grants_permission`, and `idx_permission_grants_expires_at`.
  - Constraints confirmed, including `fk_datasets_source_device_id_devices`, permission-grant subject/resource checks, PKs, FKs, and unique constraints.
  - Column inspection confirmed UUID internal IDs/FKs, enum-backed dataset/device/permission status/effect columns, `source_device_code` as text metadata, and `expires_at` as `timestamptz`.
  - Enum inspection confirmed expected public enum types remain present.
  - `docker compose down`: passed.
- Commands not run and why:
  - None.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload route, byte endpoint, storage proxy, or MQTT adapter was added.
- Clients receive no MinIO/S3 credentials: preserved. No credential exposure behavior was added.
- Complete uses object storage ListParts as authority: preserved. Upload completion remains out of scope.
- Authorization uses permission_grants: satisfied for this segment. `permission_grants` is present as the resource-scoped permission-code source of truth.
- Internal IDs remain UUIDs: satisfied. New primary keys and foreign keys are UUIDs; human-readable codes remain metadata.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway work was added.

## Risks and Follow-up

- Remaining risks:
  - T02 is not globally complete. Upload lifecycle schema, validation/audit/outbox/idempotency schema, and seed data remain separate downstream segments.
  - Runtime services do not consume these models yet.
- Known gaps:
  - No seed rows or seed scripts in this checkpoint.
  - No API or repository behavior in this checkpoint.
- Suggested next agent:
  - Next T02 upload lifecycle schema agent can start after this accepted merge checkpoint.
  - That agent should add `upload_tasks`, `upload_objects`, `upload_sessions`, and `upload_parts` only, starting from Alembic head `20260624_0003`.
  - It must keep `source_device_id` as a UUID registered-device reference and `source_device_code` as external trace metadata only.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T02 upload lifecycle schema implementation can start from committed checkpoint `9b9cea8` plus this merge handoff.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not rewrite earlier migrations; repair by adding a follow-up migration or correcting the current segment.
