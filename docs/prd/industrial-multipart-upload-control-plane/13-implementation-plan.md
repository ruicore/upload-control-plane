# Implementation Plan

Previous: [Observability, Testing, and Failure Modes](12-observability-testing-failure-modes.md) | Index: [README](README.md) | Next: [References and Completion Criteria](14-references-and-done.md)

## 30. Phased Implementation Plan

This section is written for Codex. Each phase should result in runnable code and tests.

### Phase 0 - Repository scaffold

Deliverables:

- `pyproject.toml`.
- `src/upload_control_plane` package.
- `tests` structure.
- `docker-compose.yml` with PostgreSQL and MinIO.
- `Makefile`.
- Basic FastAPI app with `/healthz`.
- Basic config loading.
- Ruff and pytest configured.

Acceptance criteria:

```bash
make dev-up
make test
curl http://localhost:8000/healthz
```

must succeed.

### Phase 1 - Domain model and database migrations

Deliverables:

- Domain enums and state transition validation.
- Part size and part range functions.
- Dataset lifecycle transition rules.
- Upload task aggregate status rules.
- Dataset exposure states including quarantine, validation pending, ready, rejected, and recovery states.
- SQLAlchemy models.
- Alembic migration for tenants, storage policies, api keys, projects, datasets, tags, devices, permission grants, upload tasks, upload objects, batches, sessions, parts, validation results, upload events, audit events, outbox events, and idempotency.
- Storage policy fields for encryption, KMS key reference, object lock, legal hold, replication policy, CORS policy, quotas, and checksum mode.
- Seed script for dev tenant and API key.

Acceptance criteria:

- Unit tests for part math and state transitions pass.
- DB migration applies cleanly from empty database.
- Seed script produces one usable dev API key, one storage policy, one project, one dataset, one device, and permission grants for upload testing.

### Phase 2 - MinIO/S3 storage adapter

Deliverables:

- `ObjectStorage` protocol.
- `S3MultipartStorage` implementation using boto3.
- Create multipart upload.
- Presign upload part.
- List parts with pagination.
- Complete multipart upload.
- Abort multipart upload.
- Head object.
- Adapter capability flags for checksums, conditional complete, encryption, object lock, replication metadata, and incomplete multipart listing.
- Optional checksum, encryption, object-lock, and conditional-write headers in adapter request models.

Acceptance criteria:

- Integration test can create multipart upload in MinIO.
- Integration test can presign a part URL and upload bytes with HTTP PUT.
- Integration test can list the part from MinIO.
- Integration test can complete and read/head final object.
- Adapter cleanly reports unsupported storage-native checksum or object-lock capabilities.

### Phase 3 - Core upload API

Deliverables:

- API key auth dependency.
- Error response format.
- Request ID middleware.
- `GET /v1/projects`.
- `GET /v1/projects/{id}` with `effective_permissions`.
- `POST /v1/projects/{id}/datasets`.
- `GET /v1/datasets/{id}` with `effective_permissions`.
- `GET /v1/me/permissions` or equivalent permission introspection endpoint.
- `POST /v1/projects/{project_id}/upload-tasks` for the single-file task path.
- Upload task creation that creates one upload object, one dataset, and one upload session transactionally.
- `POST /v1/uploads`.
- `GET /v1/uploads/{id}`.
- `POST /v1/uploads/{id}/parts/presign`.
- `POST /v1/uploads/{id}/parts/ack`.
- `GET /v1/uploads/{id}/parts`.
- `POST /v1/uploads/{id}/pause`.
- `POST /v1/uploads/{id}/resume`.
- `POST /v1/uploads/{id}/complete`.
- `POST /v1/uploads/{id}/abort`.
- Idempotency support for create/pause/resume/complete/abort.
- Quota checks before storage multipart initiation.
- Presigned URL response includes required signed headers.
- Browser CORS expectations are documented and testable in local MinIO setup.

Acceptance criteria:

- OpenAPI docs show all endpoints.
- Integration tests cover successful multipart upload through API + direct MinIO PUT.
- Upload task creation updates task/object/dataset/session rows consistently.
- Complete missing parts returns 409.
- Successful complete updates dataset object metadata and task aggregate counters.
- Pause rejects presign and resume allows fresh presign.
- Abort is idempotent.
- Quota rejection does not create storage-side multipart upload.
- Signed-header mismatch is covered by an integration test when required headers are enabled.
- Tenant isolation tests pass.

### Phase 4 - Python CLI uploader

Deliverables:

- `uploadctl` command.
- Upload command.
- Resume command.
- Status command.
- Pause command.
- Server-side resume command.
- Abort command.
- Local manifest persistence.
- Concurrent part upload.
- Retry and URL-expiry handling.
- Pause stops scheduling new parts and flushes the manifest.

Acceptance criteria:

- CLI uploads a multi-part file to local MinIO through the API.
- CLI can resume after manual interruption.
- CLI can pause and resume a multi-part upload.
- CLI does not store presigned URLs in manifest.
- CLI progress output is readable.

