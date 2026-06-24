# Observability, Testing, and Failure Modes

Previous: [Client and Backend Implementation](11-client-and-backend-implementation.md) | Index: [README](README.md) | Next: [Implementation Plan](13-implementation-plan.md)

## 27. Observability

### 27.1 Structured logs

All logs should be JSON in non-local environments.

Fields:

```text
timestamp
level
message
request_id
trace_id
tenant_id
session_id
batch_id
actor_id
operation
storage_operation
status
latency_ms
error_code
```

Never log:

- Raw API keys.
- MinIO access/secret keys.
- Full presigned URLs with query parameters.
- User-provided metadata without size limits.

### 27.2 Metrics

Expose Prometheus-compatible metrics at:

```text
GET /metrics
```

Required metrics:

```text
upload_sessions_created_total{tenant_id}
upload_sessions_completed_total{tenant_id}
upload_sessions_aborted_total{tenant_id}
upload_sessions_failed_total{tenant_id,error_code}
upload_sessions_expired_total{tenant_id}
upload_sessions_by_status{status}

upload_presign_requests_total{tenant_id}
upload_presign_parts_total{tenant_id}
upload_part_ack_total{tenant_id}
upload_pause_requests_total{tenant_id}
upload_resume_requests_total{tenant_id}
upload_complete_requests_total{tenant_id}
upload_complete_missing_parts_total{tenant_id}

dataset_created_total{tenant_id}
dataset_ready_total{tenant_id}
dataset_validation_failed_total{tenant_id}
dataset_deleted_total{tenant_id}
dataset_purged_total{tenant_id}
dataset_download_url_requests_total{tenant_id}
dataset_quarantined_total{tenant_id}
dataset_rejected_total{tenant_id}
dataset_legal_hold_denied_purge_total{tenant_id}

upload_tasks_created_total{tenant_id}
upload_tasks_completed_total{tenant_id}
upload_tasks_failed_total{tenant_id,error_code}

device_registered_total{tenant_id}
device_last_seen_age_seconds{tenant_id}
device_credential_revoked_total{tenant_id}
device_auth_failures_total{tenant_id,error_code}

outbox_events_pending{tenant_id}
outbox_events_delivered_total{tenant_id,event_type}
outbox_events_failed_total{tenant_id,event_type}

storage_operation_duration_seconds{operation}
storage_operation_errors_total{operation,error_code}
storage_backpressure_rejects_total{reason}
storage_replication_pending_total{tenant_id}
storage_replication_failed_total{tenant_id}

cleanup_sessions_scanned_total
cleanup_sessions_aborted_total
cleanup_errors_total{error_code}

quota_rejects_total{tenant_id,scope}
rate_limit_rejects_total{tenant_id,scope}
validation_queue_depth
validation_queue_oldest_age_seconds

api_request_duration_seconds{method,path,status_code}
api_requests_total{method,path,status_code}
```

For portfolio usage, avoid high-cardinality labels like raw `session_id`.

### 27.3 Tracing

Use OpenTelemetry-compatible instrumentation when practical.

Important spans:

```text
api.request
upload.create_session
storage.create_multipart_upload
storage.presign_upload_part
storage.list_parts
storage.complete_multipart_upload
storage.abort_multipart_upload
upload.pause
upload.resume
dataset.create
dataset.download_url
dataset.validation
dataset.lifecycle
device.register
outbox.dispatch
db.transaction
worker.cleanup_expired_sessions
```

### 27.4 SLOs, alerts, and operator runbooks

Metrics are not enough. Production-oriented deployments should define SLOs and runbooks for the upload control plane.

Recommended SLOs:

| Area | Example target |
|---|---|
| Control-plane availability | 99.9% monthly for authenticated API calls |
| Presign latency | p95 under 300 ms excluding storage outage |
| Complete latency | p95 under 2 seconds for metadata path, excluding storage assembly time |
| Upload recovery | resumable after client crash or URL expiry within session lifetime |
| Cleanup | expired multipart uploads aborted within cleanup grace period plus 30 minutes |
| Outbox delivery | 99% delivered within 5 minutes when downstream is healthy |
| Validation freshness | 95% of validation-enabled datasets processed within target window |

Recommended alerts:

- API 5xx rate above threshold.
- Presign p95 latency above threshold.
- Storage operation p95 latency above threshold.
- Storage error rate above threshold.
- Cleanup backlog older than threshold.
- Outbox dead-letter count greater than zero.
- Validation queue oldest item above threshold.
- Replication pending or failed above threshold when replication is enabled.
- Quota/rate-limit rejects spike unexpectedly.
- Device authentication failures spike for a tenant or project.
- Audit export or audit retention job fails.

Runbooks should cover:

- Storage outage during active uploads.
- PostgreSQL outage or migration failure.
- KMS unavailable.
- CORS misconfiguration for browser upload.
- Leaked presigned URL.
- Compromised or revoked device credential.
- Stuck multipart cleanup.
- Validation parser crash or suspected malicious file.
- Disaster recovery restore and reconciliation.

---


## 28. Testing Strategy

### 28.1 Unit tests

Required unit tests:

- Part size selection.
- Part range calculation.
- State transition rules.
- Dataset lifecycle transition rules.
- Upload task and upload object aggregate status calculation.
- Object key sanitizer.
- Request fingerprint generation.
- Idempotency conflict behavior.
- Pause/resume state transition rules.
- Effective permission calculation, including inherited grants and deny-over-allow.
- Storage policy selection and bounds validation.
- Storage policy encryption, retention, object-lock, quota, and CORS field validation.
- Device credential status and project-access checks.
- Device credential rotation, overlap window, expiration, and revocation rules.
- Tag normalization and duplicate-name validation.
- Outbox retry backoff and dead-letter transition rules.
- Missing part validation.
- File mutation detection in CLI manifest.
- Dataset exposure-state rules for `COMPLETED`, `QUARANTINED`, `VALIDATING`, `READY`, and `REJECTED`.

### 28.2 Integration tests

Use real PostgreSQL and real MinIO.

Required integration tests:

1. Project list only returns projects where caller has `project.view`.
2. Project detail returns stable `effective_permissions`.
3. Dataset create is rejected without `dataset.create`.
4. Upload creation is rejected without `dataset.upload` or `upload.create`.
5. Storage policy defaults are applied from project to upload task/session.
6. Upload task creation creates task, object, dataset, session, and MinIO multipart upload consistently.
7. Presign is rejected without `upload.presign`.
8. Presign returns valid URL for part 1.
9. Upload one part directly to MinIO using presigned URL.
10. List parts sees uploaded part.
11. Complete fails when parts are missing.
12. Complete succeeds when all parts exist.
13. Completed upload updates dataset object metadata and upload task aggregate status.
14. Abort succeeds and is idempotent.
15. Presign rejected after abort.
16. Presign rejected after completion.
17. Pause rejects future presign requests.
18. Resume allows fresh presign requests.
19. Abort succeeds from paused state.
20. Dataset download URL is rejected without `dataset.download`.
21. Dataset download URL is short-lived and scoped to the final object.
22. Dataset soft delete hides it from normal lists.
23. Restore returns the dataset to normal lists.
24. Purge deletes object storage only after retention and permission checks pass.
25. Disabled device cannot create upload tasks or request presigned URLs.
26. Device credential rotation invalidates the previous credential version.
27. Validation worker records success and extracted metadata.
28. Validation worker records failure without corrupting upload completion.
29. Audit event is written for member, permission, download, delete, and purge actions.
30. Outbox event is inserted in the same transaction as a domain change.
31. Outbox dispatcher retries transient publish failures and dead-letters after max attempts.
32. Expired paused session cleanup aborts storage upload.
33. Expired session cleanup aborts storage upload.
34. Browser CORS preflight succeeds for configured local origins and required signed headers.
35. Browser CORS preflight fails for disallowed production origins.
36. Presigned upload with required checksum or content-type header fails if the client omits or changes the signed header.
37. Storage-native checksum mode records provider checksum metadata when enabled and supported.
38. Storage-native checksum mismatch fails with a clear integrity error.
39. Conditional complete prevents overwrite when an object already exists and the provider supports it.
40. Quota rejection happens before storage multipart initiation.
41. Storage policy encryption headers are passed to `create_multipart_upload` when enabled.
42. Purge is rejected when legal hold or object-lock policy forbids deletion.
43. Restored metadata is reconciled against object storage before marking a dataset ready.

### 28.3 E2E tests

Required E2E tests using CLI:

1. Upload a small file using multipart path.
2. Upload a file large enough to produce multiple parts.
3. Kill upload halfway, resume, complete.
4. Use a very short presign expiry, force URL expiration, resume with new URLs.
5. Upload same part twice and complete with latest storage-observed ETag.
6. Pause an upload, verify no new parts are scheduled, resume, reconcile, and complete.
7. Pause with in-flight parts allowed to finish, resume, and complete using storage-observed parts.
8. Create a project-scoped dataset upload and verify the dataset becomes `READY`.
9. Download a completed dataset through a short-lived presigned download URL.
10. Run batch upload with multiple files and complete batch.
11. Run an API-only device upload flow using device credentials.
12. Run permission-denied flows for view-only and upload-only actors.

### 28.4 Failure injection tests

Required failure modes:

