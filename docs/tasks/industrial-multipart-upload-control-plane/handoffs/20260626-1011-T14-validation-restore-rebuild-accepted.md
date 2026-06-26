# Handoff: T14 completed dataset restore/rebuild validation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T14-validation-restore-rebuild
Worktree: D:\upload-control-plane-T14-validation-restore-rebuild
Started: 2026-06-26 10:03 Asia/Shanghai
Finished: 2026-06-26 10:11 Asia/Shanghai

## Scope

- Intended scope: Independently validate repair branch `codex/industrial-upload/T14-repair-restore-rebuild` at `dd24990` for completed dataset restore/rebuild reconciliation.
- Explicitly out of scope: Implementation code changes, backpressure repair, KMS unavailable repair, MQTT/Go work, and production benchmark claims.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1002-T14-repair-restore-rebuild-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`

## Changes

- Files changed by validation:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1011-T14-validation-restore-rebuild-accepted.md`
- Implementation files reviewed but not modified:
  - `src/upload_control_plane/application/worker_lifecycle.py`
  - `tests/application/test_worker_lifecycle.py`
  - `tests/test_phase13_capability_gaps.py`
- Behavior validated:
  - Completed datasets in `RECOVERY_MISSING_OBJECT` are rechecked through `ObjectStorage.head_object` and only move to `RECOVERY_VERIFIED` after expected-size validation passes.
  - Restored completed datasets get real product metadata backfilled: `object_etag`, `object_size_bytes`, and `object_version_id`.
  - Object-only references require identifiable tenant/project metadata or canonical key identity and an existing matching project before a dataset row is rebuilt.
  - Rebuilt object-only datasets are conservative: `QUARANTINED`, `validation_status=PENDING`, `recovery_status=RECOVERY_OBJECT_ONLY`, and `operator_review_required=True`.
  - Unknown object refs are counted as object-only observations but are not exposed or rebuilt when tenant/project identity cannot be proven.
  - Existing dataset exposure checks still block non-`NORMAL` recovery states; the repair does not make `RECOVERY_VERIFIED` or `RECOVERY_OBJECT_ONLY` downloadable READY.
  - `tests/test_phase13_capability_gaps.py` only retains the backpressure and KMS unavailable xfails, which are outside this repair.

## Verification

- Commands run:
  - `uv run pytest tests/application/test_worker_lifecycle.py tests/test_phase13_capability_gaps.py tests/domain/test_datasets.py tests/api/test_dataset_lifecycle_api.py -q`
  - `uv run ruff check src/upload_control_plane/application/worker_lifecycle.py tests/application/test_worker_lifecycle.py tests/test_phase13_capability_gaps.py`
  - `uv run ruff format --check src/upload_control_plane/application/worker_lifecycle.py tests/application/test_worker_lifecycle.py tests/test_phase13_capability_gaps.py`
  - `git diff --check dd24990^ dd24990 -- src/upload_control_plane/application/worker_lifecycle.py tests/application/test_worker_lifecycle.py tests/test_phase13_capability_gaps.py docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1002-T14-repair-restore-rebuild-accepted.md`
  - `uv run pytest -q`
  - `uv run ruff check .`
  - `uv run ruff format --check .`
  - `uv run pytest tests/application/test_outbox.py::test_successful_delivery_and_repeated_runs_are_idempotent -q`
  - `uv run pytest tests/application/test_outbox.py -q`
  - `uv run mypy src tests`
- Results:
  - Focused pytest: `37 passed, 2 xfailed, 1 warning`
  - Focused ruff check: `All checks passed!`
  - Focused ruff format: `3 files already formatted`
  - Diff check: passed with no output
  - Full ruff check: `All checks passed!`
  - Full ruff format: `97 files already formatted`
  - Full pytest final rerun: `216 passed, 2 xfailed, 1 warning`
  - Targeted outbox single rerun: `1 passed`
  - Targeted outbox file rerun: `6 passed`
  - Mypy: `Success: no issues found in 87 source files`
- Commands not run and why:
  - Docker/MinIO benchmark was not run because this validation targets restore/rebuild repair behavior, not T14 benchmark throughput.
- Notes:
  - The first full `uv run pytest -q` attempt failed once in `tests/application/test_outbox.py::test_successful_delivery_and_repeated_runs_are_idempotent` because the shared local test database had additional due outbox events while validation commands were being run concurrently. The specific test passed after the outbox file cleaned its artifacts, and the final full pytest rerun passed cleanly.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: satisfied; validation found no download/proxy/read-byte path in the repair, only `head_object` metadata reads.
- Clients receive no MinIO/S3 credentials: satisfied; no public response or credential path changed.
- Complete uses object storage ListParts as authority: unchanged by this repair.
- Authorization uses permission_grants: unchanged by this repair; dataset download API still enforces current `dataset.download`.
- Internal IDs remain UUIDs: satisfied; rebuilt object-only dataset IDs come from trusted UUID metadata/key path or generated UUID.
- MQTT/Go/edge remain optional and dependency-gated: unchanged.

## Risks and Follow-up

- Remaining risks:
  - `RECOVERY_VERIFIED` remains non-exposable because the domain exposure rule only allows `NORMAL`; that is conservative and accepted for this repair, but a future operator release action should define when verified recovery returns to `NORMAL`.
  - Object-only rebuild depends on metadata or UUID key namespace identity. Objects with tenant slugs or non-canonical keys are intentionally not rebuilt automatically.
  - Recovery reconciliation is still metadata-only; checksum validation is limited by available storage metadata and remains a later hardening area.
- Known gaps:
  - Backpressure rejection gate remains xfailed.
  - KMS unavailable rejection remains xfailed.
- Suggested next agent:
  - Master can treat the completed dataset restore/rebuild gap as closed for T14, while keeping backpressure and KMS as separate repair/validation scopes.

## Recovery Notes

- If accepted, next dependency unlocked: completed dataset restore/rebuild repair can proceed to Master review.
- If partial, reusable pieces: all reviewed implementation and tests are reusable; no partial status is needed.
- If blocked, unblock condition: none.
- If rejected, do not repeat: do not solve restore/rebuild by exposing object-only datasets as READY or by adding a file-byte proxy.
