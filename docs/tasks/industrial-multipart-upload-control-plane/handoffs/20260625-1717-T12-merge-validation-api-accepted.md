# Handoff: T12 validation result and retry API merge

Status: accepted
Agent type: Merge
Branch: codex/industrial-upload/T12-merge-validation-api
Worktree: D:\upload-control-plane-T12-merge-validation-api
Started: 2026-06-25 17:14 Asia/Shanghai
Finished: 2026-06-25 17:17 Asia/Shanghai

## Scope

- Merge accepted implementation branch `codex/industrial-upload/T12-implementation-validation-api` at `da5a8d2d2df151645087e482da1f838253f57384`.
- Merge accepted validation branch `codex/industrial-upload/T12-validation-validation-api` at `e95355f9b4f5c4d2d215e14c8a4aa6ad06631286`.
- Preserve both accepted handoffs:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1708-T12-implementation-validation-api-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1713-T12-validation-validation-api-accepted.md`
- Write this merge handoff.
- Do not push.

## Merge Inputs

- Base main/root HEAD: `4dde0bec7e9a78a8cf67fa78dc94469afca92cf9`
- Implementation commit: `da5a8d2d2df151645087e482da1f838253f57384`
- Validation commit: `e95355f9b4f5c4d2d215e14c8a4aa6ad06631286`
- Merge commit before this handoff: `fbbde60`

## Changes Preserved

- Validation Result API:
  - `GET /v1/projects/{project_id}/datasets/{dataset_id}/validation`
  - Requires `dataset.view` on the dataset resource.
  - Returns validation status, preview status, preview metadata, extracted metadata, latest result, and ordered result history.
- Retry Validation API:
  - `POST /v1/projects/{project_id}/datasets/{dataset_id}/validation/retry`
  - Requires `dataset.validate` on the dataset resource.
  - Resets eligible failed validation states to `PROCESSING` / `PENDING`.
  - Treats existing `PENDING` or `RUNNING` validation as idempotent no-op.
  - Preserves object identity and storage metadata.
- Dev seed now includes `dataset.validate`.
- API tests cover result retrieval, permission denial, retry state reset, retry idempotency, object identity preservation, and credential leakage guards.

## Merge Commands

- `git worktree add -b codex/industrial-upload/T12-merge-validation-api D:\upload-control-plane-T12-merge-validation-api 4dde0be`
  - Result: passed.
- `git merge --no-ff codex/industrial-upload/T12-validation-validation-api -m "Merge T12 validation API accepted implementation"`
  - Result: passed with no conflicts.
  - The validation branch is directly on top of implementation commit `da5a8d2`, so this merge included both implementation and validation handoff commits.

## Verification

- `git diff --check`
  - Result: passed, no output.
- `uv run ruff check src tests`
  - Result: passed, `All checks passed!`.
  - Non-blocking warning: Ruff could not write several `.ruff_cache` files due to access denied.
- `uv run ruff format --check src tests`
  - Result: passed, `82 files already formatted`.
  - Non-blocking warnings: first `uv` run created `.venv`, fell back from hardlink to copy, and Ruff could not write several `.ruff_cache` files due to access denied.
- `uv run mypy src tests`
  - Result: passed, `Success: no issues found in 82 source files`.
- `uv run pytest tests/api/test_dataset_lifecycle_api.py tests/application/test_dataset_validation_worker.py tests/application/test_worker_lifecycle.py tests/application/test_outbox.py -q`
  - Result: passed, `28 passed, 1 warning in 8.54s`.
- `uv run pytest -q`
  - Result: passed, `200 passed, 1 warning in 16.57s`.
- `docker compose config --quiet`
  - Result: passed, no output.
- `rg -n "UploadFile|File\(|multipart/form-data|request\.stream|request\.body|StreamingResponse|FileResponse" src/upload_control_plane/api src/upload_control_plane/application`
  - Result: passed, no matches.
- `rg -n "get_object|download_file|iter_chunks|StreamingBody|\.read\(|read_bytes|bytes\(|bytearray|memoryview" src/upload_control_plane/api/datasets.py src/upload_control_plane/application/datasets.py src/upload_control_plane/application/dataset_validation.py`
  - Result: passed, no matches.
- `rg -n "X-Amz-Signature|X-Amz-Credential|presigned_url|signed_url|upload_url|download_url|access_key|secret_key|credential_material|password|private_key" src/upload_control_plane/api/datasets.py src/upload_control_plane/application/datasets.py src/upload_control_plane/application/dataset_validation.py tests/api/test_dataset_lifecycle_api.py`
  - Result: reviewed expected matches only:
    - Existing dataset download URL code in `src/upload_control_plane/api/datasets.py` and `src/upload_control_plane/application/datasets.py`.
    - Negative assertions in `tests/api/test_dataset_lifecycle_api.py` for no access key or secret key leakage.

## Full T12 Status

- T12 validation worker foundation was already accepted and merged into `main` before this branch.
- This merge branch adds the remaining accepted T12 validation result and retry API scope.
- Full T12 is complete on this merge branch.
- T13 is unlocked after master fast-forwards `main` to this merge branch and accepts this final T12 merge state.

## Residual Risks

- HDF5 extraction remains stub-level from the prior accepted worker foundation slice.
- Retry is state-idempotent rather than backed by `idempotency_records`; acceptable for this no-body retry endpoint and covered by repeated-call tests.
- Retry uses direct `OutboxEvent` construction rather than the stricter `append_outbox_event` helper. Current payload is bounded and test-covered, but helper reuse would reduce future drift risk.
- Retry preserves prior preview metadata and extracted metadata until the next worker result overwrites them.
- Full pytest continues to emit the existing `StarletteDeprecationWarning` from FastAPI TestClient/httpx compatibility.

## Final State

- Branch is ready for master fast-forward after this handoff commit.
- No push was performed.
