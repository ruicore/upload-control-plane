# Handoff: T07 browser manual uploader

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T07-implementation-browser-uploader
Worktree: D:\upload-control-plane-T07-implementation-browser-uploader
Started: 2026-06-25 12:23 +08:00
Finished: 2026-06-25 12:39 +08:00

## Scope

- Intended scope:
  - Add `tools/manual-uploader` as a development-only Vite browser app.
  - Support manual API URL, API key, project ID, object metadata/name/content type, part size, concurrency, and file selection.
  - Use only public upload APIs for task creation, presign, optional ack, status, pause, resume, complete, and abort.
  - Upload file bytes directly from the browser to presigned object-storage URLs.
  - Redact presigned URL query strings from visible diagnostics.
  - Add root commands for running the tool.
- Explicitly out of scope:
  - Product dashboard/admin UI.
  - Project, dataset, device, permission, or storage-policy management UI.
  - Backend routes, backend service changes, or file-byte proxy endpoints.
  - MQTT, CLI, Go, or gateway work.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` sections Execution Rules and T07.
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`.
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1134-master-handoff-after-T06-lifecycle-accepted.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`.
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`.

## Changes

- Files changed:
  - `.gitignore`
  - `Makefile`
  - `README.md`
  - `scripts/dev.ps1`
  - `tools/manual-uploader/README.md`
  - `tools/manual-uploader/index.html`
  - `tools/manual-uploader/package.json`
  - `tools/manual-uploader/package-lock.json`
  - `tools/manual-uploader/tsconfig.json`
  - `tools/manual-uploader/vite.config.ts`
  - `tools/manual-uploader/src/browserMultipartUploader.ts`
  - `tools/manual-uploader/src/controlPlaneClient.ts`
  - `tools/manual-uploader/src/fileParts.ts`
  - `tools/manual-uploader/src/main.ts`
  - `tools/manual-uploader/src/redaction.ts`
  - `tools/manual-uploader/src/styles.css`
  - `tools/manual-uploader/src/types.ts`
  - `tools/manual-uploader/src/__tests__/fileParts.test.ts`
  - `tools/manual-uploader/src/__tests__/redaction.test.ts`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1239-T07-implementation-browser-uploader-accepted.md`
- Behavior changed:
  - Adds a Vite TypeScript browser tool running on `http://localhost:5173`.
  - Tool creates upload tasks through `POST /v1/projects/{project_id}/upload-tasks`.
  - Tool requests presigned part URLs through `POST /v1/uploads/{session_id}/parts/presign`.
  - Tool sends part bytes only via browser `fetch(..., { method: "PUT", body: file.slice(...) })` to presigned storage URLs.
  - Tool can ack uploaded parts, fetch status, reconcile parts, pause, resume, complete, and abort through existing T06 public APIs.
  - Tool keeps diagnostics and uploaded part hints in memory only; it does not call `localStorage`, `sessionStorage`, or `indexedDB`.
  - Diagnostics pass through redaction that strips query strings from presigned URLs.
  - `make manual-uploader` and `.\scripts\dev.ps1 manual-uploader` install frontend dependencies and start the dev server.
- Compatibility notes:
  - No backend source files were modified.
  - `node_modules/` is ignored at the repo root; Vite `dist/` was already ignored by the existing `dist/` rule.
  - The manual uploader expects the existing API CORS/storage CORS setup to allow local browser calls from `http://localhost:5173`.

## Verification

- Commands run:
  - `npm install`
  - `npm run test`
  - `npm run check`
  - `npm run build`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `git diff --check`
  - `rg` backend file-byte route marker scan.
  - `rg` backend manual-uploader shortcut marker scan.
  - `rg` browser persistent-storage marker scan.
- Results:
  - `npm install`: passed after rerun with longer timeout; 52 packages installed, 0 vulnerabilities.
  - `npm run test`: passed, 2 test files and 4 tests.
  - `npm run check`: passed.
  - `npm run build`: passed; Vite production bundle generated under ignored `tools/manual-uploader/dist`.
  - `uv run ruff check`: passed. Ruff reported cache write warnings for `.ruff_cache`, but returned success.
  - `uv run ruff format --check`: passed, 68 files already formatted.
  - `git diff --check`: passed.
  - Backend file-byte marker scan: `no backend file-byte route markers found`.
  - Backend manual-uploader shortcut scan: `no manual-uploader backend shortcut markers found`.
  - Browser persistent-storage scan: `no browser persistent storage calls found`.
  - Signed-query marker scan found only the redaction helper and fake redaction test fixtures.
- Commands not run and why:
  - Live browser/API/MinIO smoke was not run. It requires bringing up the full local API, migrations, seed data, and browser interaction; the implementation was verified by frontend build/tests and static backend shortcut scans in this handoff.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. No backend files were changed, and backend marker scan found no `UploadFile`, FastAPI `File(...)`, `Form(...)`, multipart form, request stream/body, or file-byte shortcut routes.
- Clients receive no MinIO/S3 credentials:
  - Preserved. The tool accepts only API URL/API key and uses presigned URLs returned by the public API.
- Complete uses object storage ListParts as authority:
  - Preserved. The tool calls the existing `POST /v1/uploads/{session_id}/complete`; no backend completion logic was changed.
- Authorization uses permission_grants:
  - Preserved. The tool calls existing authenticated public APIs; no backend authorization path was modified.
- Internal IDs remain UUIDs:
  - Preserved. No backend schema/domain changes.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go, or gateway files were added.
- Presigned URL persistence/redaction:
  - Preserved in the tool. It does not call browser persistent storage APIs, and visible diagnostics redact signed URL query strings.

## Risks and Follow-up

- Remaining risks:
  - A validation agent should run a real browser upload against local API/MinIO to verify CORS and signed-header behavior from `http://localhost:5173`.
  - The browser tool is intentionally simple and does not implement URL-expiry retry loops; a failed part can be uploaded again via fresh presign by rerunning Upload Missing Parts.
  - The tool stores the API key only in the password input while the page is open; operators should still treat browser dev tooling as local-only.
- Known gaps:
  - No automated browser E2E test was added.
  - No product UI polish beyond a compact dev verification surface.
- Suggested next agent:
  - T07 Validation agent should verify direct browser-to-MinIO multipart upload, CORS, no file bytes through FastAPI, and diagnostic redaction.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T07 validation can start from this branch.
- If partial, reusable pieces:
  - The Vite project, typed API client, part slicing helper, URL redaction helper, and root command wiring are reusable.
- If blocked, unblock condition:
  - Not blocked.
- If rejected, do not repeat:
  - Do not add manual-uploader-only backend routes or file-byte proxy endpoints to compensate for browser/API smoke failures. Fix CORS/config or frontend client behavior instead.
