# Handoff: T12 Dataset Validation Worker Foundation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T12-validation-validation-worker
Worktree: D:\upload-control-plane-T12-validation-validation-worker
Started: 2026-06-25 16:24 +08:00
Finished: 2026-06-25 16:28 +08:00

## Scope

- Intended scope:
  - Independently validate implementation branch `codex/industrial-upload/T12-implementation-validation-worker` at commit `c11931f`.
  - Validate the T12 dataset validation worker foundation only.
  - Confirm whether the remaining T12 API slices are still incomplete.
- Explicitly out of scope:
  - Do not modify feature code.
  - Do not implement missing Validation Result API or Retry Validation API.
  - Do not broaden T12 beyond worker foundation validation.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`
  - `D:\upload-control-plane-T12-implementation-validation-worker\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1623-T12-implementation-validation-worker-accepted.md`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1628-T12-validation-validation-worker-accepted.md`
- Behavior changed:
  - None. Validation agent made no feature-code changes.
- Compatibility notes:
  - The validation branch was created from implementation commit `c11931fd3bf09740c9e74cb7ab3d0fb749238a4d`.
  - `uv` created a local `.venv` in this worktree during verification; it is not part of the committed validation result.

## Verification

- Commands run:
  - `git worktree add -b codex/industrial-upload/T12-validation-validation-worker D:\upload-control-plane-T12-validation-validation-worker c11931f`
    - Result: passed; worktree created at implementation commit `c11931f`.
  - `uv run ruff check src tests`
    - Result: passed, `All checks passed!`.
  - `uv run ruff format --check src tests`
    - Result: passed, `82 files already formatted`.
  - `uv run mypy src tests`
    - Result: passed, `Success: no issues found in 82 source files`.
  - `uv run pytest tests/application/test_dataset_validation_worker.py tests/application/test_worker_lifecycle.py tests/application/test_outbox.py tests/api/test_dataset_lifecycle_api.py -q`
    - Result: passed, `22 passed, 1 warning in 5.83s`.
  - `uv run pytest -q`
    - Result: passed, `194 passed, 1 warning in 13.51s`.
  - `docker compose config --quiet`
    - Result: passed, no output.
  - `uv run upload-worker --help`
    - Result: passed; command list includes `validate-datasets`.
  - `uv run upload-worker validate-datasets --help`
    - Result: passed; command is exposed and documented as one dataset validation pass.
  - `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body" src\upload_control_plane\api src\upload_control_plane\application`
    - Result: passed, no backend API/application file-byte route markers found.
  - `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|bytes\(|bytearray|memoryview" src tools tests`
    - Result: reviewed. Hits are expected existing configuration fields, storage adapter internals, dataset download URL code, CLI/browser redaction tests, and outbox payload guards. No T12 validation outbox/audit payload persists presigned URLs, credentials, or file bytes.
  - `rg -n "\.read\(|open\(|get_object|download_file|iter_chunks|Body|StreamingBody|bytes\(|bytearray|memoryview" src\upload_control_plane\application\dataset_validation.py src\upload_control_plane\worker\main.py tests\application\test_dataset_validation_worker.py`
    - Result: passed, no validation worker byte-reading or object-download markers found.
  - `rg -n "@router\.(get|post|patch|delete).*validation|retry.*validation|validation-results|validation_results|validate" src\upload_control_plane\api src\upload_control_plane\application`
    - Result: confirmed no Validation Result API or Retry Validation API route exists.
- Commands not run and why:
  - None from the requested command list.

## Evidence Summary

- Completed dataset enters validation when enabled:
  - `src/upload_control_plane/application/upload_sessions.py` sets completed datasets from `NOT_REQUIRED` to `PENDING` only when `enable_dataset_validation` is true.
  - `src/upload_control_plane/application/dataset_validation.py` returns a skipped summary when validation is disabled.
- Old `NOT_REQUIRED` datasets are not accidentally picked up:
  - Worker candidates require `Dataset.validation_status == PENDING`, `Dataset.status == PROCESSING`, completed upload session, and object location.
  - There is no dedicated regression test that inserts an old completed `NOT_REQUIRED` dataset, so this is code-reviewed evidence rather than a direct test assertion.
- Worker claims explicit `PENDING` datasets and transitions safely:
  - Candidate claim uses `with_for_update(skip_locked=True)` and transitions candidates to `RUNNING` plus dataset `QUARANTINED` before validation.
- Success path:
  - Focused tests verify success writes `dataset_validation_results`, extracted metadata, preview metadata, `validation_status = PASSED`, and dataset `READY`.
- Failure path:
  - Focused tests verify storage-head failure writes `dataset_validation_results.errors`, marks `FAILED` / `REJECTED`, preserves object metadata, and does not call object delete.
  - Existing dataset lifecycle tests verify `QUARANTINED` / `REJECTED` and non-passed validation states block download URL exposure.
- HDF5 stub:
  - `Hdf5MetadataExtractor` uses `head_object`, filename/content-type inference, and bounded metadata. Static scan found no byte reads or object downloads in validation worker code.
- Worker CLI and periodic behavior:
  - `upload-worker validate-datasets` is exposed.
  - Periodic `upload-worker run` invokes lifecycle, validation, and optional outbox dispatch; validation remains a default no-op when disabled.
- Outbox/audit:
  - Validation success/failure appends audit and outbox entries before the same session commit as the final dataset transition.
  - Existing outbox guard tests reject presigned URLs, credentials, and bytes.
- Missing API slices:
  - Validation Result API and Retry Validation API are not implemented in this branch.
  - Full T12 remains incomplete until those API slices are implemented, validated, and merged.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. No backend route markers for file-byte receipt were found, and validation worker uses metadata/head-style storage calls only.
- Clients receive no MinIO/S3 credentials:
  - Preserved. No T12 client-facing API was added; scans showed only existing config/storage internals and redaction/guard tests.
- Complete uses object storage ListParts as authority:
  - Preserved. T12 changes do not alter completion authority; validation queues only after existing completion path.
- Authorization uses permission_grants:
  - Preserved for existing dataset download exposure checks. No new public validation endpoint was added.
- Internal IDs remain UUIDs:
  - Preserved. Validation results, audit, and outbox use existing UUID-backed models.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go uploader, or gateway changes were introduced.

## Risks and Follow-up

- Remaining risks:
  - This branch validates worker foundation only; it does not complete all T12 deliverables.
  - Candidate exclusion of historical `NOT_REQUIRED` datasets is supported by code inspection but lacks a dedicated regression test.
  - HDF5 extraction is intentionally stub-level and does not parse file internals.
- Known gaps:
  - Validation Result API is not implemented.
  - Retry Validation API is not implemented.
  - Permission-checked, idempotent retry validation is therefore not available.
- Suggested next agent:
  - T12 Validation API implementation agent for result retrieval and permission-checked idempotent retry/reset flow, followed by another validation agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Worker foundation can be used by the next T12 API slice, but full T12 is not complete.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
