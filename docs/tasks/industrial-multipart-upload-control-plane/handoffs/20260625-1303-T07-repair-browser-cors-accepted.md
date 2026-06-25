# Handoff: T07 browser CORS repair

Status: accepted
Agent type: Repair
Branch: codex/industrial-upload/T07-repair-browser-cors
Worktree: D:\upload-control-plane-T07-repair-browser-cors
Started: 2026-06-25 12:55 +08:00
Finished: 2026-06-25 13:03 +08:00

## Scope

- Intended scope:
  - Repair the validation blocker where browser CORS preflight from `http://localhost:5173` to the local FastAPI API returned HTTP 405.
  - Configure local MinIO CORS as needed for browser direct `PUT` to presigned URLs.
  - Add focused API CORS tests and narrow local documentation.
- Explicitly out of scope:
  - Backend upload-byte routes or file-byte proxying.
  - Manual-uploader-only backend shortcuts.
  - Product dashboard scope or UI feature expansion.
  - Relaxing authentication or `permission_grants`.
  - Merging to `main` or pushing.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` execution rules and T07 section
  - `D:\upload-control-plane-T07-implementation-browser-uploader\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1239-T07-implementation-browser-uploader-accepted.md`
  - `D:\upload-control-plane-T07-validation-browser-uploader\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1254-T07-validation-browser-uploader-partial.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`

## Changes

- Files changed:
  - `README.md`
  - `docker-compose.yml`
  - `src/upload_control_plane/config.py`
  - `src/upload_control_plane/main.py`
  - `tests/api/test_cors.py`
  - `tests/test_config.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1303-T07-repair-browser-cors-accepted.md`
- Behavior changed:
  - FastAPI now mounts `CORSMiddleware` from settings.
  - Local defaults allow `http://localhost:5173` with `Authorization`, `Content-Type`, `Idempotency-Key`, and `X-Request-ID`.
  - Docker Compose passes the local API CORS settings to the API service.
  - Docker Compose configures MinIO global CORS with `MINIO_API_CORS_ALLOW_ORIGIN` for `http://localhost:5173,http://localhost:3000`.
- Compatibility notes:
  - Current MinIO community image rejects bucket-level `mc cors set` with `NotImplemented`; the supported local fix is server-level `MINIO_API_CORS_ALLOW_ORIGIN`.
  - MinIO credentials remain only in compose/backend/minio-init environment and are not exposed to the browser.

## Verification

- Commands run:
  - `uv run pytest tests\api\test_cors.py tests\test_config.py`
  - `docker compose config --quiet`
  - `git diff --check`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `cd tools\manual-uploader; npm ci`
  - `cd tools\manual-uploader; npm run test`
  - `cd tools\manual-uploader; npm run check`
  - `cd tools\manual-uploader; npm run build`
  - `uv run pytest`
  - API preflight `TestClient` smoke for `OPTIONS /v1/projects/{project_id}/upload-tasks` with `Origin: http://localhost:5173`
  - Isolated MinIO compose smoke with `MINIO_HOST_PORT=19117`, `MINIO_CONSOLE_HOST_PORT=19118`, `docker compose -p upload-control-plane-t07-repair-cors up -d minio minio-init`
  - MinIO preflight smoke: `OPTIONS http://localhost:19117/robot-data/smoke-object?partNumber=1&uploadId=smoke` with `Origin: http://localhost:5173`, `Access-Control-Request-Method: PUT`, and `Access-Control-Request-Headers: content-type`
  - Backend file-byte/manual-uploader-route scan:
    `rg -n "UploadFile|\bFile\(|Form\(|multipart/form-data|files=|request\.body|request\.stream|StreamingResponse|/upload-bytes|/file-bytes|manual-uploader|manual_uploader" src\upload_control_plane -S`
  - Browser persistent-storage scan:
    `rg -n "localStorage|sessionStorage|indexedDB|caches\.|CacheStorage|document\.cookie" tools\manual-uploader\src -S`
  - Frontend fetch scan:
    `rg -n "fetch\(|XMLHttpRequest|axios|UploadFile|File\(|Form\(" tools\manual-uploader\src src\upload_control_plane -S`
