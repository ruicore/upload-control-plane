# Industrial Multipart Upload Control Plane Tasks

This folder turns the canonical PRD in `docs/prd/industrial-multipart-upload-control-plane/` into implementation tasks.

Each task is intended to be executable by Codex or another implementation agent. Before starting a task, open the `Applied PRD` files listed for that task and treat them as the task contract.

## Execution Rules

- Do tasks in dependency order. Do not start a task while any blocking dependency is incomplete.
- Keep each task reviewable and runnable through unit tests, integration tests, Docker Compose, or a documented smoke test.
- If implementation discovers a contract conflict, update the relevant PRD file before or together with the code change.
- Do not introduce file-byte proxy endpoints. File bytes must go directly from client/browser/device to MinIO/S3 through presigned URLs.
- Do not give clients MinIO/S3 credentials.
- Do not complete uploads from database acknowledgements alone; completion must reconcile with object storage.
- Treat `permission_grants` and permission codes as the authorization source of truth.
- Treat internal IDs as UUIDs. Human-readable slugs, device codes, storage upload IDs, object keys, and idempotency keys are not primary keys.
- Keep MQTT, Go uploader, and edge gateway work optional until their dependencies are complete.

## Dependency Graph

```text
T00 Foundation Runtime
  -> T01 Domain Kernel
    -> T02 Persistence Foundation
      -> T03 Authentication and Authorization
        -> T04 MinIO/S3 Storage Adapter
          -> T05 Upload Task Creation
            -> T06 Upload Session Runtime API
              -> T07 Development Manual Browser Uploader
              -> T08 Python CLI Uploader
              -> T09 Dataset Product Lifecycle
                -> T10 Device Identity and Device Upload Authorization
                  -> T11 Workers and Lifecycle Automation
                    -> T12 Dataset Validation and Metadata Extraction
                      -> T13 Observability and Operations
                        -> T14 Failure Injection and Benchmark Suite
                          -> T15 Optional EMQX/MQTT Control-Plane Adapter
                          -> T16 Optional Go Uploader
                          -> T17 Optional Go Edge/Control Gateway
```

Parallelism rule:

- `T07` and `T08` may proceed in parallel after `T06`.
- `T09` should wait for `T06` because dataset exposure depends on completed upload behavior.
- `T10` should wait for `T09` because device upload authorization must create ordinary upload tasks and datasets.
- `T15`, `T16`, and `T17` are optional. Do not implement them to compensate for missing HTTP/backend correctness.

## Task Index

| ID | Task | Depends on | Applied PRD |
|---|---|---|---|
| T00 | Foundation Runtime | none | `00`, `01`, `11`, `12`, `13`, `14` |
| T01 | Domain Kernel | T00 | `01`, `04`, `05`, `06`, `07`, `09`, `10`, `12`, `13`, `14` |
| T02 | Persistence Foundation | T01 | `04`, `06`, `07`, `09`, `10`, `11`, `12`, `13`, `14` |
| T03 | Authentication and Authorization | T02 | `04`, `06`, `07`, `09`, `10`, `12`, `13`, `14` |
| T04 | MinIO/S3 Storage Adapter | T02, T03 | `01`, `02`, `03`, `06`, `08`, `09`, `10`, `11`, `12`, `13`, `14` |
| T05 | Upload Task Creation | T03, T04 | `01`, `04`, `05`, `06`, `07`, `08`, `09`, `10`, `12`, `13`, `14` |
| T06 | Upload Session Runtime API | T05 | `01`, `04`, `05`, `06`, `07`, `08`, `09`, `10`, `12`, `13`, `14` |
| T07 | Development Manual Browser Uploader | T06 | `01`, `06`, `09`, `11`, `12`, `13`, `14` |
| T08 | Python CLI Uploader | T06 | `01`, `06`, `10`, `11`, `12`, `13`, `14` |
| T09 | Dataset Product Lifecycle | T06 | `04`, `06`, `07`, `09`, `10`, `12`, `13`, `14` |
| T10 | Device Identity and Device Upload Authorization | T09 | `04`, `06`, `07`, `09`, `12`, `13`, `14` |
| T11 | Workers and Lifecycle Automation | T06, T09, T10 | `04`, `05`, `07`, `10`, `12`, `13`, `14` |
| T12 | Dataset Validation and Metadata Extraction | T09, T11 | `04`, `07`, `09`, `10`, `12`, `13`, `14` |
| T13 | Observability and Operations | T11, T12 | `09`, `10`, `11`, `12`, `13`, `14` |
| T14 | Failure Injection and Benchmark Suite | T13 | `01`, `06`, `08`, `09`, `10`, `11`, `12`, `13`, `14` |
| T15 | Optional EMQX/MQTT Control-Plane Adapter | T10, T11, T13 | `01`, `03`, `06`, `09`, `10`, `11`, `12`, `13`, `14` |
| T16 | Optional Go Uploader | T08, T14 | `06`, `10`, `11`, `12`, `13`, `14` |
| T17 | Optional Go Edge/Control Gateway | T13 and accepted deployment reason | `01`, `03`, `09`, `11`, `12`, `13`, `14` |

