# Handoff: T07 browser manual uploader revalidation after CORS repair

Status: partial
Agent type: Validation
Branch: codex/industrial-upload/T07-validation-browser-uploader-after-cors
Worktree: D:\upload-control-plane-T07-validation-browser-uploader-after-cors
Started: 2026-06-25 13:04 +08:00
Finished: 2026-06-25 13:20 +08:00

## Scope

- Intended scope:
  - Revalidate `codex/industrial-upload/T07-repair-browser-cors` at commit `93bb8bb85e518eb5b833ba95d3dac2fefeeb5e9b`.
  - Verify the previous API CORS blocker is resolved for `http://localhost:5173`.
  - Verify MinIO CORS allows browser-origin direct PUT to presigned URLs.
  - Re-run T07 frontend checks, backend quality gates, static route/storage scans, and live API/MinIO smoke where feasible.
  - Do not fix implementation issues.
- Explicitly out of scope:
  - Product or repair code changes.
  - Merging to `main` or pushing.
  - Adding browser automation dependencies or manual-uploader-only backend routes.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` execution rules and T07 section
  - `D:\upload-control-plane-T07-implementation-browser-uploader\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1239-T07-implementation-browser-uploader-accepted.md`
  - `D:\upload-control-plane-T07-validation-browser-uploader\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1254-T07-validation-browser-uploader-partial.md`
  - `D:\upload-control-plane-T07-repair-browser-cors\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1303-T07-repair-browser-cors-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1320-T07-validation-browser-uploader-after-cors-partial.md`
- Behavior changed:
  - None. Validation only.
- Compatibility notes:
  - No product source files were modified.
  - Local generated artifacts included `.venv`, caches, `tools/manual-uploader/node_modules`, and Vite `dist`; these are ignored/untracked.

## Verification

- Commands run:
  - `git worktree add -B codex/industrial-upload/T07-validation-browser-uploader-after-cors D:\upload-control-plane-T07-validation-browser-uploader-after-cors 93bb8bb85e518eb5b833ba95d3dac2fefeeb5e9b`
  - `npm ci`
  - `npm run test`
  - `npm run check`
  - `npm run build`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest tests/api/test_cors.py tests/test_config.py`
  - `docker compose config --quiet`
  - `git diff --check`
  - Backend file-byte/manual-uploader route scan:
    `rg -n "UploadFile|\bFile\(|Form\(|multipart/form-data|files=|request\.body|request\.stream|StreamingResponse|/upload-bytes|/file-bytes|manual-uploader|manual_uploader" src\upload_control_plane -S`
  - Browser persistent-storage scan:
    `rg -n "localStorage|sessionStorage|indexedDB|caches\.|CacheStorage|document\.cookie" tools\manual-uploader\src -S`
  - Frontend/backend fetch scan:
    `rg -n "fetch\(|XMLHttpRequest|axios|UploadFile|\bFile\(|Form\(" tools\manual-uploader\src src\upload_control_plane -S`
  - Isolated services:
    `docker compose -p upload-control-plane-t07-after-cors up -d postgres minio minio-init` with `POSTGRES_HOST_PORT=25447`, `MINIO_HOST_PORT=19127`, `MINIO_CONSOLE_HOST_PORT=19128`, `S3_PUBLIC_ENDPOINT_URL=http://localhost:19127`, `API_CORS_ALLOWED_ORIGINS=http://localhost:5173`, `MINIO_API_CORS_ALLOW_ORIGIN=http://localhost:5173,http://localhost:3000`
  - `uv run python scripts/migrate.py` against `postgresql+psycopg://upload:upload@localhost:25447/upload`
  - `uv run python scripts/seed_dev.py` against the same clean validation database and MinIO endpoint.
  - Uvicorn smoke with JSON-form env vars: `API_CORS_ALLOWED_ORIGINS=["http://localhost:5173"]`, API on `http://127.0.0.1:18127`
  - Vite dev server smoke on `http://127.0.0.1:5173`
  - In-app browser page load for `http://localhost:5173/`
  - Live CORS/API/storage smoke:
    - API preflight from `Origin: http://localhost:5173`.
    - Create upload task through public API.
    - Presign two parts through public API.
    - MinIO preflight for direct `PUT` to a presigned part URL.
    - Direct PUT of 5 MiB and 1 MiB parts to MinIO presigned URLs with `Origin: http://localhost:5173`.
    - Ack parts through public API.
    - Reconcile parts through public API.
    - Complete through public API.
  - MinIO object inspection:
    `docker run --rm --network upload-control-plane-t07-after-cors_default --entrypoint /bin/sh minio/mc:RELEASE.2025-08-13T08-35-41Z -c "mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null && mc ls --recursive local/robot-data | tail -20"`
  - CSV env parser probe:
    `API_CORS_ALLOWED_ORIGINS=http://localhost:5173; uv run python -c/from stdin Settings()`
  - Cleanup:
    `docker compose -p upload-control-plane-t07-after-cors down`
