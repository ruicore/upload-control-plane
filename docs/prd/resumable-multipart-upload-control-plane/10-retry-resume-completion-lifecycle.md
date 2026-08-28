# Retry, Resume, Completion, and Lifecycle

Previous: [Security and Governance](09-security-governance.md) | Index: [README](README.md) | Next: [Client and Backend Implementation](11-client-and-backend-implementation.md)

## 18. Idempotency and Retry Semantics

### 18.1 Idempotency key behavior

For endpoints that accept `Idempotency-Key`:

1. Compute request fingerprint from method, path, authenticated tenant, and normalized JSON body.
2. Insert an `idempotency_records` row.
3. If insert conflicts:
   - Same fingerprint and completed response exists: return stored response.
   - Same fingerprint and request still processing: return `409` or wait briefly, depending on implementation.
   - Different fingerprint: return `409 idempotency.key_reused_with_different_request`.
4. Store response status and body after successful completion.

### 18.2 Retry behavior by endpoint

| Endpoint | Retry behavior |
|---|---|
| `POST /v1/projects/{id}/upload-tasks` | Idempotent by key; returns same task, objects, datasets, and sessions for same request |
| `POST /v1/uploads/{id}/parts/presign` | Safe to retry; may return new URLs with new expiry |
| `POST /v1/uploads/{id}/parts/ack` | Idempotent upsert |
| `GET /v1/uploads/{id}/parts` | Safe |
| `POST /v1/uploads/{id}/pause` | Idempotent if already paused; otherwise locked |
| `POST /v1/uploads/{id}/resume` | Idempotent if already uploading; otherwise locked |
| `POST /v1/uploads/{id}/complete` | Idempotent if already completed; otherwise locked |
| `POST /v1/uploads/{id}/abort` | Idempotent if already aborted |
| `POST /v1/projects/{id}/datasets` | Idempotent by key when provided |
| `POST /v1/projects/{id}/upload-tasks/{task_id}/pause` | Idempotent if already paused |
| `POST /v1/projects/{id}/upload-tasks/{task_id}/resume` | Idempotent if already processing |
| `POST /v1/projects/{id}/upload-tasks/{task_id}/cancel` | Idempotent if already cancelled |
| `POST /v1/projects/{id}/datasets/{dataset_id}/download-url` | Safe to retry; may return new URL with new expiry |
| `DELETE /v1/projects/{id}/datasets/{dataset_id}/purge` | Must be guarded by idempotency key or explicit purge confirmation token |

### 18.3 Storage retry policy

Storage calls should use bounded retries for transient failures.

Retryable examples:

- Network timeout.
- Connection reset.
- HTTP 429 / 500 / 502 / 503 / 504.

Non-retryable examples:

- Invalid upload ID.
- Invalid part number.
- Access denied due to wrong credentials.
- Entity too small during complete.

Use exponential backoff with jitter.

---


## 19. Resume Semantics

### 19.1 Client local manifest

The CLI/client must persist a local manifest, not presigned URLs.

Presigned URLs expire and should not be stored as durable state.

Manifest example:

```json
{
  "manifest_version": 1,
  "api_base_url": "http://localhost:8000",
  "project_id": "6cbce9cd-7d78-48dc-b89d-f13d724f3be8",
  "task_id": "b3fe6ef8-bb14-44a6-b8f0-124483e5d4d1",
  "object_id": "21cf75e2-70f8-4b9b-9144-1f97fe7d05f3",
  "dataset_id": "7af07a93-b4a9-48d5-8f3b-0184d2cc66bd",
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "file_path": "/data/front_camera.mp4",
  "original_filename": "front_camera.mp4",
  "file_size_bytes": 5368709120,
  "part_size_bytes": 67108864,
  "part_count": 80,
  "checksum_sha256": "optional-full-file-sha256-hex",
  "local_status": "UPLOADING",
  "paused_at": null,
  "parts": {
    "1": {
      "status": "UPLOADED",
      "etag": "\"9b2cf535f27731c974343645a3985328\"",
      "uploaded_at": "2026-06-10T08:34:01Z"
    }
  },
  "created_at": "2026-06-10T08:30:00Z",
  "updated_at": "2026-06-10T08:34:01Z"
}
```

### 19.2 Resume algorithm

Client resume flow:

```text
1. Load local manifest.
2. Call GET /v1/uploads/{session_id}.
3. If status is COMPLETED: exit success.
4. If status is ABORTED / FAILED: exit with clear error.
5. If status is PAUSED: require an explicit resume command or call POST /v1/uploads/{session_id}/resume when the user requested resume.
6. Call GET /v1/uploads/{session_id}/parts?source=reconcile.
7. Mark storage-observed parts as uploaded.
8. Compute missing part numbers.
9. For each missing part, request fresh presigned URL in batches.
10. Upload missing parts with concurrency limit.
11. Ack uploaded parts.
12. Call complete.
13. If complete returns missing parts, repeat from step 6.
```

