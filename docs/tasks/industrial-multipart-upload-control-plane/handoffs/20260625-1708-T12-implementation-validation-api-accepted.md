# Handoff: T12 validation result and retry API

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T12-implementation-validation-api
Worktree: D:\upload-control-plane-T12-implementation-validation-api
Started: 2026-06-25 16:45 Asia/Shanghai
Finished: 2026-06-25 17:08 Asia/Shanghai

## Scope

- Intended scope:
  - Complete the remaining T12 Dataset Validation and Metadata Extraction API scope.
  - Add Validation Result API.
  - Add permission-checked, idempotent Retry Validation API.
  - Preserve object identity, object storage metadata, and no-file-byte/no-secret constraints.
- Explicitly out of scope:
  - No production metrics, runbooks, or T13 observability work.
  - No MQTT, Go, edge gateway, or file-byte processing.
  - No schema migration; existing `dataset_validation_results` and dataset validation fields are reused.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1636-master-handoff-after-T11-accepted-T12-worker-partial.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1623-T12-implementation-validation-worker-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1628-T12-validation-validation-worker-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1633-T12-merge-validation-worker-accepted.md`

## Changes

- Files changed:
  - `src/upload_control_plane/api/datasets.py`
  - `src/upload_control_plane/application/datasets.py`
  - `src/upload_control_plane/infrastructure/db/seed.py`
  - `tests/api/test_dataset_lifecycle_api.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1708-T12-implementation-validation-api-accepted.md`
- Behavior changed:
  - Added `GET /v1/projects/{project_id}/datasets/{dataset_id}/validation`.
  - Added `POST /v1/projects/{project_id}/datasets/{dataset_id}/validation/retry`.
  - Validation result reads require `dataset.view` through the existing dataset-scoped authorization service.
  - Retry requires `dataset.validate` through `permission_grants`; the dev seed now grants this explicit permission code.
  - Validation result responses expose dataset validation state, preview metadata, persisted extracted metadata, latest validation result, and result history.
  - Retry resets eligible failed validation states to `dataset.status = PROCESSING` and `validation_status = PENDING`.
  - Retry is state-idempotent: already `PENDING` or `RUNNING` validation returns success with `retry_queued = false`.
  - Retry rejects non-eligible states such as `READY` / `PASSED` with `dataset.validation_retry_not_eligible`.
  - Retry appends audit and outbox events in the same DB transaction as the reset.
- Compatibility notes:
  - No object storage calls are made by these APIs.
  - No storage object identity or object metadata fields are cleared or rewritten during retry.
  - Historical validation result rows are preserved.

## Verification

- Commands run:
  - `uv run ruff format src tests`
    - Result: passed, 1 file reformatted.
  - `uv run ruff check src tests`
    - Result: passed, `All checks passed!`.
  - `uv run ruff format --check src tests`
    - Result: passed, `82 files already formatted`.
  - `uv run mypy src tests`
    - Result: passed, `Success: no issues found in 82 source files`.
  - `uv run pytest tests/api/test_dataset_lifecycle_api.py -q`
    - Result: passed, `15 passed, 1 warning in 7.06s`.
  - `uv run pytest tests/application/test_dataset_validation_worker.py tests/application/test_worker_lifecycle.py tests/application/test_outbox.py tests/api/test_dataset_lifecycle_api.py -q`
    - Result: passed, `28 passed, 1 warning in 9.13s`.
  - `uv run pytest -q`
    - Result: passed, `200 passed, 1 warning in 15.06s`.
  - `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body|StreamingResponse" src\upload_control_plane\api src\upload_control_plane\application`
    - Result: passed, no matches.
  - `rg -n "get_object|download_file|iter_chunks|StreamingBody|\.read\(|read_bytes|bytes\(|bytearray|memoryview" src\upload_control_plane\api\datasets.py src\upload_control_plane\application\datasets.py src\upload_control_plane\application\dataset_validation.py`
    - Result: passed, no matches.
  - `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material" src\upload_control_plane\api\datasets.py src\upload_control_plane\application\datasets.py tests\api\test_dataset_lifecycle_api.py`
    - Result: reviewed expected matches only: existing dataset download URL code and new negative assertions.
- Commands not run and why:
  - `docker compose config --quiet` was not rerun in this implementation slice; this API-only change does not alter compose files.

## Test Coverage Added

- Validation result success/metadata exposure:
  - `test_dataset_validation_result_api_returns_metadata_and_errors_without_storage_secrets`
- Failed/rejected validation errors:
  - Same test verifies `dataset_status = REJECTED`, `validation_status = FAILED`, and `latest_result.errors`.
- Permission denial:
  - `test_dataset_validation_result_requires_dataset_view_permission`
  - `test_retry_validation_requires_dataset_validate_permission`
- Retry success:
  - `test_retry_validation_resets_failed_dataset_and_preserves_object_metadata`
- Retry idempotence:
  - `test_retry_validation_is_idempotent_when_already_pending`
- Retry non-eligible behavior:
  - `test_retry_validation_rejects_non_eligible_passed_dataset`

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. APIs read and update metadata only; hard scans found no backend file-byte route or byte-read markers.
- Clients receive no MinIO/S3 credentials:
  - Preserved. No storage credentials or presigned URLs are returned by the validation APIs.
- Presigned URLs are not persisted:
  - Preserved. Validation result and retry paths do not create or store URLs.
- Complete uses object storage ListParts as authority:
  - Preserved. Upload completion code is unchanged.
- Authorization uses permission_grants:
  - Preserved. `dataset.view` and `dataset.validate` are enforced through the existing resource-scoped authorization service; API key scopes alone do not grant access.
- Internal IDs remain UUIDs:
  - Preserved. No schema or identifier changes.
- Object identity and storage metadata preserved on retry:
  - Preserved and test-covered for bucket, object key, ETag, object size, version ID, and dataset metadata.

## Risks and Follow-up

- Remaining risks:
  - HDF5 extraction remains stub-level from the prior worker slice.
  - Retry is state-idempotent without using `idempotency_records`; this matches the no-body retry shape and is covered by repeated-call tests.
  - T13 metrics/runbooks for validation retry and backlog remain intentionally out of scope.
- Known gaps:
  - None for the requested remaining T12 API scope.
- Suggested next agent:
  - Validation agent for this branch, then merge/master review to unblock T13.
