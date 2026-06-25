# Handoff: T07 browser manual uploader validation

Status: partial
Agent type: Validation
Branch: codex/industrial-upload/T07-validation-browser-uploader
Worktree: D:\upload-control-plane-T07-validation-browser-uploader
Started: 2026-06-25 12:40 +08:00
Finished: 2026-06-25 12:54 +08:00

## Scope

- Intended scope:
  - Independently validate `codex/industrial-upload/T07-implementation-browser-uploader` at commit `41e16db`.
  - Verify `tools/manual-uploader` is a development-only Vite browser app.
  - Verify the tool uses existing public upload APIs and sends file bytes directly to presigned storage URLs.
  - Verify no manual-uploader-only backend routes or file-byte proxy endpoints were added.
  - Verify presigned URL query strings are redacted from visible diagnostics and not persisted to browser storage.
  - Verify controls exist for create, presign/upload, status/parts, pause, resume, complete, and abort.
  - Prefer a local API/MinIO/browser smoke where practical.
- Explicitly out of scope:
  - Fixing implementation issues.
  - Adding backend CORS, storage CORS, routes, or product UI behavior.
  - Merging to `main` or pushing.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` execution rules and T07 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1239-T07-implementation-browser-uploader-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1254-T07-validation-browser-uploader-partial.md`
- Behavior changed:
  - None. Validation only.
- Compatibility notes:
  - No implementation source was modified.
  - `node_modules`, Vite `dist`, `.venv`, `.ruff_cache`, and Python `__pycache__` were generated locally and left ignored/untracked.

## Verification

- Commands run:
  - `git worktree add -b codex/industrial-upload/T07-validation-browser-uploader D:\upload-control-plane-T07-validation-browser-uploader 41e16db`
  - `npm ci`
  - `npm run test`
  - `npm run check`
  - `npm run build`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `git diff --check`
  - `docker compose config --quiet`
  - `rg -n "UploadFile|\bFile\(|Form\(|multipart/form-data|files=|request\.body|request\.stream|StreamingResponse|/upload-bytes|/file-bytes|manual-uploader|manual_uploader" src\upload_control_plane -S`
  - `rg -n "localStorage|sessionStorage|indexedDB|caches\.|CacheStorage|document\.cookie" tools\manual-uploader\src -S`
  - `rg -n "fetch\(|XMLHttpRequest|axios|UploadFile|File\(|Form\(" tools\manual-uploader\src src\upload_control_plane -S`
  - Browser plugin DOM smoke against `http://127.0.0.1:5173/`
  - `docker compose up -d postgres minio minio-init` with validation-only ports: `POSTGRES_HOST_PORT=25437`, `MINIO_HOST_PORT=19107`, `MINIO_CONSOLE_HOST_PORT=19108`, `S3_PUBLIC_ENDPOINT_URL=http://localhost:19107`
  - `uv run python scripts/migrate.py` with `DATABASE_URL=postgresql+psycopg://upload:upload@localhost:25437/upload`
  - `uv run python scripts/seed_dev.py` with the same validation DB and MinIO settings
  - `uv run uvicorn upload_control_plane.main:app --host 127.0.0.1 --port 18107`
  - `npm run dev -- --host 127.0.0.1 --port 5173`
  - API/storage smoke: create upload task, presign two parts, `PUT` two byte ranges directly to MinIO presigned URLs, ack parts, reconcile parts, complete upload
  - API CORS preflight: `OPTIONS /v1/projects/{project_id}/upload-tasks` with `Origin: http://localhost:5173`
  - `docker run --rm --network upload-control-plane-t07-validation-browser-uploader_default --entrypoint /bin/sh minio/mc:RELEASE.2025-08-13T08-35-41Z -c "mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null && mc ls --recursive local/robot-data | tail -20"`
