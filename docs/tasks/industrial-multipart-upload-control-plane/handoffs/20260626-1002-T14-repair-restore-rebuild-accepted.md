# Handoff: T14 completed dataset restore/rebuild repair

Status: accepted
Agent type: Repair
Branch: codex/industrial-upload/T14-repair-restore-rebuild
Worktree: D:\upload-control-plane
Started: 2026-06-26 09:39 Asia/Shanghai
Finished: 2026-06-26 10:02 Asia/Shanghai

## Scope

- Intended scope: Repair the completed dataset reconciliation gap for missing final objects and object-only references.
- Explicitly out of scope: Backpressure rejection, KMS unavailable rejection, MQTT, Go, file-byte proxying, and any authorization model changes.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-0939-master-handoff-after-T12-T13-T14-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`

## Changes

- Files changed:
  - `src/upload_control_plane/application/worker_lifecycle.py`
  - `tests/application/test_worker_lifecycle.py`
  - `tests/test_phase13_capability_gaps.py`
- Behavior changed:
  - Recovery reconciliation now repairs a previously `RECOVERY_MISSING_OBJECT` completed dataset when object storage again returns a matching final object via `head_object`.
  - The worker restores final-object metadata (`object_etag`, `object_size_bytes`, `object_version_id`) and marks the dataset `RECOVERY_VERIFIED` only after expected-size validation succeeds.
  - Object-only references can rebuild a quarantined dataset record when the object metadata or canonical key path identifies an existing tenant/project. The rebuilt dataset is `QUARANTINED`, `validation_status=PENDING`, and `RECOVERY_OBJECT_ONLY`, requiring operator review before exposure.
  - The completed dataset automated restore/rebuild xfail was removed from `tests/test_phase13_capability_gaps.py`; backpressure and KMS xfails remain.
- Compatibility notes:
  - No API response shape changed.
  - No new public endpoint was added.
  - No backend file-byte ingress, download proxy, or storage credential exposure was introduced.
  - A concurrent agent has staged changes in `src/upload_control_plane/application/upload_tasks.py` and `tests/api/test_upload_task_api_foundation.py`; they were not modified or committed by this repair.

## Verification

- Commands run:
  - `uv run pytest tests/application/test_worker_lifecycle.py tests/test_phase13_capability_gaps.py -q`
  - `uv run ruff check src/upload_control_plane/application/worker_lifecycle.py tests/application/test_worker_lifecycle.py tests/test_phase13_capability_gaps.py`
  - `uv run ruff format --check src/upload_control_plane/application/worker_lifecycle.py tests/application/test_worker_lifecycle.py tests/test_phase13_capability_gaps.py`
  - `git diff --check -- src/upload_control_plane/application/worker_lifecycle.py tests/application/test_worker_lifecycle.py tests/test_phase13_capability_gaps.py`
- Results:
  - Focused pytest: `6 passed, 2 xfailed`
  - Ruff check: `All checks passed!`
  - Ruff format check: `3 files already formatted`
  - Diff check: passed with no output
- Commands not run and why:
  - Full pytest and full ruff were not run because this repair was intentionally scoped to the completed dataset reconciliation gap and the working tree contains unrelated concurrent staged KMS changes.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved.
- Clients receive no MinIO/S3 credentials: preserved.
- Complete uses object storage ListParts as authority: unchanged.
- Authorization uses permission_grants: unchanged.
- Internal IDs remain UUIDs: preserved; rebuilt object-only datasets use UUID IDs from trusted metadata/key path or a generated UUID.
- MQTT/Go/edge remain optional and dependency-gated: unchanged.

## Risks and Follow-up

- Remaining risks:
  - Object-only rebuild requires object metadata or canonical key namespace to identify tenant/project; unknown orphan objects remain counted but are not exposed or rebuilt.
  - Rebuilt object-only datasets require a later operator review/release path before becoming normal downloadable datasets.
- Known gaps:
  - Backpressure rejection gate remains xfailed.
  - KMS unavailable rejection remains xfailed.
- Suggested next agent:
  - Validation agent should run the focused suite and inspect that object-only rebuild cannot bypass exposure policy.

## Recovery Notes

- If accepted, the completed dataset automated restore/rebuild gap is closed.
- If partial, reusable pieces are the worker reconciliation changes and focused tests.
- If blocked, unblock condition: none known.
- If rejected, do not replace this with a file-byte proxy or automatic object-only exposure.
