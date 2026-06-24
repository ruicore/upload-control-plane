# Handoff: T02 full persistence foundation validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 17:07 +08:00
Finished: 2026-06-24 17:12 +08:00

## Scope

- Intended scope:
  - Independently validate the full T02 Persistence Foundation after all accepted schema segments and the uncommitted accepted dev seed implementation.
  - Verify SQLAlchemy 2.x sync models, Alembic environment, empty-PostgreSQL migration to head, full T02 table coverage, UUID PK/FK strategy, source-device semantics, dev seed behavior, permission-grant seed usability, status separation, and out-of-scope boundary preservation.
- Explicitly out of scope:
  - Modifying implementation code, tests, migrations, configuration, README, or PRD.
  - Repairing schema or seed issues.
  - Adding upload APIs, auth routes, storage adapter behavior, file-byte endpoints, MQTT, Go, or edge behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T02 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1557-T02-merge-persistence-base-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1611-T02-merge-core-schema-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1627-T02-merge-dataset-governance-schema-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1643-T02-merge-upload-lifecycle-schema-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1656-T02-merge-records-schema-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1703-T02-implementation-seed-dev-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1707-T02-validation-seed-dev-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - Current `src/upload_control_plane/infrastructure/db/*`, migrations, seed script, and infrastructure tests.

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1712-T02-validation-persistence-foundation-accepted.md`
- Behavior changed:
  - None. This validation did not modify implementation, tests, migrations, configuration, README, or PRD.
- Compatibility notes:
  - Existing uncommitted accepted seed implementation files were left untouched.
  - Existing untracked accepted seed handoffs were left untouched.
  - A local validation database reset was performed with `docker compose down -v` before migration to prove empty-PostgreSQL migration semantics.

## Verification

- Commands run:
  - `git status --short --branch`
  - `docker compose down -v`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up -d postgres`
  - Wait for `upload-control-plane-postgres-1` health status `healthy`
  - `make migrate`
  - `make seed-dev`
  - `make seed-dev`
  - PostgreSQL inspection for Alembic head, full public table set, UUID ID/FK columns, prohibited batch path, constraints, enum/status separation, seed row counts, seed grants, and seed entity details.
  - Static `rg` checks for prohibited upload/file-byte/storage/auth/MQTT/Go behavior.
