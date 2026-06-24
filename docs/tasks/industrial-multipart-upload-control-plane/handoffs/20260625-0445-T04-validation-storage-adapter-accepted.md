# Handoff: T04 storage adapter validation

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 04:40 +08:00
Finished: 2026-06-25 04:45 +08:00

## Scope

- Intended scope:
  - Independently validate the full T04 storage adapter implementation already present in the worktree.
  - Verify the domain `ObjectStorage` protocol, boto3/botocore boundary, S3/MinIO adapter behavior, MinIO integration flow, and PRD hard constraints.
  - Run the requested repository, Docker Compose, integration, and `rg` checks.
- Explicitly out of scope:
  - Modifying implementation code, tests, config, README, or PRD files.
  - Repairing or extending storage behavior.
  - Adding public upload APIs, CLI uploader, T05/T06 behavior, or file-byte endpoints.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T04 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0430-T04-merge-storage-interface-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0440-T04-implementation-storage-adapter-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md` presign/CORS/security sections
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md` completion/list parts notes
  - `src/upload_control_plane/domain/storage.py`
  - `src/upload_control_plane/infrastructure/storage/s3_minio.py`
  - `tests/infrastructure/test_s3_storage.py`
  - `tests/integration/test_s3_storage_minio.py`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0445-T04-validation-storage-adapter-accepted.md`
- Behavior changed:
  - None. Validation only.
- Compatibility notes:
  - Existing uncommitted T04 implementation files were left intact.
  - No implementation, test, config, README, or PRD file was modified.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up -d minio minio-init`
  - `uv run pytest tests/integration/test_s3_storage_minio.py -q`
  - `docker compose down`
  - `rg -n "replace\(|urlsplit|urlunsplit|netloc|hostname|S3_PUBLIC_ENDPOINT_URL|s3_public_endpoint_url|s3_endpoint_url|endpoint_url" src tests pyproject.toml docker-compose.yml`
  - `rg -n "\b(boto3|botocore|minio)\b" src/upload_control_plane/domain src/upload_control_plane/infrastructure tests pyproject.toml`
  - `rg -n "UploadFile|File\(|multipart/form-data|application/octet-stream|StreamingResponse|request\.stream|request\.body|Body\(|/upload-bytes|/file-bytes|/v1/uploads|put\(|post\(" src/upload_control_plane tests`
  - `rg -n "s3_(access|secret)|S3_(ACCESS|SECRET)|secret_key|access_key|credentials|presigned.url|presign" src/upload_control_plane tests`
  - `rg -n "APIRouter|@.*\.(post|put|patch)|UploadFile|StreamingResponse|request\.body|request\.stream|/v1/uploads|upload-bytes|file-bytes" src/upload_control_plane/api src/upload_control_plane -g "*.py"`
- Results:
  - `uv run ruff check`: passed, all checks passed.
  - `uv run ruff format --check`: passed, 61 files already formatted.
  - `uv run mypy src tests`: passed, no issues found in 53 source files.
  - `uv run pytest`: passed, 126 passed, 5 skipped, 1 existing Starlette TestClient deprecation warning. The MinIO integration test skipped before MinIO was started.
  - `make test`: passed, repeated ruff, format check, mypy, and pytest with 126 passed, 5 skipped, 1 existing warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d minio minio-init`: passed; MinIO became healthy and init started.
  - `uv run pytest tests/integration/test_s3_storage_minio.py -q`: passed, 1 passed.
  - `docker compose down`: passed; MinIO, init container, and compose network removed.
  - Signed URL host rewrite check: no implementation host rewrite found. Matches were endpoint configuration/tests and unrelated `replace` in authorization message formatting.
  - Domain SDK boundary check: no boto3/botocore imports in `src/upload_control_plane/domain`; boto3/botocore are limited to dependency declarations, infrastructure adapter, and tests.
  - Prohibited upload/file-byte endpoint checks: no FastAPI upload-byte endpoint, `UploadFile`, request stream/body, `StreamingResponse`, `/v1/uploads`, `/upload-bytes`, or `/file-bytes` route found. The only direct byte PUT is the MinIO integration test using `httpx.put(presigned.url, content=body)`.
  - Credential exposure scan: MinIO access/secret settings are backend config/client construction only; no API response or public route exposes client MinIO credentials.
- Commands not run and why:
  - None of the requested validation commands were skipped.

## Full T04 Checks

- ObjectStorage protocol satisfied by implementation:
  - Accepted. `S3ObjectStorage` implements capabilities, create multipart, presign upload part, list parts, complete multipart, abort multipart, and head object using the accepted domain request/result DTOs.
- boto3/botocore dependency only in infrastructure, not domain:
  - Accepted. `src/upload_control_plane/domain/storage.py` has no boto3/botocore import; SDK imports are in `src/upload_control_plane/infrastructure/storage/s3_minio.py` and tests.
- Separate internal S3 client and presign client:
  - Accepted. `build_s3_clients(settings)` creates one client from `settings.s3_endpoint_url` and one from `settings.s3_public_endpoint_url`; unit tests assert `http://minio:9000` vs `http://localhost:19000`.
- No string post-processing rewrites signed URL host:
  - Accepted. Presigned URL generation uses the public-endpoint client directly; no string host replacement is used.
- Multipart operations:
  - Accepted. The adapter implements create multipart, presign upload part, paged list parts with marker/max parts/truncated marker, complete multipart, abort multipart, and head object.
- MinIO integration test:
  - Accepted. The integration test creates a multipart upload, presigns a host-reachable `localhost:19000` URL, directly PUTs bytes to MinIO, lists the uploaded part, completes the object, verifies `head_object`, and reads the stored object body through MinIO.
- No public upload APIs or file-byte endpoint:
  - Accepted. No such route or file-byte proxy was added.
- No client MinIO credentials exposed through API:
  - Accepted. No API route exposes storage credentials; clients receive only presigned URLs at the adapter boundary.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. No API route, request body stream, proxy, or MQTT path was added. Test bytes go directly to MinIO through the presigned URL.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Credentials remain in backend settings and boto3 client construction.
- Complete uses object storage ListParts as authority:
  - Preserved at the adapter layer. The MinIO integration test completes from storage-observed `list_parts`; downstream T06 must continue paginating until all pages are reconciled.
- Authorization uses permission_grants:
  - Preserved. No authorization behavior changed.
- Internal IDs remain UUIDs:
  - Preserved. No schema or identifier behavior changed.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No optional component was added.

## Risks and Follow-up

- Remaining risks:
  - `list_parts` intentionally exposes one provider page at a time; T06 completion orchestration must loop through `is_truncated` and `next_part_number_marker` before validating completeness.
  - CORS policy inspection/configuration is not implemented in T04, but the adapter exposes the capability flag and no browser uploader is in scope yet.
  - Production encryption, object-lock, legal-hold, and storage-native checksum paths remain policy-specific follow-up work and should be tested before production enablement.
- Known gaps:
  - No public upload task/session API yet; that is T05/T06 scope.
  - No incomplete multipart sweeper yet; that is lifecycle worker scope.
- Suggested next agent:
  - T04 merge/master review can finalize this task. After merge, T05 Upload Task Creation is unblocked.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T04 can merge/finalize. T05 can start after the accepted implementation and this validation handoff are merged.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
