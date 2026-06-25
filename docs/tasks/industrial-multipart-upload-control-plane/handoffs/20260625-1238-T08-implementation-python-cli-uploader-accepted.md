# Handoff: T08 Python CLI uploader

Status: accepted
Agent type: Implementation
Branch: codex/industrial-upload/T08-implementation-python-cli-uploader
Worktree: D:\upload-control-plane-T08-implementation-python-cli-uploader
Started: 2026-06-25 11:52 +08:00
Finished: 2026-06-25 12:38 +08:00

## Scope

- Intended scope:
  - Implement `uploadctl upload`, `resume`, `status`, `pause`, `resume-session`, and `abort`.
  - Use existing public HTTP API contracts only.
  - Upload file parts directly to presigned object-storage URLs.
  - Persist a local manifest with project/task/object/dataset/session/file/part state and file metadata.
  - Keep presigned URLs out of durable manifest state.
  - Add package entry point, tests, and local usage documentation.
- Explicitly out of scope:
  - Backend file-byte routes.
  - MinIO/S3 credentials in the CLI.
  - Backend shortcuts or CLI-only APIs.
  - Go uploader, MQTT adapter, and product UI.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1134-master-handoff-after-T06-lifecycle-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`

## Changes

- Files changed:
  - `README.md`
  - `pyproject.toml`
  - `uv.lock`
  - `src/upload_control_plane/cli/__init__.py`
  - `src/upload_control_plane/cli/client.py`
  - `src/upload_control_plane/cli/file_ranges.py`
  - `src/upload_control_plane/cli/main.py`
  - `src/upload_control_plane/cli/manifest.py`
  - `src/upload_control_plane/cli/uploader.py`
  - `tests/cli/test_cli_commands.py`
  - `tests/cli/test_manifest.py`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1238-T08-implementation-python-cli-uploader-accepted.md`
- Behavior changed:
  - Added the `uploadctl` console script.
  - Added Typer command wiring for upload/resume/status/pause/resume-session/abort.
  - Added HTTP client wrapper for create task, status, presign, ack, parts reconcile, complete, pause, resume, and abort.
  - Added bounded-memory file range streaming for direct presigned `PUT`.
  - Added concurrent part upload with retry, signature-expiry re-presign handling, ack, reconcile, and complete.
  - Added durable manifest save/load with safety checks that reject presigned URL material.
  - Added README usage notes for the CLI.
- Compatibility notes:
  - `httpx` moved from dev dependency to runtime dependency because `uploadctl` uses it.
  - `typer` is a new runtime dependency for CLI command handling.
  - `--device-id` is treated as the external device code used in the PRD example; `--source-device-id` is available for the API UUID field.

## Verification

- Commands run:
  - `uv lock`
  - `uv run ruff check`
  - `uv run ruff format`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `git diff --check`
  - `uv run uploadctl --help`
  - `docker compose config --quiet`
  - `docker compose up --build -d`
  - `docker compose ps`
  - `docker compose logs --tail 80 api postgres minio minio-init`
  - `rg -n "presigned_url|presigned_urls|signed_url|signed_urls|X-Amz-Signature|X-Amz-Credential|uploadId|partNumber|\burl\b" src\upload_control_plane\cli tests\cli`
  - `rg -n "UploadFile|File\(|Form\(|bytes|read\(|multipart/form-data|request\.stream|request\.body|Body\(" src\upload_control_plane\api src\upload_control_plane\application`
  - `git diff --name-only -- src\upload_control_plane\api src\upload_control_plane\application`
- Results:
  - `uv lock`: passed; added Typer/Rich transitive dependencies.
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed after formatting three new files.
  - `uv run mypy src tests`: passed, `Success: no issues found in 68 source files`.
  - `uv run pytest`: passed, `133 passed, 28 skipped, 1 warning`.
  - `git diff --check`: passed.
  - `uv run uploadctl --help`: passed and listed all required commands.
  - `docker compose config --quiet`: passed.
  - `docker compose up --build -d`: timed out after 180s before containers were created.
  - `docker compose ps`: no containers running after timeout.
  - `docker compose logs --tail 80 api postgres minio minio-init`: no logs because no containers were created.
  - Manifest/redaction scan: presigned URL markers only appear in manifest safety constants, transient upload code, and redaction tests; durable manifest save rejects those markers.
  - Backend route scan: no backend API/application files changed; marker scan found only metadata/size fields from existing control-plane code, no `UploadFile`, `File(...)`, request body streaming, or multipart form routes.
- Commands not run and why:
  - End-to-end local MinIO/API upload smoke with `uploadctl`: not completed because compose startup timed out after 180s and left no running containers/logs. Validation agent should retry in a clean Docker environment.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. CLI streams part bytes only to presigned storage URLs with `httpx.put`; no backend API route was added or changed.
- Clients receive no MinIO/S3 credentials:
  - Preserved. CLI accepts API URL/key only and uses backend-issued presigned URLs.
- Complete uses object storage ListParts as authority:
  - Preserved. CLI calls the existing public complete endpoint; it does not implement completion or trust local ack as authoritative.
- Authorization uses permission_grants:
  - Preserved. CLI calls existing authorized public routes; no authorization code changed.
- Internal IDs remain UUIDs:
  - Preserved. No schema or backend ID changes.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go, or edge gateway code added.

## Risks and Follow-up

- Remaining risks:
  - Real local `uploadctl` upload/resume/pause smoke still needs to be run once Docker Compose starts reliably.
  - URL-expiry handling is implemented for storage `403` responses with expiry/signature-style bodies, but needs a failure-injection test against real MinIO or a controlled fake storage response.
  - Pause during an active noninteractive upload is represented by manifest flushing on interruption plus the explicit server-side `pause` command; no interactive background pause watcher was added.
- Known gaps:
  - Multi-file upload tasks are not implemented in this CLI slice; current `uploadctl upload` creates one object per invocation.
  - Per-part checksum calculation is not implemented; full-file SHA256 is optional through `--compute-sha256` or `--checksum-sha256`.
- Suggested next agent:
  - T08 validation agent should retry compose bring-up, migrate/seed, run a real small multipart `uploadctl upload`, interrupt/resume if practical, and inspect the manifest for presigned URL absence.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T08 validation can proceed from this branch.
  - T16 remains blocked until T08 validation is accepted and T14 is accepted.
- If partial, reusable pieces:
  - CLI package, manifest safety layer, Typer command surface, and tests are reusable.
- If blocked, unblock condition:
  - Docker Compose must start local API/PostgreSQL/MinIO services for full smoke validation.
- If rejected, do not repeat:
  - Do not add backend upload-byte routes or persist presigned URL strings to manifest to make smoke testing easier.
