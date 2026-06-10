# Industrial-Grade Resumable Multipart Upload Control Plane

**Document version:** 1.0
**Document date:** 2026-06-10
**Primary implementation language:** Python first; optional Go components later
**Primary object storage:** MinIO, using S3-compatible multipart upload APIs
**Primary purpose:** portfolio-grade, production-oriented system design and implementation constraint document
**Intended downstream user:** Codex or any implementation agent working from this document

---

## 0. Executive Summary

This repository will implement an industrial-grade large-file upload control plane for AI / robotics / industrial data ingestion scenarios.

The system must support:

- Large file upload using S3-compatible Multipart Upload.
- Client-side file slicing and direct part upload to MinIO.
- Backend-controlled upload lifecycle: initiate, presign, resume, complete, abort, expire, cleanup.
- No file bytes passing through the backend API service.
- Per-tenant authorization and object-key isolation.
- Resumability after client crash, robot power loss, network outage, or presigned URL expiry.
- Idempotent APIs for repeated client calls and retry-safe behavior.
- Strong state machine discipline.
- PostgreSQL-backed metadata and audit history.
- MinIO-backed object storage for local and deployable environments.
- Observability, structured logs, metrics, tracing hooks, and failure injection tests.
- A Python CLI uploader first, with optional Go uploader or Go edge/API component later.

This is not a toy upload demo. It should be implemented as a production-oriented upload control plane. The project does not claim real-world production adoption, but the architecture, failure handling, API contracts, test suite, and documentation should be designed to production standards.

---

## 1. Non-Negotiable Design Decisions

Codex must treat this section as hard constraints.

### 1.1 Backend must never proxy file bytes

The backend API service must not receive large file bodies.

Forbidden architecture:

```text
Client / Robot App
    │ file bytes
    ▼
Backend API
    │ file bytes
    ▼
MinIO / S3
```

Required architecture:

```text
Client / Robot App
    │ control-plane API calls only
    ▼
Upload Control Plane
    │ uses storage credentials to create upload and sign part URLs
    ▼
MinIO / S3-compatible storage

Client / Robot App
    │ direct PUT part bytes through presigned URLs
    ▼
MinIO / S3-compatible storage
```

The backend may receive metadata, ETags, checksums, status reports, and control-plane commands. It must not receive multipart file content.

### 1.2 Client performs file slicing

The client is responsible for:

- Opening the local file.
- Computing part boundaries.
- Reading only the byte range for each part.
- Uploading each part to its presigned URL.
- Persisting a local upload manifest for resume.
- Retrying failed parts.
- Requesting new presigned URLs when previous URLs expire.

The backend is responsible for:

- Validating upload intent.
- Creating a multipart upload session in MinIO.
- Generating presigned URLs for specific `part_number` values.
- Tracking metadata and state transitions.
- Listing uploaded parts from object storage.
- Completing or aborting multipart upload.
- Expiring and cleaning abandoned sessions.

### 1.3 Client must not hold object-storage credentials

The client must not receive MinIO access keys or secret keys.

Only the backend service holds MinIO credentials. The client receives short-lived presigned URLs scoped to specific S3 operations.

### 1.4 Each uploaded part has its own presigned URL

For multipart upload, each part upload is a distinct signed request containing at least:

- Bucket.
- Object key.
- Upload ID.
- Part number.
- HTTP method.
- Expiry.

The presigned URL for part 1 is not the same as the presigned URL for part 2.

### 1.5 Presigned URLs are renewable

A presigned URL may expire. Expiry is normal, not fatal.

If the client loses network connectivity and later resumes after URL expiry, it must request a new presigned URL for the same `session_id` and `part_number`.

The same part number may be uploaded again. Object storage uses the latest successfully uploaded part for that part number.

### 1.6 Database state is not enough to complete an upload

Before completing a multipart upload, the backend must verify uploaded parts against object storage using `ListParts` or equivalent storage adapter behavior.

Client-reported ETags are useful for progress and debugging, but object storage is the authority for which parts actually exist.

### 1.7 ETag must not be treated as a universal MD5 checksum

The system may store ETags because S3-compatible multipart completion needs them, but the implementation must not assume an ETag always equals an MD5 digest of the full object.

Full-object integrity must be modeled explicitly through checksum fields and/or async validation workers.

### 1.8 All state-changing APIs must be retry-safe

The client may retry due to:

- Network timeout.
- 5xx from API service.
- 5xx from storage.
- Process crash after a successful server-side operation but before receiving a response.

Therefore, state-changing endpoints must support idempotency or deterministic retry behavior.

### 1.9 Object keys must be server-generated

Clients may provide original filenames and metadata, but must not directly control final object keys.

Object keys must be generated by the backend using tenant-safe, prefix-isolated rules.

### 1.10 Implementation must remain storage-adapter based

The first backend storage target is MinIO. However, the code must use a storage adapter interface so the core application logic is not tightly coupled to MinIO or boto3.

---

## 2. Problem Background

Industrial AI, robotics, autonomous systems, and data-platform workloads often generate large files:

- Robot sensor logs.
- Video streams.
- LiDAR frames.
- ROS bag files.
- Model training datasets.
- Edge-device diagnostic bundles.
- Industrial inspection images.
- Long-running telemetry archives.

These files may be uploaded from unstable environments:

- Factory Wi-Fi.
- 4G / 5G edge networks.
- Robot docking stations.
- Remote sites.
- Intermittent VPN connectivity.
- Devices that may reboot or lose power.

A single large `PUT` upload is fragile. If a 100 GB file fails at 98 GB, restarting the entire upload is unacceptable. A reliable system must upload in independently retryable parts.

S3-compatible multipart upload solves this by splitting an object into parts that can be uploaded independently and then completed into one final object.

---

## 3. Official Behavior and Storage Limits Used by This Design

This project uses S3-compatible Multipart Upload as the baseline protocol.

The design should follow these portability constraints unless explicitly configured otherwise:

| Constraint | Project default |
|---|---:|
| Minimum non-final part size | 5 MiB |
| Recommended minimum practical part size | 64 MiB |
| Maximum portable part size | 5 GiB |
| Maximum number of parts | 10,000 |
| Part number range | 1 to 10,000 |
| Default presigned URL expiry | 15 minutes |
| Maximum presigned URL expiry in this app | 6 hours by policy, configurable |
| Default upload session expiry | 24 hours, configurable |
| Default cleanup grace period | 2 hours after session expiry |

Notes:

- AWS S3 documentation currently specifies multipart limits including 10,000 parts, part numbers from 1 to 10,000, and part size from 5 MiB to 5 GiB with no minimum size for the last part.
- Current AWS S3 multipart limit documentation lists a maximum object size of 48.8 TiB.
- MinIO has its own current documented limits. At the time of this document, MinIO documents a 50 TiB maximum object size, 10,000 parts per upload, and a larger MinIO-specific maximum part size. This project should still default to the stricter S3-compatible part-size ceiling of 5 GiB for portability.
- Multipart upload completion must provide part numbers and ETags in ascending part order.
- Object storage can list parts of an in-progress upload; AWS S3 returns up to 1,000 parts per `ListParts` response, so the adapter must support pagination even if MinIO returns more.

