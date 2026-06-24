# Client and Backend Implementation

Previous: [Retry, Resume, Completion, and Lifecycle](10-retry-resume-completion-lifecycle.md) | Index: [README](README.md) | Next: [Observability, Testing, and Failure Modes](12-observability-testing-failure-modes.md)

## 23. Client Uploader Design

### 23.1 Required CLI

Implement a Python CLI called:

```text
uploadctl
```

Commands:

```bash
uploadctl upload ./front_camera.mp4 \
  --api-url http://localhost:8000 \
  --api-key dev-api-key \
  --tenant demo \
  --device-id robot-17 \
  --part-size 64MiB \
  --concurrency 8

uploadctl resume ./.uploadctl/front_camera.mp4.upload.json

uploadctl status <session_id> --api-url http://localhost:8000 --api-key dev-api-key

uploadctl pause <session_id> --api-url http://localhost:8000 --api-key dev-api-key

uploadctl resume-session <session_id> --api-url http://localhost:8000 --api-key dev-api-key

uploadctl abort <session_id> --api-url http://localhost:8000 --api-key dev-api-key
```

### 23.2 Upload flow

```text
1. Validate local file exists and is stable.
2. Optionally compute full-file SHA256.
3. Call POST /v1/uploads.
4. Write local manifest.
5. Compute missing part numbers.
6. Request presigned URLs in batches.
7. Upload parts with bounded concurrency.
8. Ack successful parts.
9. If pause is requested, stop scheduling new parts and flush manifest.
10. Periodically flush manifest to disk.
11. Call complete.
12. Mark manifest completed.
```

### 23.3 Concurrency

Default concurrency:

```text
8
```

Configurable range:

```text
1 to 64
```

Recommended local default:

```text
4 or 8
```

Client should avoid requesting presigned URLs for all 10,000 parts at once unless explicitly configured.

Recommended presign batch size:

```text
min(concurrency * 4, 100)
```

### 23.4 Retry policy

Per part upload retry:

```text
max attempts: 5
base delay: 500 ms
max delay: 30 seconds
jitter: required
```

Retryable storage status codes:

```text
408
409 if storage-specific transient conflict
425
429
500
502
503
504
```

Special handling:

- `403` with expired signature: request new presigned URL and retry.
- `404` for upload ID: call session status/reconcile; fail clearly if aborted/expired.
- `400 EntityTooSmall`: client bug or bad part-size config; fail fast.

### 23.5 File reading

The client must avoid loading the entire file into memory.

Acceptable first implementation:

- Load one part into memory per active worker.
- With 8 concurrency and 64 MiB parts, peak part buffer memory is roughly 512 MiB.

Better implementation:

- Implement bounded range reader or streaming body.
- Ensure each worker only reads its assigned byte range.

### 23.6 Local file mutation detection

The client should store in manifest:

- File size.
- Modification time.
- Optional file inode if available.
- Optional full SHA256.

On resume, if file size changed, fail unless `--force` is used.

### 23.7 Progress reporting

CLI should display:

```text
session_id
file size
part size
part count
uploaded parts
missing parts
current throughput
average throughput
ETA
retry count
```

### 23.8 Python vs Go client

Python client is required first because it aligns with the initial backend stack and is faster to implement.

Optional Go client later should demonstrate:

- Lower memory overhead.
- Strong concurrency model.
- Better standalone binary distribution.
- More realistic robot/edge-device uploader.

### 23.9 Client pause controls

The uploader should maintain an internal pause flag checked before scheduling each new part.

Default pause behavior:

- Stop scheduling new part uploads.
- Let already started part uploads finish.
- Ack any part that finishes successfully.
- Flush the manifest immediately.
- Keep the process alive in a paused state if interactive, or exit cleanly with a resumable manifest if non-interactive.

Optional force-pause behavior:

- Cancel in-flight HTTP PUT requests locally.
- Treat cancelled parts as missing.
- Retry cancelled parts only after resume and fresh presign.

The client must not assume the backend can cancel an already issued presigned URL. Server-side pause prevents future control-plane scheduling and signing, while client-side pause controls local upload workers.

---


## 24. Backend Implementation Architecture

### 24.1 Recommended stack

```text
Python 3.12+
FastAPI
Pydantic v2
SQLAlchemy 2.x
Alembic
PostgreSQL
boto3 / botocore
Typer for CLI
pytest
ruff
mypy or pyright
Docker Compose
```

### 24.2 Synchronous or asynchronous backend

Recommended first implementation:

- Use regular synchronous FastAPI route functions.
- Use SQLAlchemy sync engine.
- Use boto3 sync client.
- Run with multiple workers for API concurrency.

Reason:

- The backend is control-plane only.
- File bytes do not pass through the API.
- boto3 is blocking by default.
- Simpler code is better for correctness.

A later async implementation is acceptable only if it does not complicate correctness.

### 24.3 Package structure