- Results:
  - Initial `git status --short --branch`: `main...origin/main [ahead 15]`, modified `scripts/seed_dev.py`, untracked accepted seed files under `src/upload_control_plane/infrastructure/db/seed.py`, `tests/infrastructure/test_seed_dev.py`, and two accepted seed handoffs.
  - `docker compose down -v`: passed; local `postgres-data` and `minio-data` volumes were removed before validation.
  - `uv run ruff check`: passed, `All checks passed!`.
  - `uv run ruff format --check`: passed, `46 files already formatted`.
  - `uv run mypy src tests`: passed, `Success: no issues found in 38 source files`.
  - `uv run pytest`: passed, `104 passed, 1 warning`.
  - `make test`: passed; repeated ruff, format check, mypy, and pytest with `104 passed, 1 warning`.
  - `docker compose config --quiet`: passed with no output.
  - `docker compose up -d postgres`: passed and created a fresh Postgres volume.
  - Postgres health wait: passed, status `healthy`.
  - `make migrate`: passed from empty Postgres through all revisions to `20260624_0005`.
  - First `make seed-dev`: passed with counts `tenants=1`, `api_keys=1`, `storage_policies=1`, `projects=1`, `datasets=1`, `devices=1`, `permission_grants=6`.
  - Second `make seed-dev`: passed with the same deterministic IDs and counts, confirming local seed idempotency.
  - `alembic_version`: `20260624_0005`.
  - Public tables present: `alembic_version`, `api_keys`, `audit_events`, `dataset_tags`, `dataset_validation_results`, `datasets`, `devices`, `idempotency_records`, `outbox_events`, `permission_grants`, `projects`, `storage_policies`, `tag_categories`, `tags`, `tenants`, `upload_events`, `upload_objects`, `upload_parts`, `upload_sessions`, `upload_tasks`.
  - T02 deliverable table coverage is satisfied for tenants, storage policies, API keys, projects, datasets, tags, devices, permission grants, upload tasks/objects/sessions/parts, validation results, upload events, audit events, outbox events, and idempotency records.
  - UUID inspection confirmed internal `id` and foreign-key-style columns are UUID where expected. Text IDs remain only for non-internal identifiers such as `actor_id`, `request_id`, `resource_id` in audit events, storage upload/object version identifiers, and `source_device_code`.
  - Prohibited batch inspection returned zero rows for `upload_batches`, `batch_id`, or batch-like columns.
  - Constraint inspection confirmed `datasets.source_device_id`, `upload_tasks.source_device_id`, and `upload_sessions.source_device_id` reference `devices(id)`.
  - Constraint inspection confirmed `permission_grants` subject/resource checks, primary key, unique grant shape, and tenant FK.
  - Constraint inspection confirmed upload-session file size, part size, part count, object key uniqueness, and idempotency uniqueness constraints.
  - Enum inspection confirmed `dataset_status`, `validation_status`, and `recovery_status` are distinct enum types with separate values; upload, device, permission, and outbox enums also exist.
  - Seed row count inspection after two seed runs showed exactly one tenant, API key, storage policy, project, dataset, device, and six permission grants.
  - Seed grant inspection showed both `api_key cd6c08e8-68a1-50e8-868e-b2b17a0231db` and `device e06d5e8b-3579-5efd-8a51-e89db11c6cc9` have project-scoped `ALLOW` grants for `project.view`, `dataset.upload`, and `upload.create` on project `robotics-line-3`.
  - Seed entity inspection showed tenant `dev-industrial`, storage policy `local-minio-default`, bucket `robot-data`, project `robotics-line-3`, dataset `line-3-sample-hdf5`, dataset status `UPLOAD_PENDING`, validation status `NOT_REQUIRED`, recovery status `NORMAL`, registered source device UUID `e06d5e8b-3579-5efd-8a51-e89db11c6cc9`, source device code `robot-17`, device status `ACTIVE`, API key hash is `sha256:`-like, raw API key substring absent from stored hash, and device credential hash is `sha256:`-like.
  - Static path inspection found no `src` or `tests` API/auth/storage/MQTT/Go/CLI/manual-uploader implementation paths.
  - Static route/behavior inspection found only `GET /healthz`; no upload routes, auth routes, storage multipart calls, file-byte endpoint primitives, boto3/botocore calls, MQTT adapter, Go code, or edge behavior. Existing MQTT strings are inert T00 configuration settings defaulting disabled.
  - Static `upload_batches|batch_id` inspection found only negative assertions in tests, not implementation or migration usage.
- Commands not run and why:
  - None from the requested validation list. `docker compose down` is run after this handoff is written so final cleanup can be reported.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No file upload route, `UploadFile`, FastAPI file form endpoint, storage proxy, MQTT adapter, Go code, or file-byte path was added.
- Clients receive no MinIO/S3 credentials: preserved. Compose/config still contain local service credentials from foundation setup, but no client-facing API or seed output exposes MinIO/S3 credentials. Seed prints only the dev API key value and stores only hash-like credential material.
- Complete uses object storage ListParts as authority: preserved. Complete behavior and storage adapter calls remain unimplemented in T02.
- Authorization uses permission_grants: satisfied for T02 persistence and seed. `permission_grants` exists and seed writes resource-scoped grants for API key and device subjects.
- Internal IDs remain UUIDs: satisfied. Business table primary keys and internal foreign keys are UUID. Human-readable/external values remain text metadata.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT adapter, Go uploader, or edge gateway behavior was added.

## Risks and Follow-up

- Remaining risks:
  - T03 still needs to implement runtime API key verification, project visibility filtering, and effective permission evaluation against these persisted grants.
  - T04 and later must continue preserving the storage-authoritative complete rule and must not interpret DB ack rows as final storage proof.
  - The dev seed intentionally prints the local dev API key value to stdout; it is not persisted in the database, but console output remains local dev secret material.
- Known gaps:
  - No runtime endpoints consume the T02 persistence foundation yet; this is expected and belongs to T03+.
  - No storage multipart calls or upload task creation runtime exists yet; this is expected and belongs to T04/T05+.
- Suggested next agent:
  - Merge/Master finalization for T02 can proceed.
  - After T02 is merged/finalized, T03 Authentication and Authorization can unlock.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T02 Persistence Foundation is accepted as a full validation result.
  - T03 can start after the current T02 seed implementation and validation handoffs are merged/finalized.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