PRD shorthand maps to files under `docs/prd/industrial-multipart-upload-control-plane/`:

- `00` = `00-executive-summary.md`
- `01` = `01-non-negotiable-decisions.md`
- `02` = `02-context-goals-scope.md`
- `03` = `03-system-architecture.md`
- `04` = `04-domain-model.md`
- `05` = `05-state-machine.md`
- `06` = `06-api-contracts.md`
- `07` = `07-database-schema.md`
- `08` = `08-storage-adapter-and-object-keys.md`
- `09` = `09-security-governance.md`
- `10` = `10-retry-resume-completion-lifecycle.md`
- `11` = `11-client-and-backend-implementation.md`
- `12` = `12-observability-testing-failure-modes.md`
- `13` = `13-implementation-plan.md`
- `14` = `14-references-and-done.md`

## T00 - Foundation Runtime

Depends on: none.

Applied PRD: `00`, `01`, `11`, `12`, `13`, `14`.

Goal:

- Create the runnable Python 3.13 service foundation without implementing upload APIs.

Deliverables:

- FastAPI app with `/healthz`.
- Pydantic Settings configuration.
- `docker-compose.yml` with `api`, `worker`, `postgres`, `minio`, and `minio-init`.
- Documented host port defaults for API, MinIO S3 API, MinIO Console, and PostgreSQL while preserving container-internal ports.
- Makefile or equivalent scripts for `dev-up`, `migrate`, `seed-dev`, `test`, and `dev-down`.
- Project dependencies for FastAPI, Pydantic Settings, pytest, ruff, mypy, and local runtime.

Acceptance:

- `make dev-up` succeeds.
- `make test` succeeds.
- `curl http://localhost:18080/healthz` returns `{"status":"ok","service":"upload-control-plane"}` or the documented equivalent.
- Browser can open the documented MinIO Console URL, defaulting to `http://localhost:19001`.

Out of scope:

- Upload APIs.
- Database upload-domain migrations.
- MinIO multipart operations.

## T01 - Domain Kernel

Depends on: T00.

Applied PRD: `01`, `04`, `05`, `06`, `07`, `09`, `10`, `12`, `13`, `14`.

Goal:

- Implement pure domain logic before infrastructure or HTTP upload endpoints exist.

Deliverables:

- Part size selection and part range functions.
- Upload session state machine.
- Upload task and upload object aggregate status rules.
- Dataset lifecycle, validation, and recovery exposure rules.
- Object key sanitizer.
- Request fingerprint generation.
- Permission-code evaluation, inherited grants, expiry handling, and deny-over-allow behavior.
- Unit tests for all above behavior.

Acceptance:

- Boundary tests cover 5 MiB, 64 MiB, 5 GiB, and 10,000-part cases.
- Invalid upload session transitions are rejected.
- Tests prove upload `COMPLETED` is not equivalent to dataset `READY`.
- Tests prove `QUARANTINED`, `REJECTED`, and non-`NORMAL` recovery states block exposure.
- Effective permissions are deterministic and centralized.

Out of scope:

- FastAPI upload endpoints.
- SQLAlchemy models.
- boto3 or MinIO calls.

## T02 - Persistence Foundation

Depends on: T01.

Applied PRD: `04`, `06`, `07`, `09`, `10`, `11`, `12`, `13`, `14`.

Goal:

- Add the PostgreSQL persistence foundation that matches the domain model and ID strategy.

Deliverables:

