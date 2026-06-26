# Handoff: Python-first Final Portfolio Readiness

Status: accepted
Master agent: Codex
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-26 10:54 Asia/Shanghai
Finished: 2026-06-26 11:07 Asia/Shanghai

## Scope

- Read the previous next-master handoff:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1054-next-master-remaining-work-and-worktree-archive.md`
- Coordinate a medium-reasoning validation subagent for final static readiness.
- Complete the Python-first final portfolio readiness check for T00-T14.
- Do not implement optional T15 MQTT, T16 Go uploader, or T17 Go gateway unless they become explicitly requested scope.
- Write this handoff for the next master.

## Current Decision

The Python-first implementation is portfolio-ready for the PRD/T00-T14 scope.

T15/T16/T17 remain optional, dependency-gated work:

- T15 optional MQTT adapter: not implemented.
- T16 optional Go uploader: not implemented.
- T17 optional Go edge/control gateway: not implemented.

These optional items are not blockers for Python-first readiness because the active implementation already preserves the core PRD hard constraints:

- Backend receives no file bytes.
- Clients receive no MinIO/S3 credentials.
- Multipart completion uses object storage as the uploaded-parts authority.
- Presigned URL query strings are not persisted to manifests, logs, traces, audit, or outbox payloads.
- Authorization is permission-grant based.

## Subagent Result

Validation subagent handoff:

- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260626-1101-final-readiness-static-validation-accepted.md`

Subagent status: accepted.

Evidence summary:

- Static scan found no backend/MQTT file-byte proxy path.
- Static scan found no client-facing MinIO/S3 credential exposure.
- Static scan found no accepted-risk presigned URL persistence/logging path.
- `uv run ruff check src tests`: passed.
- `uv run ruff format --check src tests`: passed.
- `uv run mypy src tests`: passed.
- `uv run pytest`: passed, `224 passed, 1 warning`.
- The subagent flagged `README.md` repository status as stale; this master corrected it.

## Runtime Readiness Evidence

An isolated Docker Compose project was used because old validation containers occupied the default ports.

Project:

- `upload-control-plane-final-readiness`

Port overrides:

- API: `http://localhost:18082`
- PostgreSQL: `localhost:25433`
- MinIO S3 API: `http://localhost:19100`
- MinIO Console: `http://localhost:19101`
- `S3_PUBLIC_ENDPOINT_URL=http://localhost:19100`

Commands and results:

- `docker compose -p upload-control-plane-final-readiness up --build -d`: passed.
- `DATABASE_URL=postgresql+psycopg://upload:upload@localhost:25433/upload uv run python scripts\migrate.py`: passed.
- `Invoke-RestMethod http://localhost:18082/healthz`: returned `{"status":"ok","service":"upload-control-plane"}`.
- MinIO health and console endpoints returned HTTP 200.
- `DATABASE_URL=postgresql+psycopg://upload:upload@localhost:25433/upload uv run python scripts\seed_dev.py`: passed.

Seed identity used:

- Project ID: `020500f8-920c-5a49-bf01-0eca416b8ddf`
- API key: `ucp_dev_api_key_local_only_20260624`

Python CLI direct-upload smoke:

- Uploaded `.readiness\portfolio-smoke.bin`, 6 MiB, with `uploadctl upload`.
- Session: `1771ad92-94f6-4dfe-b486-cabbee05ce3a`
- Result: `session=1771ad92-94f6-4dfe-b486-cabbee05ce3a status=COMPLETED uploaded=2/2`
- Object storage inspection showed the object under the expected tenant/project/dataset/session key namespace in MinIO.
- DB inspection showed the upload session completed with two uploaded parts.
- Local manifest scan found no `X-Amz-Signature`, `X-Amz-Credential`, presigned URL, MinIO endpoint URL, or secret material.

Resume path:

- `uv run uploadctl resume .readiness\.uploadctl\portfolio-smoke.bin.upload.json --api-key ucp_dev_api_key_local_only_20260624 --concurrency 2`
- Result: `session=1771ad92-94f6-4dfe-b486-cabbee05ce3a status=COMPLETED uploaded=2/2`

Control-plane lifecycle smoke:

- Created an unfinished upload task through `POST /v1/projects/{project_id}/upload-tasks`.
- Session: `744a25cf-1e7f-4fe7-9502-8feb186159e3`
- `uv run uploadctl status`: `status=INITIATED uploaded=0/1 missing=1`
- `uv run uploadctl pause`: `status=PAUSED`
- `uv run uploadctl status`: `status=PAUSED uploaded=0/1 missing=1`
- `uv run uploadctl resume-session`: `status=UPLOADING`
- `uv run uploadctl status`: `status=UPLOADING uploaded=0/1 missing=1`
- `uv run uploadctl abort`: `status=ABORTED`
- `uv run uploadctl status`: `status=ABORTED uploaded=0/1 missing=1`

Metrics:

- `/metrics` exposed counters for upload task creation, status, presign, ack, complete, pause, resume, and abort paths during the smoke.

## Documentation Changes

Updated `README.md` to remove stale bootstrap language and stale "not implemented" claims for workers/lifecycle/validation/outbox.

The README now states:

- The Python-first implementation is present and portfolio-ready for local runtime/API/worker/validation/observability/client-upload flows.
- The project remains production-oriented but not production-proven.
- Optional MQTT, Go uploader, Go gateway, and production deployment proof are not implemented unless explicitly requested.

## Cleanup Notes

The runtime smoke created `.readiness\` as a local temporary directory. It is not intended to be committed.

Recommended cleanup before commit:

- Remove `.readiness\`.
- Stop the isolated runtime with `docker compose -p upload-control-plane-final-readiness down -v`.

## Remaining Work

No remaining mandatory PRD/T00-T14 work was found for Python-first portfolio readiness.

Optional work only:

1. Decide whether the optional MQTT adapter is desired.
2. Decide whether the optional Go uploader is desired.
3. Decide whether the optional Go edge/control gateway is desired.
4. If production deployment readiness is desired, run a separate production-readiness pass with real deployment targets, credentials handling, backups, alerting, and runbook execution evidence.

## Recommended Next Master Action

If the user wants to continue product implementation, ask which optional track to activate:

- T15 MQTT adapter
- T16 Go uploader
- T17 Go edge/control gateway
- production deployment readiness

If the user only wants the Python-first portfolio complete state, no additional implementation task is required.