### 19.3 Expired presigned URL behavior

If a part upload returns HTTP 403 or signature-expired-style error:

```text
1. Do not fail the session.
2. Request a new presigned URL for that part.
3. Retry the part upload.
```

### 19.4 Duplicate part upload behavior

If the client uploads the same part number again:

- This is allowed.
- Latest successful part overwrites the previous uploaded part for that part number.
- Client should ack the latest ETag.
- Complete should use storage-observed latest ETag.

### 19.5 Pause and resume semantics

Pause flow:

```text
1. User, Web UI, or MQTT command requests pause.
2. Client stops scheduling new part uploads.
3. Client either lets in-flight PUT requests finish or cancels them locally.
4. Client flushes local manifest immediately.
5. Backend marks session PAUSED when server-side pause is requested.
6. Future presign requests are rejected while PAUSED.
```

Resume flow:

```text
1. User, Web UI, or MQTT command requests resume.
2. Backend transitions PAUSED -> UPLOADING.
3. Client reloads local manifest.
4. Client reconciles with object storage through the API.
5. Client requests fresh presigned URLs for missing parts.
6. Client continues uploading missing parts.
```

Rules:

- Pause must not abort the multipart upload.
- Pause must not delete already uploaded parts.
- Presigned URLs must not be persisted across pause/resume.
- Resume always treats previously issued presigned URLs as expired or unsafe to reuse.
- If a part finishes after pause was requested, it is still valid if object storage lists it.
- If an in-flight part is cancelled, it is retried later as a missing part.

---


## 20. Completion Algorithm

Completion must be deterministic and storage-authoritative.

Pseudo-code:

```python
def complete_upload(session_id: UUID, actor: Actor) -> CompleteResponse:
    with transaction() as tx:
        session = repo.get_session_for_update(session_id, tenant_id=actor.tenant_id)
        previous_status = session.status

        if session.status == COMPLETED:
            return build_completed_response(session)

        if session.status in {ABORTING, ABORTED, EXPIRED, FAILED}:
            raise InvalidState(session.status)

        if session.status == COMPLETING:
            raise Conflict("completion already in progress")

        repo.transition(session, COMPLETING)
        repo.add_event("upload.complete_requested", session)

    storage_parts = storage.list_parts(
        bucket=session.bucket_name,
        object_key=session.object_key,
        upload_id=session.storage_upload_id,
    )

    validation = validate_storage_parts(session, storage_parts)
    if not validation.ok:
        with transaction() as tx:
            repo.transition(session, PAUSED if previous_status == PAUSED else UPLOADING)
            repo.reconcile_parts(session, storage_parts)
            repo.add_event("upload.complete_rejected_missing_parts", session, validation.details)
        raise MissingParts(validation.missing_part_numbers)

    result = storage.complete_multipart_upload(
        bucket=session.bucket_name,
        object_key=session.object_key,
        upload_id=session.storage_upload_id,
        parts=storage_parts,
    )

    with transaction() as tx:
        session = repo.get_session_for_update(session_id, tenant_id=actor.tenant_id)
        repo.mark_completed(session, result)
        repo.add_event("upload.completed", session, result)

    return build_completed_response(session)
```

Validation rules:

```python
def validate_storage_parts(session, parts):
    by_number = {p.part_number: p for p in parts}

    expected_numbers = set(range(1, session.part_count + 1))
    actual_numbers = set(by_number)

    missing = sorted(expected_numbers - actual_numbers)
    unexpected = sorted(actual_numbers - expected_numbers)

    if missing or unexpected:
        return invalid(missing=missing, unexpected=unexpected)

    for n in expected_numbers:
        expected_range = get_part_range(session.file_size_bytes, session.part_size_bytes, n)
        actual = by_number[n]
        if actual.size_bytes != expected_range.expected_size:
            return invalid(size_mismatch={n: [expected_range.expected_size, actual.size_bytes]})

    return valid(parts=sorted(parts, key=lambda p: p.part_number))
```

---


## 21. Cleanup and Lifecycle Management

### 21.1 Why cleanup is required

After multipart upload is initiated and parts are uploaded, object storage may retain uploaded parts until the upload is completed or aborted. Therefore abandoned uploads must be cleaned.

### 21.2 Expiry worker

Run a periodic worker, e.g. every 5 minutes.

Worker flow:

