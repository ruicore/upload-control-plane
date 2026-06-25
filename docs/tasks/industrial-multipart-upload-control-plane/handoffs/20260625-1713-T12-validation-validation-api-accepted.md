# Handoff: T12 validation result and retry API validation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T12-validation-validation-api
Worktree: D:\upload-control-plane-T12-validation-validation-api
Implementation branch: codex/industrial-upload/T12-implementation-validation-api
Implementation commit: da5a8d2d2df151645087e482da1f838253f57384
Started: 2026-06-25 17:09 Asia/Shanghai
Finished: 2026-06-25 17:13 Asia/Shanghai

## Scope

- Intended scope:
  - Independently validate the remaining T12 Dataset Validation and Metadata Extraction API scope.
  - Validate Validation Result API.
  - Validate permission-checked, idempotent Retry Validation API.
  - Validate no file-byte, presigned URL, or storage credential exposure.
- Explicitly out of scope:
  - No product code changes.
  - No T13 observability, metrics, runbooks, or operations implementation.
  - No production HDF5 parser hardening beyond the already accepted T12 worker stub.
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
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1708-T12-implementation-validation-api-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1623-T12-implementation-validation-worker-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1628-T12-validation-validation-worker-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1633-T12-merge-validation-worker-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1636-master-handoff-after-T11-accepted-T12-worker-partial.md`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1713-T12-validation-validation-api-accepted.md`
- Behavior changed:
  - None. Validation agent made no product-code changes.
- Compatibility notes:
  - Validation branch was created from implementation branch `codex/industrial-upload/T12-implementation-validation-api` at commit `da5a8d2`.
  - No push was performed.

## Verification

- Commands run from `D:\upload-control-plane-T12-implementation-validation-api`:
  - `uv run ruff check src tests`
    - Result: passed, `All checks passed!`.
  - `uv run ruff format --check src tests`
    - Result: passed, `82 files already formatted`.
  - `uv run mypy src tests`
    - Result: passed, `Success: no issues found in 82 source files`.
  - `uv run pytest tests/api/test_dataset_lifecycle_api.py -q`
    - Result: passed, `15 passed, 1 warning in 4.24s`.
  - `uv run pytest tests/application/test_dataset_validation_worker.py tests/application/test_worker_lifecycle.py tests/application/test_outbox.py tests/api/test_dataset_lifecycle_api.py -q`
    - Result: passed, `28 passed, 1 warning in 6.09s`.
  - `uv run pytest -q`
    - Result: passed, `200 passed, 1 warning in 14.00s`.
  - `docker compose config --quiet`
    - Result: passed, no output.
  - `git diff --check`
    - Result: passed, no output.
  - `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body|StreamingResponse|FileResponse" src/upload_control_plane/api src/upload_control_plane/application`
    - Result: passed, no matches.
  - `rg -n "get_object|download_file|iter_chunks|StreamingBody|\.read\(|read_bytes|bytes\(|bytearray|memoryview" src/upload_control_plane/api/datasets.py src/upload_control_plane/application/datasets.py src/upload_control_plane/application/dataset_validation.py`
    - Result: passed, no matches.
  - `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src/upload_control_plane/api/datasets.py src/upload_control_plane/application/datasets.py src/upload_control_plane/application/dataset_validation.py tests/api/test_dataset_lifecycle_api.py`
    - Result: reviewed expected matches only: existing dataset download-url code and negative assertions for storage credential leakage.
- Warnings:
  - Pytest emits the existing `StarletteDeprecationWarning` from FastAPI TestClient/httpx compatibility.
- Commands not run and why:
  - None from the requested validation list.

## Evidence Summary

- Route contract:
  - `src/upload_control_plane/api/datasets.py` implements `GET /v1/projects/{project_id}/datasets/{dataset_id}/validation`.
  - `src/upload_control_plane/api/datasets.py` implements `POST /v1/projects/{project_id}/datasets/{dataset_id}/validation/retry`.
- Permission contract:
  - Result endpoint requires `dataset.view` against `ResourceType.DATASET`.
  - Retry endpoint requires `dataset.validate` against `ResourceType.DATASET`.
  - `AuthorizationService` resolves dataset resources with project and tenant parents, so resource-scoped `permission_grants` remain authoritative and project grants can apply to dataset resources through inheritance.
  - Tests cover DENY behavior for both `dataset.view` and `dataset.validate`.
- Result API:
  - Response includes dataset status, validation status, preview status, preview metadata, extracted metadata, latest result, and validation result history.
  - Result history ordering is deterministic: `created_at desc, id desc`.
  - Response models do not include presigned URL, storage credential, or byte fields.
- Retry API:
  - Eligible failed states are `validation_status = FAILED` with dataset status `REJECTED`, `QUARANTINED`, or `PROCESSING`.
  - Retry resets eligible datasets to `status = PROCESSING` and `validation_status = PENDING`.
  - Already `PENDING` or `RUNNING` validation is treated as an idempotent no-op with `retry_queued = false`.
  - Retry preserves bucket, object key, ETag, object size, object version, and dataset metadata; this is test-covered.
  - Retry rejects non-eligible passed datasets with `dataset.validation_retry_not_eligible`.
- Audit and outbox:
  - Retry writes `dataset.validation_retry` audit and outbox records in the same transaction as the state reset.
  - The implementation directly constructs `OutboxEvent`; DB defaults and field values are compatible with existing outbox model, and the payload is bounded and contains no URL, credential, or byte material.
  - Existing worker code uses the stricter `append_outbox_event` helper. Using the helper for retry would be a consistency improvement, but not a blocker for this accepted scope because the current payload is safe and tests prove insertion.
- Dev seed:
  - Dev seed now includes `dataset.validate`, keeping permission-code coverage coherent with the new retry API.
- T13 boundary:
  - No production metrics, runbooks, alerting, dispatcher hardening, or operational dashboard work was added.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. No backend file-byte route markers or validation API byte reads were found.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Validation result and retry responses do not return access keys, secret keys, raw credentials, or presigned URLs.
- Presigned URLs are not persisted:
  - Preserved for this scope. Result and retry APIs neither generate nor persist presigned URLs.
- Complete uses object storage ListParts as authority:
  - Preserved. This API slice does not modify upload completion logic.
- Authorization uses permission_grants:
  - Preserved. Both new APIs use `AuthorizationService` with resource-scoped permission checks.
- Internal IDs remain UUIDs:
  - Preserved. No schema or identifier changes were introduced.
- Object identity and object metadata are preserved on retry:
  - Preserved and test-covered.

## Risks and Follow-up

- Remaining risks:
  - HDF5 extraction remains stub-level from the prior accepted worker slice.
  - Retry is state-idempotent rather than `idempotency_records` backed; acceptable for this no-body retry endpoint and covered by repeated-call tests.
  - Direct `OutboxEvent` construction bypasses `append_outbox_event` payload validation; current payload is safe, but using the helper would reduce future drift risk.
  - Retry preserves prior preview metadata and extracted metadata. This matches history preservation and object identity preservation, but stale preview information can remain visible until the next worker result overwrites it.
- Known gaps:
  - None blocking for the remaining T12 Validation Result API + Retry Validation API scope.
- Suggested next agent:
  - Merge agent for full T12, followed by master review. T13 should remain blocked until this accepted API slice is merged.