- Results:
  - `npm ci`: passed, 52 packages installed, 0 vulnerabilities.
  - `npm run test`: passed, 2 test files and 4 tests.
  - `npm run check`: passed.
  - `npm run build`: passed.
  - `uv run ruff check`: passed. Ruff emitted `.ruff_cache` access warnings but returned success.
  - `uv run ruff format --check`: passed, 69 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 61 source files.
  - `uv run pytest tests/api/test_cors.py tests/test_config.py`: passed, 4 tests with one Starlette/httpx deprecation warning.
  - `docker compose config --quiet`: passed.
  - `git diff --check`: passed.
  - Backend file-byte/manual-uploader route scan: no matches.
  - Browser persistent-storage scan: no matches.
  - Frontend/backend fetch scan found only expected frontend calls:
    - `tools\manual-uploader\src\controlPlaneClient.ts` uses public control-plane APIs.
    - `tools\manual-uploader\src\browserMultipartUploader.ts` uses direct presigned storage `PUT`.
  - Isolated Postgres, MinIO, and minio-init started successfully.
  - Migration and seed completed successfully. Seeded project ID `020500f8-920c-5a49-bf01-0eca416b8ddf`.
  - Vite page loaded in the in-app browser with title `Manual Upload Verification`.
  - Browser plugin page evaluation could not run a page-side upload because this runtime's supported evaluate scope does not expose `fetch`, and the plugin does not expose file-input upload control.
  - API preflight passed:
    - Status `200`
    - `access-control-allow-origin: http://localhost:5173`
    - `access-control-allow-methods: GET, POST, PATCH, DELETE, OPTIONS`
    - `access-control-allow-headers` included `authorization`, `content-type`, `idempotency-key`, and `x-request-id`.
  - MinIO preflight passed:
    - Status `204`
    - `access-control-allow-origin: http://localhost:5173`
    - `access-control-allow-methods: PUT`
    - `access-control-allow-headers: content-type`
  - Live multipart smoke passed:
    - Session `012ac72b-f846-4781-a047-53963bce4527`
    - Part count `2`
    - Presigned parts `2`
    - Ack uploaded part count `2`
    - Reconciled uploaded part count `2`
    - Complete status `COMPLETED`
    - Bucket `robot-data`
    - Object key `tenants/4f778e62-3eba-59c2-8dab-b51cb66e38e0/projects/020500f8-920c-5a49-bf01-0eca416b8ddf/datasets/d1c00f07-e2aa-402e-95aa-267fc5474842/2026/06/25/012ac72b-f846-4781-a047-53963bce4527/after-cors-validation-smoke.bin`
    - Complete response `object_size_bytes` was `null`; MinIO inspection confirmed the object exists at `6.0MiB`.
  - MinIO inspection passed:
    - `6.0MiB STANDARD .../after-cors-validation-smoke.bin`
  - CSV env parser probe failed:
    - `SettingsError`
    - `error parsing value for field "api_cors_allowed_origins" from source "EnvSettingsSource"`
