# Handoff: T00 Foundation runtime scaffold

Status: partial
Agent type: Implementation
Branch: codex/industrial-upload/T00-implementation-foundation-runtime
Worktree: D:\upload-control-plane
Started: 2026-06-24 14:32 +08:00
Finished: 2026-06-24 14:58 +08:00

## Scope

- Intended scope: T00 Foundation runtime scaffold only.
- Explicitly out of scope: upload APIs, database upload-domain migrations, SQLAlchemy domain schema, MinIO multipart operations, MQTT, Go uploader, edge gateway, and any endpoint accepting file bytes.
- PRD/task files read:
  - docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md
  - docs/tasks/industrial-multipart-upload-control-plane/README.md
  - docs/prd/industrial-multipart-upload-control-plane/00-executive-summary.md
  - docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md
  - docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md
  - docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md
  - docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md
  - docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md
  - README.md
  - pyproject.toml

## Changes

- Files changed:
  - Dockerfile
  - Makefile
  - README.md
  - docker-compose.yml
  - pyproject.toml
  - uv.lock
  - scripts/dev.ps1
  - scripts/migrate.py
  - scripts/seed_dev.py
  - src/upload_control_plane/config.py
  - src/upload_control_plane/main.py
  - src/upload_control_plane/worker/__init__.py
  - src/upload_control_plane/worker/main.py
  - tests/test_config.py
  - tests/test_health.py
- Behavior changed:
  - Added FastAPI app with `GET /healthz` returning `{"status":"ok","service":"upload-control-plane"}`.
  - Added Pydantic Settings configuration for T00/local runtime and PRD-listed storage/upload defaults.
  - Added Docker Compose services: `api`, `worker`, `postgres`, `minio`, and `minio-init`.
  - Exposed intended local ports: API `8000`, PostgreSQL `15432`, MinIO S3 `9000`, MinIO Console `9001`.
  - Added Makefile targets and equivalent Windows PowerShell script targets for `dev-up`, `migrate`, `seed-dev`, `test`, and `dev-down`.
  - Added no-op `migrate` and `seed-dev` scripts because upload-domain migrations and seed data are out of scope for T00.
  - Added health endpoint and settings tests.
- Compatibility notes:
  - `make` is not installed on this Windows host, so `scripts/dev.ps1` is provided as an equivalent local command surface.
  - The worker is a long-running scaffold only; lifecycle automation is intentionally not implemented in T00.

## Verification

- Commands run:
  - `uv lock`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `.\scripts\dev.ps1 test`
  - `docker --version`
  - `docker compose version`
  - `docker compose config --quiet`
  - `docker compose up --build -d`
  - `docker compose ps`
  - `Get-NetTCPConnection -LocalPort 8000`
  - `Get-NetTCPConnection -LocalPort 9000`
  - `Get-NetTCPConnection -LocalPort 9001`
  - local API smoke on alternate port: `python -m uvicorn upload_control_plane.main:app --host 127.0.0.1 --port 18000`, then `GET http://127.0.0.1:18000/healthz`
  - `Invoke-WebRequest http://localhost:9001`
  - `Invoke-WebRequest http://localhost:9000/minio/health/live`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 10 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 8 source files.
  - `uv run pytest`: passed, 4 tests passed with one FastAPI/Starlette TestClient deprecation warning.
  - `.\scripts\dev.ps1 test`: passed; it ran ruff, format check, mypy, and pytest successfully.
  - `docker compose config --quiet`: passed.
  - Docker is available: Docker 29.1.3, Compose v2.40.3-desktop.1.
  - Docker image build completed during `docker compose up --build -d`.
  - `docker compose up --build -d`: did not complete because `localhost:9000` is already allocated before this stack can start MinIO.
  - Port evidence: local ports `9000` and `9001` are already listened on by existing processes before this Compose stack starts. Port `8000` is also already listened on.
  - Alternate-port health smoke returned `{"status":"ok","service":"upload-control-plane"}` on `http://127.0.0.1:18000/healthz`.
  - Current existing `http://localhost:9001` responded `200 text/html`, and existing `http://localhost:9000/minio/health/live` responded `200`, but those endpoints are not attributed to this Compose stack because this stack could not bind those ports.
  - `docker compose down`: completed and removed this attempt's containers/network.
- Commands not run and why:
  - `make dev-up`: not run through `make` because this Windows host does not have the `make` executable.
  - `curl http://localhost:8000/healthz`: standard port `8000` is already bound by existing local processes; direct probe timed out against the existing listener.
  - MinIO Console confirmation for this stack at `http://localhost:9001`: blocked because port `9001` is already bound by an existing local service.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. T00 only adds `/healthz`; no file-byte endpoint exists.
- Clients receive no MinIO/S3 credentials: preserved. Credentials are present only in backend/Compose environment for local services; no client API returns them.
- Complete uses object storage ListParts as authority: not implemented in T00. No complete endpoint exists, so the constraint is not contradicted.
- Authorization uses permission_grants: not implemented in T00. No authorization shortcut or upload route was added, so the constraint is not contradicted.
- Internal IDs remain UUIDs: no domain IDs or schema introduced in T00.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or edge gateway code was added.
- Complete/ListParts not implemented in T00: confirmed.
- Authorization/permission_grants not implemented in T00 but not contradicted: confirmed.
- Internal IDs not introduced except no domain IDs yet: confirmed.

## Risks and Follow-up

- Remaining risks:
  - T00 cannot be marked fully accepted from this workspace because `make test` cannot execute without GNU Make, and required Compose ports are already occupied.
  - The compose stack still needs validation on a host or worktree where ports `8000`, `9000`, and `9001` are free.
  - `scripts/migrate.py` and `scripts/seed_dev.py` are intentional no-ops until T02; downstream agents should replace them when migrations and seed data exist.
- Known gaps:
  - No database schema, upload-domain migration, seed data, storage adapter, upload API, metrics endpoint, or lifecycle worker behavior exists in T00.
  - No production logging or observability stack exists yet.
- Suggested next agent:
  - T00 Validation Agent in an environment with GNU Make available and ports `8000`, `9000`, and `9001` free.

## Recovery Notes

- If accepted, next dependency unlocked: T01 Domain Kernel after independent validation of `make dev-up`, `make test`, `/healthz`, and MinIO Console.
- If partial, reusable pieces:
  - FastAPI app and settings scaffold.
  - Dockerfile and Docker Compose service definitions.
  - Makefile and Windows PowerShell equivalent scripts.
  - Health/settings tests and passing local quality gates.
- If blocked, unblock condition:
  - Install GNU Make or use the provided PowerShell equivalent.
  - Free local ports `8000`, `9000`, and `9001`, then rerun `make dev-up`, `curl http://localhost:8000/healthz`, and inspect `http://localhost:9001`.
- If rejected, do not repeat:
  - Do not add upload endpoints, file-byte proxy routes, domain schema, or MinIO multipart operations as part of T00.
