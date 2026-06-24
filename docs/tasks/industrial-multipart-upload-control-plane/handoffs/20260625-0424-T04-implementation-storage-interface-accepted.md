# Handoff: T04 storage adapter interface

Status: accepted
Agent type: Implementation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 04:18 +08:00
Finished: 2026-06-25 04:24 +08:00

## Scope

- Intended scope:
  - Define the provider-neutral ObjectStorage adapter boundary for multipart storage.
  - Add typed immutable DTOs/value objects for multipart create, presign, list parts, complete, abort, head object, and storage capabilities.
  - Add storage-specific exception classes that are independent from boto3, MinIO, FastAPI, and SQLAlchemy.
  - Add focused unit tests for DTO validation, immutability, storage error context, and runtime protocol shape.
- Explicitly out of scope:
  - boto3 or botocore dependencies.
  - MinIO/S3 client construction.
  - Real presigned URL generation.
  - Real create/list/complete/abort/head network operations.
  - Public upload APIs, application services, endpoint changes, file-byte handling, or storage integration tests.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0417-T03-merge-authz-project-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/02-context-goals-scope.md`
  - `docs/prd/industrial-multipart-upload-control-plane/03-system-architecture.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`

## Changes

- Files changed:
  - `src/upload_control_plane/domain/storage.py`
  - `src/upload_control_plane/domain/__init__.py`
  - `tests/domain/test_storage.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0424-T04-implementation-storage-interface-accepted.md`
- Behavior changed:
  - Added `ObjectStorage` as a runtime-checkable protocol with methods for create multipart, presign upload part, paged list parts, complete multipart, abort multipart, and head object.
  - Added immutable request/result DTOs: `CreateMultipartUploadRequest`, `CreateMultipartUploadResult`, `PresignUploadPartRequest`, `PresignedPartUrl`, `ListPartsRequest`, `ListedPart`, `ListedPartsPage`, `CompletionPart`, `CompleteMultipartUploadRequest`, `CompletedObject`, `AbortMultipartUploadRequest`, `HeadObjectRequest`, and `HeadObjectResult`.
  - Added `StorageCapabilities` flags for native checksums, conditional complete, encryption modes, object lock, legal hold, replication metadata, incomplete multipart listing, and CORS inspection.
  - Added provider-neutral storage exception types including access denied, not found, conflict, precondition failed, checksum mismatch, configuration, operation, and unsupported capability errors.
- Compatibility notes:
  - No existing API, database model, settings, migration, or infrastructure behavior changed.
  - The boundary lives in `domain` and imports no provider SDK, FastAPI, SQLAlchemy, or MinIO-specific code.
  - `list_parts` is modeled as a paged operation so the later storage implementation can loop over provider pagination without changing application contracts.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest tests/domain/test_storage.py -q`
  - `uv run pytest`
  - `make test`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 57 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 49 source files.
  - `uv run pytest tests/domain/test_storage.py -q`: passed, 7 passed.
  - `uv run pytest`: passed, 119 passed, 4 skipped, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed, repeating ruff, format check, mypy, and pytest with 119 passed, 4 skipped, 1 existing warning.
- Commands not run and why:
  - MinIO integration tests were not run because this first segment intentionally defines only the adapter boundary and does not implement network operations.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No API, MQTT, proxy, or file-byte path was added.
- Clients receive no MinIO/S3 credentials: preserved. No credential or settings exposure was added.
- Complete uses object storage ListParts as authority: preserved and enabled by explicit `list_parts` and `CompletionPart` DTOs; complete orchestration remains unimplemented.
- Authorization uses permission_grants: preserved. No authorization behavior changed.
- Internal IDs remain UUIDs: preserved. No identifiers or database schema changed.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No optional component was added.

## Risks and Follow-up

- Remaining risks:
  - The protocol uses request DTOs instead of the exact keyword-only sketch in PRD section 15.1. This keeps pagination, immutable maps, and future policy data stable but means the next implementation agent should implement the DTO-based protocol directly rather than copying the sketch literally.
  - Provider error mapping is only typed; actual boto3/botocore exception translation remains for the next T04 storage implementation agent.
- Known gaps:
  - No S3/MinIO client factory.
  - No real multipart storage operations.
  - No integration tests against MinIO.
  - No enforcement yet that `S3_ENDPOINT_URL` and `S3_PUBLIC_ENDPOINT_URL` use separate clients.
- Suggested next agent:
  - T04 storage multipart operations implementation agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - The next T04 storage implementation agent can start implementing the infrastructure adapter against this `ObjectStorage` protocol.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not add boto3/MinIO network behavior to the domain layer.
  - Do not rewrite presigned URL hosts after signing.
  - Do not complete uploads from client or database-reported parts without storage-authoritative `ListParts`.