- SQLAlchemy 2.x sync models.
- Alembic environment and initial migration for tenants, storage policies, API keys, projects, datasets, tags, devices, permission grants, upload tasks, upload objects, upload sessions, upload parts, validation results, upload events, audit events, outbox events, and idempotency records.
- UUID internal primary and foreign keys.
- `source_device_id` as registered device UUID and `source_device_code` as optional external metadata.
- No `upload_batches` table and no `batch_id` ownership path.
- Dev seed script for tenant, API key, storage policy, project, dataset, device, and permission grants.

Acceptance:

- Migration applies cleanly from an empty PostgreSQL database.
- Seed script produces one usable dev API key.
- Seeded actor can see a project through `project.view`.
- Seeded actor can upload through `dataset.upload` or `upload.create`.
- Schema keeps `dataset_status`, `validation_status`, and `recovery_status` separate.

Out of scope:

- Storage multipart calls.
- Upload task creation endpoint.

## T03 - Authentication and Authorization

Depends on: T02.

Applied PRD: `04`, `06`, `07`, `09`, `10`, `12`, `13`, `14`.

Goal:

- Implement request identity, tenant checks, permission filtering, and stable error contracts.

Deliverables:

- API key authentication dependency.
- Hashed API key verification.
- Tenant active-status enforcement.
- Request ID middleware and stable error response format.
- Central authorization service backed by `permission_grants`.
- Project list/detail endpoints with permission filtering and `effective_permissions`.
- Authorization tests for project visibility and upload permission gates.

Acceptance:

- Project list only returns projects where the caller has `project.view`.
- Project detail returns stable `effective_permissions`.
- Upload task creation is rejected without `dataset.upload` or `upload.create` once that route exists.
- Presign, pause, resume, complete, and abort are designed to re-evaluate permissions on every request.

Out of scope:

- Actual upload task creation route.
- Multipart storage operations.

## T04 - MinIO/S3 Storage Adapter

Depends on: T02, T03.

Applied PRD: `01`, `02`, `03`, `06`, `08`, `09`, `10`, `11`, `12`, `13`, `14`.

Goal:

- Implement the storage adapter boundary without leaking MinIO/S3 specifics into domain logic.

Deliverables:

- `ObjectStorage` protocol or interface.
- S3/MinIO adapter using boto3 or botocore.
- Create multipart upload.
- Presign upload part.
- List parts with pagination.
- Complete multipart upload.
- Abort multipart upload.
- Head object.
- Capability flags for checksum, conditional complete, encryption, object lock, replication metadata, and incomplete multipart listing.
- Separate internal S3 client using `S3_ENDPOINT_URL` and presign client using `S3_PUBLIC_ENDPOINT_URL`.

Acceptance:

- Integration test creates a multipart upload in MinIO.
- Integration test presigns a host-reachable part URL at `localhost:9000`.
- Integration test uploads bytes directly to MinIO through the presigned URL.
- Integration test lists the uploaded part.
- Integration test completes the object and verifies it with head/read behavior.
- No code rewrites signed URL hosts as a string post-process.

Out of scope:

- Public upload APIs.
- CLI uploader.

## T05 - Upload Task Creation

Depends on: T03, T04.

Applied PRD: `01`, `04`, `05`, `06`, `07`, `08`, `09`, `10`, `12`, `13`, `14`.

Goal:

- Implement the public product entrypoint for creating upload work.

Deliverables:

- `POST /v1/projects/{project_id}/upload-tasks`.
- Transactional creation of UploadTask, UploadObject, Dataset, UploadSession, and MinIO multipart upload.
- Idempotency support for task creation.
- Quota checks before storage multipart initiation.
- Storage-policy selection.
- Server-generated object key using tenant/project/dataset/session namespace.
- Audit/upload events for task creation and storage initiation.

Acceptance:

- Single-file task creation returns task, object, dataset, and session identifiers.
- Multi-file task creation creates one UploadObject and UploadSession per object.
- Retrying the same idempotency key and fingerprint returns the same task.
- Quota rejection does not create storage-side multipart uploads.
- Client-supplied filenames never become raw object keys.
- Direct public creation of a bare UploadSession remains unavailable.

Out of scope:

- Presign, ack, complete, pause, resume, and abort runtime endpoints.
- CLI upload flow.