- Results:
  - `npm ci`: passed, 52 packages installed, 0 vulnerabilities.
  - `npm run test`: passed, 2 test files and 4 tests.
  - `npm run check`: passed.
  - `npm run build`: passed.
  - `uv run ruff check`: passed. Ruff emitted `.ruff_cache` write warnings due local access denied, but returned success.
  - `uv run ruff format --check`: passed, 68 files already formatted.
  - `git diff --check`: passed.
  - `docker compose config --quiet`: passed.
  - Backend route/file-byte scan: no matches in `src\upload_control_plane`.
  - Browser persistent-storage scan: no matches in `tools\manual-uploader\src`.
  - Fetch scan: only expected frontend calls were found:
    - `tools\manual-uploader\src\controlPlaneClient.ts` calls public control-plane APIs.
    - `tools\manual-uploader\src\browserMultipartUploader.ts` calls `fetch(part.url, { method: "PUT", body: file.slice(...) })` to the presigned storage URL.
  - Browser plugin DOM smoke: page loaded at `http://127.0.0.1:5173/`, title was `Manual Upload Verification`, main heading was present, all controls were present, and no console warn/error logs were reported.
  - Browser plugin screenshot capture timed out. DOM and console checks still succeeded.
  - API/storage smoke passed with public contracts and direct-to-MinIO bytes:
    - Session `d51c01cf-056f-4cee-a254-4e15e2fa3b41`
    - Presigned parts: 2
    - Ack uploaded part count: 2
    - Reconciled uploaded part count: 2
    - Complete status: `COMPLETED`
    - Bucket: `robot-data`
    - Object key: `tenants/4f778e62-3eba-59c2-8dab-b51cb66e38e0/projects/020500f8-920c-5a49-bf01-0eca416b8ddf/datasets/292ac157-34fa-4840-9004-b09d8e854b03/2026/06/25/d51c01cf-056f-4cee-a254-4e15e2fa3b41/validation-browser-uploader-3.bin`
  - MinIO inspection showed the completed object exists at 6.0 MiB under the expected key namespace.
  - API CORS preflight failed:
    - `OPTIONS http://127.0.0.1:18107/v1/projects/020500f8-920c-5a49-bf01-0eca416b8ddf/upload-tasks`
    - `Origin: http://localhost:5173`
    - `Access-Control-Request-Method: POST`
    - `Access-Control-Request-Headers: authorization,content-type,idempotency-key`
    - Response: HTTP 405 `request.method_not_allowed`
    - `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, and `Access-Control-Allow-Headers` were absent.
- Commands not run and why:
  - Full browser file-input upload to completion was not completed. The in-app Browser plugin does not expose a file chooser/file input API, and the ordinary Playwright package was not available as a stable project dependency without adding/downloading tooling. More importantly, API CORS preflight already proves a real browser at `http://localhost:5173` cannot call the FastAPI upload-task endpoint in the current local stack.

## Findings

- `partial`: T07 implementation is not acceptable as a fully validated browser uploader yet because the current local API stack rejects browser CORS preflight from `http://localhost:5173`.
  - Evidence: `OPTIONS /v1/projects/{project_id}/upload-tasks` with `Origin: http://localhost:5173` returned HTTP 405 and no `Access-Control-Allow-*` headers.
  - User impact: the Vite app can render, but a real browser cannot create an upload task against the local API origin, so the required browser CORS smoke cannot pass.
  - Likely owner: upstream/local API runtime configuration, not a manual-uploader-only route. `src\upload_control_plane\main.py` does not configure CORS middleware.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved by T07 implementation. Backend scan found no file-byte route markers. The successful smoke uploaded bytes directly to MinIO presigned URLs, not to FastAPI.
- Clients receive no MinIO/S3 credentials:
  - Preserved. The browser tool accepts API URL/API key and consumes presigned URLs only; no MinIO/S3 access key or secret appears in the tool.
- Complete uses object storage ListParts as authority:
  - Preserved by T07 implementation. The tool calls the existing public complete endpoint. The smoke reconciled storage parts and completed through the backend.
- Authorization uses permission_grants:
  - Preserved by T07 implementation. The tool calls existing authenticated public APIs and does not add authorization logic or bypasses.
- Internal IDs remain UUIDs:
  - Preserved. T07 does not alter schema/domain identifiers.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go uploader, or gateway files were added.
- Presigned URL persistence/redaction:
  - Preserved in static validation. No `localStorage`, `sessionStorage`, `indexedDB`, Cache Storage, or cookie writes were found under `tools\manual-uploader\src`.
  - Redaction helper and tests strip query strings for AWS/MinIO-style presigned URL diagnostics.
- Browser direct upload CORS:
  - Not satisfied in the current runnable stack. API preflight from `http://localhost:5173` fails before the browser can create a task.

## Risks and Follow-up

- Remaining risks:
  - After API CORS is configured, storage bucket CORS may still need validation/configuration for `PUT` and exposed `ETag`. Current `minio-init` only creates the bucket; it does not configure bucket CORS.
  - Browser plugin screenshot capture timed out during validation, so visual proof is DOM/console-based rather than screenshot-based.
  - The smoke observed `complete_status: COMPLETED`, but `object_size_bytes` in the complete response was `null`. This appears to be existing runtime API behavior, not T07-specific, because MinIO inspection confirmed the 6.0 MiB final object exists.
- Known gaps:
  - No full browser file-input E2E reached completion due CORS and automation-tool file chooser limitations.
- Suggested next agent:
  - Repair or upstream validation agent should add/validate local API CORS for `http://localhost:5173` and MinIO bucket CORS for browser `PUT`/`ETag`, then rerun T07 browser validation.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Not accepted.
- If partial, reusable pieces:
  - `tools/manual-uploader` Vite app, typed public API client, browser direct PUT implementation, controls, redaction helper, and build/test setup are reusable.
  - Public API + direct-to-MinIO smoke is proven independently of browser CORS.
- If blocked, unblock condition:
  - Configure API CORS for the manual uploader origin and verify MinIO bucket CORS. Then rerun a real browser upload from `http://localhost:5173`.
- If rejected, do not repeat:
  - Do not add manual-uploader-only backend routes or file-byte proxy endpoints to work around CORS. The fix should be shared API/storage CORS configuration, not a backend data-plane path.
