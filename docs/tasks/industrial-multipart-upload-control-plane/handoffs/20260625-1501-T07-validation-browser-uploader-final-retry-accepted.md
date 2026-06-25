# Handoff: T07 browser uploader final retry validation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T07-validation-browser-uploader-final-retry
Worktree: D:\upload-control-plane-T07-validation-browser-uploader-final-retry
Started: 2026-06-25 14:49 +08:00
Finished: 2026-06-25 15:01 +08:00

## Scope

- Intended scope:
  - Final validation of `codex/industrial-upload/T07-repair-cors-settings-env` at commit `4b90e79`.
  - Re-run T07 frontend checks, backend quality gates, CORS/config checks, hard scans, and live public API/direct-MinIO upload smoke.
  - Verify the compose-style API CORS JSON-array environment values load through `Settings()`.
  - Verify browser-origin API preflight from `http://localhost:5173`.
  - Verify browser-origin MinIO preflight for direct presigned `PUT`.
  - Verify live upload completion reaches `COMPLETED` while file bytes go to the presigned MinIO URL, not FastAPI.
- Explicitly out of scope:
  - Product source or frontend repair changes.
  - Merging to `main` or pushing.
  - Adding manual-uploader-only backend routes or file-byte proxy endpoints.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T07 section
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`
  - `D:\upload-control-plane\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1323-master-handoff-after-T08-T09-accepted-T07-partial.md`
  - Prior T07 implementation, validation, repair, revalidation, and repair handoffs listed in that master handoff.

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1501-T07-validation-browser-uploader-final-retry-accepted.md`
- Behavior changed:
  - None. Validation-only handoff.
- Compatibility notes:
  - No functional source code was modified.
  - Local generated artifacts from validation included `.venv`, frontend `node_modules`, frontend `dist`, caches, and compose volumes/containers. The compose stack was shut down after validation.

## Verification

- Commands run:
  - `git worktree add -b codex/industrial-upload/T07-validation-browser-uploader-final-retry D:\upload-control-plane-T07-validation-browser-uploader-final-retry codex/industrial-upload/T07-repair-cors-settings-env`
  - `npm ci` in `tools/manual-uploader`
  - `npm run test` in `tools/manual-uploader`
  - `npm run check` in `tools/manual-uploader`
  - `npm run build` in `tools/manual-uploader`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest tests/api/test_cors.py tests/test_config.py`
  - `docker compose config --quiet`
  - Direct `Settings()` env smoke with JSON-array API CORS environment values:
    - `API_CORS_ALLOWED_ORIGINS=["http://localhost:5173"]`
    - `API_CORS_ALLOWED_METHODS=["GET","POST","PATCH","DELETE","OPTIONS"]`
    - `API_CORS_ALLOWED_HEADERS=["authorization","content-type","idempotency-key","x-request-id"]`
    - `API_CORS_EXPOSE_HEADERS=["x-request-id"]`
  - Backend file-byte/manual-uploader route scan:
    `rg -n "UploadFile|\bFile\(|Form\(|multipart/form-data|files=|request\.body|request\.stream|StreamingResponse|/upload-bytes|/file-bytes|manual-uploader|manual_uploader" src\upload_control_plane -S`
  - Browser persistent presigned URL/storage scan:
    `rg -n "localStorage|sessionStorage|indexedDB|caches\.|CacheStorage|document\.cookie|presigned.*(setItem|put|add|persist|save)|setItem\(.*url|setItem\(.*URL" tools\manual-uploader\src -S`
  - `docker compose -p upload-control-plane-t07-final-retry up -d postgres minio minio-init` with isolated ports:
    - `POSTGRES_HOST_PORT=25457`
    - `MINIO_HOST_PORT=19157`
    - `MINIO_CONSOLE_HOST_PORT=19158`
    - `S3_PUBLIC_ENDPOINT_URL=http://localhost:19157`
    - `API_CORS_ALLOWED_ORIGINS=["http://localhost:5173"]`
    - `MINIO_API_CORS_ALLOW_ORIGIN=http://localhost:5173,http://localhost:3000`
  - `uv run python scripts/migrate.py`
  - `uv run python scripts/seed_dev.py`
  - Temporary `uvicorn upload_control_plane.main:app` on `http://127.0.0.1:18157`
  - API preflight:
    `OPTIONS /v1/projects/020500f8-920c-5a49-bf01-0eca416b8ddf/upload-tasks` from `Origin: http://localhost:5173`
  - Live upload smoke:
    - Create upload task through public API.
    - Presign two parts through public API.
    - MinIO preflight to first presigned URL from `Origin: http://localhost:5173`.
    - Direct `PUT` two file byte ranges to presigned MinIO URLs.
    - Ack parts through public API.
    - Reconcile parts through public API with `source=storage`.
    - Complete through public API.
    - Read final session status.
  - MinIO object inspection:
    `docker run --rm --network upload-control-plane-t07-final-retry_default --entrypoint /bin/sh minio/mc:RELEASE.2025-08-13T08-35-41Z -c "mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null && mc ls --recursive local/robot-data | tail -20 && mc stat local/robot-data/.../t07-final-retry-smoke.bin"`
  - `docker compose -p upload-control-plane-t07-final-retry down`
  - `git diff --check`
