# Handoff: T13 Observability and Operations implementation

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T13-implementation-observability
Worktree: D:\upload-control-plane-T13-implementation-observability
Base: c3efbc4
Started: 2026-06-25 17:17 Asia/Shanghai
Finished: 2026-06-25 17:33 Asia/Shanghai

## Scope

- Implement T13 Observability and Operations after full T12 acceptance.
- Preserve no-file-byte-proxy and no-storage-credential exposure constraints.
- Do not push.

## Changes

- Added project-scoped request observability:
  - Request middleware records API request count and duration metrics.
  - Request logs include request ID, operation template, path, method, status, latency, and route IDs where available.
  - Logging configuration is scoped to `upload_control_plane` loggers to avoid breaking third-party log records.
- Added `src/upload_control_plane/observability.py`:
  - JSON log formatter for non-local environments.
  - URL query redaction and recursive secret-field sanitization.
  - In-memory counters/histograms rendered as Prometheus text.
  - DB-backed operational gauges for upload session status, validation backlog, cleanup backlog, recovery mismatch state, and outbox pending/dead-letter state.
- Added `GET /metrics`:
  - Returns `text/plain; version=0.0.4; charset=utf-8`.
  - Includes expected API request metrics, storage operation metrics, upload session status, validation backlog, cleanup backlog, recovery, and outbox metrics.
- Instrumented S3/MinIO adapter `_call` boundary:
  - Records `storage_operation_duration_seconds{operation}`.
  - Records `storage_operation_errors_total{operation,error_code}` with provider code or exception class only.
  - Does not record object keys, bucket credentials, or URLs.
- Added `GET /v1/projects/{project_id}/audit-events`:
  - Requires `audit.view` on the project via existing `permission_grants`.
  - Supports bounded `limit`, `dataset_id`, and `action` filters.
  - Redacts presigned URL query strings and secret-looking fields from `before_state`, `after_state`, and `metadata`.
- Added dev seed permission:
  - `audit.view` on the seeded project for the seeded API key and device subject.
- Added `docs/operations-observability.md`:
  - Metric list, structured-log contract, alert examples, operator audit notes, and runbooks for KMS, CORS, storage outage, leaked URL, device compromise, cleanup backlog, outbox dead letters, and recovery.
  - No signed URL query-string examples.
- Added focused tests:
  - Metrics content type/body and expected metric names.
  - Request logging path context and no query-string leakage.
  - Audit endpoint permission and redaction.
  - JSON formatter redaction.

## Verification

- `uv run ruff check src tests`
  - Result: passed, `All checks passed!`.
- `uv run ruff format --check src tests`
  - Result: passed, `85 files already formatted`.
- `uv run mypy src tests`
  - Result: passed, `Success: no issues found in 85 source files`.
- `uv run pytest tests/api/test_observability.py tests/infrastructure/test_s3_storage.py tests/infrastructure/test_seed_dev.py -q`
  - Result: passed, `14 passed, 1 warning in 1.76s`.
- `uv run pytest -q`
  - Result: passed, `204 passed, 1 warning in 15.44s`.
- `docker compose config --quiet`
  - Result: passed, no output.
- `git diff --check`
  - Result: passed, no output.
- Backend file-byte/proxy route scan:
  - Command: `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body|StreamingResponse|FileResponse" src\upload_control_plane\api src\upload_control_plane\application`
  - Result: passed, no matches.
- Backend byte-read/download scan:
  - Command: `rg -n "get_object|download_file|iter_chunks|StreamingBody|\.read\(|read_bytes|bytes\(|bytearray|memoryview" src\upload_control_plane\api src\upload_control_plane\application`
  - Result: reviewed expected matches only:
    - `src\upload_control_plane\application\outbox.py` rejects byte-like payloads.
    - `src\upload_control_plane\api\upload_tasks.py` uses `get_object_storage` dependency naming only.
- Credential/presigned URL marker scan:
  - Command: `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\operations-observability.md`
  - Result: reviewed expected matches only:
    - Redaction constants and negative tests.
    - Existing config/storage adapter internal credentials.
    - Existing device credential one-time provisioning response code/tests.
    - Existing dataset download URL API names.
    - New observability tests that assert redaction.
- Signed-query example scan:
  - Command: `rg -n 'https?://[^\s"'']+\?[^\s"'']*(X-Amz|Signature|Credential|secret|token|uploadId|partNumber)' docs src\upload_control_plane tests`
  - Result: reviewed expected matches only:
    - Existing PRD API-contract examples from earlier accepted docs.
    - Existing accepted handoff smoke command text.
    - Negative tests proving manifest/outbox/observability redaction.
    - No matches in `docs/operations-observability.md`.

## Product Constraints

- No backend file-byte proxy route added.
- No request body streaming route added.
- No storage object download through API added.
- No MinIO/S3 access key or secret is returned to clients.
- No presigned URL query string is emitted by the new logs, metrics, audit endpoint, or operations doc.
- Authorization remains based on resource-scoped `permission_grants`.
- No hosted monitoring stack or Compose service was added.
- T14 failure injection and benchmark scope was not implemented.

## Residual Risks

- Metrics are a lightweight in-process implementation, so API/storage counters reset on process restart.
- DB-backed gauges are point-in-time snapshots and not historical counters for prior lifecycle events.
- Quota/rate-limit/backpressure metrics expose zero-valued families until those rejection paths are implemented with explicit instrumentation.
- Replication metrics are zero-valued placeholders because current local storage integration does not expose provider replication state.
- Audit query is project-scoped and bounded; broader tenant/admin audit search remains future scope if a concrete operator model is accepted.
- Full pytest continues to emit the existing `StarletteDeprecationWarning` from FastAPI TestClient/httpx compatibility.

## Final State

- Implementation branch is ready for validation.
- No push was performed.