| Failure | Expected behavior |
|---|---|
| API timeout after session creation | Retrying init with same idempotency key returns same session |
| Presigned URL expires | Client requests a new URL and retries part |
| Part upload network failure | Only failed part is retried |
| Client crash | Manifest resumes from storage reconciliation |
| Pause during upload | Client stops scheduling new parts; already uploaded parts remain valid |
| Presign while paused | API returns invalid state and no URL |
| Resume after long pause | Client reconciles storage and requests fresh URLs |
| Missing part on complete | API returns 409 with missing parts |
| Duplicate complete requests | One completes; the other returns completed or conflict safely |
| Abort during upload | Further presign and complete are rejected |
| DB has ack but storage lacks part | Complete rejects missing storage part |
| Storage has part but DB lacks ack | Reconcile updates DB and complete can succeed |
| Storage complete succeeds but API response lost | Retry complete returns completed state after repair/reconcile |
| Dataset validation fails | Dataset remains visible with validation failure status and error details |
| Outbox publish fails | Domain transaction remains committed; outbox retries later |
| Device credential revoked mid-upload | New control-plane requests are rejected; already uploaded storage parts remain reconciliable |
| Purge requested before retention allows it | API rejects purge and records audit event |
| Purge requested under object lock or legal hold | API rejects purge and records policy audit event |
| Download URL leaked after expiry | Object storage rejects the expired URL |
| Presigned URL leaked before expiry | Operator can rotate credentials, pause/abort session, and rely on expiry/network restrictions |
| KMS unavailable during multipart initiation | API fails explicitly without creating an unencrypted fallback upload |
| Storage latency/error spike | API applies backpressure or returns retryable errors before creating unbounded sessions |
| Browser CORS config missing required header | Browser upload fails in a diagnosed CORS/signed-header test |
| Validation parser crashes on malicious file | Upload remains completed but dataset is quarantined or validation failed |
| DB restored but object missing | Recovery marks dataset/session with missing-object state |
| Object exists without DB metadata | Recovery marks orphan object for operator review rather than exposing it |
| Tag deleted while dataset list is queried | Query remains stable and dataset remains accessible |

### 28.5 Performance tests

Provide benchmark scripts, not hard production claims.

Recommended benchmark dimensions:

```text
file_size: 512 MiB, 1 GiB, 5 GiB
part_size: 16 MiB, 64 MiB, 128 MiB
concurrency: 1, 4, 8, 16, 32
```

Report:

```text
total duration
average throughput
p50 part latency
p95 part latency
retry count
API presign latency
complete latency
dataset ready latency
validation latency
download-url latency
CPU/memory usage if available
```

### 28.6 Security and governance tests

Required security/governance test cases:

1. Metadata rejects oversized keys and values.
2. Metadata rejects configured secret-looking keys such as `password`, `token`, and `secret`.
3. Unsupported content type is rejected when allowlist is enabled.
4. Original filename is stored only as metadata and never appears in object key.
5. Dataset cannot be downloaded while `QUARANTINED`, `VALIDATING`, or `REJECTED`.
6. Dataset can be downloaded after validation marks it `READY` and caller has `dataset.download`.
7. Audit events are written for legal hold, purge denial, credential revocation, and validation release.
8. Presigned URLs are redacted from logs, traces, audit events, outbox payloads, and MQTT payload storage.
9. Device cannot publish or subscribe outside its authorized MQTT topic prefix.
10. Rate-limit and quota errors use stable error codes.
11. Object-lock bypass, if implemented, requires separate privileged permission and audit event.
12. Backup/restore rehearsal verifies at least one completed object and one incomplete multipart upload.

---


## 29. Failure Modes and Required Handling

### 29.1 Network failure during part upload

Handling:

- Client retries same part.
- If URL expired, client requests a new URL.
- Other uploaded parts are not affected.

### 29.2 Client process crash

Handling:

- Client manifest persists session and uploaded part hints.
- On restart, client reconciles with server/storage.
- Missing parts are uploaded.

### 29.3 API crash after storage upload initiated

Handling:

- Idempotency record and DB session reduce duplicate creation.
- Orphan sweeper handles rare storage-side orphan multipart uploads.

### 29.4 DB update failure after storage complete

Handling:

- Retry complete should check final object existence if storage upload ID no longer exists.
- A repair command can mark session completed if final object exists and metadata matches.

### 29.5 Storage unavailable

Handling:

- Return 503 for storage-dependent operations.
- Do not corrupt DB state.
- Retry worker cleanup later.

### 29.6 Complete with missing parts

Handling:

- Return 409.
- Include missing part summary.
- Transition back to `UPLOADING`, or back to `PAUSED` if completion was attempted from `PAUSED`.
- Client resumes missing parts.

### 29.7 Complete while aborting

Handling:

- Lock session.
- Only one transition wins.
- Losing request receives `409 invalid_state`.

### 29.8 Presign after session expiry

Handling:

- Return `410 Gone` or `409 invalid_state` depending on final chosen error policy.
- Recommended: `410 Gone` for `EXPIRED`.