## T06 - Upload Session Runtime API

Depends on: T05.

Applied PRD: `01`, `04`, `05`, `06`, `07`, `08`, `09`, `10`, `12`, `13`, `14`.

Goal:

- Implement runtime control-plane APIs for upload sessions.

Deliverables:

- `GET /v1/uploads/{session_id}`.
- `POST /v1/uploads/{session_id}/parts/presign`.
- `POST /v1/uploads/{session_id}/parts/ack`.
- `GET /v1/uploads/{session_id}/parts`.
- `POST /v1/uploads/{session_id}/pause`.
- `POST /v1/uploads/{session_id}/resume`.
- `POST /v1/uploads/{session_id}/complete`.
- `POST /v1/uploads/{session_id}/abort`.
- Idempotency for pause, resume, complete, and abort.
- Storage-authoritative completion based on `ListParts`.
- Session-level locking for pause, resume, complete, and abort.

Acceptance:

- Presign is rejected while paused.
- Resume allows fresh presigned URLs.
- Complete fails with `409 upload.missing_parts` when storage parts are missing.
- Complete succeeds only after all expected parts exist in object storage.
- Abort is idempotent and never deletes completed final objects.
- Tenant isolation and permission re-evaluation tests pass.

Out of scope:

- Browser manual uploader.
- CLI uploader.

## T07 - Development Manual Browser Uploader

Depends on: T06.

Applied PRD: `01`, `06`, `09`, `11`, `12`, `13`, `14`.

Goal:

- Add a development-only browser tool to manually exercise the real upload API and browser CORS behavior.

Deliverables:

- `tools/manual-uploader` Vite-based browser app.
- Manual file picker.
- Inputs for API URL, API key, project ID, object metadata, part size, and concurrency.
- UploadTask creation through the public API.
- Part presign through the public API.
- Direct browser `PUT` to presigned URLs.
- Optional ack after each successful part.
- Complete, pause, resume, abort, and status controls.
- Local development state for diagnostics.
- Makefile command such as `make manual-uploader`.

Acceptance:

- Browser uploads a multi-part file to local MinIO without sending file bytes to FastAPI.
- Tool runs from `http://localhost:5173`.
- Tool uses existing public API contracts only.
- No manual-uploader-only backend routes are added.
- Presigned URLs are not persisted.
- Presigned URL query strings are redacted from diagnostics and logs.

Out of scope:

- Product dashboard or admin UI.
- Project/dataset/device management UI.

## T08 - Python CLI Uploader

Depends on: T06.

Applied PRD: `01`, `06`, `10`, `11`, `12`, `13`, `14`.

Goal:

- Implement `uploadctl` as the required Python CLI uploader.

Deliverables:

- `uploadctl upload`.
- `uploadctl resume`.
- `uploadctl status`.
- `uploadctl pause`.
- `uploadctl resume-session`.
- `uploadctl abort`.
- Local manifest with project, task, object, dataset, session, file, part state, file size, modification time, and optional checksum.
- Concurrent part upload with bounded memory.
- URL expiry detection and re-presign behavior.
- Pause behavior that stops scheduling new parts and flushes the manifest.

Acceptance:

- CLI uploads a multi-part file to local MinIO through the API.
- CLI can resume after manual interruption.
- CLI can pause and resume a multi-part upload.
- CLI manifest does not store presigned URLs.
- CLI progress output is readable.

Out of scope:

- Go uploader.
- MQTT control-plane adapter.

## T09 - Dataset Product Lifecycle

Depends on: T06.

Applied PRD: `04`, `06`, `07`, `09`, `10`, `12`, `13`, `14`.

Goal:

- Implement product-facing dataset APIs and lifecycle controls.

Deliverables:

- Project dataset list/search/filter/detail/update APIs.
- Dataset download URL endpoint.
- Dataset archive, soft delete, restore, and purge APIs.
- Tag category and tag APIs.
- Dataset exposure checks using dataset, validation, and recovery state.
- Audit events for download, delete, restore, purge, and policy denial.

Acceptance:

- Dataset download requires `dataset.download`.
- Dataset download is rejected while dataset is `QUARANTINED`, `REJECTED`, validation is not passed when required, or recovery state is not `NORMAL`.
- Soft-deleted datasets are hidden from normal lists and restorable.
- Purge requires permission and retention-policy approval.
- Purge is rejected under legal hold or object lock.