```text
upload-control-plane/
+-- README.md
+-- docs/
|   +-- architecture.md
|   +-- api.md
|   +-- failure-modes.md
|   +-- benchmarks.md
|   +-- development.md
+-- src/
|   +-- upload_control_plane/
|       +-- __init__.py
|       +-- main.py
|       +-- config.py
|       +-- logging.py
|       +-- api/
|       |   +-- __init__.py
|       |   +-- dependencies.py
|       |   +-- error_handlers.py
|       |   +-- middleware.py
|       |   +-- routes/
|       |       +-- health.py
|       |       +-- projects.py
|       |       +-- datasets.py
|       |       +-- devices.py
|       |       +-- tags.py
|       |       +-- uploads.py
|       |       +-- upload_tasks.py
|       |       +-- batches.py
|       |       +-- storage_policies.py
|       |       +-- validation.py
|       |       +-- downloads.py
|       |       +-- audit.py
|       |       +-- permissions.py
|       +-- mqtt/                         # optional later
|       |   +-- __init__.py
|       |   +-- command_adapter.py
|       |   +-- schemas.py
|       |   +-- topics.py
|       +-- domain/
|       |   +-- __init__.py
|       |   +-- errors.py
|       |   +-- models.py
|       |   +-- policies.py
|       |   +-- states.py
|       |   +-- part_size.py
|       +-- application/
|       |   +-- __init__.py
|       |   +-- project_service.py
|       |   +-- dataset_service.py
|       |   +-- device_service.py
|       |   +-- tag_service.py
|       |   +-- upload_service.py
|       |   +-- upload_task_service.py
|       |   +-- batch_service.py
|       |   +-- part_service.py
|       |   +-- completion_service.py
|       |   +-- abort_service.py
|       |   +-- storage_policy_service.py
|       |   +-- download_service.py
|       |   +-- validation_service.py
|       |   +-- lifecycle_service.py
|       |   +-- audit_service.py
|       |   +-- outbox_service.py
|       |   +-- authorization_service.py
|       |   +-- idempotency_service.py
|       +-- infrastructure/
|       |   +-- __init__.py
|       |   +-- db/
|       |   |   +-- __init__.py
|       |   |   +-- base.py
|       |   |   +-- models.py
|       |   |   +-- session.py
|       |   |   +-- repositories.py
|       |   +-- storage/
|       |   |   +-- __init__.py
|       |   |   +-- base.py
|       |   |   +-- s3_minio.py
|       |   +-- messaging/                # optional later
|       |   |   +-- __init__.py
|       |   |   +-- base.py
|       |   |   +-- emqx_mqtt.py
|       |   +-- auth/
|       |       +-- __init__.py
|       |       +-- api_key.py
|       |       +-- models.py
|       +-- worker/
|       |   +-- __init__.py
|       |   +-- cleanup.py
|       |   +-- checksum_validator.py
|       |   +-- dataset_validator.py
|       |   +-- metadata_extractor.py
|       |   +-- lifecycle.py
|       |   +-- outbox_dispatcher.py
|       +-- cli/
|           +-- __init__.py
|           +-- main.py
|           +-- client.py
|           +-- manifest.py
|           +-- uploader.py
|           +-- file_ranges.py
+-- migrations/
|   +-- env.py
|   +-- versions/
+-- tests/
|   +-- unit/
|   +-- integration/
|   +-- e2e/
|   +-- failure_injection/
+-- docker-compose.yml
+-- Dockerfile
+-- pyproject.toml
+-- Makefile
+-- scripts/
    +-- create_dev_api_key.py
    +-- seed_dev.py
    +-- generate_test_file.py
    +-- benchmark_upload.py
```

### 24.4 Layering rules

- `domain` must not import FastAPI, SQLAlchemy, boto3, or MinIO-specific code.
- `application` may depend on domain interfaces and repositories.
- `infrastructure` implements repositories and storage adapters.
- `api` maps HTTP DTOs to application commands.
- Optional `mqtt` maps MQTT command DTOs to the same application commands used by HTTP.
- Optional `infrastructure.messaging` owns broker connectivity, topic subscription, publishing, TLS, and reconnect behavior.
- `cli` uses HTTP API only; it must not import backend application services.
- MQTT code must not implement a separate upload state machine or bypass application services.
- Permission evaluation should live in one application-level authorization service, not be reimplemented in each route.
- API responses may include `effective_permissions`, but the database source of truth is `permission_grants`.
- Tests should target domain functions without infrastructure whenever possible.

---


## 25. Configuration

Use environment variables with Pydantic Settings.

Required settings:

