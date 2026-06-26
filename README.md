# Upload Control Plane

Production-oriented resumable multipart upload control plane for AI, robotics, and industrial data ingestion, using FastAPI, PostgreSQL, and MinIO.

This repository contains the Python-first implementation of the control plane described by the PRD. It is production-oriented, but it is not production-proven: the local runtime, APIs, workers, validation, observability, and client upload flows are implemented and tested for portfolio readiness, while optional MQTT/Go components and production deployment evidence remain out of scope unless explicitly requested.

## Design Status

The canonical PRD is split into a Codex-readable document set:

- [Industrial Multipart Upload Control Plane PRD](docs/prd/industrial-multipart-upload-control-plane/README.md)
- [Compatibility entrypoint for older links](docs/industrial_multipart_upload_control_plane_design.md)

The PRD defines the target architecture, API contracts, storage adapter boundaries, database schema, security controls, observability plan, failure modes, and phased implementation plan.

## Architecture Direction

The system is designed around a strict control-plane / data-plane split:

```text
Clients and devices
    | control-plane calls only
    v
Upload Control Plane
    | creates sessions and signs scoped storage operations
    v
MinIO / S3-compatible storage

Clients and devices
    | direct PUT part bytes through presigned URLs
    v
MinIO / S3-compatible storage
```

The backend and optional EMQX/MQTT adapter must never receive large file bodies. They manage authorization, upload lifecycle state, presigned URL issuance, pause/resume, completion, abort, cleanup, audit, and observability. File bytes move directly from browsers, CLI tools, or industrial devices to object storage.

## Planned Scope

The PRD currently covers:

- S3-compatible multipart upload with client-side slicing and retry.
- Resumability after client crash, robot power loss, network outage, or URL expiry.
- Pause and resume as control-plane scheduling states.
- PostgreSQL-backed upload, dataset, device, permission, audit, outbox, and lifecycle metadata.
- MinIO-first storage through an adapter boundary.
- Project, dataset, device, upload task, storage policy, and resource-scoped permission models.
- Optional EMQX/MQTT control-plane integration for device-triggered uploads.
- Browser direct-upload CORS and signed-header requirements.
- Storage-native checksums, KMS/encryption, object lock, legal hold, quota, backpressure, backup/restore, and recovery reconciliation.
- Structured logs, Prometheus metrics, OpenTelemetry hooks, SLOs, alerts, and operator runbooks.

## Repository Status

Implemented today:

- Project structure, packaging, development tooling, and quality gates.
- PRD, task packs, orchestration notes, and handoff history.
- Docker Compose local runtime with FastAPI, PostgreSQL, MinIO, migrations, and seed data.
- Public upload task and upload session runtime APIs.
- `uploadctl` Python CLI uploader for direct-to-object-storage multipart uploads.
- Development-only browser uploader with direct browser-to-object-storage uploads.
- Dataset lifecycle API, device identity and device upload flow, permission grants, audit, and outbox foundations.
- Cleanup, validation, outbox, lifecycle, and recovery worker behavior.
- Observability, metrics, redaction, failure benchmarks, KMS-unavailable handling, restore/rebuild reconciliation, and storage backpressure gate hardening.

Not implemented unless explicitly requested:

- Optional MQTT adapter.
- Optional Go uploader.
- Optional Go edge/control gateway.
- Production deployment and operations proof beyond the local Docker Compose readiness path.

## Python CLI Uploader

`uploadctl` uses only the public HTTP API and presigned upload URLs. It does
not receive MinIO/S3 credentials, and it streams file parts directly from disk
to object storage without sending file bytes through FastAPI.

Example local upload after `make dev-up`, `make migrate`, and `make seed-dev`:

```bash
uv run uploadctl upload ./front_camera.mp4 \
  --api-url http://localhost:18080 \
  --api-key ucp_dev_api_key_local_only_20260624 \
  --project-id <seeded-project-id> \
  --device-id robot-17 \
  --part-size 64MiB \
  --concurrency 8
```

Resume from the durable local manifest:

```bash
uv run uploadctl resume ./.uploadctl/front_camera.mp4.upload.json \
  --api-key ucp_dev_api_key_local_only_20260624
```

Operational controls:

```bash
uv run uploadctl status <session-id> --api-url http://localhost:18080 --api-key <api-key>
uv run uploadctl pause <session-id> --api-url http://localhost:18080 --api-key <api-key>
uv run uploadctl resume-session <session-id> --api-url http://localhost:18080 --api-key <api-key>
uv run uploadctl abort <session-id> --api-url http://localhost:18080 --api-key <api-key>
```

This project is production-oriented, but it is not production-proven.

## Development Principles

- Keep file bytes out of backend control-plane services.
- Do not give clients MinIO/S3 credentials.
- Treat object storage as authoritative for uploaded parts before completion.
- Keep domain logic independent from FastAPI, SQLAlchemy, boto3, and broker clients.
- Make state transitions explicit and test-covered.
- Make every state-changing API retry-safe.
- Redact secrets and presigned URL query strings from logs, traces, audit events, and outbox payloads.
- Add focused tests with every behavior change.

## Local Development

Install dependencies with:

```bash
uv sync --group dev --group docs
```

Run quality gates with:

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src tests
uv run pytest
```

Start the local T00 runtime with Docker Compose:

```bash
make dev-up
curl http://localhost:18080/healthz
make dev-down
```

Run the development-only browser uploader from `http://localhost:5173`:

```bash
make manual-uploader
```

The browser uploader lives under `tools/manual-uploader`. It calls the public
upload APIs for task creation, presign, status, pause, resume, complete, and
abort, then uploads part bytes directly to MinIO/S3 through presigned URLs. It
does not add backend routes, does not receive object-storage credentials, and
does not persist presigned URLs.

The local API allows browser CORS from `http://localhost:5173` through
`API_CORS_ALLOWED_ORIGINS`, including the `Authorization`, `Content-Type`,
`Idempotency-Key`, and `X-Request-ID` headers used by the manual uploader.
API CORS list environment overrides should use JSON arrays, for example
`API_CORS_ALLOWED_ORIGINS=["http://localhost:5173"]`, because these values are
loaded by `pydantic-settings` as `list[str]` fields at process startup.
The local MinIO service allows the same browser origin through
`MINIO_API_CORS_ALLOW_ORIGIN` so direct browser `PUT` requests to presigned URLs
can pass preflight without exposing MinIO credentials to the browser.

On Windows hosts without GNU Make, use the equivalent PowerShell script:

```powershell
.\scripts\dev.ps1 dev-up
Invoke-RestMethod http://localhost:18080/healthz
.\scripts\dev.ps1 manual-uploader
.\scripts\dev.ps1 dev-down
```

Default host ports avoid common local conflicts while preserving container-internal ports:

```text
API:           http://localhost:18080 -> api:8000
PostgreSQL:    localhost:25432       -> postgres:5432
MinIO S3 API:  http://localhost:19000 -> minio:9000
MinIO Console: http://localhost:19001 -> minio:9001
```

Override them with `API_HOST_PORT`, `POSTGRES_HOST_PORT`, `MINIO_HOST_PORT`, and
`MINIO_CONSOLE_HOST_PORT`. If `MINIO_HOST_PORT` changes, set
`S3_PUBLIC_ENDPOINT_URL` to the matching host URL so future presigned URLs use a
host-reachable endpoint.

Install pre-commit hooks with:

```bash
uv run pre-commit install
```
