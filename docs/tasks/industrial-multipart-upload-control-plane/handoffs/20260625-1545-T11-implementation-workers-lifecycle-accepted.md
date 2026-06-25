# Handoff: T11 Workers Lifecycle

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T11-implementation-workers-lifecycle
Worktree: D:\upload-control-plane-T11-implementation-workers-lifecycle
Started: 2026-06-25 15:30 +08:00 Asia/Shanghai
Finished: 2026-06-25 15:45 +08:00 Asia/Shanghai

## Scope

- Intended scope: T11 lifecycle slice only: worker process entrypoint, expired session cleanup, expired multipart abort, recycle-bin retention purge, object-storage deletion for lifecycle purge, and backup/restore reconciliation through `recovery_status`.
- Explicitly out of scope: outbox append helper, outbox dispatcher/retry/dead-letter body, dataset validation parsing/T12, MQTT/Go/edge.
- PRD/task files read: `agent-orchestration.md`, T11 section in task README, PRD `04`, `05`, `07`, `10`, `12`, `13`, `14`, and `20260625-1530-master-handoff-after-T07-T10-accepted.md`.

## Changes

- Files changed:
  - `src/upload_control_plane/application/worker_lifecycle.py`
  - `src/upload_control_plane/worker/main.py`
  - `src/upload_control_plane/config.py`
  - `pyproject.toml`
  - `docker-compose.yml`
  - `tests/application/test_worker_lifecycle.py`
  - this handoff
- Behavior changed:
  - Added `WorkerLifecycleService` for idempotent lifecycle operations.
  - Active expired sessions transition to `EXPIRED`; expired/aborting sessions then transition through `ABORTING` to `ABORTED` after storage abort succeeds or storage reports no upload.
  - Completed sessions are excluded from cleanup aborts, so final objects are not deleted by multipart abort automation.
  - Recycle-bin retention enforcement auto-purges only `DELETED` datasets after retention and only when legal hold/object lock policies do not deny purge.
  - Purge deletes final object storage through `ObjectStorage.delete_object` and then clears object metadata after marking the dataset `PURGED`.
  - Added explicit `upload-worker run`, `run-once`, and `reconcile` commands; `reconcile` handles missing-object, metadata-only, verified, and operator-supplied object-only detection without running as part of the periodic lifecycle pass.
- Compatibility notes:
  - Docker worker command now invokes `python -m upload_control_plane.worker.main run`.
  - `upload-worker` console script is available beside `uploadctl`.

## Verification

- Commands run:
  - `uv run ruff check src tests`: passed.
  - `uv run ruff format --check src tests`: passed, 78 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 78 source files.
  - `uv run pytest tests/application/test_worker_lifecycle.py -q`: passed, 4 passed.
  - `uv run pytest tests/api/test_upload_session_runtime_api.py tests/api/test_dataset_lifecycle_api.py tests/api/test_device_identity_api.py -q`: passed, 26 passed, 1 Starlette/httpx deprecation warning.
  - `uv run pytest -q`: passed, 185 passed, 1 Starlette/httpx deprecation warning.
  - `docker compose config --quiet`: passed.
  - `uv run upload-worker --help`: passed, commands listed.
  - `rg -n "UploadFile|File\(|Form\(|request\.body\(|request\.stream\(|Body\(.*bytes|bytes\s*=\s*Body|receive\(|StreamingResponse|FileResponse|/upload-bytes|/file-bytes" src\upload_control_plane\api src\upload_control_plane\main.py`: no matches, exit 1 expected.
  - `rg -n "s3_access_key|s3_secret_key|S3_ACCESS_KEY|S3_SECRET_KEY|aws_access_key_id|aws_secret_access_key|minioadmin" src\upload_control_plane\api src\upload_control_plane\application src\upload_control_plane\cli tools\manual-uploader\src`: no matches, exit 1 expected.
  - `git diff --check`: passed.
- Commands not run and why:
  - Live MinIO lifecycle smoke was not run; existing storage adapter coverage plus fake-storage lifecycle tests cover this implementation slice without requiring object-storage side effects.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. Worker uses metadata rows and storage adapter calls only.
- Clients receive no MinIO/S3 credentials: preserved. No API, CLI, or manual uploader credential exposure path added.
- Complete uses object storage ListParts as authority: preserved. No complete path changed.
- Authorization uses permission_grants: preserved. No API authorization path changed.
- Internal IDs remain UUIDs: preserved. New code uses existing UUID models only.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT/Go/edge implementation added.

## Risks and Follow-up

- Remaining risks:
  - Recovery object-only detection is operator-supplied via `--object-ref bucket:object/key`; the current `ObjectStorage` protocol has no object listing method.
  - Periodic worker does not run recovery reconciliation by default to avoid broad restore-state changes outside an explicit operator command.
  - Outbox atomicity/delivery acceptance remains for the next T11 outbox slice.
- Known gaps:
  - No outbox append helper or dispatcher in this branch by design.
  - No orphan multipart upload sweeper because the current adapter protocol does not expose incomplete multipart listing.
- Suggested next agent:
  - T11 Workers outbox implementation agent should add transaction-local outbox helper and dispatcher/retry/dead-letter behavior.

## Recovery Notes

- If accepted, next dependency unlocked: T11 workers-outbox slice can start; T12 still waits for full T11 acceptance including outbox validation.
- If partial, reusable pieces: `WorkerLifecycleService`, `upload-worker` CLI, and lifecycle tests.
- If blocked, unblock condition: none.
- If rejected, do not repeat: do not run recovery reconciliation as an implicit periodic cleanup pass; keep it an explicit operator command unless Master changes that contract.
