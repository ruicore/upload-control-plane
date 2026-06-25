# Handoff: T10 Device Identity and Device Upload Authorization Validation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T10-validation-device-identity
Worktree: D:\upload-control-plane-T10-validation-device-identity
Started: 2026-06-25 15:11 +08:00
Finished: 2026-06-25 15:17 +08:00

## Scope

- Intended scope:
  - Independently validate T10 implementation branch `codex/industrial-upload/T10-implementation-device-identity` at commit `3496c240319f903fbdf07bca7c71288d7ef4a154`.
  - Verify device register/update/disable/enable endpoints, credential provisioning/rotation/revocation, and device upload authorization.
  - Verify disabled/revoked/expired device credentials cannot create upload tasks or request presigned URLs.
  - Verify device uploads create ordinary UploadTask, Dataset, UploadObject, and UploadSession records without adding a backend file-byte path.
  - Verify `source_device_id` remains a registered device UUID and `source_device_code` remains metadata.
  - Verify runtime presign/ack/list/lifecycle routes bind device credentials to upload sessions with matching `source_device_id`.
- Explicitly out of scope:
  - Repairing implementation defects.
  - MQTT, Go uploader, edge gateway, or broker/device file transfer.
  - Manual browser uploader validation.
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
  - `D:\upload-control-plane-T10-implementation-device-identity\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1511-T10-implementation-device-identity-accepted.md`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1517-T10-validation-device-identity-accepted.md`
- Behavior changed:
  - None. Validation agent did not modify functional code.
- Compatibility notes:
  - Validation branch is based directly on implementation commit `3496c240319f903fbdf07bca7c71288d7ef4a154`.

## Verification

- Commands run:
  - `git worktree add -b codex/industrial-upload/T10-validation-device-identity D:\upload-control-plane-T10-validation-device-identity 3496c24`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest tests/api/test_device_identity_api.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py -q`
  - `rg -n "UploadFile|File\(|Form\(|request\.stream|request\.body\(|iter_bytes|multipart/form-data|read\(\).*file|\.write\(.*chunk|chunks?" src tests README.md docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1511-T10-implementation-device-identity-accepted.md`
  - `rg -n "aws_access_key_id|aws_secret_access_key|s3_access_key|s3_secret_key|MINIO_ROOT|credential_material|secret_key|access_key|X-Amz-Credential" src tests docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1511-T10-implementation-device-identity-accepted.md`
  - `docker compose config --quiet`
  - `uv run python scripts\migrate.py`
  - `uv run pytest -q`
  - `uv run alembic heads`
  - `uv run alembic current`
- Results:
  - `ruff check`: passed.
  - `ruff format --check`: passed, 84 files already formatted.
  - `mypy`: passed, no issues in 75 source files.
  - Focused T10/API/runtime tests: passed, 30 passed with 1 Starlette/httpx deprecation warning.
  - Backend file-byte route scan: no FastAPI backend file-byte receive markers found. Hits were local CLI file reads and the implementation handoff text.
  - Credential exposure scan: no client-facing MinIO/S3 credential response path found. Hits were backend settings/storage adapter internals, one-time device credential response/test assertions, manifest redaction markers, and schema tests proving `credential_material` is absent from the table.
  - `docker compose config --quiet`: passed.
  - Migration smoke: `uv run python scripts\migrate.py` completed successfully against the local PostgreSQL stack.
  - Full pytest: passed, 178 passed with 1 Starlette/httpx deprecation warning.
  - Alembic head/current: both report `20260625_0006 (head)`.
- Commands not run and why:
  - Clean empty-database migration from a newly created database was not run; the local stack already existed. I ran the repository migration command and confirmed Alembic current/head instead.
  - Live object upload to MinIO was not rerun for T10 because T10 does not alter storage adapter behavior; upload task/session regressions and full pytest passed.
  - Browser, MQTT, Go, and edge tests were not run because they are outside T10 validation scope.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Accepted. No backend `UploadFile`, form upload, request stream/body file-byte route, MQTT, or broker data-plane implementation was found. Device upload routes call the existing upload task creation service.
- Clients receive no MinIO/S3 credentials:
  - Accepted. MinIO/S3 access keys remain backend settings/storage-adapter internals. T10 API responses return device control-plane credentials only during provision/rotate.
- Complete uses object storage ListParts as authority:
  - Accepted. T10 did not alter complete behavior; runtime/full tests pass.
- Authorization uses permission_grants:
  - Accepted. Device actors map to `SubjectType.DEVICE`; device upload and runtime presign/ack/list/lifecycle authorization evaluates permission grants instead of API-key scopes.
- Internal IDs remain UUIDs:
  - Accepted. `source_device_id`, device credentials, upload tasks, datasets, sessions, and related FKs remain UUID-backed. `source_device_code` is metadata.
- MQTT/Go/edge remain optional and dependency-gated:
  - Accepted. No MQTT, Go uploader, or edge gateway implementation was introduced.

## Risks and Follow-up

- Remaining risks:
  - This validation did not create a brand-new empty PostgreSQL database; it used the local stack and verified migration/current head there.
  - One-time raw device credential behavior is covered by tests for register/get and rotation use, but there is no separate list endpoint assertion in the focused test file. The response model and route implementation for list/get do not include credential material.
  - Existing presigned URLs remain valid until expiry after device revocation; this is consistent with the PRD failure-mode guidance and was not treated as a blocker.
- Known gaps:
  - No T13 operator runbook for device compromise yet.
  - No per-device rate limit enforcement beyond existing settings and project/task limits.
- Suggested next agent:
  - Master review can proceed. If accepted by Master, a Merge agent may merge T10 after reviewing this validation handoff and the implementation handoff.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T11 Workers and Lifecycle Automation may proceed after Master review and merge acceptance.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