- Results:
  - Focused pytest: passed, 4 tests.
  - `docker compose config --quiet`: passed.
  - `git diff --check`: passed.
  - `uv run ruff check`: passed. Ruff emitted cache write warnings in this worktree on one run, but returned success.
  - `uv run ruff format --check`: passed, 69 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 61 source files.
  - `npm ci`: passed, 52 packages installed, 0 vulnerabilities.
  - `npm run test`: passed, 2 files and 4 tests.
  - `npm run check`: passed.
  - `npm run build`: passed.
  - `uv run pytest`: 156 passed, 1 failed. The failure is an existing local PostgreSQL state issue: duplicate `permission_grants` row for `dataset.download` in `tests/api/test_project_authorization.py`, unrelated to the CORS repair.
  - API preflight smoke returned:
    - `OPTIONS_STATUS=200`
    - `access-control-allow-origin: http://localhost:5173`
    - `access-control-allow-methods: GET, POST, PATCH, DELETE, OPTIONS`
    - `access-control-allow-headers` included `authorization`, `content-type`, `idempotency-key`, and `x-request-id`
  - Initial bucket-level MinIO CORS attempt with `mc cors set` was rejected:
    - JSON file: `decoding xml: EOF`
    - XML file: `A header you provided implies functionality that is not implemented`
  - MinIO global CORS smoke with `MINIO_API_CORS_ALLOW_ORIGIN` returned:
    - `OPTIONS_STATUS=204`
    - `Access-Control-Allow-Origin: http://localhost:5173`
    - `Access-Control-Allow-Methods: PUT`
    - `Access-Control-Allow-Headers: content-type`
  - Backend file-byte/manual-uploader-route scan: no matches.
  - Browser persistent-storage scan: no matches.
  - Frontend fetch scan found only expected calls:
    - `tools\manual-uploader\src\controlPlaneClient.ts` public control-plane fetch.
    - `tools\manual-uploader\src\browserMultipartUploader.ts` direct presigned storage `PUT`.
    - `tools\manual-uploader\src\main.ts` file input handling.
- Commands not run and why:
  - Full browser file-picker upload was not rerun. The prior validation already proved the app renders and API/storage non-browser smoke works; this repair verified the exact API and MinIO preflight blockers without adding browser automation dependencies.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. No upload-byte route was added, and backend scan found no file-byte route markers.
- Clients receive no MinIO/S3 credentials:
  - Preserved. MinIO credentials remain in compose/backend/minio-init only.
- Complete uses object storage ListParts as authority:
  - Preserved. No completion logic changed.
- Authorization uses permission_grants:
  - Preserved. No auth or permission code path changed.
- Internal IDs remain UUIDs:
  - Preserved. No schema/domain ID changes.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go, or gateway files changed.
- Presigned URL persistence/redaction:
  - Preserved. No browser persistent-storage calls were found.

## Risks and Follow-up

- Remaining risks:
  - A follow-up Validation Agent should rerun the full real browser upload now that API and MinIO preflights are fixed.
  - MinIO community image does not support bucket-level `mc cors set`; production or AIStor deployments should use provider-supported bucket CORS where available.
  - `uv run pytest` is currently sensitive to dirty local PostgreSQL seed state; use a clean database or isolated test database for full-suite proof.
- Known gaps:
  - No Playwright/file-picker E2E test was added in this repair scope.
- Suggested next agent:
  - T07 Validation agent should rerun real browser upload from `http://localhost:5173`, including create task, presign, direct MinIO `PUT`, ack, reconcile, and complete.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T07 can return to Validation for a full browser smoke.
- If partial, reusable pieces:
  - Settings-driven API CORS, focused CORS tests, and MinIO global CORS compose config.
- If blocked, unblock condition:
  - Not blocked.
- If rejected, do not repeat:
  - Do not add manual-uploader-only backend routes or file-byte proxy endpoints. Browser failures should be fixed in API/storage CORS or signed-header configuration.