### Phase 5 - Project, dataset, device, and task-center APIs

Deliverables:

- Project CRUD and archive/restore/delete.
- Project member management through permission grants.
- Dataset list/search/filter/detail/update.
- Dataset tags and tag categories.
- Dataset soft delete, restore, and purge.
- Dataset download URL endpoint.
- Device register/update/disable/enable.
- Device credential rotation.
- Device credential expiration, revocation, and optional overlap window.
- Device provisioning state and device-to-MQTT topic authorization model.
- Upload task list/detail and task/object pause/resume/cancel/retry.
- Dataset quarantine/release and legal-hold APIs if enabled.
- Audit events for sensitive actions.

Acceptance criteria:

- A view-only actor can list allowed projects and datasets but cannot upload.
- An upload actor can create upload tasks but cannot manage members.
- A disabled device cannot create an upload task.
- A revoked or expired device credential cannot create upload tasks or request presigned URLs.
- Dataset download URL requires `dataset.download`.
- Dataset download is rejected while dataset is quarantined, validation failed, rejected, or recovery pending.
- Dataset purge requires `dataset.purge` and retention-policy approval.
- Dataset purge is rejected under legal hold or storage object lock.
- Audit events are written for permission, credential, download, delete, restore, and purge actions.

### Phase 6 - Batch upload support

Deliverables:

- `POST /v1/upload-batches`.
- `GET /v1/upload-batches/{id}`.
- `POST /v1/upload-batches/{id}/complete`.
- Ability to create upload sessions under a batch.
- CLI support for a directory/batch manifest.

Acceptance criteria:

- E2E test uploads multiple files under one batch.
- Batch cannot complete until child uploads are complete.
- Batch completion is idempotent.

### Phase 7 - Cleanup worker and lifecycle

Deliverables:

- Worker process.
- Expire old sessions.
- Abort expired multipart uploads.
- Dataset recycle-bin retention enforcement.
- Dataset purge object-storage deletion.
- Backup/restore reconciliation command.
- Recovery state transitions for metadata/object mismatches.
- Cleanup idempotency records.
- Cleanup events/metrics.

Acceptance criteria:

- Test session expires and worker aborts it.
- Test soft-deleted dataset is restored before retention expiry.
- Test purge deletes final object only when retention allows it.
- Test restore reconciliation detects missing final object and orphan object.
- Worker can be run repeatedly safely.
- Worker errors are logged and metriced.

### Phase 8 - Dataset validation and metadata extraction

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

### Phase 9 - Outbox and optional notification delivery

Deliverables:

- Transactional outbox append helper.
- Outbox dispatcher worker.
- Retry and dead-letter policy.
- Optional WebSocket/webhook publisher interface.
- Optional EMQX publisher for device/task status events.

Acceptance criteria:

- Domain writes and outbox inserts commit atomically.
- Dispatcher retry behavior is test-covered.
- Failed delivery never rolls back the completed domain action.
- Presigned URL responses are never retained by MQTT.

### Phase 10 - Observability

Deliverables:

- Structured JSON logs.
- Prometheus metrics endpoint.
- Storage operation latency metrics.
- API latency metrics.
- Quota, rate-limit, backpressure, validation backlog, and replication metrics.
- SLO and alert rule examples.
- Operator runbook notes for KMS, CORS, storage outage, leaked URL, device compromise, and recovery.
- Optional OpenTelemetry tracing.
- Audit query endpoint for operators.

Acceptance criteria:

- `/metrics` returns expected counters/histograms.
- Logs contain request ID, project ID, dataset ID, session ID, operation, and status where applicable.
- Presigned URL query strings are not logged.
- Outbox, validation, download URL, device, and purge paths emit metrics.
- Alert thresholds are documented for storage errors, cleanup backlog, validation backlog, and outbox dead letters.

### Phase 11 - Failure injection and benchmark suite

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

### Phase 12 - Optional EMQX/MQTT control-plane adapter

Only implement after HTTP upload correctness, authorization, outbox, and device credentials are implemented.

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

### Phase 13 - Optional Go uploader

Deliverables:

- `go/robot-uploader` module.
- Upload/resume/status support through the same API.
- Concurrent part upload using Go routines.
- Local manifest compatible with Python CLI or explicitly versioned.

Acceptance criteria:

- Go uploader can upload and resume files using the Python backend.
- Benchmark compares Python CLI and Go uploader.
- Go implementation must not bypass the backend or use MinIO credentials.

### Phase 14 - Optional Go edge/control gateway

Only implement if the core system is complete.

Possible scope:

- Reverse proxy for control-plane API.
- API key/JWT validation.
- Rate limiting.
- Request ID propagation.
- No data-plane proxying.

Acceptance criteria:

- Gateway never proxies file bytes.
- Gateway can be disabled without changing core upload semantics.

---

