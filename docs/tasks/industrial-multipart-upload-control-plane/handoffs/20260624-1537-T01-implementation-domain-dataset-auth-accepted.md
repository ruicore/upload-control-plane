# Handoff: T01 domain dataset lifecycle, object keys, fingerprints, and permissions

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 15:31 +08:00
Finished: 2026-06-24 15:37 +08:00

## Scope

- Intended scope:
  - Implement pure domain dataset lifecycle, validation, recovery, and exposure rules.
  - Implement object name sanitizer and server-side object key builder without storage SDK dependencies.
  - Implement deterministic canonical request fingerprint generation.
  - Implement permission-code evaluation over loaded `permission_grants` with inherited grants, expiry handling, stable effective permissions, and deny-over-allow.
  - Add focused unit tests for the above behavior.
- Explicitly out of scope:
  - FastAPI upload endpoints.
  - SQLAlchemy models, Alembic, migrations, or database repositories.
  - boto3, MinIO, or S3 storage calls.
  - API key authentication dependency or database-backed authorization service.
  - Any endpoint or code path accepting file bytes.
- PRD/task files read:
  - docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md
  - docs/tasks/industrial-multipart-upload-control-plane/README.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1528-T01-implementation-domain-part-state-accepted.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1531-T01-validation-domain-part-state-accepted.md
  - docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md
  - docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md
  - docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md
  - docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md
  - docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md
  - docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md
  - docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md
  - docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md
  - docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md
  - src/upload_control_plane/domain/*.py

## Changes

- Files changed:
  - src/upload_control_plane/domain/__init__.py
  - src/upload_control_plane/domain/datasets.py
  - src/upload_control_plane/domain/errors.py
  - src/upload_control_plane/domain/fingerprints.py
  - src/upload_control_plane/domain/object_keys.py
  - src/upload_control_plane/domain/permissions.py
  - tests/domain/test_datasets.py
  - tests/domain/test_fingerprints.py
  - tests/domain/test_object_keys.py
  - tests/domain/test_permissions.py
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1537-T01-implementation-domain-dataset-auth-accepted.md
- Behavior changed:
  - Added dataset status, validation status, and recovery status enums with explicit lifecycle transitions and exposure checks.
  - Added tests proving upload `COMPLETED` does not make a dataset `READY`, and that `QUARANTINED`, `REJECTED`, pending/failed validation, and non-`NORMAL` recovery states block exposure.
  - Added server-side object key helper using tenant/project/dataset/session UUID namespace and sanitized original object name.
  - Added deterministic request fingerprinting from method, path, tenant UUID, and canonical JSON body.
  - Added pure permission grant evaluator for subject matching, inherited resource scopes, expiry filtering, stable sorted effective permissions, and `DENY` over `ALLOW`.
- Compatibility notes:
  - Domain code remains independent from FastAPI, SQLAlchemy, boto3, and MinIO.
  - No API schemas, routes, persistence models, Docker files, or runtime configuration were changed.
  - The permission evaluator expects grants and resource parent IDs to be supplied by a later application/persistence layer; it performs no DB access.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 26 files already formatted.
  - `uv run mypy src tests`: passed; no issues in 24 source files.
  - `uv run pytest`: passed; 70 tests passed with one existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; reran ruff, format check, mypy, and pytest successfully.
- Commands not run and why:
  - Docker Compose, PostgreSQL, and MinIO checks were not run because this slice is pure domain logic and the required verification list did not include service smoke tests.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No endpoints, MQTT adapter, or data-plane code were added.
- Clients receive no MinIO/S3 credentials: preserved. No storage credentials or presign implementation were added.
- Complete uses object storage ListParts as authority: preserved. This slice does not implement completion; dataset exposure explicitly remains separate from upload completion.
- Authorization uses permission_grants: implemented as a pure domain evaluator over supplied permission grants and permission codes, with no API-key-scope shortcut.
- Internal IDs remain UUIDs: preserved. Object key and permission helpers use UUID values for internal resource identity and do not introduce text primary keys.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or edge gateway code was added.

## Risks and Follow-up

- Remaining risks:
  - Dataset lifecycle transitions are domain-level rules and may need narrow additions when T09/T11/T12 wire retention, validation retry, and recovery workflows to persistence.
  - Permission inheritance currently depends on callers supplying the relevant parent resource UUIDs; T03/T09 must ensure project/dataset/session parent context is loaded consistently.
- Known gaps:
  - No database-backed authorization service, API key verification, project filtering query, or `effective_permissions` API response wiring exists yet; those belong to T02/T03.
  - No download URL endpoint or dataset lifecycle API exists yet; those belong to T09.
  - No storage ListParts reconciliation exists yet; that belongs to T04/T06.
- Suggested next agent:
  - T01 Domain validation agent for the full domain kernel.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Full T01 validation can start, covering both the accepted part/state segment and this dataset/auth segment together.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