```text
1. Find sessions where status in INITIATED/UPLOADING/PAUSED and expires_at < now().
2. Mark them EXPIRED.
3. For expired sessions older than cleanup grace period, transition to ABORTING.
4. Call storage abort multipart upload.
5. Mark ABORTED.
6. Emit events and metrics.
```

### 21.3 Orphan multipart upload sweeper

Some failures can create storage-side multipart uploads that are not fully represented in DB.

Examples:

- Backend process crashes after storage create succeeds but before DB update.
- DB commit fails after storage upload ID is created.
- Manual test interrupted at the wrong moment.

The sweeper should:

- List incomplete multipart uploads in the configured bucket/prefix if available.
- Match by object key prefix and upload ID against DB.
- Abort uploads older than a configured threshold when no DB session exists.
- Emit metrics.

This can be implemented later if the storage SDK exposes needed APIs cleanly.

### 21.4 Final object retention

Abort must not delete completed objects.

Deleting final objects is a separate lifecycle policy and out of scope for core upload correctness.

### 21.5 Backup, restore, replication, and disaster recovery

The upload control plane has two authoritative persistence layers:

- PostgreSQL for metadata, authorization, lifecycle, audit, outbox, and idempotency state.
- Object storage for multipart parts and final object bytes.

Production deployments must define recovery behavior for both layers together.

Required planning:

- PostgreSQL must have a backup and point-in-time recovery strategy.
- Object storage must have a backup, replication, or mirror strategy appropriate to the deployment.
- RPO and RTO targets must be documented for metadata and object bytes separately.
- Restores must include a reconciliation run that compares DB upload/session/object records against object storage.
- Restored systems must not blindly mark datasets `READY`; they must verify object existence, size, checksum metadata when available, and retention/lock status.
- Replication status should be observable when the storage provider exposes it.
- Lifecycle expiration rules must be coordinated with replication. Edge or source buckets must not expire objects before required replication has completed.
- Disaster-recovery drills should include at least one incomplete multipart upload, one completed dataset, one soft-deleted dataset, and one retention-protected dataset.

Recommended recovery states:

```text
RECOVERY_PENDING
RECOVERY_VERIFIED
RECOVERY_MISSING_OBJECT
RECOVERY_METADATA_ONLY
RECOVERY_OBJECT_ONLY
```

The initial product stages may document these states without implementing an operator UI, but the schema and workers should not make recovery reconciliation impossible.

---


## 22. Checksum and Data Integrity Strategy

### 22.1 Modes

Support configurable checksum modes:

```text
NONE
CLIENT_REPORTED
SERVER_ASYNC_VALIDATE
SERVER_STRICT_VALIDATE
```

Recommended initial implementation:

```text
CLIENT_REPORTED
```

Optional later implementation:

```text
SERVER_ASYNC_VALIDATE
```

### 22.2 Client-reported checksum

Client may compute:

- Full-file SHA256.
- Per-part SHA256.

Benefits:

- Detect local file changes between init and resume.
- Improve auditability.
- Allow optional async server validation.

Limitations:

- Backend cannot trust it fully unless it validates.

### 22.3 Server async validation

After completion, a worker may stream the object from MinIO and compute SHA256.

Flow:

```text
1. Upload completed.
2. Worker reads object stream from MinIO.
3. Worker computes SHA256.
4. Compare with client-reported checksum.
5. Mark validation status PASSED or FAILED.
```

This is expensive for very large objects, so it should be optional.

### 22.4 Do not misuse ETag

Store ETag for S3 protocol completion and object identification, but do not present it as a full-file checksum.

### 22.5 Storage-native checksum mode

S3-compatible storage may support checksum algorithms such as:

```text
CRC64NVME
CRC32
CRC32C
SHA1
SHA256
```

Storage-native checksum support must be modeled as an adapter capability, not assumed globally.

Recommended policy values:

```text
STORAGE_NATIVE_CRC64NVME
STORAGE_NATIVE_CRC32C
STORAGE_NATIVE_SHA256
```

Storage-native checksum requirements:

- `create_multipart_upload` must accept a checksum algorithm when the policy requires it.
- `presign_upload_part` must include any required checksum headers in `required_headers`.
- The client must compute and send the signed checksum header when required.
- `list_parts` and `head_object` should capture provider-returned checksum fields when available.
- `complete_multipart_upload` must pass full-object or composite checksum fields only when supported and tested for the target provider.
- Checksum-enabled multipart uploads may require consecutive part numbers beginning at 1.
- A provider `BadDigest` or equivalent integrity error must transition the session or validation result to a clear failure state.
- MinIO and AWS S3 compatibility differences must be covered by integration tests before enabling this mode by default.

The initial product stages should keep `CLIENT_REPORTED` as the default, but the adapter and schema should not block storage-native checksum adoption.

---

