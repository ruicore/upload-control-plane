# T14 Failure Injection and Benchmark Suite independent validation

Status: rejected
Agent type: T14 independent validation agent
Branch: codex/industrial-upload/T14-validation-failure-benchmark
Validated branch: codex/industrial-upload/T14-repair-failure-benchmark-gaps
Validated HEAD: ec92af5
Worktree: D:\upload-control-plane-T14-implementation-failure-benchmark
Started: 2026-06-25 18:18 Asia/Shanghai
Finished: 2026-06-25 18:18 Asia/Shanghai

## Required documents read

- `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`, Phase 13 - Failure Injection and Benchmark Suite.
- `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`, relevant failure-mode sections for validation failure, outbox failure, retention purge, legal hold/object lock, CORS, checksum, quota/backpressure, KMS, and restore reconciliation.
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1803-T14-implementation-failure-benchmark-accepted.md`.
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1807-T14-repair-failure-benchmark-gaps-accepted.md`.

## Verdict

Rejected for one correctness issue in the remaining xfail inventory.

`tests/test_phase13_capability_gaps.py::test_quota_or_backpressure_rejection_gap` is not narrow enough and its reason is factually overbroad. It says quota/backpressure upload or presign rejection gates are not implemented, but the current product path already has a create-upload quota gate in `CreateUploadTaskService._validate_quota_before_storage`:

- rejects too many objects with `upload_task.too_many_objects`;
- rejects too many open upload tasks with `quota.open_upload_tasks_exceeded`;
- rejects project byte quota with `quota.project_bytes_exceeded`;
- rejects tenant byte quota with `quota.tenant_bytes_exceeded`.

The remaining real gap appears to be narrower: no dedicated backpressure rejection path was found, and no focused Phase 13 regression currently proves the existing quota rejection behavior. Keeping a combined quota/backpressure xfail risks masking an already implemented product path.

## Accepted evidence

- Purge/legal-hold is no longer hidden by a capability-gap xfail.
- Existing purge governance tests cover the real API path:
  - `tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_requires_confirmation_and_retention_policy_approval`
  - `tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_rejects_object_lock_and_legal_hold_policy`
- Worker lifecycle reconciliation is included in the focused suite and covers missing-object, metadata-only, verified, and object-only classification behavior.
- The benchmark script defaults to `512MiB`, supports `--dry-run`, creates sparse files by default, and writes deterministic materialized files in bounded chunks.
- The benchmark path delegates to the existing CLI uploader: API create, presign, ack, complete, plus direct `httpx.Client.put(..., content=iter_file_range(...))` to presigned storage URLs.
- No benchmark path uses MinIO credentials or adds a backend byte proxy.
- `docs/benchmarks.md` provides safe local commands and a report template. It does not include signed URL query examples or credentials.
- No Phase 14 MQTT adapter, Go uploader, or gateway work was added in this validation scope.

## Validation commands

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `87 files already formatted`
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 87 source files`
- Focused T14 plus purge and worker lifecycle suite:
  - Command: `uv run pytest tests/api/test_upload_session_runtime_api.py tests/api/test_cors.py tests/application/test_dataset_validation_worker.py tests/application/test_outbox.py tests/api/test_device_identity_api.py tests/api/test_observability.py tests/infrastructure/test_s3_storage.py tests/scripts/test_benchmark_upload.py tests/test_phase13_capability_gaps.py tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_requires_confirmation_and_retention_policy_approval tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_rejects_object_lock_and_legal_hold_policy tests/application/test_worker_lifecycle.py -q`
  - Passed: `52 passed, 3 xfailed, 1 warning`
- Full pytest:
  - Command: `uv run pytest -q`
  - Passed: `211 passed, 3 xfailed, 1 warning`
- Benchmark dry-run:
  - Command: `uv run python scripts\benchmark_upload.py --dry-run --size 1MiB --file .benchmarks\tiny-ci-validation.bin`
  - Passed: `dry-run file=...\tiny-ci-validation.bin size_bytes=1048576 upload_path=api-presign-direct-storage-put`
- `docker compose config --quiet`
  - Passed with no output.
- `git diff --check`
  - Passed with no output.

## Hard scans

- Backend file-byte/proxy scan:
  - Command: `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body|StreamingResponse|FileResponse" src\upload_control_plane\api src\upload_control_plane\application`
  - Passed: no matches.
- Byte-read/download route scan:
  - Command: `rg -n "get_object|download_file|iter_chunks|StreamingBody|\.read\(|read_bytes|bytes\(|bytearray|memoryview" src\upload_control_plane\api src\upload_control_plane\application scripts tests docs\benchmarks.md`
  - Reviewed expected matches only: benchmark size parsing and bounded deterministic bytes generation, outbox byte payload rejection, test helper file writes, integration/storage adapter tests, and API dependency names.
- Credential/signed marker scan:
  - Command: `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\benchmarks.md scripts\benchmark_upload.py`
  - Reviewed expected matches only: redaction constants/tests, internal storage config fields, one-time device credential tests/API shape, storage presign implementation, and dataset download URL API names.
- Signed-query scan:
  - Command: `rg -n 'https?://[^\s"'']+\?[^\s"'']*(X-Amz|Signature|Credential|secret|token|uploadId|partNumber)' docs src\upload_control_plane tests scripts\benchmark_upload.py`
  - Reviewed expected matches only: existing negative redaction tests, existing PRD examples, existing storage-domain tests, and older T07 handoff smoke text. No signed-query examples were found in `docs/benchmarks.md` or `scripts/benchmark_upload.py`.

## Required repair before acceptance

- Replace the combined quota/backpressure xfail with narrower coverage:
  - add real regression tests for the existing create-upload quota rejection behavior; and
  - keep only the genuinely missing backpressure rejection as xfail, if still unimplemented.

## Residual risks

- The live 512 MiB benchmark path was not executed during validation; only dry-run was executed, matching the requested validation command list.
- Expired presign attempts currently assert `409 upload.invalid_state`; this remains a product decision risk if the PRD-preferred `410 Gone` is adopted later.
- Completed dataset automated restore/rebuild remains a legitimate gap if product requirements require DB metadata rebuild from object-only storage listings or restoration of missing final objects.
