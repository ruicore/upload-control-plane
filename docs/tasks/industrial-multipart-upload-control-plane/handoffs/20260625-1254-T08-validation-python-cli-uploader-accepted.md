# Handoff: T08 Python CLI uploader validation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T08-validation-python-cli-uploader
Worktree: D:\upload-control-plane-T08-validation-python-cli-uploader
Started: 2026-06-25 12:39 +08:00
Finished: 2026-06-25 12:54 +08:00

## Scope

- Intended scope:
  - Independently validate source branch `codex/industrial-upload/T08-implementation-python-cli-uploader` at commit `97c8ed0`.
  - Verify `uploadctl` command surface: `upload`, `resume`, `status`, `pause`, `resume-session`, and `abort`.
  - Verify CLI uses public HTTP API routes and direct `PUT` to presigned storage URLs.
  - Verify no MinIO/S3 credentials are used by CLI code and no backend file-byte proxy path is added.
  - Verify manifest durability fields and presigned URL exclusion.
  - Verify bounded file reading, resume, pause/resume controls, abort controls, and URL-expiry re-presign behavior where practical.
  - Prefer real local API/PostgreSQL/MinIO smoke without touching other agents' worktrees or containers.
- Explicitly out of scope:
  - Fixing implementation issues.
  - Merging to `main`.
  - Pushing any branch.
  - Stopping or modifying other agents' containers using default or adjacent ports.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1238-T08-implementation-python-cli-uploader-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1254-T08-validation-python-cli-uploader-accepted.md`
- Behavior changed:
  - None. Validation only.
- Compatibility notes:
  - None.

## Verification

- Commands run:
  - `git worktree add -b codex/industrial-upload/T08-validation-python-cli-uploader D:\upload-control-plane-T08-validation-python-cli-uploader 97c8ed0`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest tests/cli -q`
  - `uv run uploadctl --help`
  - `docker compose config --quiet`
  - `git diff --check`
  - `uv run pytest`
  - `rg -n 'UploadFile|File\(|Form\(|multipart/form-data|request\.stream|request\.body|Body\(' src\upload_control_plane\api src\upload_control_plane\application`
  - `rg -n 'S3_ACCESS|S3_SECRET|s3_access|s3_secret|minioadmin|boto3|botocore|upload_control_plane\.application|upload_control_plane\.infrastructure' src\upload_control_plane\cli tests\cli`
  - `rg -n 'presigned_url|presigned_urls|signed_url|signed_urls|X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token|partNumber|uploadId' src\upload_control_plane\cli tests\cli`
  - `docker compose up -d postgres minio minio-init` with `POSTGRES_HOST_PORT=25438`, `MINIO_HOST_PORT=19008`, `MINIO_CONSOLE_HOST_PORT=19009`, and `S3_PUBLIC_ENDPOINT_URL=http://localhost:19008`
  - `uv run python scripts/migrate.py` with `DATABASE_URL=postgresql+psycopg://upload:upload@localhost:25438/upload`
  - `uv run python scripts/seed_dev.py` with `DATABASE_URL=postgresql+psycopg://upload:upload@localhost:25438/upload`, `S3_ENDPOINT_URL=http://localhost:19008`, and `S3_PUBLIC_ENDPOINT_URL=http://localhost:19008`
  - `uv run uvicorn upload_control_plane.main:app --host 127.0.0.1 --port 18088` with the same isolated database/storage environment
  - `Invoke-RestMethod -Uri http://127.0.0.1:18088/healthz`
  - `uv run uploadctl upload C:\Users\dex\AppData\Local\Temp\ucp-t08-validation-smoke.bin --api-url http://127.0.0.1:18088 --api-key ucp_dev_api_key_local_only_20260624 --project-id 020500f8-920c-5a49-bf01-0eca416b8ddf --part-size 5MiB --concurrency 2 --manifest C:\Users\dex\AppData\Local\Temp\ucp-t08-validation-smoke.upload.json`
  - `Select-String` manifest scans for `X-Amz-Signature|X-Amz-Credential|uploadId|partNumber|presigned|signed_url`
  - Public API create task, then `uv run uploadctl status`, `pause`, `resume-session`, and `abort` against the created session.
  - Public API create task plus generated local manifest, then `uv run uploadctl resume C:\Users\dex\AppData\Local\Temp\ucp-t08-validation-resume.upload.json --api-key ucp_dev_api_key_local_only_20260624 --concurrency 2`
  - Focused inline Python simulation for first storage `PUT` returning HTTP 403 expired response, followed by re-presign and retry success.
  - `docker compose down` for the validation worktree compose project.
