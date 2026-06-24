# Handoff: T04 storage adapter final merge

Status: accepted
Agent type: Merge
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-25 04:45 +08:00
Finished: 2026-06-25 04:49 +08:00

## Scope

- Intended scope:
  - Commit the accepted T04 storage adapter implementation, tests, dependency lock, and implementation/validation handoffs.
  - Run final repository validation after the stable checkpoint commit.
  - Preserve T04 boundaries and document whether T05 Upload Task Creation is unlocked.
- Explicitly out of scope:
  - Starting T05.
  - Adding public upload APIs, upload task/session application services, CLI/browser uploader behavior, or file-byte endpoints.
  - Changing storage adapter business logic after accepted implementation and validation.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0430-T04-merge-storage-interface-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0440-T04-implementation-storage-adapter-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0445-T04-validation-storage-adapter-accepted.md`

## Changes

- Files changed:
  - `pyproject.toml`
  - `uv.lock`
  - `src/upload_control_plane/infrastructure/storage/__init__.py`
  - `src/upload_control_plane/infrastructure/storage/s3_minio.py`
  - `tests/infrastructure/test_s3_storage.py`
  - `tests/integration/test_s3_storage_minio.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0440-T04-implementation-storage-adapter-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0445-T04-validation-storage-adapter-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0449-T04-merge-storage-adapter-accepted.md`
- Behavior changed:
  - Committed the accepted boto3/botocore S3/MinIO storage adapter checkpoint.
  - Added runtime dependency `boto3` and dev typing dependency `boto3-stubs[s3]`.
  - Preserved separate internal storage client and public presign client construction.
  - Presigned upload-part URLs are generated from the public endpoint client; no signed URL host rewrite is used.
  - Added focused infrastructure unit tests and real MinIO multipart integration test.
- Compatibility notes:
  - No API routes, database schema, public upload APIs, file-byte proxy, MQTT, Go, or edge behavior were added.
  - Domain layer remains free of boto3/botocore imports.
  - Stable implementation checkpoint commit is `183d79e` (`T04 storage adapter accepted`).

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
  - `rg -n "UploadFile|File\(|multipart/form-data|application/octet-stream|StreamingResponse|request\.stream|request\.body|Body\(|/upload-bytes|/file-bytes|/v1/uploads|@.*\.(post|put|patch).*upload|APIRouter" src/upload_control_plane tests`
  - `rg -n "s3_(access|secret)|S3_(ACCESS|SECRET)|secret_key|access_key|credentials|presigned\.url|presign" src/upload_control_plane tests`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 61 files already formatted.
  - `uv run mypy src tests`: passed, no issues found in 53 source files.
  - `uv run pytest`: passed, 126 passed, 5 skipped, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed, repeating ruff, format check, mypy, and pytest with 126 passed, 5 skipped, 1 existing warning.
  - `docker compose config --quiet`: passed.
  - `docker compose up -d minio minio-init`: passed; MinIO became healthy and init container started.
  - `uv run pytest tests/integration/test_s3_storage_minio.py -q`: passed, 1 passed.
  - `docker compose down`: passed; MinIO, init container, and compose network were removed.
  - Signed URL host rewrite scan: passed. Matches were endpoint configuration/tests plus unrelated authorization message formatting; no implementation host rewrite was found.
  - Public upload/file-byte endpoint scan: passed. Matches were MinIO direct PUT test content type and existing project router; no backend file-byte route or proxy was found.
  - API credential exposure scan: passed. Matches were backend settings/client construction, schema/test fields, and presign tests; no public API credential exposure was found.
- Commands not run and why:
  - None of the requested final validation commands were skipped.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. No FastAPI upload-byte route, request stream/body handler, backend proxy, or MQTT file path was added. Test bytes go directly to MinIO through a presigned URL.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Credentials remain in backend settings and boto3 client construction; adapter returns presigned URLs, not credentials.
- Complete uses object storage ListParts as authority:
  - Preserved at the adapter layer. MinIO integration completes from storage-observed `list_parts`; T06 must continue paginating before lifecycle completion.
- Authorization uses permission_grants:
  - Preserved. No authorization behavior changed.
- Internal IDs remain UUIDs:
  - Preserved. No schema or identifier behavior changed.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No optional component was added.

## Risks and Follow-up

- Remaining risks:
  - T06 completion orchestration must paginate `list_parts` until storage is fully observed before deciding completeness.
  - CORS inspection/configuration, incomplete multipart sweeping, and production encryption/object-lock policy tests remain later-task work.
  - `CompletedObject.size_bytes` remains `None` after S3 complete; callers needing size should use `head_object`.
- Known gaps:
  - No upload task creation API yet.
  - No runtime presign/status/ack/complete API yet.
  - No browser or CLI uploader yet.
- Suggested next agent:
  - T05 Upload Task Creation implementation agent.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T05 is unlocked after commit `183d79e` and this final merge handoff.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Do not generate signed URLs from the internal MinIO endpoint and rewrite the host afterward.
  - Do not add public upload/file-byte endpoints to T04.
  - Do not expose MinIO/S3 access key or secret key through API responses, logs, traces, manifests, or handoffs.
