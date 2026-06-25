# Handoff: T07 CORS settings env repair

Status: accepted
Agent type: Repair
Branch: codex/industrial-upload/T07-repair-cors-settings-env
Worktree: D:\upload-control-plane-T07-repair-cors-settings-env
Started: 2026-06-25 13:20 +08:00
Finished: 2026-06-25 13:21 +08:00

## Scope

- Intended scope:
  - Repair the T07 compose/runtime blocker where `API_CORS_ALLOWED_ORIGINS=http://localhost:5173` failed before `Settings()` could run the CSV list validator.
  - Keep the existing API CORS behavior for `http://localhost:5173`.
  - Keep MinIO CORS support unchanged.
  - Add focused test coverage for the compose-style `Settings()` environment value.
- Explicitly out of scope:
  - Backend upload-byte routes or file-byte proxying.
  - Manual-uploader-only backend shortcuts.
  - Product UI, dashboard work, or frontend feature expansion.
  - Relaxing authentication or `permission_grants`.
  - Merging to `main` or pushing.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` execution rules and T07 section
  - `D:\upload-control-plane-T07-repair-browser-cors\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1303-T07-repair-browser-cors-accepted.md`
  - `D:\upload-control-plane-T07-validation-browser-uploader-after-cors\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1320-T07-validation-browser-uploader-after-cors-partial.md`

## Changes

- Files changed:
  - `README.md`
  - `docker-compose.yml`
  - `tests/test_config.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1321-T07-repair-cors-settings-env-accepted.md`
- Behavior changed:
  - Docker Compose now supplies API CORS list settings as JSON array strings, which `pydantic-settings` can parse for `list[str]` fields at startup.
  - API CORS defaults still allow `http://localhost:5173` with `Authorization`, `Content-Type`, `Idempotency-Key`, and `X-Request-ID`.
  - MinIO `MINIO_API_CORS_ALLOW_ORIGIN` remains CSV and unchanged because it is consumed by MinIO, not by `Settings()`.
- Compatibility notes:
  - Existing model-level CSV parsing remains available for direct `Settings.model_validate(...)` usage.
  - Runtime environment overrides for API CORS list settings should use JSON arrays.

## Verification

- Commands run:
  - `uv run pytest tests/api/test_cors.py tests/test_config.py`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `docker compose config --quiet`
  - Direct `Settings()` env smoke with:
    - `API_CORS_ALLOWED_ORIGINS=["http://localhost:5173"]`
    - `API_CORS_ALLOWED_METHODS=["GET","POST","PATCH","DELETE","OPTIONS"]`
    - `API_CORS_ALLOWED_HEADERS=["authorization","content-type","idempotency-key","x-request-id"]`
    - `API_CORS_EXPOSE_HEADERS=["x-request-id"]`
  - `git diff --check`
  - Backend file-byte/manual-uploader-route scan:
    `rg -n "UploadFile|\bFile\(|Form\(|multipart/form-data|files=|request\.body|request\.stream|StreamingResponse|/upload-bytes|/file-bytes|manual-uploader|manual_uploader" src\upload_control_plane -S`
  - Browser persistent-storage scan:
    `rg -n "localStorage|sessionStorage|indexedDB|caches\.|CacheStorage|document\.cookie" tools\manual-uploader\src -S`
- Results:
  - Focused pytest: passed, 5 tests with one Starlette/httpx deprecation warning.
  - `uv run ruff check`: passed. Ruff emitted cache write warnings for `.ruff_cache` access, but returned success.
  - `uv run ruff format --check`: passed, 69 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 61 source files.
  - `docker compose config --quiet`: passed.
  - Direct `Settings()` env smoke: passed and printed the expected API CORS origins, methods, headers, and exposed headers.
  - `git diff --check`: passed.
  - Backend file-byte/manual-uploader-route scan: no matches.
  - Browser persistent-storage scan: no matches.
- Commands not run and why:
  - Full compose `api` container startup was not rerun because the validation blocker was the settings parse path and the requested `Settings()` smoke plus `docker compose config --quiet` covered that path without network-sensitive image rebuilds.
  - Full browser file-picker E2E was not rerun; prior validation already identified the remaining blocker as settings/env parsing, and this repair did not change uploader behavior.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. No backend route code changed, and the backend file-byte/manual-uploader-route scan found no matches.
- Clients receive no MinIO/S3 credentials:
  - Preserved. No frontend or credential handling changed.
- Complete uses object storage ListParts as authority:
  - Preserved. No completion logic changed.
- Authorization uses permission_grants:
  - Preserved. No auth or permission code path changed.
- Internal IDs remain UUIDs:
  - Preserved. No schema/domain ID changes.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go, or gateway files changed.
- Presigned URL persistence/redaction:
  - Preserved. No browser storage calls were found under `tools/manual-uploader/src`.

## Risks and Follow-up

- Remaining risks:
  - A follow-up Validation Agent should rerun compose/runtime API startup and the full T07 browser upload smoke on this repair branch.
  - Operators overriding API CORS env vars must use JSON array strings for these `list[str]` settings.
- Known gaps:
  - No pydantic-settings custom source was added for arbitrary CSV env parsing; this repair intentionally chose the narrower compose JSON fix allowed by the validation handoff.
- Suggested next agent:
  - T07 Validation agent should revalidate local compose/runtime startup and browser/manual uploader flow from `http://localhost:5173`.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T07 can return to Validation for compose runtime startup and full browser smoke.
- If partial, reusable pieces:
  - JSON compose API CORS values, focused settings env test, and README override guidance.
- If blocked, unblock condition:
  - Not blocked.
- If rejected, do not repeat:
  - Do not add manual-uploader-only backend routes or file-byte proxy endpoints. Settings startup failures should be fixed at settings/compose configuration boundaries.