```text
APP_ENV=local
APP_NAME=upload-control-plane
DATABASE_URL=postgresql+psycopg://upload:upload@postgres:5432/upload
S3_ENDPOINT_URL=http://minio:9000
S3_PUBLIC_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_REGION=us-east-1
S3_BUCKET=robot-data
S3_ADDRESSING_STYLE=path
S3_REQUIRE_TLS_IN_PRODUCTION=true
S3_DEFAULT_ENCRYPTION_MODE=NONE
S3_DEFAULT_KMS_KEY_REF=
S3_ENABLE_OBJECT_LOCK=false
S3_DEFAULT_OBJECT_LOCK_MODE=
S3_DEFAULT_OBJECT_LOCK_RETENTION_DAYS=
S3_ENABLE_CONDITIONAL_COMPLETE=false
S3_CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
S3_CORS_ALLOWED_HEADERS=content-type,etag,x-amz-checksum-sha256,x-amz-checksum-crc32c,x-amz-server-side-encryption
S3_CORS_EXPOSE_HEADERS=etag,x-amz-checksum-sha256,x-amz-checksum-crc32c
DEFAULT_PART_SIZE_BYTES=67108864
MIN_PART_SIZE_BYTES=5242880
MAX_PART_SIZE_BYTES=5368709120
MAX_PART_COUNT=10000
DEFAULT_PRESIGN_EXPIRY_SECONDS=900
MAX_PRESIGN_EXPIRY_SECONDS=21600
MAX_PRESIGN_SIGNATURE_AGE_SECONDS=900
DEFAULT_UPLOAD_SESSION_EXPIRY_SECONDS=86400
MAX_UPLOAD_SESSION_EXPIRY_SECONDS=604800
MAX_PARTS_PER_PRESIGN_REQUEST=100
MAX_OPEN_UPLOADS_PER_TENANT=1000
MAX_OPEN_UPLOAD_TASKS_PER_PROJECT=200
MAX_OPEN_UPLOADS_PER_DEVICE=20
MAX_BYTES_PER_TENANT=
MAX_BYTES_PER_PROJECT=
PRESIGN_RATE_LIMIT_PER_TENANT_PER_MINUTE=600
PRESIGN_RATE_LIMIT_PER_DEVICE_PER_MINUTE=120
DEFAULT_RECYCLE_RETENTION_DAYS=30
DEFAULT_DATASET_RETENTION_DAYS=
DEFAULT_DOWNLOAD_URL_EXPIRY_SECONDS=900
MAX_DOWNLOAD_URL_EXPIRY_SECONDS=21600
ENABLE_DATASET_VALIDATION=false
ENABLE_METADATA_EXTRACTION=false
ENABLE_MALWARE_SCAN=false
ENABLE_STORAGE_NATIVE_CHECKSUM=false
STORAGE_NATIVE_CHECKSUM_ALGORITHM=
ENABLE_OUTBOX_DISPATCHER=true
OUTBOX_MAX_ATTEMPTS=12
OUTBOX_BATCH_SIZE=100
VALIDATION_QUEUE_MAX_DEPTH=1000
BACKPRESSURE_STORAGE_ERROR_RATE_THRESHOLD=0.05
BACKPRESSURE_STORAGE_P95_LATENCY_MS=5000
LOG_LEVEL=INFO
ENABLE_CHECKSUM_VALIDATOR=false
```

Important distinction:

- `S3_ENDPOINT_URL` is used by the backend inside Docker/network.
- `S3_PUBLIC_ENDPOINT_URL` may be needed when generating presigned URLs that the host client can reach.

For local Docker Compose, the backend may talk to `http://minio:9000`, but the CLI running on host may need URLs pointing to `http://localhost:9000`.

The storage adapter should support endpoint URL rewriting if required:

```text
internal signed URL host: minio:9000
external client host: localhost:9000
```

Implementation must be careful: changing the host after signing can break signatures depending on signature configuration. The preferred local setup is to configure the S3 client endpoint to the public endpoint when generating URLs for host clients, or run the CLI inside the same Docker network.

Optional EMQX/MQTT settings, only required when MQTT support is enabled:

```text
ENABLE_MQTT_CONTROL_PLANE=false
MQTT_BROKER_HOST=emqx
MQTT_BROKER_PORT=1883
MQTT_USE_TLS=false
MQTT_CLIENT_ID=upload-control-plane
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_CA_FILE=
MQTT_CERT_FILE=
MQTT_KEY_FILE=
MQTT_TOPIC_PREFIX=device
MQTT_QOS=1
MQTT_RETAIN_PRESIGNED_URL_RESPONSES=false
```

Production configuration requirements:

- `S3_PUBLIC_ENDPOINT_URL` must use `https://`.
- Public API base URLs must use `https://`.
- Production browser origins must be explicit. Do not use wildcard CORS origins for production uploads.
- Signed upload headers must be reflected in both `PresignedPartUrl.required_headers` and bucket CORS `AllowedHeaders`.
- Production storage policies must document encryption mode, object-lock mode, retention, and replication expectations, even when disabled.
- `MQTT_USE_TLS` must be `true` when `ENABLE_MQTT_CONTROL_PLANE=true`.
- MQTT broker listener configuration must reject unauthenticated production clients.
- `MQTT_RETAIN_PRESIGNED_URL_RESPONSES` must remain `false`.

---


## 26. Docker Compose Development Environment

Required services:

```text
api
worker
postgres
minio
minio-init
```

Optional services:

```text
prometheus
grafana
jaeger
```

Minimum Compose behavior:

- Start PostgreSQL.
- Start MinIO.
- Create required bucket.
- Run DB migrations.
- Start API.
- Start cleanup worker.

Example commands:

```bash
make dev-up
make migrate
make seed-dev
make test
make e2e-upload
make dev-down
```

---


