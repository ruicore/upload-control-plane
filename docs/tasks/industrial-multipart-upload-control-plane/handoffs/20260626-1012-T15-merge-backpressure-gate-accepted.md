# T15 Backpressure Gate merge acceptance

Status: accepted
Agent type: master merge integration
Branch: codex/industrial-upload/T15-merge-backpressure-gate
Base branch: main
Main baseline: 0f30ba9
Final HEAD before this handoff: 102acac
Started: 2026-06-26 10:12 Asia/Shanghai
Finished: 2026-06-26 10:12 Asia/Shanghai

## Scope

- Create the final T15 merge branch from the accepted validation branch.
- Confirm the branch remains linear and fast-forward-ready from local `main` baseline `0f30ba9`.
- Preserve the implementation handoff and validation accepted handoff.
- Do not change implementation logic.
- Do not push.

## Lineage

- `git status --short --branch`: clean on `codex/industrial-upload/T15-validation-backpressure-gate` before merge branch creation.
- Created `codex/industrial-upload/T15-merge-backpressure-gate` from validation HEAD `102acac`.
- `git log --oneline --decorate --max-count=5` showed:
  - `102acac` `docs: accept T15 backpressure validation`
  - `39d785e` `feat: add storage backpressure gate`
  - `0f30ba9` `docs: record master handoff after T12 T13 T14`
- `git merge-base --is-ancestor 0f30ba9 HEAD`: passed.

## Preserved handoffs

- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1003-T15-implementation-backpressure-gate-accepted.md`
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1040-T15-validation-backpressure-gate-accepted.md`

## Accepted evidence

- Upload task creation rejects storage backpressure before storage multipart allocation.
- Upload part presign rejects storage backpressure before storage presign.
- Rejection responses use HTTP 503, stable backpressure error details, and `Retry-After`.
- Metrics include `storage_backpressure_active` and `storage_backpressure_rejections_total` without tenant, session, object, URL, or secret labels.
- The previous Phase 13 backpressure xfail was replaced by concrete passing coverage.
- No MQTT, Go uploader, gateway, storage credential exposure, or backend byte proxy scope was added.

## Validation

- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `88 files already formatted`.
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 88 source files`.
- Focused suite:
  - Command: `uv run pytest -q tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/api/test_observability.py tests/test_phase13_capability_gaps.py`
  - Passed: `39 passed, 2 xfailed, 1 warning`.
- Full pytest:
  - First run had one transient local database contamination failure in `tests/application/test_outbox.py::test_successful_delivery_and_repeated_runs_are_idempotent`: the dispatcher claimed 13 due outbox events instead of the test's one seeded event.
  - The failed test passed when rerun in isolation.
  - Full suite passed on rerun: `218 passed, 2 xfailed, 1 warning`.
- `docker compose config --quiet`
  - Passed with no output.
- `git diff --check`
  - Passed with no output.
- Backend file-byte/proxy scan:
  - Command: `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body|StreamingResponse|FileResponse|/upload-bytes|/file-bytes|/upload-file" src\upload_control_plane\api src\upload_control_plane\application src\upload_control_plane\main.py`
  - Passed: no matches.
- Backend byte-read/download scan:
  - Command: `rg -n "get_object|download_file|iter_chunks|StreamingBody|\.read\(|read_bytes|bytes\(|bytearray|memoryview" src\upload_control_plane\api src\upload_control_plane\application`
  - Reviewed expected matches only: outbox byte-payload rejection and the `get_object_storage` dependency name.
- Credential/signed marker scan:
  - Command: `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src\upload_control_plane tests docs\benchmarks.md scripts\benchmark_upload.py`
  - Reviewed expected matches only: redaction constants/tests, internal configuration/storage adapter fields, device credential once-only API/tests, dataset download URL API names, storage presign implementation, and manifest/outbox negative tests.
- Signed-query scan:
  - Command: `rg -n 'https?://[^\s"'']+\?[^\s"'']*(X-Amz|Signature|Credential|secret|token|uploadId|partNumber)' docs src\upload_control_plane tests scripts\benchmark_upload.py`
  - Reviewed expected matches only: negative redaction tests, storage-domain tests, PRD examples, observability fake URLs, and older T07 handoff smoke text.

## Remaining gaps and risks

- Full pytest's first outbox failure indicates the local integration database can contain unrelated due outbox rows that affect this test when stale rows are present; isolation rerun and full rerun both passed without code changes.
- KMS unavailable rejection remains a Phase 13 capability gap.
- Completed dataset automated restore/rebuild remains beyond the current worker lifecycle reconciliation classification coverage.
- Full pytest still emits the existing `StarletteDeprecationWarning`.

## Final state

- T15 is accepted on `codex/industrial-upload/T15-merge-backpressure-gate`.
- The branch is ready for local `main` fast-forward from `0f30ba9` after this handoff commit.
- No implementation logic was changed.
- No push was performed.
