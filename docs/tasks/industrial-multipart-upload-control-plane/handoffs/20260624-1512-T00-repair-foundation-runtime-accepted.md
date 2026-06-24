# Handoff: T00 Foundation runtime repair

Status: accepted
Agent type: Repair
Branch: codex/industrial-upload/T00-implementation-foundation-runtime
Worktree: D:\upload-control-plane
Started: 2026-06-24 15:04 +08:00
Finished: 2026-06-24 15:12 +08:00

## Scope

- Intended scope: repair T00 validation blockers for GNU Make availability and local host port conflicts.
- Explicitly out of scope: upload APIs, domain logic, database schema/migrations beyond the existing no-op T00 scaffold, MinIO multipart operations, killing unrelated local processes, and starting T01.
- PRD/task files read:
  - docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md
  - docs/tasks/industrial-multipart-upload-control-plane/README.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1458-T00-implementation-foundation-runtime-partial.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1503-T00-validation-foundation-runtime-partial.md
  - docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md
  - README.md
  - docker-compose.yml
  - Makefile
  - scripts/dev.ps1

## Changes

- Files changed:
  - Dockerfile
  - README.md
  - docker-compose.yml
  - docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md
  - docs/tasks/industrial-multipart-upload-control-plane/README.md
  - scripts/dev.ps1
  - src/upload_control_plane/config.py
  - tests/test_config.py
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1512-T00-repair-foundation-runtime-accepted.md
- Behavior changed:
  - Default host ports now avoid the occupied standard ports on this host:
    - API: `localhost:18080 -> api:8000`
    - PostgreSQL: `localhost:25432 -> postgres:5432`
    - MinIO S3 API: `localhost:19000 -> minio:9000`
    - MinIO Console: `localhost:19001 -> minio:9001`
  - Host ports are configurable with `API_HOST_PORT`, `POSTGRES_HOST_PORT`, `MINIO_HOST_PORT`, and `MINIO_CONSOLE_HOST_PORT`.
  - `S3_PUBLIC_ENDPOINT_URL` defaults to `http://localhost:19000` and remains overrideable.
  - `scripts/dev.ps1 dev-up` prints the active local URLs after compose starts.
  - Docker API and worker commands use `uv run --no-sync` so containers do not resync dev dependencies during startup.
- Compatibility notes:
  - Container-internal ports remain unchanged: API `8000`, Postgres `5432`, MinIO `9000/9001`.
  - Existing standard host ports `8000`, `9000`, `9001`, and `15432` were not freed or killed.

## Make Availability

- Existing `make.exe` was not found before repair via `Get-Command make` or common Git/MSYS paths.
- Command attempted: `choco install make -y`.
- Result:
  - Chocolatey returned exit code `1` because the shell was not elevated and it could not create `C:\ProgramData\chocolatey\.chocolatey\make.4.4.1`.
  - The package payload and shim were still installed enough for this environment: `C:\ProgramData\chocolatey\bin\make.exe`.
  - `make --version` returned GNU Make 4.4.1.
  - `make test` passed from PowerShell in this repository.
- No repo-local `make.cmd` wrapper was added.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `docker compose config --quiet`
  - `docker compose up --build -d`
  - `Invoke-RestMethod http://localhost:18080/healthz`
  - `Invoke-WebRequest http://localhost:19001 -UseBasicParsing`
  - `docker compose ps`
  - `docker compose logs --tail 60 api`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed.
  - `uv run ruff format --check`: passed, 10 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 8 source files.
  - `uv run pytest`: passed, 4 tests passed with one FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; ran ruff, format check, mypy, and pytest.
  - `docker compose config --quiet`: passed.
  - `docker compose up --build -d`: passed.
  - API smoke: `http://localhost:18080/healthz` returned `{"status":"ok","service":"upload-control-plane"}`.
  - MinIO Console smoke: `http://localhost:19001` returned HTTP 200 with `text/html`.
  - `docker compose ps`: api, worker, postgres, and minio were up; postgres and minio were healthy; published ports matched the new defaults.
  - `docker compose logs --tail 60 api`: uvicorn started on container port `8000` and logged `GET /healthz` 200.
  - `docker compose down`: passed and removed the compose containers/network.
- Commands not run and why:
  - None of the required verification commands were skipped.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload or file-byte endpoint was added.
- Clients receive no MinIO/S3 credentials: preserved. Only local service environment/settings were changed.
- Complete uses object storage ListParts as authority: not implemented in T00 and not contradicted.
- Authorization uses permission_grants: not implemented in T00 and not contradicted.
- Internal IDs remain UUIDs: no domain schema or IDs added.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or gateway code added.

## Risks and Follow-up

- Remaining risks:
  - Chocolatey package registration for make is incomplete due to non-elevated install, even though `make.exe` is currently on PATH and works.
  - Port `18000` was also occupied by an existing local uvicorn process, so API default was set to `18080` instead of the initially suggested `18000`.
  - `scripts/migrate.py` and `scripts/seed_dev.py` remain intentional no-ops until T02.
- Known gaps:
  - T00 still does not include upload APIs, domain schema, real migrations, MinIO multipart adapter, metrics, or lifecycle worker behavior.
- Suggested next agent:
  - Independent T00 Validation Agent should rerun the same required command list against this branch.

## Recovery Notes

- If accepted, next dependency unlocked: T01 Domain Kernel can begin after independent validation confirms the same evidence.
- If partial, reusable pieces: configurable local host ports, working GNU Make path, and Docker no-sync startup fix.
- If blocked, unblock condition: repair or reinstall GNU Make with administrator rights if `C:\ProgramData\chocolatey\bin\make.exe` disappears from PATH.
- If rejected, do not repeat: do not kill unrelated processes or change container-internal ports to avoid host conflicts.