Out of scope:

- Device credential lifecycle.
- Validation worker implementation.

## T10 - Device Identity and Device Upload Authorization

Depends on: T09.

Applied PRD: `04`, `06`, `07`, `09`, `12`, `13`, `14`.

Goal:

- Make industrial devices first-class authenticated subjects.

Deliverables:

- Device register/update/disable/enable endpoints.
- Device credential provisioning and rotation.
- Credential material returned once only during provisioning or rotation.
- Credential expiration, revocation, and optional overlap window.
- Device-to-project authorization.
- Device upload task creation path that creates ordinary UploadTasks and UploadSessions.
- Tests proving `source_device_id` is registered-device UUID and `source_device_code` is metadata only.

Acceptance:

- Disabled, revoked, or expired device credentials cannot create upload tasks or request presigned URLs.
- Rotation invalidates or overlaps old credentials according to policy.
- No endpoint reveals existing raw credential material.
- Device upload requests create ordinary UploadTasks and UploadSessions.

Out of scope:

- MQTT adapter.
- Device file transfer through backend or broker.

## T11 - Workers and Lifecycle Automation

Depends on: T06, T09, T10.

Applied PRD: `04`, `05`, `07`, `10`, `12`, `13`, `14`.

Goal:

- Add background automation for cleanup, recovery, purge, and outbox delivery.

Deliverables:

- Worker process.
- Expire old sessions.
- Abort expired multipart uploads.
- Dataset recycle-bin retention enforcement.
- Dataset purge object-storage deletion.
- Backup/restore reconciliation command using `recovery_status`.
- Outbox append helper.
- Outbox dispatcher with retry and dead-letter policy.

Acceptance:

- Expired sessions transition through `EXPIRED -> ABORTING -> ABORTED`.
- Worker can run repeatedly without corrupting state.
- Restore reconciliation detects missing final objects and object-only or metadata-only cases.
- Domain writes and outbox inserts commit atomically.
- Outbox delivery failure never rolls back the completed domain action.

Out of scope:

- Dataset validation parsing.
- MQTT publishing adapter, unless only represented as an outbox sink stub.

## T12 - Dataset Validation and Metadata Extraction

Depends on: T09, T11.

Applied PRD: `04`, `07`, `09`, `10`, `12`, `13`, `14`.

Goal:

- Add validation and metadata extraction lifecycle after upload completion.

Deliverables:

- Validation worker.
- Quarantine/release state transitions.
- Metadata extractor interface.
- HDF5 metadata extractor stub or real implementation.
- Optional malware/file-inspection hook interface.
- Validation result API.
- Retry validation API.
- Dataset preview metadata persistence.

Acceptance:

- A completed dataset enters validation when enabled.
- Successful validation writes extracted metadata and marks dataset ready.
- Failed validation records errors without deleting the object.
- Dataset remains unavailable for download/processing while quarantined or rejected.
- Retry validation is permission-checked and idempotent.

Out of scope:

- Full product analytics or preview UI.
- Mandatory real HDF5 parser if a stub is sufficient for the current phase.

## T13 - Observability and Operations

Depends on: T11, T12.

Applied PRD: `09`, `10`, `11`, `12`, `13`, `14`.

Goal:

- Make the system operationally inspectable and production-oriented.

Deliverables:

- Structured JSON logs.
- Prometheus `/metrics`.
- Storage operation latency metrics.
- API latency metrics.
- Quota, rate-limit, backpressure, validation backlog, cleanup, recovery, and outbox metrics.
- SLO and alert rule examples.
- Operator runbook notes for KMS, CORS, storage outage, leaked URL, device compromise, cleanup backlog, outbox dead letters, and recovery.
- Optional OpenTelemetry tracing.
- Operator-only audit query endpoint.

Acceptance:

- `/metrics` returns expected counters and histograms.
- Logs contain request ID, project ID, dataset ID, session ID, operation, and status where applicable.
- Presigned URL query strings are not logged.
- Alert thresholds are documented for storage errors, cleanup backlog, validation backlog, recovery mismatches, and outbox dead letters.

Out of scope:

- Production SLO claims.
- Hosted monitoring stack unless added as optional local compose services.

