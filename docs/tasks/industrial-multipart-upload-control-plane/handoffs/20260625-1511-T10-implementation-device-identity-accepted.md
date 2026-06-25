# Handoff: T10 Device Identity and Device Upload Authorization

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T10-implementation-device-identity
Worktree: D:\upload-control-plane-T10-implementation-device-identity
Started: 2026-06-25 14:00 +08:00
Finished: 2026-06-25 15:11 +08:00

## Scope

- Intended scope:
  - Device register/update/disable/enable endpoints.
  - Device credential provisioning during registration and rotation.
  - Once-only raw credential return on provisioning/rotation only.
  - Credential expiration, revocation, and rotation overlap behavior.
  - Device-to-project upload authorization through `permission_grants`.
  - Device upload path creating ordinary UploadTask, UploadObject, Dataset, and UploadSession records.
- Explicitly out of scope:
  - MQTT, Go uploader, edge gateway, or file-byte transfer through backend.
  - Storage-side instant revocation of already issued presigned URLs.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T10 section
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1323-master-handoff-after-T08-T09-accepted-T07-partial.md`

## Changes

- Files changed:
  - `migrations/versions/20260625_0006_device_credentials_schema.py`
  - `src/upload_control_plane/api/auth.py`
  - `src/upload_control_plane/api/authorization.py`
  - `src/upload_control_plane/api/devices.py`
  - `src/upload_control_plane/api/upload_sessions.py`
  - `src/upload_control_plane/api/upload_tasks.py`
  - `src/upload_control_plane/application/devices.py`
  - `src/upload_control_plane/application/upload_sessions.py`
  - `src/upload_control_plane/application/upload_tasks.py`
  - `src/upload_control_plane/infrastructure/db/__init__.py`
  - `src/upload_control_plane/infrastructure/db/models.py`
  - `src/upload_control_plane/infrastructure/db/seed.py`
  - `src/upload_control_plane/main.py`
  - `tests/api/test_auth_foundation.py`
  - `tests/api/test_device_identity_api.py`
  - `tests/infrastructure/test_alembic_config.py`
  - `tests/infrastructure/test_device_credentials_schema.py`
- Behavior changed:
  - Added `device_credentials` table with hash, version, issued/expires/revoked/last-used metadata; no raw credential column.
  - Bearer auth now accepts active API keys or active device credentials.
  - Device subjects evaluate `permission_grants` as `subject_type=device`.
  - Added project device routes for list/get/register/update/disable/enable/credential rotation/credential revoke/device upload.
  - Registration and rotation return raw credential material once in the response.
  - Rotation with `overlap_seconds=0` revokes old active credentials immediately; positive overlap shortens old credential expiry to the overlap window.
  - Device upload route forces `task_initiator=device`, registered device UUID as `source_device_id`, and device code as metadata.
  - Generic upload task creation validates supplied `source_device_id` is a registered active device UUID authorized to the project; `source_device_code` alone remains metadata.
  - Runtime upload session routes reject device credentials for sessions whose `source_device_id` does not match the authenticated device.
  - Dev seed now creates a device credential lifecycle row and grants device management permissions to the dev API key.
- Compatibility notes:
  - Existing API key auth contract remains `Authorization: Bearer <api_key>`.
  - Existing `devices.credential_hash/version` columns are retained for compatibility but new auth uses `device_credentials`.
  - `/internal/auth-smoke` now includes `actor_type`; `api_key_id` may be null for device actors.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest tests\infrastructure\test_device_credentials_schema.py tests\infrastructure\test_alembic_config.py tests\infrastructure\test_seed_dev.py tests\api\test_auth_foundation.py -q`
  - `uv run pytest tests\api\test_device_identity_api.py -q`
  - `uv run pytest tests\api\test_upload_task_api_foundation.py tests\api\test_upload_session_runtime_api.py -q`
  - `uv run pytest`
  - `docker compose config --quiet`
  - `uv run python scripts\migrate.py`
- Results:
  - `ruff check`: passed.
  - `ruff format --check`: passed, 84 files already formatted.
  - `mypy`: passed, no issues in 75 source files.
  - Focused schema/auth tests: 16 passed, 1 Starlette/httpx deprecation warning.
  - T10 device API tests: first run failed because local PostgreSQL had not applied `device_credentials`; after `uv run python scripts\migrate.py`, rerun passed with 6 passed, 1 Starlette/httpx deprecation warning.
  - Upload task/runtime regression tests: 24 passed, 1 Starlette/httpx deprecation warning.
  - Full pytest: 178 passed, 1 Starlette/httpx deprecation warning.
  - `docker compose config --quiet`: passed.
- Commands not run and why:
  - No live browser/manual uploader validation; T10 does not change T07 browser tooling.
  - No MQTT/Go/edge tests; explicitly out of scope and dependency-gated.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. No `UploadFile`, multipart form, request stream/body file path, MQTT, or broker data-plane path was added.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Device credentials authenticate only to the control-plane API; no MinIO/S3 access key or secret is returned.
- Complete uses object storage ListParts as authority:
  - Preserved. T10 did not alter complete behavior; full pytest and runtime tests still pass.
- Authorization uses permission_grants:
  - Preserved. Device upload and presign authorization evaluate `permission_grants` with `subject_type=device`; API key scopes do not replace resource authorization.
- Internal IDs remain UUIDs:
  - Preserved. Device, credential, upload task, dataset, session, and foreign keys use UUIDs.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go uploader, or edge gateway implementation was added.

## Risks and Follow-up

- Remaining risks:
  - Credential material format is a generated bearer token suitable for local portfolio implementation, not mTLS/X.509.
  - Existing presigned URLs cannot be revoked instantly after device revocation; this matches PRD guidance and relies on short expiry/operator pause/abort.
  - Device project access is represented by project-scoped `permission_grants`; no separate `device_project_grants` table was added because the hard constraint keeps permission grants authoritative.
- Known gaps:
  - No rate-limit quota enforcement per device beyond existing project/tenant upload task limits.
  - No operator docs/runbook for compromised device yet; this belongs in T13 operations docs.
- Suggested next agent:
  - T10 validation agent should independently verify migration, device credential lifecycle, disabled/revoked/expired behavior, and no file-byte route expansion.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T11 Workers and Lifecycle Automation may start after independent T10 validation and merge acceptance.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
