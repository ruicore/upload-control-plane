# T14 Merge Gap Repairs - Accepted

## Scope

- Worktree: `D:\upload-control-plane-T14-merge-gap-repairs`
- Branch: `codex/industrial-upload/T14-merge-gap-repairs`
- Base: `main` commit `0f30ba9`
- Merge strategy: cherry-pick accepted repair and validation commits in sequence to preserve clear history.

## Commits merged

- `14d6267` KMS repair -> `99bd648`
- `23fdef3` KMS validation -> `5a88802`
- `c2342e2` backpressure repair -> `cb8476c`
- `22c4039` backpressure validation -> `f2e9a54`
- `dd24990` restore/rebuild repair -> `1dba464`
- `79137e5` restore/rebuild validation -> `9b941e0`

## Conflict handling

- `tests/api/test_upload_task_api_foundation.py`: mechanical conflict between KMS and backpressure tests. Kept both KMS rejection tests and the storage backpressure rejection test.
- `tests/test_phase13_capability_gaps.py`: removed the repaired KMS, backpressure, and restore/rebuild xfail sentinels while keeping the file path present for required focused verification.
- `src/upload_control_plane/application/upload_tasks.py`: auto-merged and retains both KMS-unavailable rejection and storage backpressure rejection behavior.

## Verification

- `git diff --check`: passed.
- `uv run ruff check src tests`: passed.
- `uv run ruff format --check src tests`: passed, 87 files already formatted.
- `uv run mypy src tests`: passed, no issues in 87 source files.
- `uv run pytest -q tests/test_phase13_capability_gaps.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/application/test_worker_lifecycle.py`: passed, 40 passed, 1 `StarletteDeprecationWarning`.
- `uv run pytest -q`: failed, 219 passed and 1 failed. Failure was `tests/application/test_outbox.py::test_successful_delivery_and_repeated_runs_are_idempotent`, where a shared local test database had 13 due outbox events claimed instead of the test's expected 1. Isolated rerun of that test failed the same way with the same 13 claimed events, indicating residual DB state rather than a T14 gap-repair conflict.

## Static scans

- File-byte proxy scan: `rg -n "UploadFile|File\(|Form\(|request\.stream|request\.body|\.read\(|iter_bytes|StreamingResponse|FileResponse" src tests`
  - No API/server upload-byte proxy ingress found.
  - Matches were limited to CLI local file reads, CLI range helpers, and storage integration/test reads.
- Signed URL/query leakage scan: `rg -n "presign|signed_url|url|query|X-Amz|Signature|Credential|token|secret|kms_key_ref|response\.text|details" src/upload_control_plane tests | Select-String -Pattern "log|logger|metric|error|detail|response|secret|kms_key_ref|Signature|Credential|X-Amz|token"`
  - Matches include existing redaction tests, fake signed URLs in tests, configuration fields, and explicit KMS non-leak assertions.
  - No new T14 merge conflict artifact was found leaking signed URL query material or KMS key refs in error responses.

## Remaining risks

- Full pytest needs a clean DB/outbox state or a test isolation repair before it can be used as a green merge signal in this worktree.
- No product behavior beyond the accepted KMS, backpressure, and restore/rebuild repairs was intentionally added.
