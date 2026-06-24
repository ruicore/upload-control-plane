# Implementation Plan

Previous: [Observability, Testing, and Failure Modes](12-observability-testing-failure-modes.md) | Index: [README](README.md) | Next: [References and Completion Criteria](14-references-and-done.md)

## 30. Industrial Product Implementation Plan

This section is written for Codex and engineering execution. The product target is an industrial upload control plane, not a minimal demo. The implementation must still be split into reviewable, runnable stages so each stage has clear ownership, tests, and rollback shape.

Every stage should result in code that runs locally through Docker Compose or unit tests. Optional components are delayed only when their dependencies are not ready, not because they are out of product scope.

### Phase 0 - Foundation Runtime

Deliverables:

- Python 3.13 project dependencies for FastAPI, Pydantic Settings, pytest, ruff, and mypy.
- Basic FastAPI app with `/healthz`.
- Configuration loading.
- `docker-compose.yml` with `api`, `worker`, `postgres`, `minio`, and `minio-init`.
- MinIO S3 API exposed at `http://localhost:9000`.
- MinIO Console exposed at `http://localhost:9001`.
- PostgreSQL exposed at `localhost:15432` for local inspection.
- `Makefile` or equivalent scripts for dev-up, migrate, seed, test, and dev-down.

Acceptance criteria:

```bash
make dev-up
make test
curl http://localhost:8000/healthz
```

must succeed, and a local browser can open the MinIO Console at `http://localhost:9001`.

### Phase 1 - Domain Kernel

Deliverables:

- Part size selection and part range functions.
- Upload session state machine.
- Upload task and upload object aggregate status rules.
- Dataset lifecycle state rules using `dataset_status`.
- Dataset validation state rules using `validation_status`.
- Dataset recovery state rules using `recovery_status`.
- Object key sanitizer.
- Request fingerprint generation.
- Permission-code evaluation model, including inherited grants and deny-over-allow.

Acceptance criteria:

- Unit tests cover 5 MiB, 64 MiB, 5 GiB, and 10,000-part boundaries.
- Unit tests reject invalid upload session transitions.
- Unit tests prove upload `COMPLETED` is not equivalent to dataset `READY`.
- Unit tests prove `QUARANTINED`, `REJECTED`, and non-`NORMAL` recovery states block exposure.
- Unit tests prove effective permission calculation is centralized and deterministic.

### Phase 2 - Persistence Foundation

Deliverables:

- SQLAlchemy 2.x sync models.
- Alembic migration for tenants, storage policies, API keys, projects, datasets, tags, devices, permission grants, upload tasks, upload objects, upload sessions, upload parts, validation results, upload events, audit events, outbox events, and idempotency records.
- No `upload_batches` table.
- No `batch_id` ownership path on upload sessions or upload events.
- Seed script for dev tenant, API key, storage policy, project, dataset, device, and permission grants.

Acceptance criteria:

- Migration applies cleanly from an empty PostgreSQL database.
- Seed script produces one usable dev API key.
- Seeded actor can see a project through `project.view` and can upload through `dataset.upload` or `upload.create`.
- Schema contains separate `dataset_status`, `validation_status`, and `recovery_status` concepts.

### Phase 3 - Authentication and Authorization

Deliverables:

- API key authentication dependency.
- Hashed API key storage and verification.
- Tenant active-status checks.
- Project-scoped permission filtering.
- `effective_permissions` response helper.
- Stable error response format.
- Request ID middleware.

Acceptance criteria:

- Project list only returns projects where the caller has `project.view`.
- Project detail returns stable `effective_permissions`.
- Upload task creation is rejected without `dataset.upload` or `upload.create`.
- Presign, pause, resume, complete, and abort re-evaluate permissions on every request.

### Phase 4 - MinIO/S3 Storage Adapter

Deliverables:

- `ObjectStorage` protocol.
- S3/MinIO adapter using boto3.
- Create multipart upload.
- Presign upload part.
- List parts with pagination.
- Complete multipart upload.
- Abort multipart upload.
- Head object.
- Capability flags for checksums, conditional complete, encryption, object lock, replication metadata, and incomplete multipart listing.
- Internal S3 client using `S3_ENDPOINT_URL`.
- Presign S3 client using `S3_PUBLIC_ENDPOINT_URL`.

Acceptance criteria:

