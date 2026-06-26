# Handoff: T14 KMS unavailable rejection path

Status: accepted
Agent type: Repair
Branch: codex/industrial-upload/T14-repair-kms-unavailable
Worktree: D:\upload-control-plane
Started: 2026-06-26 09:40 Asia/Shanghai
Finished: 2026-06-26 10:05 Asia/Shanghai

## Scope

- Intended scope: repair the remaining T14 KMS unavailable initiation rejection gap.
- Explicitly out of scope: backpressure rejection, completed dataset restore/rebuild, file-byte proxy paths, and unrelated worker lifecycle changes.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-0939-master-handoff-after-T12-T13-T14-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T04/T13/T14 sections
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `tests/test_phase13_capability_gaps.py`
  - `src/upload_control_plane/infrastructure/storage/s3_minio.py`

## Changes

- Files changed:
  - `src/upload_control_plane/application/upload_tasks.py`
  - `tests/api/test_upload_task_api_foundation.py`
  - `tests/test_phase13_capability_gaps.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1005-T14-repair-kms-unavailable-accepted.md`
- Behavior changed:
  - Upload task creation now rejects `SSE_KMS` storage policies before creating task/session rows when the selected adapter does not advertise `SSE_KMS` support or the policy has no `kms_key_ref`.
  - If `create_multipart_upload` fails with a KMS provider code under an `SSE_KMS` policy, the API returns stable `storage_policy.kms_unavailable` instead of a generic initiation failure.
  - KMS rejection responses include only bounded reason enums and do not echo `kms_key_ref`, provider messages, secrets, or key material.
  - The KMS gap xfail was removed from `tests/test_phase13_capability_gaps.py`; the remaining xfails are backpressure and restore/rebuild.
- Compatibility notes:
  - Non-KMS policies continue through the existing path.
  - Provider KMS failures still avoid committing DB task/session rows because the service raises before commit.

## Verification

- Commands run:
  - `uv run pytest tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_kms_policy_when_adapter_cannot_provide_kms tests/api/test_upload_task_api_foundation.py::test_upload_task_create_rejects_kms_provider_failure_without_persisting_session tests/test_phase13_capability_gaps.py -q`
  - `uv run pytest tests/api/test_upload_task_api_foundation.py -q`
  - `uv run ruff check src/upload_control_plane/application/upload_tasks.py tests/api/test_upload_task_api_foundation.py tests/test_phase13_capability_gaps.py`
  - `uv run ruff format --check src/upload_control_plane/application/upload_tasks.py tests/api/test_upload_task_api_foundation.py tests/test_phase13_capability_gaps.py`
  - `git diff --cached --check`
- Results:
  - Focused pytest: `2 passed, 2 xfailed, 1 warning`.
  - Upload task API pytest: `18 passed, 1 warning`.
  - Ruff check: `All checks passed!`
  - Ruff format check: `3 files already formatted`.
  - Cached diff whitespace check: passed with no output.
- Commands not run and why:
  - Full pytest/mypy were not run; this was a narrow Repair slice and the focused upload-task/API coverage passed.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved; no byte upload/proxy path added.
- Clients receive no MinIO/S3 credentials: preserved; no storage credentials or KMS key material returned.
- Complete uses object storage ListParts as authority: untouched.
- Authorization uses permission_grants: untouched.
- Internal IDs remain UUIDs: untouched.
- MQTT/Go/edge remain optional and dependency-gated: untouched.

## Risks and Follow-up

- Remaining risks:
  - KMS provider detection uses provider code containing `kms` for initiation-stage mapping. Unknown providers with non-KMS error codes will still return the existing generic storage initiation failure.
- Known gaps:
  - Backpressure rejection gate remains xfailed.
  - Completed dataset automated restore/rebuild is outside this repair scope.
- Suggested next agent:
  - Validation agent should re-run the focused KMS tests and inspect response payload redaction.

## Recovery Notes

- If accepted, this closes the T14 KMS unavailable rejection gap.
- During execution, a parallel restore/rebuild branch briefly changed the active branch. This commit intentionally excludes worker lifecycle files and restore/rebuild gap changes.
