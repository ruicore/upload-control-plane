# Handoff: T12 Dataset Validation Worker Foundation

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T12-implementation-validation-worker
Worktree: D:\upload-control-plane-T12-implementation-validation-worker
Started: 2026-06-25 16:12 +08:00
Finished: 2026-06-25 16:23 +08:00

## Scope

- Intended scope:
  - Implement the T12 worker foundation for dataset validation and metadata extraction.
  - Find completed datasets explicitly queued for validation and transition validation lifecycle.
  - Persist validation result rows and dataset preview/extracted metadata where the current schema supports it.
  - Mark successful validation as `READY` / `PASSED`; mark failed validation as `REJECTED` / `FAILED` without deleting object storage data.
  - Add a worker CLI command for one validation pass.
- Explicitly out of scope:
  - Validation result API.
  - Retry validation API.
  - Product analytics, preview UI, and full HDF5 byte parser.
  - T13 metrics, alerting, and runbook work.
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
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1612-T11-merge-workers-outbox-accepted.md`

## Changes

- Files changed:
  - `src/upload_control_plane/application/dataset_validation.py`
  - `src/upload_control_plane/application/upload_sessions.py`
  - `src/upload_control_plane/worker/main.py`
  - `tests/application/test_dataset_validation_worker.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1623-T12-implementation-validation-worker-accepted.md`
- Behavior changed:
  - When `enable_dataset_validation` is true, upload completion now changes a `NOT_REQUIRED` dataset validation state to `PENDING` while keeping dataset lifecycle in `PROCESSING`.
  - `DatasetValidationWorkerService` claims `PROCESSING` datasets with completed upload sessions and `validation_status = PENDING`.
  - Claimed datasets move through `RUNNING` and temporary `QUARANTINED` state while the worker validates them.
  - Successful validation writes `dataset_validation_results`, stores bounded extracted metadata under dataset metadata, stores preview metadata, sets `validation_status = PASSED`, and releases the dataset to `READY`.
  - Failed validation writes `dataset_validation_results.errors`, sets `validation_status = FAILED`, and keeps the object metadata intact while setting dataset status to `REJECTED`.
  - Validation pass/fail audit and outbox events are appended in the same DB transaction as the final domain transition.
  - `upload-worker validate-datasets` runs one validation pass; periodic `upload-worker run` also runs validation as a no-op unless validation is enabled.
- Compatibility notes:
  - No schema migration was needed because T02 already created `dataset_validation_results`, `preview_metadata`, and validation status columns.
  - The HDF5 extractor is a lightweight stub: it uses storage `head_object`, filename/content-type inference, and bounded metadata only. It does not parse file bytes.
  - Worker candidates intentionally require `validation_status = PENDING`; this avoids accidentally processing old `NOT_REQUIRED` datasets from before validation was enabled.

## Verification

- Commands run:
  - `uv run ruff check src tests`
    - Result: passed, `All checks passed!`.
  - `uv run ruff format --check src tests`
    - Result: passed, `82 files already formatted`.
  - `uv run mypy src tests`
    - Result: passed, `Success: no issues found in 82 source files`.
  - `uv run pytest tests/application/test_dataset_validation_worker.py tests/application/test_worker_lifecycle.py tests/application/test_outbox.py tests/api/test_dataset_lifecycle_api.py -q`
    - Result: passed, `22 passed, 1 warning in 6.26s`.
  - `uv run pytest -q`
    - Result: passed, `194 passed, 1 warning in 12.36s`.
  - `uv run upload-worker --help`
    - Result: passed; command list includes `validate-datasets`.
  - `docker compose config --quiet`
    - Result: passed, no output.
  - `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body" src/upload_control_plane/api src/upload_control_plane/application`
    - Result: passed, no hits.
  - `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body" src tools tests`
    - Result: reviewed expected non-backend hits only: CLI temp file usage and manual browser uploader browser `File` object handling.
  - `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|bytes\(|bytearray|memoryview" src tools tests`
    - Result: reviewed expected hits only: CLI/browser redaction tests, server-side S3 config/adapter internals, dataset download URL API, and outbox guard tests.
- Commands not run and why:
  - None within this foundation slice.
- Diagnostic note:
  - An initial focused pytest run failed because the first worker candidate query also selected historical `NOT_REQUIRED` completed datasets in the shared local test DB. The implementation was narrowed to explicit `PENDING` validation candidates, and completion now sets `PENDING` only when validation is enabled. The focused and full suites passed after this fix.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. The validation worker reads only object metadata through `head_object`; it does not download or proxy object bytes.
- Clients receive no MinIO/S3 credentials:
  - Preserved. No client-facing response or API shape was added.
- Complete uses object storage ListParts as authority:
  - Preserved. Completion logic is unchanged except for setting dataset validation queue state after successful storage-authoritative completion.
- Authorization uses permission_grants:
  - Preserved. No authorization shortcut or public endpoint was added.
- Internal IDs remain UUIDs:
  - Preserved. Validation result and outbox/audit rows use existing UUID model.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go uploader, or edge gateway behavior was introduced.

## Risks and Follow-up

- Remaining risks:
  - HDF5 extraction is intentionally stub-level and does not inspect file internals yet.
  - Periodic validation currently uses the same simple pass as the CLI command; T13 should add backlog/latency metrics and operational controls.
- Known gaps:
  - No Validation Result API in this slice.
  - No Retry Validation API in this slice.
  - No permission-checked retry flow yet; failed datasets remain `REJECTED` until a future API/worker reset path is added.
- Suggested next agent:
  - T12 Validation API agent for result retrieval, permission-checked retry, and idempotent retry state reset from `FAILED` / `REJECTED` to `PENDING` / `PROCESSING`.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T12 Validation API implementation can build on `DatasetValidationWorkerService` and `dataset_validation_results`.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not scan all historical `NOT_REQUIRED` completed datasets as validation candidates; queue validation with explicit `PENDING` state.
