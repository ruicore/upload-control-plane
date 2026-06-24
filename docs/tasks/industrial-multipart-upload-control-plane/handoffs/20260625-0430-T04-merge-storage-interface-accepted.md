# Handoff: T04 storage adapter interface merge

Status: accepted
Agent type: Merge
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 04:27 +08:00
Finished: 2026-06-25 04:30 +08:00

## Scope

- Intended scope:
  - Commit the accepted T04 storage interface implementation, tests, and implementation/validation handoffs.
  - Re-run repository validation after the stable checkpoint commit.
  - Preserve the boundary that the next T04 segment is adapter implementation, not part of this merge.
- Explicitly out of scope:
  - Implementing boto3, botocore, MinIO, or S3 adapter behavior.
  - Adding real multipart network operations or MinIO integration tests.
  - Adding public upload APIs, file-byte endpoints, or downstream T05/T06 behavior.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0424-T04-implementation-storage-interface-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0427-T04-validation-storage-interface-accepted.md`

## Changes

- Files changed:
  - `src/upload_control_plane/domain/storage.py`
  - `src/upload_control_plane/domain/__init__.py`
  - `tests/domain/test_storage.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0424-T04-implementation-storage-interface-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0427-T04-validation-storage-interface-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0430-T04-merge-storage-interface-accepted.md`
- Behavior changed:
  - Merged the provider-neutral `ObjectStorage` protocol, immutable storage DTOs, storage capability model, and provider-neutral storage errors.
  - Exposed the storage interface types through the domain package exports.
  - Added focused domain tests for storage DTO validation, immutability, protocol shape, and storage error context.
- Compatibility notes:
  - No API routes, database schema, settings, infrastructure adapter, or storage network behavior changed.
  - The stable checkpoint commit is `9123369` (`T04 storage interface accepted`).

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `rg -n "^\s*(from|import)\s+(fastapi|sqlalchemy|boto3|botocore|minio|httpx|requests|urllib3|aiohttp)\b|^\s*from\s+.*\s+import\s+.*\b(FastAPI|APIRouter|Depends|UploadFile|File)\b" src/upload_control_plane/domain`
  - `rg -n "(UploadFile|File\(|multipart/form-data|application/octet-stream|StreamingResponse|request\.stream|request\.body|Body\(|/upload-bytes|/file-bytes|/v1/uploads)" src tests`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 57 files already formatted.
  - `uv run mypy src tests`: passed, no issues found in 49 source files.
  - `uv run pytest`: passed, 119 passed, 4 skipped, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed, repeating ruff, format check, mypy, and pytest with 119 passed, 4 skipped, 1 existing warning.
  - Forbidden domain import check: passed with no matches.
  - Upload/file-byte endpoint check: passed with no matches.
- Commands not run and why:
  - MinIO multipart integration tests were not run because this merge only accepts the T04 storage interface segment; the boto3/MinIO adapter is explicitly out of scope.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No API route, body parser, stream handler, MQTT path, or proxy behavior was added.
- Clients receive no MinIO/S3 credentials: preserved. No settings or credential exposure was added.
- Complete uses object storage ListParts as authority: preserved at the interface boundary through `list_parts` and completion DTOs; complete orchestration remains unimplemented.
- Authorization uses permission_grants: preserved. No authorization behavior changed.
- Internal IDs remain UUIDs: preserved. No schema or identifier changes were made.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No optional component was added.

## Risks and Follow-up

- Remaining risks:
  - This merge accepts only the storage interface segment, not the full T04 storage adapter task.
  - The next implementation must keep separate internal storage client behavior and public presign behavior, and must not rewrite presigned URL hosts after signing.
- Known gaps:
  - No boto3/botocore adapter.
  - No MinIO/S3 client factory.
  - No real create, presign, list, complete, abort, or head storage operation.
  - No MinIO integration tests.
- Suggested next agent:
  - T04 storage multipart operations implementation agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The next T04 adapter implementation can start against the accepted `ObjectStorage` protocol.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not add boto3/MinIO dependencies to the domain layer.
  - Do not proxy file bytes through the backend.
  - Do not expose MinIO/S3 credentials to clients.
  - Do not complete uploads from client or DB ack data without storage-authoritative `ListParts`.
