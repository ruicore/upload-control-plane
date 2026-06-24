# Handoff: T01 full domain kernel validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 15:38 +08:00
Finished: 2026-06-24 15:40 +08:00

## Scope

- Intended scope:
  - Independently validate the complete T01 domain kernel currently present on `main`.
  - Validate both accepted T01 implementation segments together: part/state/aggregate rules and dataset/auth/object-key/fingerprint rules.
  - Confirm T01 remains pure domain code and does not add upload endpoints, file-byte endpoints, persistence, or storage SDK dependencies.
- Explicitly out of scope:
  - Modifying implementation code, tests, configuration, README, or PRD files.
  - Storage-authoritative completion against real object storage; this remains for T04/T06.
  - Database-backed authorization, project filtering, API responses, and persistence schema wiring; these remain for T02/T03.
  - Dataset product API/download endpoint behavior; this remains for T09.
- PRD/task files read:
  - docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md
  - docs/tasks/industrial-multipart-upload-control-plane/README.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1528-T01-implementation-domain-part-state-accepted.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1531-T01-validation-domain-part-state-accepted.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1537-T01-implementation-domain-dataset-auth-accepted.md
  - docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md
  - docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md
  - docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md
  - docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md
  - docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md
  - docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md
  - docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md
  - docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md
  - docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md
  - docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md
  - src/upload_control_plane/domain/*.py
  - tests/domain/*.py

## Validation Findings

- T01 deliverables are present:
  - Part size selection and part range functions are implemented in `parts.py`.
  - Upload session state machine and action guards are implemented in `session_state.py`.
  - Upload task/object aggregate status rules are implemented in `aggregates.py`.
  - Dataset lifecycle, validation, recovery, and exposure rules are implemented in `datasets.py`.
  - Object key sanitizer and server-side key builder are implemented in `object_keys.py`.
  - Canonical request fingerprint generation is implemented in `fingerprints.py`.
  - Permission-code evaluation over loaded grants is implemented in `permissions.py`.
- Acceptance coverage:
  - `tests/domain/test_parts.py` covers 5 MiB minimum, 64 MiB default, 5 GiB maximum, and 10,000-part boundary/exceedance cases.
  - `tests/domain/test_session_state.py` rejects invalid upload session transitions and proves PAUSED rejects presign.
  - `tests/domain/test_datasets.py` proves upload `COMPLETED` does not map to dataset `READY`.
  - `tests/domain/test_datasets.py` proves `QUARANTINED`, `REJECTED`, pending/running/failed validation, and every non-`NORMAL` recovery state block exposure.
  - `tests/domain/test_permissions.py` proves deterministic sorted `effective_permissions`, group/inherited project grants, expiry filtering, other-tenant filtering, and DENY-over-ALLOW.
- Dependency and endpoint constraints:
  - Domain imports are standard-library plus sibling domain modules only.
  - `rg` found no FastAPI, SQLAlchemy, boto3, botocore, MinIO, HTTP framework, or HTTP client dependency in `src/upload_control_plane/domain` or `tests/domain`.
  - Endpoint search found only the existing `/healthz` route and path strings inside fingerprint tests. No upload endpoint or file-byte endpoint was added.
- Design note for later phases:
  - `aggregates.py` currently uses pure-domain `CANCELING`, `CANCELED`, and `EXPIRED` object/task statuses, while the PRD database enum sketch uses `CANCELLED` and does not list every derived pure-domain intermediate. This is not a T01 blocker because T01 is persistence-free, but T02/T05 should explicitly align persisted enum values or add a mapping layer instead of leaking persistence names back into the domain helpers.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `rg -n "FastAPI|APIRouter|@app\.|@router\.|UploadFile|File\(|Form\(|Request\(|StreamingResponse|SQLAlchemy|sqlalchemy|boto3|botocore|minio|MinIO|requests|httpx|aiohttp|starlette" src/upload_control_plane/domain tests/domain`
  - `rg -n "@app\.|@router\.|APIRouter|UploadFile|File\(|StreamingResponse|/v1/uploads|upload-tasks|parts/presign|parts/ack|/complete|/abort|/pause|/resume" src tests -g "*.py"`
  - `rg -n "5 \* MIB|64 \* MIB|5 \* GIB|10_000|MAX_PART_COUNT|MAX_PART_SIZE|DEFAULT_PART_SIZE|MIN_PART_SIZE|10000" src/upload_control_plane/domain/parts.py tests/domain/test_parts.py`
  - `rg -n "COMPLETED|READY|QUARANTINED|REJECTED|RECOVERY|NORMAL|dataset_allows_exposure|derive_dataset_upload_status" src/upload_control_plane/domain/datasets.py tests/domain/test_datasets.py`
  - `rg -n "effective_permissions|has_permission|DENY|ALLOW|expires_at|GROUP|PROJECT|DATASET|resource_parents|deny_overrides|inherited|sorted" src/upload_control_plane/domain/permissions.py tests/domain/test_permissions.py`
  - `rg -n "^from |^import " src/upload_control_plane/domain tests/domain`
  - `rg -n "bytes|stream|UploadFile|File\(|form-data|multipart/form-data|request\.body|iter_bytes|read\(" src tests -g "*.py"`
- Results:
  - `uv run ruff check`: passed; all checks passed.
  - `uv run ruff format --check`: passed; 26 files already formatted.
  - `uv run mypy src tests`: passed; no issues found in 24 source files.
  - `uv run pytest`: passed; 70 tests passed with one existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; reran ruff, format check, mypy, and pytest successfully with 70 tests passed and the same deprecation warning.
  - Forbidden domain dependency search: no matches.
  - Endpoint search: only `src/upload_control_plane/main.py` health route and fingerprint test path strings matched; no upload or file-byte route implementation was present.
  - Boundary, dataset exposure, permission, import, and file-byte searches produced expected evidence and no blocking findings.
- Commands not run and why:
  - Docker Compose, PostgreSQL, and MinIO checks were not run because T01 is pure domain logic and the required command list for this validation did not include service smoke tests.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload/file-byte endpoint, MQTT adapter, stream handler, or data-plane proxy was added.
- Clients receive no MinIO/S3 credentials: preserved. No storage credential, presign implementation, or storage client was added.
- Complete uses object storage ListParts as authority: preserved. T01 does not implement completion; it only exposes part math and state guards for later T04/T06.
- Authorization uses permission_grants: preserved at domain level through centralized pure permission grant evaluation. No API-key-scope shortcut was introduced.
- Internal IDs remain UUIDs: preserved. Domain permission/resource/object-key helpers use UUIDs for internal resource identity and do not introduce text primary keys.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or edge gateway code was added.
- Pause is a control-plane scheduling state: preserved. Domain state rejects presign while paused and does not imply storage abort or storage write lock.
- Presigned URLs are not persisted or logged: preserved. No presigned URL persistence, logging, browser storage, audit, outbox, or manifest code was added.

## Risks and Follow-up

- Remaining risks:
  - Persistence/API layers must keep permission parent-context loading deterministic when they wire `resource_parents` for project, dataset, upload task, and upload session targets.
  - Later persistence/API tasks should align or explicitly map pure-domain aggregate statuses to database/API enum values.
  - Storage-authoritative completion, permission re-evaluation per endpoint, and dataset download policy are not implemented yet by design and must be validated in T03/T06/T09.
- Known gaps:
  - No SQLAlchemy models, Alembic migrations, or seed data exist in T01; this is T02 scope.
  - No FastAPI upload, auth, storage, or dataset lifecycle endpoints exist in T01; this is T03-T09 scope.
  - No real object storage reconciliation exists in T01; this is T04/T06 scope.
- Suggested next agent:
  - T01 can proceed to Master review and merge. After T01 is merged, T02 Persistence Foundation can unlock.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Merge T01 domain kernel into the accepted baseline, then start T02 Persistence Foundation.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
