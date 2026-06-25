# Handoff: T13 Observability and Operations validation

Status: rejected
Agent type: Validation
Branch: codex/industrial-upload/T13-validation-observability
Validated implementation branch: codex/industrial-upload/T13-implementation-observability
Validated implementation commit: a595f5ab762db44c8aa6085d1ed87d4ce6b4ffa6
Worktree: D:\upload-control-plane-T13-implementation-observability
Started: 2026-06-25 17:33 Asia/Shanghai
Finished: 2026-06-25 17:37 Asia/Shanghai

## Scope

- Independently validate T13 Observability and Operations.
- Do not modify implementation code.
- Do not push.

## Read Inputs

- `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
- `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
- `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1733-T13-implementation-observability-accepted.md`

Note: the prompt referenced `docs/tasks/industrial-multipart-upload-control-plane/13-implementation-plan.md`, but that file does not exist in this worktree. The corresponding implementation plan is under `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`.

## Blocking Finding

### P1 - `/metrics` omits many PRD-contracted metric families

`GET /metrics` is reachable and returns Prometheus text format, but it does not expose a large part of the metric family list required by PRD section 27.2. A direct response comparison against the PRD metric names found 30 missing families:

```text
upload_sessions_created_total
upload_sessions_completed_total
upload_sessions_aborted_total
upload_sessions_failed_total
upload_sessions_expired_total
upload_presign_requests_total
upload_presign_parts_total
upload_part_ack_total
upload_pause_requests_total
upload_resume_requests_total
upload_complete_requests_total
upload_complete_missing_parts_total
dataset_created_total
dataset_ready_total
dataset_validation_failed_total
dataset_deleted_total
dataset_purged_total
dataset_download_url_requests_total
dataset_quarantined_total
dataset_rejected_total
dataset_legal_hold_denied_purge_total
upload_tasks_created_total
upload_tasks_completed_total
upload_tasks_failed_total
device_registered_total
device_last_seen_age_seconds
device_credential_revoked_total
device_auth_failures_total
outbox_events_delivered_total
outbox_events_failed_total
```

Evidence:

- PRD `12-observability-testing-failure-modes.md` section 27.2 lists these as required metrics.
- `src/upload_control_plane/observability.py` currently renders API request metrics, storage duration/errors, storage backpressure, quota/rate limit placeholders, upload session status gauge, validation backlog, recovery, cleanup, outbox pending/dead-letter gauges, and replication placeholders.
- A direct `uv run python` TestClient check of `/metrics` returned status `200` and content type `text/plain; version=0.0.4; charset=utf-8`, then reported `missing 30` for the list above.

This is not a request for a production monitoring stack. The endpoint can remain lightweight and in-process, but it should at least emit the PRD-contracted family names as counters/gauges, even if some unsupported paths are zero-valued until later instrumentation exists.

## Accepted Evidence

- Prometheus compatibility: `/metrics` returns HTTP 200 and `text/plain; version=0.0.4; charset=utf-8`.
- API latency metrics: `api_requests_total` and `api_request_duration_seconds` are recorded in request middleware with method, route template path, and status code labels.
- Storage metrics: S3/MinIO `_call` records `storage_operation_duration_seconds{operation}` and `storage_operation_errors_total{operation,error_code}`. The adapter passes only operation and mapped provider/error class to observability, not bucket, key, URL, or credentials.
- Structured request log context: request middleware logs `request_id`, route template operation, path without query string, method, status/status_code, latency, and path-derived project/dataset/session IDs where available.
- Audit endpoint: `GET /v1/projects/{project_id}/audit-events` is project-scoped, tenant-scoped, requires `audit.view` through `AuthorizationService` and `permission_grants`, supports bounded `limit` of 1..200, and filters by `dataset_id` and action.
- Redaction: audit response sanitizes `before_state`, `after_state`, and `metadata`; focused tests prove URL query markers and access-key-like values are not returned.
- Dev seed permission: `audit.view` is included for seeded API-key and device grants.
- T14 scope: no failure injection suite or benchmark implementation was added in this slice.

## Verification Commands

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `85 files already formatted`
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 85 source files`
- `uv run pytest tests/api/test_observability.py tests/infrastructure/test_s3_storage.py tests/infrastructure/test_seed_dev.py -q`
  - Passed: `14 passed, 1 warning in 1.29s`
- `uv run pytest -q`
  - Passed: `204 passed, 1 warning in 14.17s`
- `docker compose config --quiet`
  - Passed with no output
- `git diff --check`
  - Passed with no output
- Backend file-byte/proxy route scan:
  - Command: `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body|StreamingResponse|FileResponse" src\upload_control_plane\api src\upload_control_plane\application`
  - Passed: no matches
- Backend byte-read/download scan:
  - Command: `rg -n "get_object|download_file|iter_chunks|StreamingBody|\.read\(|read_bytes|bytes\(|bytearray|memoryview" src\upload_control_plane\api src\upload_control_plane\application`
  - Reviewed expected matches only: outbox byte-payload rejection and `get_object_storage` dependency naming.
- Credential/presigned URL marker scan:
  - Command: `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\operations-observability.md`
  - Reviewed expected matches only: redaction constants/tests, internal config/storage adapter credential fields, one-time device credential response code/tests, and existing API names.
- Signed-query example scan:
  - Command: `rg -n "https?://[^\s\"']+\?[^\s\"']*(X-Amz|Signature|Credential|secret|token|uploadId|partNumber)" docs src\upload_control_plane tests`
  - Reviewed expected matches only: negative tests, existing PRD examples, existing accepted handoff smoke text, and storage-domain test examples. No match in `docs/operations-observability.md`.

## Minimal Fix Recommendation

- Extend `MetricsRegistry.render()` and/or DB-backed render helpers to emit all metric families listed in PRD 27.2.
- For paths not yet implemented or not yet instrumented, emit zero-valued counters/gauges with the contracted labels where practical. Keep label cardinality bounded; use tenant/status/error/event labels from DB or known constants, not raw session IDs.
- Add a focused test that checks the complete PRD metric family list, not only the current subset.

## Residual Risks After Fix

- In-process counters reset on API process restart; acceptable for T13 if documented.
- DB-backed gauges are snapshots, not historical counters; acceptable for local portfolio scope if the contracted counter families are still present.
- Worker process logging uses `logging.basicConfig` rather than the app JSON formatter, so non-local worker structured logging may need a later tightening pass if worker log format becomes part of the hard acceptance surface.

## Final State

- T13 validation result: rejected.
- Implementation code was not modified.
- No push was performed.