- Results:
  - `npm ci`: passed, 52 packages installed, 0 vulnerabilities.
  - `npm run test`: passed, 2 test files and 4 tests.
  - `npm run check`: passed.
  - `npm run build`: passed, Vite built `dist` successfully.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 69 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 61 source files.
  - `uv run pytest tests/api/test_cors.py tests/test_config.py`: passed, 5 tests with one Starlette/httpx deprecation warning.
  - `docker compose config --quiet`: passed.
  - Direct `Settings()` env smoke: passed and printed expected origins, methods, headers, and exposed headers.
  - Backend file-byte/manual-uploader route scan: no matches.
  - Browser persistent presigned URL/storage scan: no matches.
  - Migration: passed through Alembic head `20260624_0005`.
  - Seed: passed, deterministic dev project `020500f8-920c-5a49-bf01-0eca416b8ddf`, 14 permission grants.
  - API preflight passed:
    - Status `200`
    - `access-control-allow-origin: http://localhost:5173`
    - `access-control-allow-methods: GET, POST, PATCH, DELETE, OPTIONS`
    - `access-control-allow-headers` included `authorization`, `content-type`, `idempotency-key`, and `x-request-id`.
  - MinIO preflight passed:
    - Status `204`
    - `access-control-allow-origin: http://localhost:5173`
    - `access-control-allow-methods: PUT`
  - Live upload smoke passed:
    - Session `7f14f59a-8406-4e0c-8b45-7c0ff0fbb605`
    - Part count `2`
    - Presigned parts `2`
    - Direct PUT hosts: `localhost:19157`
    - API host: `127.0.0.1:18157`
    - Ack uploaded part count `2`
    - Reconciled uploaded part count `2`
    - Complete status `COMPLETED`
    - Status endpoint status `COMPLETED`
    - Bucket `robot-data`
    - Object key `tenants/4f778e62-3eba-59c2-8dab-b51cb66e38e0/projects/020500f8-920c-5a49-bf01-0eca416b8ddf/datasets/1d145713-450b-4f07-8c8a-80e603c48be3/2026/06/25/7f14f59a-8406-4e0c-8b45-7c0ff0fbb605/t07-final-retry-smoke.bin`
    - Complete response ETag present.
  - MinIO object inspection passed:
    - `6.0MiB STANDARD .../t07-final-retry-smoke.bin`
    - `mc stat` size `6.0 MiB`
    - Multipart ETag `87ba9c9d2e69480fe31b834308ef08dc-2`
    - Object metadata included session, project, dataset, task, object, and tenant IDs.
  - `docker compose -p upload-control-plane-t07-final-retry down`: passed and removed validation containers/network.
  - `git diff --check`: passed.
- Commands not run and why:
  - Full file-picker browser automation was not run. The required browser-origin behavior was validated with API and MinIO CORS preflights from `http://localhost:5173` plus a live public API/direct-presigned-MinIO multipart smoke. This matches the previous validation approach and avoids adding tooling or changing product code.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Passed. Static backend scan found no file-byte route markers or manual-uploader backend shortcuts. The live smoke sent file bytes only to presigned URLs hosted at `localhost:19157`, while FastAPI ran at `127.0.0.1:18157` and handled only JSON control-plane calls.
- Clients receive no MinIO/S3 credentials:
  - Passed. The manual uploader and live smoke used the seeded API key plus presigned URLs. MinIO credentials were only used by backend/storage setup and `mc` inspection.
- Complete uses object storage ListParts as authority:
  - Passed through the existing T06 complete path. The smoke reconciled storage parts before complete, complete returned `COMPLETED`, and MinIO inspection confirmed the final object.
- Authorization uses permission_grants:
  - Passed for the validation path. The seeded API key used permission grants for upload creation and runtime actions; no bypass or manual-uploader-only route exists.
- Internal IDs remain UUIDs:
  - Passed. T07 validation introduced no schema/domain changes, and observed project/session/dataset/object IDs are UUIDs.
- MQTT/Go/edge remain optional and dependency-gated:
  - Passed. No MQTT, Go uploader, or gateway code was involved.
- Presigned URL persistence/redaction:
  - Passed. Static scan found no `localStorage`, `sessionStorage`, `indexedDB`, Cache Storage, cookie persistence, or presigned URL storage patterns under `tools/manual-uploader/src`.

## Risks and Follow-up

- Remaining risks:
  - Full browser file-picker automation remains unproven because no browser automation dependency/control was added in validation scope.
  - Complete response still reports `object_size_bytes: null`; MinIO inspection confirmed the completed 6.0 MiB object. This is existing runtime response behavior, not T07-specific.
- Known gaps:
  - None blocking T07 acceptance.
- Suggested next agent:
  - Merge agent can merge T07 after Master review, expecting conflicts because current `main` has T08/T09 work not present on the T07 source branch.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T07 can proceed to Master review and then Merge Agent.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not blocked.
- If rejected, do not repeat:
  - Not rejected. Continue to avoid backend file-byte routes, manual-uploader-only routes, and presigned URL persistence.