References are listed in [Section 31](#31-source-references).

---

## 4. Project Name and Positioning

Recommended repository name:

```text
upload-control-plane
```

Alternative names:

```text
industrial-upload-control-plane
resumable-upload-control-plane
robot-data-upload-control-plane
```

Recommended one-line description:

```text
Production-oriented resumable multipart upload control plane for AI and robotics data ingestion, using FastAPI, PostgreSQL, and MinIO.
```

Recommended GitHub topic tags:

```text
multipart-upload
s3
minio
fastapi
postgresql
resumable-upload
large-file-upload
robotics
ai-infrastructure
data-ingestion
observability
```

---

## 5. Goals

### 5.1 Functional goals

The system must support:

1. Creating an upload session for one large file.
2. Creating a batch upload for a logical dataset containing multiple file uploads.
3. Generating presigned URLs for one or more part numbers.
4. Direct client-to-MinIO part upload.
5. Client resume after interruption.
6. Server-side reconciliation using `ListParts`.
7. Completing multipart upload only when all expected parts exist.
8. Aborting multipart upload.
9. Expiring stale sessions.
10. Cleaning abandoned multipart uploads.
11. Recording upload lifecycle events.
12. Recording optional client-reported ETags and part checksums.
13. Enforcing tenant/user/device authorization.
14. Enforcing object-key namespace isolation.
15. Providing a CLI uploader for E2E testing and real demonstration.
16. Providing OpenAPI documentation.
17. Providing deterministic local development through Docker Compose.
18. Providing integration tests using real PostgreSQL and real MinIO.
19. Providing failure injection tests.
20. Providing benchmark scripts.

### 5.2 Non-functional goals

The system should demonstrate:

- Reliability under network failure.
- Retry-safe API design.
- Clear state machine ownership.
- High concurrency at the upload data plane because file bytes go directly to MinIO.
- Bounded backend CPU, memory, and network usage.
- Secure credential handling.
- Clear observability.
- Testability.
- Maintainable architecture.
- Future portability to AWS S3, Alibaba OSS, Tencent COS, or other S3-compatible storage.

---

## 6. Non-Goals

The first complete design does not need to implement:

- Browser UI dashboard, although API design should allow it later.
- Real payment or quota billing.
- Real enterprise SSO.
- Multi-region active-active object replication.
- Custom binary transport protocol.
- tus protocol support.
- Direct backend file streaming upload.
- Virus scanning as a blocking step.
- Real production deployment to Kubernetes on day one.

Optional future extensions are allowed, but Codex must not implement them before core upload correctness is complete.

---

## 7. System Architecture

### 7.1 High-level architecture

```text
┌────────────────────┐
│ Robot App / CLI    │
│ / Edge Device      │
└─────────┬──────────┘
          │
          │ Control-plane API:
          │ init, presign, status, complete, abort
          ▼
┌──────────────────────────────────────────────┐
│ Upload Control Plane API                     │
│ FastAPI                                      │
│                                              │
│ Responsibilities:                            │
│ - AuthN/AuthZ                                │
│ - Upload session state machine               │
│ - Presigned URL generation                   │
│ - Metadata validation                        │
│ - Complete / Abort orchestration             │
│ - Reconciliation with object storage         │
│ - Observability                              │
└─────────┬─────────────────────┬──────────────┘
          │                     │
          │ SQL metadata         │ S3-compatible control APIs
          ▼                     ▼
┌────────────────────┐   ┌────────────────────┐
│ PostgreSQL         │   │ MinIO              │
│                    │   │                    │
│ - sessions         │   │ - multipart upload │
│ - parts            │   │ - part storage     │
│ - batches          │   │ - final objects    │
│ - events           │   │                    │
└────────────────────┘   └─────────▲──────────┘
                                    │
                                    │ Data-plane direct upload:
                                    │ PUT part bytes via presigned URL
                                    │
                         ┌──────────┴─────────┐
                         │ Robot App / CLI    │
                         └────────────────────┘
```

### 7.2 Control plane vs data plane

Control plane:

- Low bandwidth.
- JSON APIs.
- Authentication and authorization.
- Session state.
- Presigned URL generation.
- Completion and cleanup.

Data plane:

- High bandwidth.
- Part bytes.
- Direct client-to-MinIO `PUT` requests.
- No backend involvement in file body transfer.

### 7.3 Component responsibilities

| Component | Responsibilities | Must not do |
|---|---|---|
| Robot App / CLI | Slice file, request URLs, upload parts, retry, persist manifest, report progress | Hold MinIO credentials |
| Upload API | Auth, session creation, presign, status, complete, abort, validation | Accept file bytes |
| Worker | Expire sessions, abort stale storage uploads, reconcile orphan state, async checksum validation | Serve user upload traffic |
| PostgreSQL | Store durable metadata, state, audit events, idempotency records | Store file bytes |
| MinIO | Store multipart parts and final objects | Decide application-level tenant authorization |
| Optional Go uploader | Higher-performance client-side upload implementation | Replace core correctness model |
| Optional Go edge gateway | API routing/auth/rate-limit for control-plane requests | Proxy large file bytes |

---

## 8. Core Domain Model

### 8.1 Upload batch

An upload batch groups multiple file upload sessions into one logical dataset or ingestion job.

Example:

```text
Batch: robot-run-2026-06-10-shanghai-factory-line-3
  - front_camera.mp4
  - rear_camera.mp4
  - lidar.bin
  - robot_state.jsonl
  - diagnostics.zip
```

A batch is optional. A file upload can exist without a batch.

### 8.2 Upload session

An upload session represents one logical final object.

It owns:

- Tenant ID.
- Optional batch ID.
- Object key.
- Original filename.
- File size.
- Part size.
- Part count.
- Storage upload ID.
- Status.
- Expiry.
- Metadata.

### 8.3 Upload part

An upload part represents one expected or observed part of a file.

It owns:

- Session ID.
- Part number.
- Expected offset.
- Expected size.
- Optional ETag.
- Optional checksum.
- Status.
- Uploaded timestamp.

The system does not need to eagerly insert all part rows at initiation time. It may compute expected ranges dynamically and upsert observed parts.

### 8.4 Storage object

The final completed object is represented by:

- Bucket.
- Object key.
- Object size.
- Storage ETag.
- Optional version ID.
- Optional checksum.
- Completed timestamp.

### 8.5 Upload lifecycle event

Every important action should create an audit event:

- `upload.initiated`
- `upload.presign_issued`
- `upload.part_acknowledged`
- `upload.parts_reconciled`
- `upload.complete_requested`
- `upload.completed`
- `upload.abort_requested`
- `upload.aborted`
- `upload.expired`
- `upload.cleanup_failed`
- `upload.failed`

Events are append-only.

---

## 9. State Machine

### 9.1 Upload session statuses

Use the following states:

```text
INITIATING
INITIATED
UPLOADING
COMPLETING
COMPLETED
ABORTING
ABORTED
EXPIRED
FAILED
```

### 9.2 State definitions

| State | Meaning |
|---|---|
| `INITIATING` | DB record exists, storage multipart upload is being created or persisted |
| `INITIATED` | Storage upload ID exists; no confirmed upload progress yet |
| `UPLOADING` | One or more presigned URLs issued or parts acknowledged/listed |
| `COMPLETING` | Completion is in progress; presign should be rejected |
| `COMPLETED` | Final object exists; multipart parts are assembled |
| `ABORTING` | Abort is in progress |
| `ABORTED` | Multipart upload has been aborted or considered aborted |
| `EXPIRED` | App-level session expired before completion |
| `FAILED` | Terminal failure requiring manual or automated remediation |

### 9.3 Allowed transitions

| From | To | Trigger |
|---|---|---|
| none | `INITIATING` | `POST /v1/uploads` accepted |
| `INITIATING` | `INITIATED` | Storage create multipart upload succeeded and DB updated |
| `INITIATING` | `FAILED` | Storage create failed permanently |
| `INITIATED` | `UPLOADING` | Presign issued or part acknowledged |
| `UPLOADING` | `UPLOADING` | More parts uploaded, listed, or acknowledged |
| `INITIATED` | `COMPLETING` | Complete requested and all parts exist |
| `UPLOADING` | `COMPLETING` | Complete requested and all parts exist |
| `COMPLETING` | `COMPLETED` | Storage complete succeeded |
| `COMPLETING` | `FAILED` | Storage complete failed non-retryably |
| `INITIATED` | `ABORTING` | Abort requested or cleanup worker starts abort |
| `UPLOADING` | `ABORTING` | Abort requested or cleanup worker starts abort |
| `EXPIRED` | `ABORTING` | Cleanup worker starts abort |
| `ABORTING` | `ABORTED` | Storage abort succeeded or upload no longer exists |
| `INITIATED` | `EXPIRED` | Session expiry reached |
| `UPLOADING` | `EXPIRED` | Session expiry reached |
| any non-terminal | `FAILED` | Internal unrecoverable error |

Terminal states:

```text
COMPLETED
ABORTED
FAILED
```

`EXPIRED` is not terminal because cleanup may transition it to `ABORTING` and then `ABORTED`.

### 9.4 Invalid transitions

Codex must reject:

- `COMPLETED` -> anything else.
- `ABORTED` -> `UPLOADING` or `COMPLETING`.
- `FAILED` -> `UPLOADING` unless an explicit repair endpoint is added later.
- Presign requests for `COMPLETING`, `COMPLETED`, `ABORTING`, `ABORTED`, `FAILED`.
- Complete requests for `ABORTING`, `ABORTED`, `EXPIRED`, `FAILED`.

### 9.5 Race control

Completion and abort must acquire a session-level lock.

Acceptable implementations:

- PostgreSQL row lock using `SELECT ... FOR UPDATE`.
- PostgreSQL advisory lock keyed by session UUID.
- Optimistic version field with retry, if carefully implemented.

Recommended first implementation:

- Use `SELECT ... FOR UPDATE` inside transaction for state transition checks.
- Set status to `COMPLETING` or `ABORTING` before calling long-running storage operation.
- Record lifecycle event.
- Perform storage call.
- Re-open transaction and mark final state.

---

## 10. API Contract

All public API routes must be versioned under:

```text
/v1
```

All JSON fields should use `snake_case`.

All responses must include a request ID header:

```text
X-Request-ID: <uuid-or-trace-id>
```

All state-changing client endpoints should accept:

```text
Idempotency-Key: <client-generated-key>
```

### 10.1 Authentication model

For portfolio implementation, support API key authentication first.

Required header:

```http
Authorization: Bearer <api_key>
```

The API key maps to:

- Tenant ID.
- Principal ID.
- Allowed scopes.
- Optional device ID restrictions.

Later, this may be replaced or extended by JWT/OIDC.

### 10.2 Error response format

All errors must follow this shape:

```json
{
  "error": {
    "code": "upload.invalid_state",
    "message": "Upload session is not in a state that allows presigning parts.",
    "details": {
      "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
      "current_status": "COMPLETING"
    },
    "request_id": "req_01J..."
  }
}
```

Error codes must be stable and test-covered.

---

## 11. Upload Batch APIs

### 11.1 Create upload batch

```http
POST /v1/upload-batches
Authorization: Bearer <api_key>
Idempotency-Key: <key>
Content-Type: application/json
```

Request:

```json
{
  "name": "robot-run-2026-06-10-line-3",
  "source_device_id": "robot-17",
  "expected_file_count": 5,
  "expected_total_size_bytes": 23891238912,
  "metadata": {
    "site": "factory-shanghai",
    "line": "3",
    "mission_id": "mission-20260610-001"
  }
}
```

Response `201 Created`:

```json
{
  "batch_id": "5e17d62f-1c65-4f49-85c1-7cd78356a582",
  "status": "OPEN",
  "created_at": "2026-06-10T08:30:00Z"
}
```

### 11.2 Get batch status

```http
GET /v1/upload-batches/{batch_id}
Authorization: Bearer <api_key>
```

Response:

```json
{
  "batch_id": "5e17d62f-1c65-4f49-85c1-7cd78356a582",
  "status": "OPEN",
  "expected_file_count": 5,
  "actual_file_count": 3,
  "completed_file_count": 2,
  "failed_file_count": 0,
  "expected_total_size_bytes": 23891238912,
  "completed_size_bytes": 10737418240,
  "uploads": [
    {
      "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
      "original_filename": "front_camera.mp4",
      "status": "COMPLETED",
      "file_size_bytes": 5368709120
    }
  ]
}
```

### 11.3 Complete batch

```http
POST /v1/upload-batches/{batch_id}/complete
Authorization: Bearer <api_key>
Idempotency-Key: <key>
```

Rules:

- Batch can only complete if all child upload sessions are `COMPLETED`.
- If any upload is incomplete, return `409 Conflict`.
- Completion is idempotent.

Response:

```json
{
  "batch_id": "5e17d62f-1c65-4f49-85c1-7cd78356a582",
  "status": "COMPLETED",
  "completed_at": "2026-06-10T09:14:12Z"
}
```

---

## 12. File Upload APIs

### 12.1 Create upload session

```http
POST /v1/uploads
Authorization: Bearer <api_key>
Idempotency-Key: <key>
Content-Type: application/json
```

Request:

```json
{
  "batch_id": "5e17d62f-1c65-4f49-85c1-7cd78356a582",
  "original_filename": "front_camera.mp4",
  "file_size_bytes": 5368709120,
  "content_type": "video/mp4",
  "part_size_bytes": 67108864,
  "checksum_sha256": "optional-full-file-sha256-hex",
  "source_device_id": "robot-17",
  "metadata": {
    "camera": "front",
    "recorded_at": "2026-06-10T08:00:00Z"
  }
}
```

Rules:

- `file_size_bytes` must be positive.
- `part_size_bytes` is optional. If omitted, server chooses it.
- Non-final part size must be at least 5 MiB.
- The resulting part count must be less than or equal to 10,000.
- Server must generate the object key.
- Server must reject path traversal in filenames.
- Server must reject unsupported or disallowed content types if configured.
- Server must create the multipart upload in MinIO and persist the returned storage upload ID.

Response `201 Created`:

```json
{
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "batch_id": "5e17d62f-1c65-4f49-85c1-7cd78356a582",
  "status": "INITIATED",
  "bucket": "robot-data",
  "object_key": "tenants/tnt_123/2026/06/10/2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9/front_camera.mp4",
  "file_size_bytes": 5368709120,
  "part_size_bytes": 67108864,
  "part_count": 80,
  "expires_at": "2026-06-11T08:30:00Z",
  "created_at": "2026-06-10T08:30:00Z"
}
```

Do not return the raw MinIO access key, secret key, or any long-lived storage credential.

The raw storage upload ID may be stored in DB. It does not need to be returned to the client because presigned URLs encode what the client needs. Returning only `session_id` is preferred.

### 12.2 Get upload session

```http
GET /v1/uploads/{session_id}
Authorization: Bearer <api_key>
```

Response:

```json
{
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "status": "UPLOADING",
  "bucket": "robot-data",
  "object_key": "tenants/tnt_123/2026/06/10/2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9/front_camera.mp4",
  "original_filename": "front_camera.mp4",
  "file_size_bytes": 5368709120,
  "part_size_bytes": 67108864,
  "part_count": 80,
  "uploaded_part_count": 41,
  "missing_part_count": 39,
  "expires_at": "2026-06-11T08:30:00Z",
  "created_at": "2026-06-10T08:30:00Z",
  "updated_at": "2026-06-10T08:43:21Z"
}
```

This endpoint may use DB state only for speed. It should not call `ListParts` on every request unless `?reconcile=true` is set.

### 12.3 Presign parts

```http
POST /v1/uploads/{session_id}/parts/presign
Authorization: Bearer <api_key>
Content-Type: application/json
```

Request:

```json
{
  "part_numbers": [1, 2, 3, 4],
  "expires_in_seconds": 900
}
```

Alternative range request:

```json
{
  "part_number_start": 1,
  "part_number_end": 20,
  "expires_in_seconds": 900
}
```

Rules:

- Caller must own the session's tenant.
- Session status must allow upload.
- Each part number must be within `[1, part_count]`.
- Maximum number of URLs per request should be limited, default 100.
- `expires_in_seconds` must be bounded by server policy.
- Response must not be cached by shared caches.
- Signed URLs must not be logged.

Response:

```json
{
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "method": "PUT",
  "expires_at": "2026-06-10T08:45:00Z",
  "parts": [
    {
      "part_number": 1,
      "url": "http://localhost:9000/robot-data/...?partNumber=1&uploadId=...&X-Amz-Signature=...",
      "expected_size_bytes": 67108864,
      "offset_start": 0,
      "offset_end_exclusive": 67108864,
      "required_headers": {}
    },
    {
      "part_number": 2,
      "url": "http://localhost:9000/robot-data/...?partNumber=2&uploadId=...&X-Amz-Signature=...",
      "expected_size_bytes": 67108864,
      "offset_start": 67108864,
      "offset_end_exclusive": 134217728,
      "required_headers": {}
    }
  ]
}
```

Client upload behavior:

```http
PUT <presigned-url-for-part-N>
Content-Length: <part-size>

<exact bytes for part N>
```

Successful storage response should include an `ETag` header. The client should record it locally and may acknowledge it to the control plane.

### 12.4 Acknowledge uploaded parts

```http
POST /v1/uploads/{session_id}/parts/ack
Authorization: Bearer <api_key>
Content-Type: application/json
```

Request:

```json
{
  "parts": [
    {
      "part_number": 1,
      "etag": "\"9b2cf535f27731c974343645a3985328\"",
      "size_bytes": 67108864,
      "checksum_sha256": "optional-part-sha256-hex"
    }
  ]
}
```

Rules:

- This endpoint is optional for correctness but useful for progress.
- It must upsert part rows idempotently.
- It must not blindly trust the part as final proof.
- If the same part is acknowledged with a different ETag, store the latest ETag and create an event.
- Complete must still reconcile with object storage.

Response:

```json
{
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "acknowledged_part_count": 1,
  "uploaded_part_count": 41
}
```

### 12.5 List parts / reconcile parts

```http
GET /v1/uploads/{session_id}/parts
Authorization: Bearer <api_key>
```

Optional query:

```text
?source=db
?source=storage
?source=reconcile
```

Rules:

- `source=db` returns locally acknowledged state.
- `source=storage` calls object storage `ListParts` and returns observed storage parts.
- `source=reconcile` calls object storage, updates DB part rows, and returns reconciled state.

Response:

```json
{
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "source": "reconcile",
  "part_count": 80,
  "uploaded_part_count": 41,
  "missing_part_numbers": [42, 43, 44],
  "parts": [
    {
      "part_number": 1,
      "etag": "\"9b2cf535f27731c974343645a3985328\"",
      "size_bytes": 67108864,
      "status": "UPLOADED",
      "uploaded_at": "2026-06-10T08:34:01Z"
    }
  ]
}
```

For large part counts, support pagination:

```text
GET /v1/uploads/{session_id}/parts?source=db&limit=500&cursor=...
```

### 12.6 Complete upload

```http
POST /v1/uploads/{session_id}/complete
Authorization: Bearer <api_key>
Idempotency-Key: <key>
Content-Type: application/json
```

Request:

```json
{
  "client_reported_parts": [
    {
      "part_number": 1,
      "etag": "\"9b2cf535f27731c974343645a3985328\""
    }
  ],
  "checksum_sha256": "optional-full-file-sha256-hex"
}
```

Rules:

- `client_reported_parts` is optional and not authoritative.
- Backend must call storage `ListParts` and build the final completion parts list from storage-observed parts.
- Backend must verify all expected part numbers from `1..part_count` exist.
- Backend must verify all non-final parts have expected size.
- Backend should verify final part size equals `file_size_bytes - part_size_bytes * (part_count - 1)`.
- If any part is missing, return `409 Conflict` with missing part numbers or a truncated summary.
- If already `COMPLETED`, return the previous completion result idempotently.
- If complete succeeds but DB update fails, a repair/reconcile command must be able to mark the session completed after checking final object existence.

Response `200 OK`:

```json
{
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "status": "COMPLETED",
  "bucket": "robot-data",
  "object_key": "tenants/tnt_123/2026/06/10/2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9/front_camera.mp4",
  "object_size_bytes": 5368709120,
  "etag": "\"final-storage-etag\"",
  "completed_at": "2026-06-10T08:59:00Z"
}
```

Missing part response `409 Conflict`:

```json
{
  "error": {
    "code": "upload.missing_parts",
    "message": "Upload cannot be completed because some parts are missing.",
    "details": {
      "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
      "missing_part_count": 3,
      "missing_part_numbers": [42, 43, 44]
    },
    "request_id": "req_01J..."
  }
}
```

### 12.7 Abort upload

```http
POST /v1/uploads/{session_id}/abort
Authorization: Bearer <api_key>
Idempotency-Key: <key>
Content-Type: application/json
```

Request:

```json
{
  "reason": "client_cancelled"
}
```

Rules:

- Abort is idempotent.
- If already `ABORTED`, return success.
- If already `COMPLETED`, return `409 Conflict`; do not delete the final object.
- If storage says upload no longer exists, mark as `ABORTED` if final object does not exist.

Response:

```json
{
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "status": "ABORTED",
  "aborted_at": "2026-06-10T08:52:00Z"
}
```

### 12.8 Extend session expiry

```http
POST /v1/uploads/{session_id}/extend
Authorization: Bearer <api_key>
Idempotency-Key: <key>
Content-Type: application/json
```

Request:

```json
{
  "extend_by_seconds": 86400,
  "reason": "device_offline_recovery"
}
```

Rules:

- Optional endpoint.
- May be disabled by config.
- Must enforce maximum lifetime.
- Must reject terminal states.

---

## 13. Part Sizing Rules

### 13.1 Required function

Implement a pure function:

```python
def choose_part_size(file_size_bytes: int, requested_part_size_bytes: int | None) -> int:
    ...
```

### 13.2 Constraints

Constants:

```python
MIB = 1024 * 1024
GIB = 1024 * MIB
MIN_PART_SIZE = 5 * MIB
DEFAULT_PART_SIZE = 64 * MIB
MAX_PART_SIZE = 5 * GIB
MAX_PART_COUNT = 10_000
```

Rules:

1. If `requested_part_size_bytes` is provided, validate it.
2. If omitted, choose a value that keeps part count <= 10,000.
3. Prefer 64 MiB as the minimum practical default for large files.
4. Round chosen part size up to a MiB boundary.
5. The last part may be smaller than 5 MiB.
6. Reject file sizes that cannot fit within configured constraints.

Pseudo-code:

```python
def choose_part_size(file_size_bytes: int, requested: int | None) -> int:
    if file_size_bytes <= 0:
        raise ValidationError("file size must be positive")

    if requested is not None:
        if requested < MIN_PART_SIZE:
            raise ValidationError("part size too small")
        if requested > MAX_PART_SIZE:
            raise ValidationError("part size too large")
        part_size = requested
    else:
        minimum_to_fit = ceil_div(file_size_bytes, MAX_PART_COUNT)
        part_size = max(DEFAULT_PART_SIZE, minimum_to_fit, MIN_PART_SIZE)
        part_size = round_up_to_mib(part_size)

    part_count = ceil_div(file_size_bytes, part_size)
    if part_count > MAX_PART_COUNT:
        raise ValidationError("file requires too many parts")

    return part_size
```

### 13.3 Expected part range function

Implement:

```python
def get_part_range(file_size_bytes: int, part_size_bytes: int, part_number: int) -> PartRange:
    ...
```

For part `n`:

```text
offset_start = (n - 1) * part_size_bytes
offset_end_exclusive = min(offset_start + part_size_bytes, file_size_bytes)
expected_size = offset_end_exclusive - offset_start
```

Rules:

- Part numbers start at 1.
- Part numbers greater than `part_count` are invalid.
- Last part size may be smaller.

---

## 14. Database Schema

Use PostgreSQL.

Use Alembic migrations.

Use UUID primary keys.

Use `timestamptz` for all timestamps.

Use `jsonb` for metadata.

### 14.1 Enum types

```sql
CREATE TYPE upload_session_status AS ENUM (
  'INITIATING',
  'INITIATED',
  'UPLOADING',
  'COMPLETING',
  'COMPLETED',
  'ABORTING',
  'ABORTED',
  'EXPIRED',
  'FAILED'
);

CREATE TYPE upload_part_status AS ENUM (
  'EXPECTED',
  'PRESIGNED',
  'UPLOADED',
  'MISSING',
  'FAILED'
);

CREATE TYPE upload_batch_status AS ENUM (
  'OPEN',
  'COMPLETING',
  'COMPLETED',
  'ABORTED',
  'FAILED'
);
```

### 14.2 Tenants

```sql
CREATE TABLE tenants (
  id UUID PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 14.3 API keys

For portfolio implementation, store hashed API keys.

```sql
CREATE TABLE api_keys (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  key_hash TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  expires_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at TIMESTAMPTZ NULL
);

CREATE INDEX idx_api_keys_tenant_id ON api_keys(tenant_id);
```

Do not store raw API keys.

### 14.4 Upload batches

```sql
CREATE TABLE upload_batches (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  source_device_id TEXT NULL,
  status upload_batch_status NOT NULL DEFAULT 'OPEN',
  expected_file_count INTEGER NULL,
  expected_total_size_bytes BIGINT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ NULL,
  failed_at TIMESTAMPTZ NULL,
  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX idx_upload_batches_tenant_status ON upload_batches(tenant_id, status);
```

### 14.5 Upload sessions

```sql
CREATE TABLE upload_sessions (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  batch_id UUID NULL REFERENCES upload_batches(id),

  status upload_session_status NOT NULL DEFAULT 'INITIATING',

  bucket_name TEXT NOT NULL,
  object_key TEXT NOT NULL,
  storage_provider TEXT NOT NULL DEFAULT 'minio',
  storage_upload_id TEXT NULL,

  original_filename TEXT NOT NULL,
  content_type TEXT NULL,
  file_size_bytes BIGINT NOT NULL,
  part_size_bytes BIGINT NOT NULL,
  part_count INTEGER NOT NULL,

  checksum_sha256 TEXT NULL,
  checksum_mode TEXT NOT NULL DEFAULT 'CLIENT_REPORTED',

  source_device_id TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

  idempotency_key TEXT NULL,
  request_fingerprint TEXT NULL,

  uploaded_part_count INTEGER NOT NULL DEFAULT 0,
  completed_part_count INTEGER NOT NULL DEFAULT 0,

  object_etag TEXT NULL,
  object_size_bytes BIGINT NULL,
  object_version_id TEXT NULL,

  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ NULL,
  aborted_at TIMESTAMPTZ NULL,
  failed_at TIMESTAMPTZ NULL,

  last_error_code TEXT NULL,
  last_error_message TEXT NULL,

  version INTEGER NOT NULL DEFAULT 1,

  CONSTRAINT upload_sessions_file_size_positive CHECK (file_size_bytes > 0),
  CONSTRAINT upload_sessions_part_size_positive CHECK (part_size_bytes > 0),
  CONSTRAINT upload_sessions_part_count_valid CHECK (part_count >= 1 AND part_count <= 10000),
  CONSTRAINT upload_sessions_object_key_unique UNIQUE (bucket_name, object_key),
  CONSTRAINT upload_sessions_idempotency_unique UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX idx_upload_sessions_tenant_status ON upload_sessions(tenant_id, status);
CREATE INDEX idx_upload_sessions_batch_id ON upload_sessions(batch_id);
CREATE INDEX idx_upload_sessions_expires_at ON upload_sessions(expires_at);
CREATE INDEX idx_upload_sessions_storage_upload_id ON upload_sessions(storage_upload_id);
```

### 14.6 Upload parts

```sql
CREATE TABLE upload_parts (
  session_id UUID NOT NULL REFERENCES upload_sessions(id) ON DELETE CASCADE,
  part_number INTEGER NOT NULL,

  status upload_part_status NOT NULL DEFAULT 'EXPECTED',

  offset_start BIGINT NOT NULL,
  offset_end_exclusive BIGINT NOT NULL,
  expected_size_bytes BIGINT NOT NULL,

  etag TEXT NULL,
  size_bytes BIGINT NULL,
  checksum_sha256 TEXT NULL,

  last_presigned_at TIMESTAMPTZ NULL,
  presign_expires_at TIMESTAMPTZ NULL,
  uploaded_at TIMESTAMPTZ NULL,

  source TEXT NOT NULL DEFAULT 'db',

  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (session_id, part_number),
  CONSTRAINT upload_parts_part_number_valid CHECK (part_number >= 1 AND part_number <= 10000),
  CONSTRAINT upload_parts_expected_size_positive CHECK (expected_size_bytes >= 0)
);

CREATE INDEX idx_upload_parts_session_status ON upload_parts(session_id, status);
```

### 14.7 Upload events

```sql
CREATE TABLE upload_events (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  session_id UUID NULL REFERENCES upload_sessions(id) ON DELETE CASCADE,
  batch_id UUID NULL REFERENCES upload_batches(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  actor_type TEXT NOT NULL DEFAULT 'system',
  actor_id TEXT NULL,
  request_id TEXT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_upload_events_session_id ON upload_events(session_id, created_at);
CREATE INDEX idx_upload_events_batch_id ON upload_events(batch_id, created_at);
CREATE INDEX idx_upload_events_tenant_type ON upload_events(tenant_id, event_type, created_at);
```

### 14.8 Idempotency records

```sql
CREATE TABLE idempotency_records (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  key TEXT NOT NULL,
  request_method TEXT NOT NULL,
  request_path TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  response_status INTEGER NULL,
  response_body JSONB NULL,
  locked_until TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  UNIQUE (tenant_id, key)
);

CREATE INDEX idx_idempotency_records_expires_at ON idempotency_records(expires_at);
```

Rules:

- If same idempotency key and same request fingerprint are received again, return stored response if available.
- If same idempotency key but different request fingerprint is received, return `409 Conflict`.
- Idempotency records must expire after a configurable retention period.

---

## 15. Storage Adapter Interface

Core application logic must depend on an interface, not directly on boto3.

### 15.1 Interface

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

@dataclass(frozen=True)
class CreateMultipartUploadResult:
    upload_id: str

@dataclass(frozen=True)
class PresignedPartUrl:
    part_number: int
    url: str
    expires_at: datetime
    required_headers: dict[str, str]

@dataclass(frozen=True)
class StoragePart:
    part_number: int
    etag: str
    size_bytes: int
    last_modified: datetime | None = None

@dataclass(frozen=True)
class CompleteMultipartUploadResult:
    bucket: str
    object_key: str
    etag: str | None
    version_id: str | None
    size_bytes: int | None

class ObjectStorage(Protocol):
    def create_multipart_upload(
        self,
        *,
        bucket: str,
        object_key: str,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> CreateMultipartUploadResult:
        ...

    def presign_upload_part(
        self,
        *,
        bucket: str,
        object_key: str,
        upload_id: str,
        part_number: int,
        expires_in_seconds: int,
    ) -> PresignedPartUrl:
        ...

    def list_parts(
        self,
        *,
        bucket: str,
        object_key: str,
        upload_id: str,
    ) -> list[StoragePart]:
        ...

    def complete_multipart_upload(
        self,
        *,
        bucket: str,
        object_key: str,
        upload_id: str,
        parts: list[StoragePart],
    ) -> CompleteMultipartUploadResult:
        ...

    def abort_multipart_upload(
        self,
        *,
        bucket: str,
        object_key: str,
        upload_id: str,
    ) -> None:
        ...

    def head_object(
        self,
        *,
        bucket: str,
        object_key: str,
    ) -> dict:
        ...
```

### 15.2 MinIO/S3 adapter implementation

Use boto3 against MinIO because boto3 exposes low-level S3 multipart APIs and presigned URL generation for `upload_part`.

Client initialization:

```python
import boto3
from botocore.config import Config

s3_client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    region_name=settings.s3_region,
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        retries={"max_attempts": 3, "mode": "standard"},
    ),
)
```

Create multipart upload:

```python
response = s3_client.create_multipart_upload(
    Bucket=bucket,
    Key=object_key,
    ContentType=content_type,
    Metadata=metadata,
)
upload_id = response["UploadId"]
```

Presign upload part:

```python
url = s3_client.generate_presigned_url(
    ClientMethod="upload_part",
    Params={
        "Bucket": bucket,
        "Key": object_key,
        "UploadId": upload_id,
        "PartNumber": part_number,
    },
    ExpiresIn=expires_in_seconds,
    HttpMethod="PUT",
)
```

List parts with pagination:

```python
parts: list[StoragePart] = []
part_number_marker = None

while True:
    kwargs = {
        "Bucket": bucket,
        "Key": object_key,
        "UploadId": upload_id,
    }
    if part_number_marker is not None:
        kwargs["PartNumberMarker"] = part_number_marker

    response = s3_client.list_parts(**kwargs)

    for item in response.get("Parts", []):
        parts.append(
            StoragePart(
                part_number=item["PartNumber"],
                etag=item["ETag"],
                size_bytes=item["Size"],
                last_modified=item.get("LastModified"),
            )
        )

    if not response.get("IsTruncated"):
        break

    part_number_marker = response.get("NextPartNumberMarker")

return sorted(parts, key=lambda p: p.part_number)
```

Complete multipart upload:

```python
response = s3_client.complete_multipart_upload(
    Bucket=bucket,
    Key=object_key,
    UploadId=upload_id,
    MultipartUpload={
        "Parts": [
            {"PartNumber": p.part_number, "ETag": p.etag}
            for p in sorted(parts, key=lambda x: x.part_number)
        ]
    },
)
```

Abort multipart upload:

```python
s3_client.abort_multipart_upload(
    Bucket=bucket,
    Key=object_key,
    UploadId=upload_id,
)
```

---

## 16. Object Key Strategy

Object keys must be generated by the backend.

Recommended pattern:

```text
tenants/{tenant_slug_or_id}/yyyy/mm/dd/{session_id}/{safe_filename}
```

Example:

```text
tenants/tnt_123/2026/06/10/2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9/front_camera.mp4
```

Rules:

- Never trust client-provided paths.
- Strip directory components from filename.
- Normalize Unicode if needed.
- Replace unsupported characters with `_`.
- Preserve useful extension when safe.
- Enforce maximum object key length.
- Include `session_id` to avoid collisions.
- Prefix by tenant to enforce namespace isolation.

Recommended filename sanitizer behavior:

```text
"../../etc/passwd"        -> "passwd"
"front camera.mp4"        -> "front_camera.mp4"
"设备日志 01.jsonl"       -> "设备日志_01.jsonl" or ASCII-safe fallback
""                        -> "upload.bin"
```

---

## 17. Security Requirements

### 17.1 Credential handling

- MinIO credentials must live only in backend/worker environment variables or secret store.
- Presigned URLs must be considered bearer tokens.
- Do not log full presigned URLs.
- When logging a URL is unavoidable in debug mode, strip query string.
- API keys must be hashed at rest.
- API responses must not expose MinIO secret values.

### 17.2 Authorization

Every endpoint must validate:

- API key is active.
- Tenant is active.
- Caller tenant owns the batch/session.
- Caller has required scope.
- Optional device restriction matches `source_device_id`.

Suggested scopes:

```text
uploads:create
uploads:read
uploads:write
uploads:complete
uploads:abort
batches:create
batches:read
batches:complete
admin:uploads
```

### 17.3 Presigned URL scope

A part presigned URL should be scoped to exactly one operation:

```text
PUT object_key?partNumber=N&uploadId=...
```

It should not allow listing buckets, deleting objects, reading other objects, or completing multipart upload.

### 17.4 Content validation

On initiation:

- Validate file size.
- Validate content type, if allowlist enabled.
- Validate metadata key/value lengths.
- Validate original filename length.
- Validate batch ownership.
- Validate part count.

On completion:

- Validate observed parts match expected part numbers.
- Validate observed sizes match expected part sizes.
- Validate final object metadata if supported.

### 17.5 Transport security

Local development may use HTTP for MinIO.

Production-like deployment should use HTTPS for:

- Client -> API.
- Client -> MinIO presigned URL.
- API -> MinIO.

### 17.6 Abuse controls

The API should support configurable limits:

```text
MAX_FILE_SIZE_BYTES
MAX_PART_COUNT
MAX_PARTS_PER_PRESIGN_REQUEST
MAX_UPLOAD_SESSION_LIFETIME_SECONDS
MAX_PRESIGN_EXPIRY_SECONDS
MAX_OPEN_UPLOADS_PER_TENANT
MAX_OPEN_BATCHES_PER_TENANT
MAX_UPLOADS_PER_BATCH
```

---

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
| `POST /v1/uploads` | Idempotent by key; returns same session for same request |
| `POST /v1/uploads/{id}/parts/presign` | Safe to retry; may return new URLs with new expiry |
| `POST /v1/uploads/{id}/parts/ack` | Idempotent upsert |
| `GET /v1/uploads/{id}/parts` | Safe |
| `POST /v1/uploads/{id}/complete` | Idempotent if already completed; otherwise locked |
| `POST /v1/uploads/{id}/abort` | Idempotent if already aborted |
| `POST /v1/upload-batches` | Idempotent by key |
| `POST /v1/upload-batches/{id}/complete` | Idempotent if already completed |

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
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "batch_id": "5e17d62f-1c65-4f49-85c1-7cd78356a582",
  "file_path": "/data/front_camera.mp4",
  "original_filename": "front_camera.mp4",
  "file_size_bytes": 5368709120,
  "part_size_bytes": 67108864,
  "part_count": 80,
  "checksum_sha256": "optional-full-file-sha256-hex",
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
5. Call GET /v1/uploads/{session_id}/parts?source=reconcile.
6. Mark storage-observed parts as uploaded.
7. Compute missing part numbers.
8. For each missing part, request fresh presigned URL in batches.
9. Upload missing parts with concurrency limit.
10. Ack uploaded parts.
11. Call complete.
12. If complete returns missing parts, repeat from step 5.
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

---

## 20. Completion Algorithm

Completion must be deterministic and storage-authoritative.

Pseudo-code:

```python
def complete_upload(session_id: UUID, actor: Actor) -> CompleteResponse:
    with transaction() as tx:
        session = repo.get_session_for_update(session_id, tenant_id=actor.tenant_id)

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
            repo.transition(session, UPLOADING)
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
1. Find sessions where status in INITIATED/UPLOADING and expires_at < now().
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

Recommended first implementation:

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

---

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
9. Periodically flush manifest to disk.
10. Call complete.
11. Mark manifest completed.
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
├── README.md
├── docs/
│   ├── architecture.md
│   ├── api.md
│   ├── failure-modes.md
│   ├── benchmarks.md
│   └── development.md
├── src/
│   └── upload_control_plane/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── logging.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── dependencies.py
│       │   ├── error_handlers.py
│       │   ├── middleware.py
│       │   └── routes/
│       │       ├── health.py
│       │       ├── uploads.py
│       │       └── batches.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── errors.py
│       │   ├── models.py
│       │   ├── policies.py
│       │   ├── states.py
│       │   └── part_size.py
│       ├── application/
│       │   ├── __init__.py
│       │   ├── upload_service.py
│       │   ├── batch_service.py
│       │   ├── part_service.py
│       │   ├── completion_service.py
│       │   ├── abort_service.py
│       │   └── idempotency_service.py
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── db/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── models.py
│       │   │   ├── session.py
│       │   │   └── repositories.py
│       │   ├── storage/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   └── s3_minio.py
│       │   └── auth/
│       │       ├── __init__.py
│       │       ├── api_key.py
│       │       └── models.py
│       ├── worker/
│       │   ├── __init__.py
│       │   ├── cleanup.py
│       │   └── checksum_validator.py
│       └── cli/
│           ├── __init__.py
│           ├── main.py
│           ├── client.py
│           ├── manifest.py
│           ├── uploader.py
│           └── file_ranges.py
├── migrations/
│   ├── env.py
│   └── versions/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── failure_injection/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── Makefile
└── scripts/
    ├── create_dev_api_key.py
    ├── seed_dev.py
    ├── generate_test_file.py
    └── benchmark_upload.py
```

### 24.4 Layering rules

- `domain` must not import FastAPI, SQLAlchemy, boto3, or MinIO-specific code.
- `application` may depend on domain interfaces and repositories.
- `infrastructure` implements repositories and storage adapters.
- `api` maps HTTP DTOs to application commands.
- `cli` uses HTTP API only; it must not import backend application services.
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
DEFAULT_PART_SIZE_BYTES=67108864
MIN_PART_SIZE_BYTES=5242880
MAX_PART_SIZE_BYTES=5368709120
MAX_PART_COUNT=10000
DEFAULT_PRESIGN_EXPIRY_SECONDS=900
MAX_PRESIGN_EXPIRY_SECONDS=21600
DEFAULT_UPLOAD_SESSION_EXPIRY_SECONDS=86400
MAX_UPLOAD_SESSION_EXPIRY_SECONDS=604800
MAX_PARTS_PER_PRESIGN_REQUEST=100
MAX_OPEN_UPLOADS_PER_TENANT=1000
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
upload_complete_requests_total{tenant_id}
upload_complete_missing_parts_total{tenant_id}

storage_operation_duration_seconds{operation}
storage_operation_errors_total{operation,error_code}

cleanup_sessions_scanned_total
cleanup_sessions_aborted_total
cleanup_errors_total{error_code}

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
db.transaction
worker.cleanup_expired_sessions
```

---

## 28. Testing Strategy

### 28.1 Unit tests

Required unit tests:

- Part size selection.
- Part range calculation.
- State transition rules.
- Object key sanitizer.
- Request fingerprint generation.
- Idempotency conflict behavior.
- Missing part validation.
- File mutation detection in CLI manifest.

### 28.2 Integration tests

Use real PostgreSQL and real MinIO.

Required integration tests:

1. Create upload session creates DB row and MinIO multipart upload.
2. Presign returns valid URL for part 1.
3. Upload one part directly to MinIO using presigned URL.
4. List parts sees uploaded part.
5. Complete fails when parts are missing.
6. Complete succeeds when all parts exist.
7. Abort succeeds and is idempotent.
8. Presign rejected after abort.
9. Presign rejected after completion.
10. Expired session cleanup aborts storage upload.

### 28.3 E2E tests

Required E2E tests using CLI:

1. Upload a small file using multipart path.
2. Upload a file large enough to produce multiple parts.
3. Kill upload halfway, resume, complete.
4. Use a very short presign expiry, force URL expiration, resume with new URLs.
5. Upload same part twice and complete with latest storage-observed ETag.
6. Run batch upload with multiple files and complete batch.

### 28.4 Failure injection tests

Required failure modes:

| Failure | Expected behavior |
|---|---|
| API timeout after session creation | Retrying init with same idempotency key returns same session |
| Presigned URL expires | Client requests a new URL and retries part |
| Part upload network failure | Only failed part is retried |
| Client crash | Manifest resumes from storage reconciliation |
| Missing part on complete | API returns 409 with missing parts |
| Duplicate complete requests | One completes; the other returns completed or conflict safely |
| Abort during upload | Further presign and complete are rejected |
| DB has ack but storage lacks part | Complete rejects missing storage part |
| Storage has part but DB lacks ack | Reconcile updates DB and complete can succeed |
| Storage complete succeeds but API response lost | Retry complete returns completed state after repair/reconcile |

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
CPU/memory usage if available
```

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
- Transition back to `UPLOADING`.
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

---

## 30. Phased Implementation Plan

This section is written for Codex. Each phase should result in runnable code and tests.

### Phase 0 — Repository scaffold

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

### Phase 1 — Domain model and database migrations

Deliverables:

- Domain enums and state transition validation.
- Part size and part range functions.
- SQLAlchemy models.
- Alembic migration for tenants, api keys, batches, sessions, parts, events, idempotency.
- Seed script for dev tenant and API key.

Acceptance criteria:

- Unit tests for part math and state transitions pass.
- DB migration applies cleanly from empty database.
- Seed script produces one usable dev API key.

### Phase 2 — MinIO/S3 storage adapter

Deliverables:

- `ObjectStorage` protocol.
- `S3MultipartStorage` implementation using boto3.
- Create multipart upload.
- Presign upload part.
- List parts with pagination.
- Complete multipart upload.
- Abort multipart upload.
- Head object.

Acceptance criteria:

- Integration test can create multipart upload in MinIO.
- Integration test can presign a part URL and upload bytes with HTTP PUT.
- Integration test can list the part from MinIO.
- Integration test can complete and read/head final object.

### Phase 3 — Core upload API

Deliverables:

- API key auth dependency.
- Error response format.
- Request ID middleware.
- `POST /v1/uploads`.
- `GET /v1/uploads/{id}`.
- `POST /v1/uploads/{id}/parts/presign`.
- `POST /v1/uploads/{id}/parts/ack`.
- `GET /v1/uploads/{id}/parts`.
- `POST /v1/uploads/{id}/complete`.
- `POST /v1/uploads/{id}/abort`.
- Idempotency support for create/complete/abort.

Acceptance criteria:

- OpenAPI docs show all endpoints.
- Integration tests cover successful multipart upload through API + direct MinIO PUT.
- Complete missing parts returns 409.
- Abort is idempotent.
- Tenant isolation tests pass.

### Phase 4 — Python CLI uploader

Deliverables:

- `uploadctl` command.
- Upload command.
- Resume command.
- Status command.
- Abort command.
- Local manifest persistence.
- Concurrent part upload.
- Retry and URL-expiry handling.

Acceptance criteria:

- CLI uploads a multi-part file to local MinIO through the API.
- CLI can resume after manual interruption.
- CLI does not store presigned URLs in manifest.
- CLI progress output is readable.

### Phase 5 — Batch upload support

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

### Phase 6 — Cleanup worker and lifecycle

Deliverables:

- Worker process.
- Expire old sessions.
- Abort expired multipart uploads.
- Cleanup idempotency records.
- Cleanup events/metrics.

Acceptance criteria:

- Test session expires and worker aborts it.
- Worker can be run repeatedly safely.
- Worker errors are logged and metriced.

### Phase 7 — Observability

Deliverables:

- Structured JSON logs.
- Prometheus metrics endpoint.
- Storage operation latency metrics.
- API latency metrics.
- Optional OpenTelemetry tracing.

Acceptance criteria:

- `/metrics` returns expected counters/histograms.
- Logs contain request ID, session ID, operation, status.
- Presigned URL query strings are not logged.

### Phase 8 — Failure injection and benchmark suite

Deliverables:

- Tests for URL expiry.
- Tests for duplicate complete.
- Tests for missing storage part despite DB ack.
- Benchmark script.
- Benchmark report template in `docs/benchmarks.md`.

Acceptance criteria:

- Failure injection test suite passes locally.
- Benchmark can upload at least a generated 512 MiB file against local MinIO.

### Phase 9 — Optional Go uploader

Deliverables:

- `go/robot-uploader` module.
- Upload/resume/status support through the same API.
- Concurrent part upload using Go routines.
- Local manifest compatible with Python CLI or explicitly versioned.

Acceptance criteria:

- Go uploader can upload and resume files using the Python backend.
- Benchmark compares Python CLI and Go uploader.
- Go implementation must not bypass the backend or use MinIO credentials.

### Phase 10 — Optional Go edge/control gateway

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

## 31. Source References

This design is based on the official behavior and APIs documented by AWS and MinIO:

1. AWS S3 Multipart Upload Overview
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html

2. AWS S3 Multipart Upload Limits
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html

3. AWS Boto3 `generate_presigned_url`
   https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/generate_presigned_url.html

4. AWS Boto3 `create_multipart_upload`
   https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/create_multipart_upload.html

5. AWS Boto3 `upload_part`
   https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/upload_part.html

6. AWS Boto3 `complete_multipart_upload`
   https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/complete_multipart_upload.html

7. MinIO S3 API compatibility
   https://docs.min.io/aistor/developers/s3-api-compatibility/

8. MinIO Python SDK API reference
   https://docs.min.io/aistor/developers/sdk/python/api/

9. MinIO limits
   https://github.com/minio/minio/blob/master/docs/minio-limits.md

---

## 32. Definition of Done

The repository can be considered portfolio-ready when:

1. A reader can run the system locally with Docker Compose.
2. A reader can upload a multi-part file to MinIO using `uploadctl`.
3. A reader can interrupt the client and resume successfully.
4. A reader can see upload metadata in PostgreSQL.
5. A reader can inspect MinIO and find the completed object.
6. Tests prove missing part handling, URL expiry recovery, duplicate completion, and abort idempotency.
7. The README explains why file bytes do not pass through the backend.
8. API docs are available through OpenAPI.
9. Logs and metrics demonstrate operational thinking.
10. The repo clearly states it is production-oriented but not production-proven.

---

## 33. README Narrative

The README should frame the project like this:

```text
This repository implements a production-oriented large-file upload control plane for AI and robotics data ingestion. It uses S3-compatible multipart upload to allow clients to upload file parts directly to object storage while the backend controls authorization, presigned URL generation, session state, completion, abort, cleanup, and observability.

The design intentionally separates the control plane from the data plane: the API service never receives large file bodies. This keeps backend bandwidth and memory usage bounded while allowing clients to upload large datasets directly to MinIO/S3 with resumability and parallelism.
```

Avoid framing it as:

```text
A simple file upload demo.
```

Correct framing:

```text
A production-oriented upload control plane for resumable multipart ingestion.
```

---

## 34. Codex Implementation Rules

Codex must follow these rules:

1. Do not create endpoints that accept file bytes unless explicitly requested later.
2. Do not give the client MinIO credentials.
3. Do not bypass the storage adapter from application services.
4. Do not assume ETag is a full-file MD5 checksum.
5. Do not complete uploads based only on DB ack rows.
6. Always validate tenant ownership.
7. Always keep state transitions explicit and test-covered.
8. Add tests with every new feature.
9. Do not silently change API response shapes after they are introduced.
10. Prefer small, well-named services over one large upload service class.
11. Keep domain logic independent from FastAPI, SQLAlchemy, and boto3.
12. Avoid high-cardinality metric labels.
13. Mask secrets and presigned URL query strings in logs.
14. Make local development deterministic.
15. Keep Go components optional until Python backend and CLI are correct.

---

## 35. Recommended First Codex Task

The first implementation task should be:

```text
Create the repository scaffold for upload-control-plane with FastAPI, PostgreSQL, MinIO Docker Compose, pyproject.toml, ruff, pytest, a health endpoint, configuration loading, and a Makefile. Do not implement upload APIs yet.
```

Acceptance criteria for the first task:

```bash
make dev-up
make test
curl http://localhost:8000/healthz
```

Expected health response:

```json
{
  "status": "ok",
  "service": "upload-control-plane"
}
```

---

## 36. Recommended Second Codex Task

The second task should be:

```text
Implement domain-level part size selection, part range calculation, upload session state machine, and unit tests. Do not add FastAPI upload endpoints yet.
```

Acceptance criteria:

- `choose_part_size` handles explicit and automatic part sizes.
- `get_part_range` handles first, middle, and last parts.
- State transition rules reject invalid transitions.
- Unit tests cover boundary cases around 5 MiB, 64 MiB, 5 GiB, and 10,000 parts.

---

## 37. Final Design Reminder

The core insight of this project is:

```text
Industrial-grade large-file upload is not about making the backend better at receiving huge files.
It is about preventing the backend from receiving huge files at all.

The backend controls authorization and lifecycle.
Object storage handles the data plane.
The client handles slicing, retries, and resume.
```

All implementation decisions must preserve that separation.
