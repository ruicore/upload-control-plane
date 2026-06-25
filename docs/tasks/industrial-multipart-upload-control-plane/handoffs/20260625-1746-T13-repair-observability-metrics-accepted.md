# T13 Repair Observability Metrics Accepted

## Scope

- Branch: `codex/industrial-upload/T13-repair-observability-metrics`
- Base: validation rejection commit `4dd996a`
- Repair target: `/metrics` must render every metric family required by PRD 27.2.
- Explicitly out of scope: T14 failure injection, benchmark implementation, production monitoring stack, external dependencies, or high-cardinality/object-key metrics.

## Changes

- Extended `src/upload_control_plane/observability.py` so `/metrics` renders all PRD 27.2 required metric families.
- Added DB-backed bounded aggregate samples where current tables provide safe state:
  - upload sessions by tenant/status/error code
  - datasets by tenant/status/validation state
  - upload tasks by tenant/status/error code
  - device registration, last-seen age, and revoked credentials by tenant
  - outbox pending/dead-letter/delivered/failed by tenant and event type
- Added zero-valued placeholder samples for not-yet-instrumented paths, with bounded labels such as `tenant_id="unknown"`, `scope="unknown"`, `error_code="unknown"`, and `event_type="unknown"`.
- Tightened empty in-memory counter/histogram samples so required labels are present on placeholder output.
- Added `tests/api/test_observability.py::test_metrics_covers_complete_prd_required_metric_family_list`, which parses the PRD required metrics block and compares it to rendered `# TYPE` families.
- Updated `docs/operations-observability.md` to document process-local/in-memory reset behavior, placeholder samples, DB-backed snapshot limits, and secret/object-key exclusion.

## Security and Cardinality

- No metric labels include object keys, bucket URLs, credentials, presigned query strings, raw filenames, or raw `session_id`.
- Placeholder labels are bounded and use fixed values for not-yet-instrumented paths.
- Existing redaction and signed URL query stripping behavior was preserved.

## Verification

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `85 files already formatted`
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 85 source files`
- `uv run pytest tests/api/test_observability.py tests/infrastructure/test_s3_storage.py tests/infrastructure/test_seed_dev.py -q`
  - Passed: `15 passed, 1 warning in 1.48s`
- `uv run pytest -q`
  - Passed: `205 passed, 1 warning in 13.64s`
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
  - Reviewed expected matches only: outbox byte-payload rejection and `get_object_storage` dependency naming.
- Credential/presigned URL marker scan:
  - Command: `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\operations-observability.md`
  - Reviewed expected matches only: redaction constants/tests, storage adapter/config credential fields, device credential response code/tests, and API names.
- Signed-query example scan:
  - Command: `rg -n "https?://[^\s\"']+\?[^\s\"']*(X-Amz|Signature|Credential|secret|token|uploadId|partNumber)" docs src\upload_control_plane tests`
  - Passed: no matches.

## Residual Risks

- In-process counters and histograms still reset on API process restart.
- Placeholder samples are present for not-yet-instrumented request paths until later slices wire those paths to runtime events.
- DB-backed values are aggregate snapshots, not historical counter streams.
