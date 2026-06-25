# T13 Observability and Operations validation 2 accepted

Status: accepted
Agent type: Independent validation
Validation branch: codex/industrial-upload/T13-validation2-observability
Validated repair branch: codex/industrial-upload/T13-repair-observability-metrics
Validated repair commit: 4a06425
Worktree: D:\upload-control-plane-T13-implementation-observability
Started: 2026-06-25 17:40 Asia/Shanghai
Finished: 2026-06-25 17:50 Asia/Shanghai

## Scope

- Independently re-validate full T13 after the repair.
- Do not modify implementation code.
- Do not push.

## Read Inputs

- `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md` T13/Phase 12 section.
- `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md` sections 27.2 and 27.4.
- `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md` redaction, secret, URL, and implementation-rule constraints.
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1733-T13-implementation-observability-accepted.md`.
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1737-T13-validation-observability-rejected.md`.
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1746-T13-repair-observability-metrics-accepted.md`.

## Acceptance Evidence

- The previous rejected blocker is fixed. A direct TestClient check of `GET /metrics` parsed the PRD 27.2 required metrics block and compared it to rendered `# TYPE` families:
  - Required families: 46.
  - Rendered metric families: 49.
  - Missing required families: none.
  - Response status: 200.
  - Content-Type: `text/plain; version=0.0.4; charset=utf-8`.
- `tests/api/test_observability.py::test_metrics_covers_complete_prd_required_metric_family_list` now enforces full PRD metric-family coverage from the PRD source text.
- Placeholder metric labels are bounded fixed values such as `unknown` or fixed low-cardinality dimensions, and the direct `/metrics` scan found no `X-Amz-Signature`, `X-Amz-Credential`, `secret`, `password`, `AKIA`, `http://`, or `https://` in the response body.
- Prometheus text compatibility is acceptable for T13: metric families include `# HELP`, `# TYPE`, labeled samples, histogram bucket/count/sum samples, and the endpoint returns Prometheus text content type.
- Structured request logging preserves request context:
  - Middleware records `request_id`, route template operation, path without query string, method, status/status_code, latency, and route-derived `project_id`, `dataset_id`, or `session_id` where applicable.
  - Focused tests prove query-string markers are absent from captured request log records.
- Redaction and secret handling remain in scope:
  - `JsonLogFormatter` sanitizes log fields.
  - `sanitize_for_observability` recursively redacts sensitive keys and strips URL query strings.
  - Audit response redacts `before_state`, `after_state`, and `metadata`.
- S3 instrumentation remains at the storage adapter `_call` boundary:
  - Records `storage_operation_duration_seconds{operation}` for success and failure.
  - Records `storage_operation_errors_total{operation,error_code}` with provider code or exception class only.
  - Does not include bucket, object key, URL, credentials, or upload ID in labels.
- Operator audit endpoint remains project-scoped and permission-checked:
  - `GET /v1/projects/{project_id}/audit-events`.
  - Requires `audit.view` through `AuthorizationService`.
  - Tenant/project filters are applied before returning events.
  - `limit` is bounded to 1..200, with optional `dataset_id` and `action` filters.
- SLO, alert, and runbook documentation exists in `docs/operations-observability.md` and covers storage errors, cleanup backlog, validation backlog, recovery, outbox dead letters, KMS, CORS, leaked URL, device compromise, cleanup, outbox, and recovery.
- No T14 failure-injection or benchmark implementation was found in `src`, `tests`, or `docs/operations-observability.md`.

## Verification Commands

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `85 files already formatted`
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 85 source files`
- `uv run pytest tests/api/test_observability.py tests/infrastructure/test_s3_storage.py tests/infrastructure/test_seed_dev.py -q`
  - Passed: `15 passed, 1 warning in 1.65s`
- `uv run pytest -q`
  - Passed: `205 passed, 1 warning in 13.47s`
- `docker compose config --quiet`
  - Passed with no output.
- `git diff --check`
  - Passed with no output.

## Hard Scans

- Backend file-byte/proxy route scan:
  - Command: `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body|StreamingResponse|FileResponse" src\upload_control_plane\api src\upload_control_plane\application`
  - Passed: no matches.
- Backend byte-read/download scan:
  - Command: `rg -n "get_object|download_file|iter_chunks|StreamingBody|\.read\(|read_bytes|bytes\(|bytearray|memoryview" src\upload_control_plane\api src\upload_control_plane\application`
  - Reviewed expected matches only: outbox rejects byte-like payloads; `get_object_storage` is dependency naming only.
- Credential and signed URL marker scan:
  - Command: `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\operations-observability.md`
  - Reviewed expected matches only: config/internal storage credential fields, redaction constants, one-time device credential response/tests, API names, and negative tests proving redaction.
- Signed-query example scan:
  - Command: `rg -n "https?://[^\s\"']+\?[^\s\"']*(X-Amz|Signature|Credential|secret|token|uploadId|partNumber)" docs src\upload_control_plane tests`
  - Passed: no matches.
- T14/failure-injection scope scan:
  - Command: `rg -n "failure injection|benchmark|toxiproxy|chaos|latency injection|fault injection|T14|Phase 13" src tests docs\operations-observability.md docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1746-T13-repair-observability-metrics-accepted.md`
  - Reviewed expected out-of-scope note in the repair handoff only.

## Residual Risks

- In-process counters and histograms reset when the API process restarts.
- DB-backed metrics are aggregate snapshots, not durable historical counter streams.
- Some PRD metric families are zero-valued placeholders until later slices wire explicit runtime instrumentation for those paths.
- Worker process logs may need later tightening if worker JSON logging becomes a hard acceptance surface beyond API request logging.
- Full pytest still emits the existing `StarletteDeprecationWarning` from FastAPI TestClient/httpx compatibility.

## Final State

- T13 validation result: accepted.
- Implementation code was not modified.
- Validation handoff was added on `codex/industrial-upload/T13-validation2-observability`.
- No push was performed.
