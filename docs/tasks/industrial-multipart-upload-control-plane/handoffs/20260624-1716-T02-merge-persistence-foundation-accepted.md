# Handoff: T02 persistence foundation final merge

Status: accepted
Agent type: Merge
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 17:12 +08:00
Finished: 2026-06-24 17:16 +08:00

## Scope

- Intended scope:
  - Commit the accepted T02 dev seed implementation, seed tests, seed validation handoff, and full T02 validation handoff.
  - Run the final T02 validation gate after commit.
  - Confirm Alembic head, T02 table coverage, seed grants, UUID internal IDs, separated status fields, and absence of `upload_batches` / `batch_id`.
  - Leave a final merge handoff for Master final review.
- Explicitly out of scope:
  - New features, business logic changes, schema changes, API/auth implementation, storage adapter behavior, upload routes, MQTT, Go, edge gateway, or T03 work.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1703-T02-implementation-seed-dev-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1707-T02-validation-seed-dev-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1712-T02-validation-persistence-foundation-accepted.md`

## Changes

- Files changed:
  - `scripts/seed_dev.py`
  - `src/upload_control_plane/infrastructure/db/seed.py`
  - `tests/infrastructure/test_seed_dev.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1703-T02-implementation-seed-dev-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1707-T02-validation-seed-dev-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1712-T02-validation-persistence-foundation-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1716-T02-merge-persistence-foundation-accepted.md`
- Commits:
  - `e3e04ad` - `提交 T02 开发 seed 与最终验证交接`
- Behavior changed:
  - `make seed-dev` now loads deterministic dev persistence rows and prints the dev-only API key value while storing only hash-like credential material.
  - No runtime API, storage, upload, MQTT, Go, or edge behavior was added.
- Compatibility notes:
  - No migration was added in the final merge step.
  - Existing Alembic head remains `20260624_0005`.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up -d postgres`
  - Postgres health wait for `upload-control-plane-postgres-1`
  - `make migrate`
  - `make seed-dev`
  - `make seed-dev`
  - PostgreSQL inspection for Alembic head, public table set, prohibited batch paths, seed counts, permission grants, seeded entity state, enum separation, and UUID internal columns.
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 46 files already formatted.
  - `uv run mypy src tests`: passed; no issues in 38 source files.
  - `uv run pytest`: passed; 104 passed, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with 104 passed / 1 warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d postgres`: passed.
  - Postgres health wait: passed, status `healthy`.
  - `make migrate`: passed.
  - First `make seed-dev`: passed with counts `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - Second `make seed-dev`: passed with the same counts, confirming deterministic seed idempotency for the local dev dataset.
  - Alembic inspection returned `20260624_0005`.
  - Public table inspection returned 20 tables: `alembic_version`, `api_keys`, `audit_events`, `dataset_tags`, `dataset_validation_results`, `datasets`, `devices`, `idempotency_records`, `outbox_events`, `permission_grants`, `projects`, `storage_policies`, `tag_categories`, `tags`, `tenants`, `upload_events`, `upload_objects`, `upload_parts`, `upload_sessions`, `upload_tasks`.
  - Prohibited batch inspection returned zero rows for `upload_batches`, `batch_id`, or batch-like public tables/columns.
  - Seed grants inspection returned six project-scoped `ALLOW` grants from `dev_seed`: `project.view`, `dataset.upload`, and `upload.create` for both API key and device subjects.
  - Seeded entity inspection returned tenant `dev-industrial`, storage policy `local-minio-default`, bucket `robot-data`, project `robotics-line-3`, dataset `line-3-sample-hdf5`, dataset status `UPLOAD_PENDING`, validation status `NOT_REQUIRED`, recovery status `NORMAL`, device `robot-17`, device status `ACTIVE`, hash-like API key and device credential values, and raw dev API key absent from the stored hash.
  - Enum inspection confirmed separated `dataset_status`, `validation_status`, and `recovery_status` enum types, plus upload/device/permission/outbox enums.
  - UUID inspection confirmed internal business primary keys and foreign-key-style columns are UUID where expected; text IDs remain only for non-internal identifiers such as audit actors, request IDs, storage upload/version IDs, and source device code.
  - `docker compose down`: passed and removed the Postgres container and compose network.
- Commands not run and why:
  - None from the requested validation list.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload route, `UploadFile`, storage proxy, MQTT adapter, Go code, or file-byte path was added.
- Clients receive no MinIO/S3 credentials: preserved. Seed prints only a local dev API key and stores hash-like credential material; it does not expose MinIO/S3 credentials.
- Complete uses object storage ListParts as authority: preserved. Completion behavior remains unimplemented and out of scope for T02.
- Authorization uses permission_grants: satisfied for T02 persistence and seed. Seed writes resource-scoped project grants to `permission_grants`.
- Internal IDs remain UUIDs: satisfied. T02 table inspection confirmed UUID primary keys and internal foreign keys.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway behavior was added.

## Risks and Follow-up

- Remaining risks:
  - T03 must implement runtime API key verification, project visibility filtering, stable error response, request ID handling, and permission evaluation against `permission_grants`.
  - T04+ must preserve storage-authoritative complete behavior and must not treat DB ack rows as final storage proof.
  - `make seed-dev` intentionally prints the local dev API key value; it is not persisted in the database but console output remains local dev secret material.
- Known gaps:
  - No runtime endpoint consumes the T02 persistence foundation yet; this is expected and belongs to T03+.
  - No storage multipart calls or upload task runtime exists yet; this is expected and belongs to T04/T05+.
- Suggested next agent:
  - T03 Authentication and Authorization foundation can start after Master final review accepts this merge handoff.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T03 can start from `main` after Master final review.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
