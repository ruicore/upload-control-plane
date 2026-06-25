# T14 Failure Injection and Benchmark Suite implementation acceptance

Status: accepted
Agent type: Implementation agent
Branch: codex/industrial-upload/T14-implementation-failure-benchmark
Worktree: D:\upload-control-plane-T14-implementation-failure-benchmark
Baseline: a1f663c
Started: 2026-06-25 17:55 Asia/Shanghai
Finished: 2026-06-25 18:03 Asia/Shanghai

## Scope

- Implement Phase 13 local failure injection/regression coverage where existing product paths already support the behavior.
- Add a local benchmark helper that can generate and upload a 512 MiB file through API presign plus direct storage PUTs.
- Add `docs/benchmarks.md` with local prerequisites, safe commands, and a report template.
- Do not implement Phase 14 MQTT, Phase 15 Go uploader, or Phase 16 gateway.
- Preserve no backend file-byte proxy, no storage credential exposure, and no signed URL query strings in new docs/log-oriented output.

## Implemented coverage

- URL/presign expiry bounds:
  - Added `test_presign_expiry_is_bounded_and_expired_sessions_are_gone`.
  - Confirms requested presign expiry is bounded by `max_presign_expiry_seconds`.
  - Confirms expired sessions reject new presign attempts without issuing another storage URL.
  - Current product policy returns `409 upload.invalid_state` for expired presign attempts, not PRD-recommended `410`.
- Duplicate complete idempotency:
  - Existing `test_complete_succeeds_from_storage_parts_without_db_ack_and_is_idempotent` remains in the focused suite.
- Missing storage part despite DB ack:
  - Existing `test_complete_uses_storage_list_parts_not_db_ack_rows_for_missing_parts` remains in the focused suite.
- Permission revocation during upload:
  - Added `test_complete_re_evaluates_current_permissions_after_part_upload`.
  - Existing presign/lifecycle permission re-evaluation tests remain in the focused suite.
- Device credential revocation/auth failure:
  - Existing disabled, rotated/revoked, expired, and device-session authorization tests remain in the focused suite.
- Validation failure:
  - Existing `test_validation_worker_records_failure_without_deleting_object_or_exposing_dataset` remains in the focused suite.
- Outbox delivery failure:
  - Existing `test_delivery_failure_does_not_roll_back_committed_domain_state` remains in the focused suite.
- CORS/signed-header mismatch:
  - Added `test_unconfigured_signed_upload_header_preflight_is_not_allowed`.
- Storage-native checksum mismatch:
  - Added `test_storage_native_checksum_mismatch_does_not_mark_dataset_ready`.
  - Uses the current storage abstraction's `StorageChecksumMismatchError` and verifies the dataset is not exposed as ready.
- Restore reconciliation cases already supported:
  - Existing storage/reconcile part-list tests remain in the focused suite.

## Benchmark deliverables

- Added `scripts/benchmark_upload.py`.
  - Generates a default 512 MiB benchmark file.
  - Uses sparse `truncate` by default and bounded deterministic chunk writes with `--materialize`.
  - Uploads through the existing CLI uploader: API create/presign/ack/complete plus direct presigned storage `PUT`.
  - Does not use MinIO credentials and does not proxy bytes through the backend.
  - Supports `--dry-run --size 1MiB` for CI-safe smoke coverage.
- Added `tests/scripts/test_benchmark_upload.py`.
- Added `docs/benchmarks.md` with dry-run, smoke, and 512 MiB benchmark commands.

## Unsupported or gap items

- Retention/legal-hold protected purge denial:
  - Documented as xfailed in `tests/test_phase13_capability_gaps.py`.
  - Reason: storage capability metadata exists, but no purge policy workflow exists yet.
- Quota/backpressure rejection:
  - Documented as xfailed.
  - Reason: settings and metrics exist, but upload/presign rejection gates are not implemented.
- KMS unavailable:
  - Documented as xfailed.
  - Reason: KMS config fields exist, but no policy path requires KMS and rejects initiation on KMS failure.
- Completed dataset restore reconciliation:
  - Documented as xfailed.
  - Reason: in-progress multipart part reconciliation exists; completed dataset restore after DB/object-storage loss is not implemented.

## Validation commands

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `87 files already formatted`
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 87 source files`
- Focused failure/API/storage/outbox/observability suite:
  - Command: `uv run pytest tests/api/test_upload_session_runtime_api.py tests/api/test_cors.py tests/application/test_dataset_validation_worker.py tests/application/test_outbox.py tests/api/test_device_identity_api.py tests/api/test_observability.py tests/infrastructure/test_s3_storage.py tests/scripts/test_benchmark_upload.py tests/test_phase13_capability_gaps.py -q`
  - Passed: `46 passed, 4 xfailed, 1 warning`
- Full pytest:
  - Command: `uv run pytest -q`
  - Passed: `211 passed, 4 xfailed, 1 warning`
- Benchmark dry-run:
  - Command: `uv run python scripts\benchmark_upload.py --dry-run --size 1MiB --file .benchmarks\tiny-ci.bin`
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
  - Reviewed expected matches only: outbox byte payload rejection, dependency names, existing storage adapter tests, and benchmark bounded deterministic file generation.
- Credential/signed marker scan:
  - Command: `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\benchmarks.md scripts\benchmark_upload.py`
  - Reviewed expected matches only: redaction constants/tests, config/internal storage credential fields, device one-time credential tests/API shape, storage presign implementation, and dataset download URL API names.
- Signed-query scan:
  - Command: `rg -n 'https?://[^\s"'']+\?[^\s"'']*(X-Amz|Signature|Credential|secret|token|uploadId|partNumber)' docs src\upload_control_plane tests scripts\benchmark_upload.py`
  - Reviewed expected matches only: existing negative redaction tests, existing storage-domain examples/tests, existing PRD examples, and an older T07 handoff smoke command. No new signed-query examples were added in `docs/benchmarks.md` or the benchmark script.

## Residual risks

- The benchmark script was dry-run validated only; the 512 MiB live upload path still requires a running local API, migrated DB, dev seed credentials, and MinIO.
- Expired presign attempts currently return `409 upload.invalid_state`; if the product chooses the PRD-recommended `410 Gone`, the regression should be updated with the product change.
- xfailed gaps are deliberately narrow and should be converted to real tests when those product paths are implemented.
