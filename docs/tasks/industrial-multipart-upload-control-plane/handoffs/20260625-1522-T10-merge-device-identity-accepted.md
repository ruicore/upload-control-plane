# Handoff: T10 Device Identity Merge

Status: accepted
Agent type: Merge
Branch: codex/industrial-upload/T10-merge-device-identity
Worktree: D:\upload-control-plane-T10-merge-device-identity
Started: 2026-06-25 15:18 Asia/Shanghai
Finished: 2026-06-25 15:22 Asia/Shanghai

## Scope

- Intended scope: merge accepted T10 validation branch `codex/industrial-upload/T10-validation-device-identity` at `e6713ca` into current main `fced193`.
- Explicitly out of scope: product behavior changes, new features, semantic conflict resolution, repair beyond merge mechanics, changes to T07/T08/T09 accepted behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1517-T10-validation-device-identity-accepted.md`

## Changes

- Files changed:
  - Merged T10 device identity and device upload authorization from the accepted validation branch.
  - Merged `device_credentials` migration, API/application code, auth integration, seed updates, and focused tests.
  - Merged T10 implementation and validation handoffs.
  - Added this merge handoff.
- Behavior changed:
  - T10 accepted behavior is present on the merge branch: device register/update/disable/enable, credential provision/rotate/revoke, device credential auth, and device upload creation through ordinary upload tasks/sessions.
  - T07 CORS middleware and accepted route registration remain present in `src/upload_control_plane/main.py`.
- Compatibility notes:
  - Merge completed with Git ort auto-merge.
  - `src/upload_control_plane/main.py` auto-merged route/CORS registration without conflict: T07 CORS settings remain configured and T10 `devices_router` is included.
  - No manual semantic conflict resolution was required.

## Verification

- Commands run:
  - `git merge --no-ff codex/industrial-upload/T10-validation-device-identity`
  - `git diff --check`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest tests/api/test_device_identity_api.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py -q`
  - `uv run pytest tests/api/test_cors.py tests/test_config.py -q`
  - `docker compose config --quiet`
  - `rg -n "UploadFile|File\(|Form\(|multipart/form-data|request\.body\(|request\.stream\(|Body\(.*bytes|bytes\s*=\s*Body|receive\(" src\upload_control_plane\api src\upload_control_plane\main.py`
  - `rg -n "S3_ACCESS|S3_SECRET|s3_access|s3_secret|minioadmin|AWS_ACCESS_KEY|AWS_SECRET|aws_access_key_id|aws_secret_access_key|MINIO_ROOT|X-Amz-Credential|boto3|botocore|upload_control_plane\.infrastructure" src\upload_control_plane\cli tools tests\cli`
  - `rg -n "access_key|secret_key|aws_access_key_id|aws_secret_access_key|s3_access_key|s3_secret_key|MINIO_ROOT|X-Amz-Credential" src\upload_control_plane\api src\upload_control_plane\application tests\api`
- Results:
  - Merge succeeded with no conflicts.
  - `git diff --check`: passed.
  - `uv run ruff check`: passed, all checks passed. `uv` created a local `.venv` and emitted a hardlink fallback performance warning.
  - `uv run ruff format --check`: passed, 85 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 76 source files.
  - T10/T05/T06 API regression pytest: passed, 30 tests passed with one Starlette/TestClient deprecation warning.
  - T07 CORS/config regression pytest: passed, 5 tests passed with one Starlette/TestClient deprecation warning.
  - `docker compose config --quiet`: passed.
  - Backend file-byte API route marker scan: no matches.
  - CLI/client credential scan: one expected redaction marker hit in `src\upload_control_plane\cli\manifest.py` for `X-Amz-Credential`; no MinIO/S3 access key or secret exposure markers.
  - API/application credential exposure scan: no matches for MinIO/S3 access key, secret key, AWS credential, MinIO root, or `X-Amz-Credential` exposure markers.
- Commands not run and why:
  - No broader full test suite was run because the merge request specified the targeted validation set.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. API route marker scan found no `UploadFile`, FastAPI `File(...)`, form upload, request body read/stream, or bytes body markers under API/main.
- Clients receive no MinIO/S3 credentials: preserved. Client/API scans found no client-facing MinIO/S3 access key or secret exposure. The only client-side credential marker hit is a manifest redaction marker for `X-Amz-Credential`. T10 device credentials are control-plane credentials returned only during provisioning/rotation.
- Complete uses object storage ListParts as authority: preserved. Merge did not alter accepted T06 storage-authoritative complete behavior.
- Authorization uses permission_grants: preserved. T10 device management and device upload authorization continue to use permission grants and resource checks.
- Internal IDs remain UUIDs: preserved. T10 device, credential, upload task, dataset, session, and related foreign keys remain UUID-backed.
- MQTT/Go/edge remain optional and dependency-gated: preserved. Merge did not add MQTT, Go uploader, Go gateway, or edge components.
- Presigned URLs are not persisted: preserved. Merge did not alter accepted presign URL handling; CLI manifest redaction includes `X-Amz-Credential`.

## Risks and Follow-up

- Remaining risks:
  - The new worktree contains ignored local tool caches and `.venv` from validation; they are not part of the commit.
  - Starlette/TestClient deprecation warnings remain existing dependency noise in targeted pytest runs.
- Known gaps:
  - No live MinIO upload smoke was rerun by this Merge Agent; Master review already accepted the T10 validation source and this merge ran the requested targeted regressions.
- Suggested next agent:
  - Master final review for the T10 merge branch.

## Recovery Notes

- If accepted, next dependency unlocked: T10 merge can enter Master final review and downstream T11 planning can proceed after Master final acceptance.
- If partial, reusable pieces: not applicable.
- If blocked, unblock condition: not applicable.
- If rejected, do not repeat: not applicable.