- Results:
  - Worktree/branch creation succeeded from `97c8ed0`.
  - `uv run ruff check`: passed. First run created `.venv`; ruff emitted cache write warnings under `.ruff_cache` but exited `0`.
  - `uv run ruff format --check`: passed, `76 files already formatted`.
  - `uv run mypy src tests`: passed, `Success: no issues found in 68 source files`.
  - `uv run pytest tests/cli -q`: passed, `6 passed`.
  - `uv run uploadctl --help`: passed and listed `upload`, `resume`, `status`, `pause`, `resume-session`, and `abort`.
  - `docker compose config --quiet`: passed.
  - `git diff --check`: passed before handoff creation.
  - Backend file-byte route scan returned no matches for FastAPI file/form/body streaming markers in API/application code.
  - CLI credential/import scan returned no matches for MinIO/S3 credentials, boto3/botocore, or backend application/infrastructure imports under CLI code.
  - Manifest presigned-marker scan found markers only in manifest safety constants/tests, not durable smoke manifests.
  - Isolated local smoke succeeded:
    - Health returned `{"status":"ok","service":"upload-control-plane"}`.
    - `uploadctl upload` uploaded a 6 MiB file as 2 parts with 5 MiB part size, direct to MinIO through presigned URLs, and completed session `8a169521-6e24-4b1f-834d-a20d4191168d`.
    - Smoke manifest contained project/task/object/dataset/session/file metadata, file size, mtime, part size/count, part states, ETags, sizes, and timestamps; no presigned URL markers were found.
    - `uploadctl status`, `pause`, `resume-session`, and `abort` succeeded against a separate non-uploaded session `4563e00b-a0c0-4938-8b4c-a7da20a8c6a4`.
    - Simulated interruption/resume from a generated manifest succeeded and completed session `6ce0bf89-189d-4088-8c69-650363bed7c1`.
    - Focused expiry simulation proved first old URL `PUT` 403 triggers a fresh presign call for the same part and succeeds on the new URL.
  - `uv run pytest` default environment result: failed with `1 failed, 160 passed, 1 warning` because default `localhost:25432` was occupied by another agent's T09 validation Postgres containing pre-existing deterministic permission grant data. Failure was `UniqueViolation` on `permission_grants`, not T08 CLI behavior.
  - `uv run pytest` isolated environment result: failed with `2 failed, 159 passed, 1 warning`; all API/CLI/domain/storage behavior tests passed, and the two failures were default-configuration assertions expecting `localhost:25432` while validation intentionally set `DATABASE_URL=...localhost:25438` to avoid another agent's container.
- Commands not run and why:
  - Full default-port clean `uv run pytest`: not feasible without stopping or replacing another agent's container bound to `localhost:25432`, which would violate parallel-agent isolation.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Satisfied for T08. CLI streams file bytes only through `ControlPlaneClient.put_presigned_part()` using `httpx.Client().put(url, content=body, headers=...)` to storage-issued URLs. Backend API/application scan found no file/form/body streaming route markers.
- Clients receive no MinIO/S3 credentials:
  - Satisfied for T08. CLI accepts API URL/API key only. CLI code scan found no MinIO/S3 credential constants, boto3/botocore imports, or backend infrastructure imports.
- Complete uses object storage ListParts as authority:
  - Preserved. CLI calls the existing public complete endpoint and does not implement completion itself. Existing API tests for storage-authoritative completion passed in the isolated run.
- Authorization uses permission_grants:
  - Preserved. CLI uses existing authorized public API routes. No authorization implementation was changed.
- Internal IDs remain UUIDs:
  - Preserved. No schema or ID model changes were made by T08. Smoke responses used UUID project/task/object/dataset/session IDs.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go uploader, or gateway code was added.

## Risks and Follow-up

- Remaining risks:
  - Runtime `uploadctl upload` has no separate local interactive pause watcher. Server-side `uploadctl pause` prevents future presign requests, and interruption flushes the manifest as `PAUSED`, but an already presigned batch may continue until the next scheduling boundary. This is consistent with the PRD allowance for in-flight parts but is less ergonomic than a true interactive pause flag.
  - Full default-port test command remains blocked by parallel-agent environment state, not by the T08 implementation.
- Known gaps:
  - No durable unit test currently exercises the URL-expiry re-presign path; validation covered it with a focused inline simulation.
  - T08 CLI is single-file per invocation. The task did not require multi-file CLI support, and the implementation handoff explicitly documented this gap.
- Suggested next agent:
  - Master review can proceed. No Repair agent is required for T08 based on this validation.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T08 may be treated as accepted for downstream dependency planning, subject to Master review.
  - T16 remains blocked until T14 is accepted because its task dependency is T08 plus T14.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable for T08 acceptance. For a literal clean default-port full pytest run, stop or move the other agent's service currently bound to `localhost:25432`, then rerun from a clean database.
- If rejected, do not repeat:
  - Not applicable.
