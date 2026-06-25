# Observability and Operations

This service exposes operational signals without moving file bytes through the API.

## Metrics

`GET /metrics` returns Prometheus-compatible text. The endpoint is intended for an internal
scraper or a trusted network path.

Core metric families:

- `api_requests_total{method,path,status_code}`
- `api_request_duration_seconds{method,path,status_code}`
- `upload_sessions_created_total{tenant_id}`
- `upload_sessions_completed_total{tenant_id}`
- `upload_sessions_aborted_total{tenant_id}`
- `upload_sessions_failed_total{tenant_id,error_code}`
- `upload_sessions_expired_total{tenant_id}`
- `storage_operation_duration_seconds{operation}`
- `storage_operation_errors_total{operation,error_code}`
- `upload_sessions_by_status{status}`
- `validation_queue_depth`
- `validation_queue_oldest_age_seconds`
- `cleanup_expired_sessions_backlog`
- `outbox_events_pending{tenant_id}`
- `outbox_events_dead_lettered{tenant_id,event_type}`
- `recovery_datasets_by_status{status}`

Labels intentionally avoid raw `session_id`, object keys, URLs, credentials, and filenames.
The endpoint is lightweight and process-local: in-memory counters and histograms reset when the
API process restarts. Metric families for paths that are not wired to runtime instrumentation yet
emit zero-valued placeholder samples with bounded labels such as `tenant_id="unknown"` or
`error_code="unknown"`. DB-backed samples are aggregate snapshots and do not include object keys,
bucket URLs, credentials, presigned query strings, or raw filenames.

## Structured Logs

Request logs include:

- `request_id`
- `operation`
- `path`
- `method`
- `status`
- `latency_ms`
- `project_id`, `dataset_id`, and `session_id` when present as route path parameters

Do not log presigned URL query strings. If a URL must appear in diagnostics, use only the
scheme, host, and path, for example:

```text
http://storage.example.local/bucket/object
```

Never include signed query parameters, API keys, MinIO access keys, MinIO secret keys, raw device
credential material, or file bytes in logs, metrics, audit events, traces, or docs examples.

## Alert Examples

These examples are starting thresholds for local and staging environments. Tune them after real
traffic exists.

```yaml
groups:
  - name: upload-control-plane
    rules:
      - alert: UploadControlPlaneApi5xxRateHigh
        expr: sum(rate(api_requests_total{status_code=~"5.."}[5m])) > 0.05
        for: 10m
        labels:
          severity: page
        annotations:
          summary: API 5xx rate is elevated

      - alert: UploadControlPlaneApiLatencyHigh
        expr: histogram_quantile(0.95, sum(rate(api_request_duration_seconds_bucket[5m])) by (le, path)) > 1
        for: 15m
        labels:
          severity: ticket
        annotations:
          summary: API p95 latency is above 1 second

      - alert: StorageOperationLatencyHigh
        expr: histogram_quantile(0.95, sum(rate(storage_operation_duration_seconds_bucket[5m])) by (le, operation)) > 5
        for: 10m
        labels:
          severity: page
        annotations:
          summary: Storage p95 latency is above 5 seconds

      - alert: StorageOperationErrorsHigh
        expr: sum(rate(storage_operation_errors_total[5m])) by (operation) > 0.05
        for: 10m
        labels:
          severity: page
        annotations:
          summary: Storage operation errors are elevated

      - alert: CleanupBacklogStuck
        expr: cleanup_expired_sessions_backlog > 0
        for: 30m
        labels:
          severity: ticket
        annotations:
          summary: Expired upload sessions are waiting for cleanup

      - alert: ValidationBacklogOld
        expr: validation_queue_oldest_age_seconds > 3600
        for: 15m
        labels:
          severity: ticket
        annotations:
          summary: Validation backlog oldest item is older than 1 hour

      - alert: OutboxDeadLettersPresent
        expr: sum(outbox_events_dead_lettered) > 0
        for: 5m
        labels:
          severity: page
        annotations:
          summary: Outbox has dead-lettered events

      - alert: RecoveryMismatchPresent
        expr: sum(recovery_datasets_by_status) > 0
        for: 15m
        labels:
          severity: ticket
        annotations:
          summary: Recovery reconciliation found non-normal dataset state
```

## Operator Audit Query

`GET /v1/projects/{project_id}/audit-events` is for operators with `audit.view` on the project.
It returns bounded audit metadata only. It must not expose file bytes, MinIO/S3 credentials, raw
device credential material, or signed URL query strings.

Useful filters:

- `dataset_id`
- `action`
- `limit`

## Runbooks

### Storage outage

Symptoms:

- Storage operation error rate increases.
- Presign, complete, abort, or dataset download URL calls return storage errors.
- Cleanup backlog may grow.

Actions:

- Confirm object storage endpoint, DNS, TLS, and credentials from backend environment.
- Pause new upload intake if errors are broad.
- Do not mark uploads complete from database acknowledgements alone.
- After recovery, run lifecycle cleanup and recovery reconciliation.

### KMS unavailable

Symptoms:

- Multipart initiation or object metadata operations fail when encryption policy requires KMS.

Actions:

- Treat this as an explicit storage policy failure.
- Do not retry with encryption disabled.
- Verify KMS key reference and backend access policy.
- Audit any storage-policy changes.

### CORS misconfiguration

Symptoms:

- Browser direct upload fails before or during `PUT`.
- API presign succeeds but browser reports CORS or signed-header mismatch.

Actions:

- Check allowed origins, `PUT`, required signed headers, and exposed `ETag` or checksum headers.
- Keep production origins explicit.
- Do not add a backend file-byte proxy as a workaround.

### Leaked presigned URL

Symptoms:

- A signed object storage URL appears in a ticket, browser log, or external system.

Actions:

- Remove the signed query string from all durable records.
- Pause or abort affected sessions when policy requires it.
- Rotate storage credentials or apply a storage deny layer if immediate revocation is required.
- Rely on short expiry for already issued URLs when provider-side revocation is unavailable.

### Device compromise

Symptoms:

- Unexpected device authentication failures or suspicious upload requests.

Actions:

- Revoke or rotate device credentials.
- Audit recent device-scoped actions.
- Pause, abort, or reassign affected sessions according to policy.
- Remember that already issued presigned URLs may work until expiry.

### Cleanup backlog

Symptoms:

- `cleanup_expired_sessions_backlog` remains above zero.

Actions:

- Run the worker cleanup pass.
- Check storage abort errors.
- Verify session expiry and cleanup grace settings.
- Do not delete completed final objects as part of multipart cleanup.

### Outbox dead letters

Symptoms:

- `outbox_events_dead_lettered` is above zero.

Actions:

- Inspect the event type and last error.
- Fix downstream connectivity or payload handling.
- Replay only after confirming the domain transaction already committed.
- Keep failed outbox delivery separate from upload completion state.

### Recovery mismatch

Symptoms:

- `recovery_datasets_by_status` reports non-normal states.

Actions:

- Run recovery reconciliation against object storage.
- For metadata-only records, verify object existence before restoring exposure.
- For object-only records, keep objects hidden until operator review.
- Do not mark datasets `READY` solely because metadata exists.