### 29.9 Local file changed during resume

Handling:

- CLI detects size or checksum mismatch.
- Abort local operation unless user passes explicit force option.
- Force option must create a new upload session, not continue old session.

### 29.10 Pause during active upload

Handling:

- Server-side pause transitions the session to `PAUSED`.
- New presign requests are rejected.
- Client-side uploader stops scheduling new parts.
- In-flight part uploads may finish or be cancelled locally.
- Finished in-flight parts remain valid if storage lists them.
- Resume reconciles storage and requests fresh presigned URLs.

### 29.11 Pause command delivered while device is offline

Handling:

- MQTT may deliver the pause command after reconnect depending on broker/session configuration.
- The command must be idempotent.
- The device must compare command `session_id` and current local manifest before acting.
- The backend must not assume the device stopped immediately.
- Complete and reconciliation remain storage-authoritative.

### 29.12 Device credential revoked during upload

Handling:

- New control-plane API calls from the device are rejected.
- Previously uploaded storage parts are not deleted automatically.
- A human or service account with permission may resume, complete, abort, or purge according to policy.
- Audit event must record the rejected device request and credential version.

### 29.13 Dataset validation failure after successful upload

Handling:

- Upload session remains `COMPLETED`.
- Dataset transitions to `VALIDATION_FAILED`, or remains `PROCESSING` with retryable error state if policy requires retry.
- Validation error details are stored in `dataset_validation_results`.
- The object must not be deleted automatically unless an explicit policy says failed validation should be purged.

### 29.14 Outbox delivery failure

Handling:

- Domain transaction remains committed.
- Outbox event remains `PENDING` or `FAILED` with incremented attempt count.
- Dispatcher retries with bounded backoff.
- After max attempts, event transitions to `DEAD_LETTERED` and emits metrics/alerts.
- Operators can inspect and replay dead-lettered events.

### 29.15 Retention-protected purge request

Handling:

- API rejects purge with a stable authorization or policy error.
- Object storage is not touched.
- Audit event records actor, dataset, policy, and rejection reason.
- The UI should explain that the dataset is deleted/archived but not yet purgeable.

### 29.16 Stale or leaked presigned download URL

Handling:

- URLs must be short-lived and generated only after `dataset.download`.
- Expired URLs are rejected by object storage.
- Download URL request events are audited without logging the signed query string.
- Revocation before expiry requires either short expiry, object key rotation, storage policy support, or a deny layer outside plain presigned URL semantics.

### 29.17 Project membership changed during active upload

Handling:

- Each new control-plane request re-evaluates effective permissions.
- Existing storage PUTs that already have valid presigned URLs may still reach object storage.
- Completion must require current `upload.complete` or equivalent service permission.
- Operators can pause/abort sessions after permission revocation.

### 29.18 KMS unavailable

Handling:

- Multipart initiation or completion fails with a clear storage policy error.
- The system must not silently retry without encryption.
- No session should be marked uploadable if storage initiation did not succeed.
- Alert operators because KMS outage can block new uploads and reads of encrypted objects.

### 29.19 Object locked or legal hold blocks purge

Handling:

- API rejects purge with a stable policy error.
- Object storage is not touched except for safe metadata/head checks.
- Audit event records actor, dataset, storage policy, lock mode, and legal-hold status when available.
- Dataset remains deleted/archived or retention-protected according to application lifecycle.

### 29.20 Browser CORS or signed-header mismatch

Handling:

- Browser upload fails before or during part PUT.
- Client surfaces a clear diagnostic that includes missing CORS method/header/origin or signed-header mismatch category, without exposing the full URL.
- Backend support endpoint can report expected upload headers and configured public storage endpoint.
- The fix is operator configuration, not retrying the same bad request indefinitely.

### 29.21 Storage-native checksum mismatch

Handling:

- Provider returns `BadDigest` or equivalent integrity failure.
- Client does not retry indefinitely with the same bad bytes.
- Session records integrity failure details without storing file bytes.
- Dataset must not become `READY`.
- Operator or client may restart upload after local file verification.

### 29.22 Quota or backpressure rejection

Handling:

- API rejects new upload or presign requests before allocating unnecessary storage resources.
- Response includes stable error code and optional `Retry-After`.
- Existing valid upload parts are not discarded.
- Metrics identify whether the rejection came from tenant quota, project quota, device limit, rate limit, validation backlog, or storage health.

### 29.23 Restore after DB or object-storage loss

Handling:

- Restored metadata starts in a recovery state until object storage is checked.
- Completed datasets require object existence, expected size, and checksum metadata when available before returning to `READY`.
- Missing final objects are marked `RECOVERY_MISSING_OBJECT`.
- Orphan objects without DB metadata are not exposed automatically; they require operator review.
- Recovery actions emit audit events and metrics.

---

