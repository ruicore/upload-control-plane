# T14 Failure Injection and Benchmark Suite independent validation 2

Status: accepted
Agent type: T14 independent validation agent
Branch: codex/industrial-upload/T14-validation2-failure-benchmark
Validated branch: codex/industrial-upload/T14-repair2-quota-backpressure
Validated HEAD: 660c3e6
Worktree: D:\upload-control-plane-T14-implementation-failure-benchmark
Started: 2026-06-26 Asia/Shanghai
Finished: 2026-06-26 Asia/Shanghai

## Required documents read

- `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`, Phase 13 - Failure Injection and Benchmark Suite.
- `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`, relevant failure-mode sections.
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1803-T14-implementation-failure-benchmark-accepted.md`.
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1807-T14-repair-failure-benchmark-gaps-accepted.md`.
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1818-T14-validation-failure-benchmark-rejected.md`.
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1817-T14-repair2-quota-backpressure-accepted.md`.

## Verdict

Accepted.

The previous rejected blocker is repaired. Create-upload quota gates are now covered by real API regression tests, and the remaining xfail is narrowed to the missing storage backpressure rejection gate.

## Acceptance evidence

- Existing create-upload quota gates are implemented in `CreateUploadTaskService._validate_quota_before_storage` before storage multipart initiation.
- New regression tests cover:
  - `tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_too_many_objects_before_storage`
  - `tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_open_task_quota_before_storage`
  - `tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_project_byte_quota_before_storage`
- Each quota regression asserts `storage.create_calls == []`, proving rejection happens before storage multipart initiation.
- Remaining xfails are:
  - `tests/test_phase13_capability_gaps.py::test_backpressure_rejection_gate_gap`
  - `tests/test_phase13_capability_gaps.py::test_kms_unavailable_rejection_gap`
  - `tests/test_phase13_capability_gaps.py::test_completed_dataset_automated_restore_or_rebuild_gap`
- Phase 13 coverage evidence remains present for:
  - purge retention, object-lock, and legal-hold denial in dataset lifecycle API tests;
  - worker lifecycle reconciliation in `tests/application/test_worker_lifecycle.py`;
  - validation failure in `tests/application/test_dataset_validation_worker.py`;
  - outbox delivery failure in `tests/application/test_outbox.py`;
  - device credential revocation/disable/expiration in `tests/api/test_device_identity_api.py`;
  - CORS/signed-header mismatch in `tests/api/test_cors.py`;
  - checksum mismatch, duplicate complete, missing storage part, and permission revocation in `tests/api/test_upload_session_runtime_api.py`.
- `scripts/benchmark_upload.py` defaults to `512MiB`, supports `--dry-run`, creates sparse files by default, and materializes deterministic files in bounded chunks when requested.
- Benchmark upload uses the existing CLI uploader path: API create/presign/ack/complete plus direct storage `PUT`. It does not use MinIO credentials and does not add a backend byte proxy.
- `docs/benchmarks.md` contains safe benchmark commands and a report template without signed URL query samples or credentials.
- No Phase 14 MQTT adapter, Go uploader, or gateway implementation was added.

## Validation commands

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `87 files already formatted`
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 87 source files`
- Focused T14 plus quota, purge, and worker lifecycle suite:
  - Command: `uv run pytest tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_too_many_objects_before_storage tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_open_task_quota_before_storage tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_project_byte_quota_before_storage tests/api/test_upload_session_runtime_api.py tests/api/test_cors.py tests/application/test_dataset_validation_worker.py tests/application/test_outbox.py tests/api/test_device_identity_api.py tests/api/test_observability.py tests/infrastructure/test_s3_storage.py tests/scripts/test_benchmark_upload.py tests/test_phase13_capability_gaps.py tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_requires_confirmation_and_retention_policy_approval tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_rejects_object_lock_and_legal_hold_policy tests/application/test_worker_lifecycle.py -q`
  - Passed: `55 passed, 3 xfailed, 1 warning`
- `uv run pytest -q`
  - Passed: `214 passed, 3 xfailed, 1 warning`
- Benchmark dry-run:
  - Command: `uv run python scripts\benchmark_upload.py --dry-run --size 1MiB --file .benchmarks\tiny-ci-validation2.bin`
  - Passed: `dry-run file=...\tiny-ci-validation2.bin size_bytes=1048576 upload_path=api-presign-direct-storage-put`
  - Generated dry-run file removed after validation.
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
  - Reviewed expected matches only: benchmark size parsing and bounded deterministic bytes generation, outbox byte payload rejection, test helper writes, storage integration tests, and API dependency names.
- Credential/signed marker scan:
  - Command: `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\benchmarks.md scripts\benchmark_upload.py`
  - Reviewed expected matches only: redaction constants/tests, internal storage config fields, one-time device credential tests/API shape, storage presign implementation, and dataset download URL API names.
- Signed-query scan:
  - Command: `rg -n 'https?://[^\s"'']+\?[^\s"'']*(X-Amz|Signature|Credential|secret|token|uploadId|partNumber)' docs src\upload_control_plane tests scripts\benchmark_upload.py`
  - Reviewed expected matches only: existing negative redaction tests, existing PRD examples, storage-domain tests, observability fake presigned URLs, and older T07 handoff smoke text. No signed-query examples were found in `docs/benchmarks.md` or `scripts/benchmark_upload.py`.

## Remaining gaps and risks

- Backpressure rejection remains a real missing product path and is intentionally tracked by a narrow xfail.
- KMS unavailable rejection remains a Phase 13 capability gap.
- Completed dataset automated restore/rebuild remains a capability gap beyond current lifecycle reconciliation classification coverage.
- Live 512 MiB benchmark was not executed in this validation; dry-run was executed as requested.