- Commands not run and why:
  - Full manual file-picker UI upload was not completed. The in-app browser loaded the page, but its supported evaluate scope does not expose `fetch`, and it does not provide file chooser/file input automation. Validation therefore used CORS preflights plus a live public API/direct-MinIO multipart smoke.
  - `docker compose up -d api` was attempted but did not reach runtime because the image build failed while downloading/extracting `pydantic-core` due a network timeout. This was not used as the primary evidence for the runtime parsing issue.

## Findings

- `partial`: The original browser CORS blocker is resolved when the API runs with valid list settings.
  - Evidence: API preflight from `http://localhost:5173` returned status `200` and the required allow-origin/method/header values.
  - Evidence: MinIO preflight to a presigned part URL returned status `204`, allowed origin `http://localhost:5173`, and allowed method `PUT`.
  - Evidence: Live create -> presign -> direct MinIO PUT -> ack -> reconcile -> complete smoke reached `COMPLETED`.
- `partial`: Docker Compose/runtime env configuration is still not acceptable as-is.
  - Evidence: `docker-compose.yml` sets `API_CORS_ALLOWED_ORIGINS: ${API_CORS_ALLOWED_ORIGINS:-http://localhost:5173}`, but `Settings()` with `API_CORS_ALLOWED_ORIGINS=http://localhost:5173` raises `SettingsError` because Pydantic Settings JSON-decodes list env fields before the CSV validator handles them.
  - Impact: the compose API service can fail at startup when it reaches runtime with the current default CORS env values, despite `docker compose config --quiet` passing and focused tests passing.
  - Narrow likely fix: use JSON-list values in compose/env docs or customize Pydantic Settings env parsing for comma-separated list values. Validation agent did not apply a fix.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. Backend scan found no file-byte route markers. Live smoke sent bytes directly to MinIO presigned URLs.
- Clients receive no MinIO/S3 credentials:
  - Preserved. Frontend uses API key plus presigned URLs only; MinIO credentials stayed in backend/compose/minio-init environment.
- Complete uses object storage ListParts as authority:
  - Preserved. Live smoke reconciled storage parts and complete returned `COMPLETED`; T07 did not change completion logic.
- Authorization uses permission_grants:
  - Preserved. Live smoke used the seeded API key and public authenticated APIs; no bypass route exists.
- Internal IDs remain UUIDs:
  - Preserved. T07/CORS repair did not change schema or ID strategy.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go uploader, or gateway files are involved.
- Presigned URL persistence/redaction:
  - Preserved by static scan. No browser persistent-storage calls were found under `tools/manual-uploader/src`.

## Risks and Follow-up

- Remaining risks:
  - Compose/runtime env list parsing must be repaired before accepting the CORS repair as local-compose-ready.
  - Full manual file-picker browser E2E remains unproven due current browser automation limitations, although CORS preflight and multipart smoke passed.
  - Complete response still reports `object_size_bytes: null` even though MinIO contains the completed 6.0 MiB object. This appears pre-existing/runtime-specific, not T07-specific.
- Known gaps:
  - No product source fix was made.
- Suggested next agent:
  - Repair agent should fix settings/compose list env parsing for API CORS values, then re-run this validation.

## Recovery Notes

- If accepted, next dependency unlocked:
  - Not accepted.
- If partial, reusable pieces:
  - FastAPI CORS behavior, MinIO CORS behavior, and the manual uploader's public API/direct PUT flow are validated when settings load successfully.
- If blocked, unblock condition:
  - Not blocked.
- If rejected, do not repeat:
  - Do not add manual-uploader-only backend routes or file-byte proxy endpoints. Fix the shared settings/compose CORS configuration instead.
