# T14 Quota Backpressure Repair 2 acceptance

Status: accepted
Agent type: T14 repair2 agent
Branch: codex/industrial-upload/T14-repair2-quota-backpressure
Worktree: D:\upload-control-plane-T14-implementation-failure-benchmark
Baseline: 4a6d1c6
Started: 2026-06-25 18:17 Asia/Shanghai
Finished: 2026-06-25 18:17 Asia/Shanghai

## Scope

- Repair the rejected T14 handoff finding from `20260625-1818-T14-validation-failure-benchmark-rejected.md`.
- Convert already implemented create-upload quota gates into real regression tests.
- Keep only the genuinely missing storage backpressure rejection as a narrow xfail.
- Do not implement new product behavior.
- Do not touch Phase 14 MQTT, Go uploader/gateway work, backend byte proxying, or MinIO credential exposure.

## Rejected handoff fix

The rejected handoff correctly identified that `tests/test_phase13_capability_gaps.py::test_quota_or_backpressure_rejection_gap` was too broad. Current product code already rejects create-upload quota violations in `CreateUploadTaskService._validate_quota_before_storage`.

This repair:

- Added API regression tests in `tests/api/test_upload_task_api_foundation.py` for existing create-upload quota behavior:
  - `test_upload_task_create_rejects_too_many_objects_before_storage`
  - `test_upload_task_create_rejects_open_task_quota_before_storage`
  - `test_upload_task_create_rejects_project_byte_quota_before_storage`
- Each quota test uses the existing dev seed/client/fake storage pattern and asserts `storage.create_calls == []`, proving quota rejection happens before storage multipart initiation.
- Replaced the broad quota/backpressure xfail with `test_backpressure_rejection_gate_gap`.
- The remaining backpressure xfail reason now states the narrow gap: backpressure settings and metrics exist, but no upload create or presign path rejects requests based on storage backpressure.

## Remaining xfail list

- `tests/test_phase13_capability_gaps.py::test_backpressure_rejection_gate_gap`
  - Reason: backpressure settings and metrics exist, but no upload create or presign path rejects requests based on storage backpressure yet.
- `tests/test_phase13_capability_gaps.py::test_kms_unavailable_rejection_gap`
  - Reason: KMS configuration fields exist, but there is no policy path that requires KMS and rejects initiation when KMS is unavailable.
- `tests/test_phase13_capability_gaps.py::test_completed_dataset_automated_restore_or_rebuild_gap`
  - Reason: completed dataset reconciliation classifies missing-object, metadata-only, verified, and object-only cases in the lifecycle worker, but no product path rebuilds dataset DB metadata from an object-only reference or restores a missing final object.

## Validation commands

- `uv run pytest tests\api\test_upload_task_api_foundation.py::test_upload_task_create_rejects_too_many_objects_before_storage tests\api\test_upload_task_api_foundation.py::test_upload_task_create_rejects_open_task_quota_before_storage tests\api\test_upload_task_api_foundation.py::test_upload_task_create_rejects_project_byte_quota_before_storage tests\test_phase13_capability_gaps.py -q`
  - Passed: `3 passed, 3 xfailed, 1 warning`.
- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `87 files already formatted`.
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 87 source files`.
- Focused T14 plus new quota, purge, and worker lifecycle suite:
  - Command: `uv run pytest tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_too_many_objects_before_storage tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_open_task_quota_before_storage tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_project_byte_quota_before_storage tests/api/test_upload_session_runtime_api.py tests/api/test_cors.py tests/application/test_dataset_validation_worker.py tests/application/test_outbox.py tests/api/test_device_identity_api.py tests/api/test_observability.py tests/infrastructure/test_s3_storage.py tests/scripts/test_benchmark_upload.py tests/test_phase13_capability_gaps.py tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_requires_confirmation_and_retention_policy_approval tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_rejects_object_lock_and_legal_hold_policy tests/application/test_worker_lifecycle.py -q`
  - Passed: `55 passed, 3 xfailed, 1 warning`.
- `uv run pytest -q`
  - Passed: `214 passed, 3 xfailed, 1 warning`.
- Benchmark dry-run:
  - Command: `uv run python scripts\benchmark_upload.py --dry-run --size 1MiB --file .benchmarks\tiny-ci-repair2.bin`
  - Passed: `dry-run file=...\tiny-ci-repair2.bin size_bytes=1048576 upload_path=api-presign-direct-storage-put`.
  - The generated local file was removed after validation.
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
  - Reviewed expected matches only: existing negative redaction tests, existing PRD examples, existing storage-domain tests, existing observability fake presigned URLs, and older T07 handoff smoke text. No signed-query examples were added in this repair.

## Residual risks

- The live 512 MiB benchmark path was not executed in this repair; only dry-run was required and revalidated.
- Backpressure rejection remains a real missing product path and is tracked by the narrow xfail.
- KMS unavailable rejection and completed dataset automated restore/rebuild remain unchanged capability gaps.