## T14 - Failure Injection and Benchmark Suite

Depends on: T13.

Applied PRD: `01`, `06`, `08`, `09`, `10`, `11`, `12`, `13`, `14`.

Goal:

- Prove core failure modes and provide local performance evidence.

Deliverables:

- Failure tests for URL expiry, duplicate complete, missing storage part despite DB ack, permission revocation during upload, device credential revocation, validation failure, outbox delivery failure, retention-protected purge, CORS/signed-header mismatch, storage-native checksum mismatch when enabled, quota and backpressure rejection, KMS unavailable when encryption is enabled, object-lock/legal-hold purge denial, and restore reconciliation.
- Benchmark script.
- `docs/benchmarks.md` report template.

Acceptance:

- Failure injection suite passes locally.
- Benchmark can upload at least a generated 512 MiB file against local MinIO.
- Results avoid production throughput claims unless measured and scoped.

Out of scope:

- External cloud-provider benchmark claims.

## T15 - Optional EMQX/MQTT Control-Plane Adapter

Depends on: T10, T11, T13.

Applied PRD: `01`, `03`, `06`, `09`, `10`, `11`, `12`, `13`, `14`.

Goal:

- Add MQTT as an optional control-plane ingress/notification layer, not a data plane.

Deliverables:

- MQTT command adapter.
- Topic naming and schema validation.
- Device authentication mapping.
- MQTT request/response correlation.
- MQTT ACL/topic authorization for each device.
- Device credential revocation handling.
- TLS-enabled production configuration.
- QoS and retain policy documentation.

Acceptance:

- MQTT adapter calls the same application services as HTTP routes.
- MQTT messages never carry file bytes.
- Presigned URL response messages are not retained.
- Duplicate MQTT commands are idempotent.
- Device cannot publish or subscribe outside its authorized topic namespace.
- Disabled or revoked devices are rejected.

Out of scope:

- File chunk transfer over MQTT.
- Separate upload state machine.

## T16 - Optional Go Uploader

Depends on: T08, T14.

Applied PRD: `06`, `10`, `11`, `12`, `13`, `14`.

Goal:

- Add an optional Go uploader after Python CLI correctness exists.

Deliverables:

- `go/robot-uploader` module.
- Upload/resume/status support through the same API.
- Concurrent part upload using goroutines.
- Local manifest compatible with Python CLI or explicitly versioned.

Acceptance:

- Go uploader can upload and resume files using the Python backend.
- Benchmark compares Python CLI and Go uploader.
- Go implementation does not bypass the backend or use MinIO credentials.

Out of scope:

- Backend rewrite in Go.
- Direct MinIO credential use by the uploader.

## T17 - Optional Go Edge/Control Gateway

Depends on: T13 and an accepted deployment reason.

Applied PRD: `01`, `03`, `09`, `11`, `12`, `13`, `14`.

Goal:

- Add an optional edge/control gateway only if the core system is complete and a concrete deployment need exists.

Possible deliverables:

- Reverse proxy for control-plane API.
- API key or JWT validation.
- Rate limiting.
- Request ID propagation.
- Explicit no-data-plane-proxying guarantees.

Acceptance:

- Gateway never proxies file bytes.
- Gateway can be disabled without changing core upload semantics.
- Gateway does not replace backend authorization or storage reconciliation.

Out of scope:

- Required MVP functionality.
- File-byte proxying.

## Final Portfolio Readiness Check

Run after T14 and any selected optional tasks.

Applied PRD: `14`.

Checklist:

- Docker Compose local run works.
- `uploadctl` can upload, interrupt, resume, pause, resume, reconcile, and complete.
- PostgreSQL exposes expected project, dataset, task, session, part, audit, and outbox metadata.
- MinIO contains completed objects under expected project/dataset key namespaces.
- Permission tests prove hidden/forbidden actions stay inaccessible.
- Device tests prove registered devices can trigger uploads and disabled/revoked devices cannot.
- Dataset lifecycle tests cover soft delete, restore, download authorization, validation persistence, and purge policy behavior.
- Tests cover missing parts, URL expiry recovery, duplicate completion, pause/resume, and abort idempotency.
- Logs, metrics, alerts, audit events, outbox behavior, and runbooks demonstrate operational thinking.
- README clearly states the project is production-oriented but not production-proven.