- Integration test creates a multipart upload in MinIO.
- Integration test presigns a part URL reachable from the host at `localhost:9000`.
- Integration test uploads bytes through the presigned URL and lists the part.
- Integration test completes the object and verifies it with head/read behavior.
- No implementation rewrites a signed URL host as a string post-process.

### Phase 5 - Upload Task Creation

Deliverables:

- `POST /v1/projects/{project_id}/upload-tasks`.
- Transactional creation of UploadTask, UploadObject, Dataset, UploadSession, and MinIO multipart upload.
- Idempotency support for task creation.
- Quota checks before storage multipart initiation.
- Storage-policy selection from project default or explicit allowed policy.
- Object key generation using tenant/project/dataset/session namespace.

Acceptance criteria:

- Single-file task creation returns task, object, dataset, and session identifiers.
- Multi-file task creation creates one UploadObject and UploadSession per object.
- Retrying the same idempotency key and fingerprint returns the same task.
- Quota rejection does not create storage-side multipart uploads.
- Client-supplied filenames never become raw object keys.

### Phase 6 - Upload Session Runtime API

Deliverables:

- `GET /v1/uploads/{id}`.
- `POST /v1/uploads/{id}/parts/presign`.
- `POST /v1/uploads/{id}/parts/ack`.
- `GET /v1/uploads/{id}/parts`.
- `POST /v1/uploads/{id}/pause`.
- `POST /v1/uploads/{id}/resume`.
- `POST /v1/uploads/{id}/complete`.
- `POST /v1/uploads/{id}/abort`.
- Idempotency support for pause, resume, complete, and abort.
- Storage-authoritative completion using `ListParts`.

Acceptance criteria:

- Presign is rejected while paused.
- Resume allows fresh presigned URLs.
- Complete fails with `409 upload.missing_parts` when storage parts are missing.
- Complete succeeds only after all expected parts exist in object storage.
- Abort is idempotent and never deletes completed final objects.
- Tenant isolation tests pass.

### Phase 7 - Python CLI Uploader

Deliverables:

- `uploadctl` command.
- Upload command using `POST /v1/projects/{project_id}/upload-tasks`.
- Resume command from local manifest.
- Status, pause, server-side resume, and abort commands.
- Local manifest with project, task, object, dataset, session, file, and part state.
- Concurrent part upload.
- URL-expiry detection and re-presign behavior.
- Pause behavior that stops scheduling new parts and flushes the manifest.

Acceptance criteria:

- CLI uploads a multi-part file to local MinIO through the API.
- CLI can resume after manual interruption.
- CLI can pause and resume a multi-part upload.
- CLI manifest does not store presigned URLs.
- CLI progress output is readable.

### Phase 8 - Dataset Product Lifecycle

Deliverables:

- Project dataset list/search/filter/detail/update APIs.
- Dataset download URL endpoint.
- Dataset archive, soft delete, restore, and purge APIs.
- Dataset tag category and tag APIs.
- Dataset exposure checks using dataset, validation, and recovery state.
- Audit events for download, delete, restore, purge, and policy denial.

Acceptance criteria:

- Dataset download requires `dataset.download`.
- Dataset download is rejected while dataset is `QUARANTINED`, `REJECTED`, validation is not passed when required, or recovery state is not `NORMAL`.
- Soft-deleted datasets are hidden from normal lists and restorable.
- Purge requires permission and retention-policy approval.
- Purge is rejected under legal hold or object lock.

### Phase 9 - Device Identity and Device Upload Authorization

Deliverables:

- Device register/update/disable/enable.
- Device credential provisioning and rotation.
- Credential material returned once only during provisioning or rotation.
- Credential expiration, revocation, and optional overlap window.
- Device-to-project authorization.
- Device upload task creation path.

Acceptance criteria:

- Disabled, revoked, or expired device credentials cannot create upload tasks or request presigned URLs.
- Device credential rotation invalidates or overlaps old credentials according to policy.
- No endpoint reveals existing raw credential material.
- Device upload requests still create ordinary UploadTasks and UploadSessions.

### Phase 10 - Workers and Lifecycle Automation

Deliverables:

- Worker process.
- Expire old sessions.
- Abort expired multipart uploads.
- Dataset recycle-bin retention enforcement.
- Dataset purge object-storage deletion.
- Backup/restore reconciliation command using `recovery_status`.
- Outbox append helper.
- Outbox dispatcher with retry and dead-letter policy.

