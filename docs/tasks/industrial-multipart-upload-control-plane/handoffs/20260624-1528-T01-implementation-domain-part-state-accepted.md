# Handoff: T01 domain part sizing, session state, and aggregate upload status

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 15:24 +08:00
Finished: 2026-06-24 15:28 +08:00

## Scope

- Intended scope:
  - Implement pure domain part size selection and part range calculations.
  - Implement upload session state machine with `PAUSED`, valid transitions, terminal states, and action guard helpers.
  - Implement upload object and upload task aggregate status derivation.
  - Add focused unit tests for the above behavior.
- Explicitly out of scope:
  - FastAPI upload endpoints.
  - SQLAlchemy models, Alembic, migrations, or database repositories.
  - boto3, MinIO, or S3 storage calls.
  - Dataset lifecycle/exposure rules, object key sanitizer, request fingerprint, and permission evaluator; these remain for the next T01 dataset/auth agent.
  - Any endpoint or code path accepting file bytes.
- PRD/task files read:
  - docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md
  - docs/tasks/industrial-multipart-upload-control-plane/README.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1523-T00-merge-foundation-runtime-accepted.md
  - docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md
  - docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md
  - docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md
  - docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md
  - docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md
  - docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md
  - docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md
  - docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md
  - src/upload_control_plane existing package
  - tests existing structure

## Changes

- Files changed:
  - src/upload_control_plane/domain/__init__.py
  - src/upload_control_plane/domain/aggregates.py
  - src/upload_control_plane/domain/errors.py
  - src/upload_control_plane/domain/parts.py
  - src/upload_control_plane/domain/session_state.py
  - tests/domain/test_aggregates.py
  - tests/domain/test_parts.py
  - tests/domain/test_session_state.py
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1528-T01-implementation-domain-part-state-accepted.md
- Behavior changed:
  - Added `choose_part_size`, `get_part_count`, and `get_part_range` with PRD limits: 5 MiB minimum non-final part size, 64 MiB automatic default, 5 GiB maximum part size, and 10,000 maximum parts.
  - Added explicit upload session transition validation and helpers for presign, pause, resume, complete, and abort eligibility.
  - Added aggregate mapping from session status to upload object status and child object statuses to upload task status.
- Compatibility notes:
  - Domain code is independent from FastAPI, SQLAlchemy, boto3, and MinIO.
  - No API schemas, routes, persistence models, Docker files, or runtime configuration were changed.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed; 18 files already formatted.
  - `uv run mypy src tests`: passed; no issues in 16 source files.
  - `uv run pytest`: passed; 42 tests passed with one existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; ran ruff, format check, mypy, and pytest successfully.
- Commands not run and why:
  - Docker Compose smoke was not run because this slice is pure domain logic and the required verification list did not include compose.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No endpoints or data-plane code were added.
- Clients receive no MinIO/S3 credentials: preserved. No storage credentials or presign implementation were added.
- Complete uses object storage ListParts as authority: preserved. This slice only provides range math and state guards; storage-authoritative completion remains for T04/T06.
- Authorization uses permission_grants: not implemented in this slice. Left explicitly for the next T01 dataset/auth agent.
- Internal IDs remain UUIDs: preserved. This slice introduces no persistence identifiers.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or edge gateway code was added.

## Risks and Follow-up

- Remaining risks:
  - Aggregate status rules are pure derivation helpers and may need wiring refinements once persistence models define exact task/object status columns.
  - `can_complete` and `can_abort` include idempotent already-completed/already-aborted request states as API-level guards; actual transition validation remains strict through `apply_transition`.
- Known gaps:
  - Dataset lifecycle/exposure rules are intentionally not implemented in this handoff.
  - Object key sanitizer, request fingerprint generation, and permission-code evaluator are intentionally not implemented in this handoff.
  - Storage part reconciliation and `ListParts` validation are intentionally not implemented until storage adapter/runtime phases.
- Suggested next agent:
  - T01 Domain dataset/auth rules implementation agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The next T01 dataset/auth agent can build on `src/upload_control_plane/domain/` without waiting for infrastructure.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
