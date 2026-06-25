# T14 Failure Benchmark Gap Repair acceptance

Status: accepted
Agent type: T14 repair agent
Branch: codex/industrial-upload/T14-repair-failure-benchmark-gaps
Worktree: D:\upload-control-plane-T14-implementation-failure-benchmark
Baseline: 250fee7
Started: 2026-06-25 18:07 Asia/Shanghai
Finished: 2026-06-25 18:07 Asia/Shanghai

## Scope

- Repair the Phase 13/T14 gap benchmark facts without changing product behavior.
- Remove the incorrect xfail gap for retention/legal-hold protected purge denial.
- Re-check completed dataset restore/reconciliation coverage against `tests/application/test_worker_lifecycle.py` and `WorkerLifecycleService`.
- Preserve the old T14 implementation handoff as historical fact; record this repair as a new handoff.
- Do not implement new product features, Phase 14 MQTT, Go uploader/gateway work, backend byte proxying, or MinIO credential exposure.

## Changes

- Updated `tests/test_phase13_capability_gaps.py`.
- Deleted `test_retention_or_legal_hold_protected_purge_denial_gap`.
  - This was a false gap. Existing API tests cover the real product purge path:
    - `tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_requires_confirmation_and_retention_policy_approval`
    - `tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_rejects_object_lock_and_legal_hold_policy`
  - Those tests prove confirmation is required, active retention denies purge, object lock denies purge, and legal hold denies purge.
- Kept quota/backpressure as an xfail gap.
  - Reason: settings and metrics exist, but there is no upload/create/presign rejection gate tied to quota or backpressure.
- Kept KMS unavailable as an xfail gap.
  - Reason: configuration fields exist, but no storage policy path requires KMS and fails initiation/presign when KMS is unavailable.
- Kept completed dataset automated restore/rebuild as an xfail gap, with corrected wording.
  - Existing real coverage in `tests/application/test_worker_lifecycle.py::test_recovery_reconciliation_marks_missing_metadata_and_object_only_cases` proves lifecycle reconciliation classifies completed dataset cases as missing-object, metadata-only, verified, and object-only.
  - The remaining gap is narrower: there is no product path that rebuilds dataset DB metadata from an object-only reference or restores a missing final object.

## Focused suite

The focused T14 suite now explicitly includes the existing purge governance tests and worker lifecycle tests instead of duplicating those larger tests:

```powershell
uv run pytest tests/api/test_upload_session_runtime_api.py tests/api/test_cors.py tests/application/test_dataset_validation_worker.py tests/application/test_outbox.py tests/api/test_device_identity_api.py tests/api/test_observability.py tests/infrastructure/test_s3_storage.py tests/scripts/test_benchmark_upload.py tests/test_phase13_capability_gaps.py tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_requires_confirmation_and_retention_policy_approval tests/api/test_dataset_lifecycle_api.py::test_dataset_purge_rejects_object_lock_and_legal_hold_policy tests/application/test_worker_lifecycle.py -q
```

Result: `52 passed, 3 xfailed, 1 warning`.

## Validation commands

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `87 files already formatted`
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 87 source files`
- Focused T14 plus purge/worker lifecycle suite:
  - Passed: `52 passed, 3 xfailed, 1 warning`
- `uv run pytest -q`
  - Passed: `211 passed, 3 xfailed, 1 warning`
- Benchmark dry-run:
  - Command: `uv run python scripts\benchmark_upload.py --dry-run --size 1MiB --file .benchmarks\tiny-ci-repair.bin`
  - Passed: generated a 1 MiB local file and reported `upload_path=api-presign-direct-storage-put`.
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
  - Reviewed expected matches only: benchmark size parsing and bounded deterministic bytes generation, outbox byte payload rejection, test helper file writes, existing MinIO integration read, API dependency names, and storage adapter tests.
- Credential/signed marker scan:
  - Command: `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\benchmarks.md scripts\benchmark_upload.py`
  - Reviewed expected matches only: redaction constants/tests, config/internal storage credential fields, device one-time credential tests/API shape, storage presign implementation, and dataset download URL API names.
- Signed-query scan:
  - Command: `rg -n 'https?://[^\s"'']+\?[^\s"'']*(X-Amz|Signature|Credential|secret|token|uploadId|partNumber)' docs src\upload_control_plane tests scripts\benchmark_upload.py`
  - Reviewed expected matches only: existing negative redaction tests, existing storage-domain examples/tests, existing PRD examples, and an older T07 handoff smoke command. No new signed-query examples were added in this repair.

## Residual risks

- The old T14 implementation handoff still records the original false xfail as historical fact; this repair handoff supersedes it for current acceptance.
- Completed dataset reconciliation is covered for classification/status outcomes, not automated DB metadata rebuild from object-only storage listings or restoration of a missing final object.
- The benchmark live 512 MiB path was not rerun in this repair; only the dry-run was revalidated because product benchmark behavior was not changed.