Acceptance criteria:

- Expired sessions transition through `EXPIRED -> ABORTING -> ABORTED`.
- Worker can be run repeatedly safely.
- Restore reconciliation detects missing final objects and object-only or metadata-only cases.
- Domain writes and outbox inserts commit atomically.
- Outbox delivery failure never rolls back the completed domain action.

### Phase 11 - Dataset Validation and Metadata Extraction

Deliverables:

- Validation worker.
- Quarantine/release state transitions.
- Metadata extractor interface.
- HDF5 metadata extractor stub or real implementation.
- Optional malware/file-inspection hook interface.
- Validation result API.
- Retry validation API.
- Dataset preview metadata persistence.

Acceptance criteria:

- A completed dataset enters validation when enabled.
- Successful validation writes extracted metadata and marks dataset ready.
- Failed validation records errors without deleting the object.
- Dataset remains unavailable for download/processing while quarantined or rejected.
- Retry validation is permission-checked and idempotent.

### Phase 12 - Observability and Operations

Deliverables:

- Structured JSON logs.
- Prometheus metrics endpoint.
- Storage operation latency metrics.
- API latency metrics.
- Quota, rate-limit, backpressure, validation backlog, cleanup, recovery, and outbox metrics.
- SLO and alert rule examples.
- Operator runbook notes for KMS, CORS, storage outage, leaked URL, device compromise, cleanup backlog, outbox dead letters, and recovery.
- Optional OpenTelemetry tracing.
- Operator-only audit query endpoint.

Acceptance criteria:

- `/metrics` returns expected counters/histograms.
- Logs contain request ID, project ID, dataset ID, session ID, operation, and status where applicable.
- Presigned URL query strings are not logged.
- Alert thresholds are documented for storage errors, cleanup backlog, validation backlog, recovery mismatches, and outbox dead letters.

### Phase 13 - Failure Injection and Benchmark Suite

Deliverables:

- Tests for URL expiry.
- Tests for duplicate complete.
- Tests for missing storage part despite DB ack.
- Tests for permission revocation during upload.
- Tests for device credential revocation.
- Tests for validation failure.
- Tests for outbox delivery failure.
- Tests for retention-protected purge.
- Tests for CORS/signed-header mismatch.
- Tests for storage-native checksum mismatch when enabled.
- Tests for quota and backpressure rejection.
- Tests for KMS unavailable when encryption is enabled.
- Tests for object-lock/legal-hold purge denial.
- Tests for restore reconciliation.
- Benchmark script.
- Benchmark report template in `docs/benchmarks.md`.

Acceptance criteria:

- Failure injection test suite passes locally.
- Benchmark can upload at least a generated 512 MiB file against local MinIO.

### Phase 14 - Optional EMQX/MQTT Control-Plane Adapter

Only implement after HTTP upload correctness, authorization, device credentials, and outbox behavior are implemented.

Deliverables:

- MQTT command adapter.
- Topic naming and schema validation.
- Device authentication mapping.
- MQTT request/response correlation.
- MQTT ACL/topic authorization for each device.
- Device credential revocation handling.
- TLS-enabled production configuration.
- QoS and retain policy documentation.

Acceptance criteria:

- MQTT adapter calls the same application services as HTTP routes.
- MQTT messages never carry file bytes.
- Presigned URL response messages are not retained.
- Duplicate MQTT commands are idempotent.
- Device cannot publish or subscribe outside its authorized topic namespace.
- Disabled or revoked devices are rejected.

### Phase 15 - Optional Go Uploader

Deliverables:

- `go/robot-uploader` module.
- Upload/resume/status support through the same API.
- Concurrent part upload using Go routines.
- Local manifest compatible with Python CLI or explicitly versioned.

Acceptance criteria:

- Go uploader can upload and resume files using the Python backend.
- Benchmark compares Python CLI and Go uploader.
- Go implementation must not bypass the backend or use MinIO credentials.

### Phase 16 - Optional Go Edge/Control Gateway

Only implement if the core system is complete and a gateway has a real deployment reason.

Possible scope:

- Reverse proxy for control-plane API.
- API key/JWT validation.
- Rate limiting.
- Request ID propagation.
- No data-plane proxying.

Acceptance criteria:

- Gateway never proxies file bytes.
- Gateway can be disabled without changing core upload semantics.
