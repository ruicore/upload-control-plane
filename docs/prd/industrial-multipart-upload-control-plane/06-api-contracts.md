# API Contracts and Part Sizing

Previous: [State Machine](05-state-machine.md) | Index: [README](README.md) | Next: [Database Schema](07-database-schema.md)

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
- Optional coarse scopes.
- A subject used for permission-grant evaluation.
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

### 10.3 Effective permissions response contract

APIs that return user-visible resources should expose effective permission codes when the frontend needs to decide which actions to show.

Preferred response shape:

```json
{
  "project_id": "project_123",
  "name": "Shanghai Factory Line 3",
  "effective_permissions": [
    "project.view",
    "dataset.create",
    "dataset.view",
    "dataset.download",
    "upload.create",
    "upload.pause",
    "upload.resume"
  ]
}
```

Rules:

- `effective_permissions` is an array of stable permission codes.
- Permission codes should use `<resource>.<action>` or `<resource>.<subresource>.<action>`.
- The frontend should derive UI behavior from permission codes, e.g. `hasPermission(project, "dataset.upload")`.
- Fixed `can_xxx` fields must not be the primary authorization contract because they force API schema changes whenever a new permission is added.
- Optional `ui_actions` may be returned as a frontend convenience, but it is derived data and not the permission source of truth.
- Backend endpoints must still enforce permission checks even when the frontend hides a button.

Example optional derived UI action shape:

```json
{
  "effective_permissions": [
    "project.view",
    "dataset.view",
    "dataset.download"
  ],
  "ui_actions": {
    "show_upload_button": false,
    "show_download_button": true,
    "show_member_settings": false
  }
}
```

### 10.4 Platform API groups

The upload APIs are only one part of the industrial control plane. The product API surface should be grouped around resources:

Project APIs:

```text
GET    /v1/projects
POST   /v1/projects
GET    /v1/projects/{project_id}
PATCH  /v1/projects/{project_id}
POST   /v1/projects/{project_id}/archive
POST   /v1/projects/{project_id}/restore
DELETE /v1/projects/{project_id}
GET    /v1/projects/{project_id}/members
POST   /v1/projects/{project_id}/members/invite
PATCH  /v1/projects/{project_id}/members/{subject_id}
POST   /v1/projects/{project_id}/members/{subject_id}/disable
POST   /v1/projects/{project_id}/members/{subject_id}/enable
DELETE /v1/projects/{project_id}/members/{subject_id}
```

Dataset APIs:

```text
GET    /v1/projects/{project_id}/datasets
POST   /v1/projects/{project_id}/datasets
GET    /v1/projects/{project_id}/datasets/{dataset_id}
PATCH  /v1/projects/{project_id}/datasets/{dataset_id}
POST   /v1/projects/{project_id}/datasets/{dataset_id}/archive
DELETE /v1/projects/{project_id}/datasets/{dataset_id}
POST   /v1/projects/{project_id}/datasets/{dataset_id}/restore
DELETE /v1/projects/{project_id}/datasets/{dataset_id}/purge
GET    /v1/projects/{project_id}/datasets/{dataset_id}/preview
POST   /v1/projects/{project_id}/datasets/{dataset_id}/download-url
PATCH  /v1/projects/{project_id}/datasets/batch/rename
PATCH  /v1/projects/{project_id}/datasets/batch/metadata
PATCH  /v1/projects/{project_id}/datasets/batch/tags
```

Tag APIs:

```text
GET    /v1/projects/{project_id}/tag-categories
POST   /v1/projects/{project_id}/tag-categories
PATCH  /v1/projects/{project_id}/tag-categories/{category_id}
DELETE /v1/projects/{project_id}/tag-categories/{category_id}
GET    /v1/projects/{project_id}/tags
POST   /v1/projects/{project_id}/tags
PATCH  /v1/projects/{project_id}/tags/{tag_id}
DELETE /v1/projects/{project_id}/tags/{tag_id}
```

Device APIs:

```text
GET    /v1/projects/{project_id}/devices
POST   /v1/projects/{project_id}/devices
GET    /v1/projects/{project_id}/devices/{device_id}
PATCH  /v1/projects/{project_id}/devices/{device_id}
POST   /v1/projects/{project_id}/devices/{device_id}/disable
POST   /v1/projects/{project_id}/devices/{device_id}/enable
POST   /v1/projects/{project_id}/devices/{device_id}/credentials/rotate
GET    /v1/projects/{project_id}/devices/{device_id}/credentials
POST   /v1/projects/{project_id}/devices/{device_id}/local-data
POST   /v1/projects/{project_id}/devices/{device_id}/upload
```

Upload task APIs:

```text
POST   /v1/projects/{project_id}/upload-tasks
GET    /v1/upload-tasks
GET    /v1/projects/{project_id}/upload-tasks/{task_id}
POST   /v1/projects/{project_id}/upload-tasks/{task_id}/pause
POST   /v1/projects/{project_id}/upload-tasks/{task_id}/resume
POST   /v1/projects/{project_id}/upload-tasks/{task_id}/cancel
POST   /v1/projects/{project_id}/upload-tasks/{task_id}/retry
GET    /v1/projects/{project_id}/upload-tasks/{task_id}/objects/{object_id}
POST   /v1/projects/{project_id}/upload-tasks/{task_id}/objects/{object_id}/pause
POST   /v1/projects/{project_id}/upload-tasks/{task_id}/objects/{object_id}/resume
POST   /v1/projects/{project_id}/upload-tasks/{task_id}/objects/{object_id}/cancel
POST   /v1/projects/{project_id}/upload-tasks/{task_id}/objects/{object_id}/retry
```

Storage policy APIs:

```text
GET    /v1/storage-policies
POST   /v1/storage-policies
GET    /v1/storage-policies/{storage_policy_id}
PATCH  /v1/storage-policies/{storage_policy_id}
POST   /v1/projects/{project_id}/storage-policy
```

Validation, audit, and outbox APIs:

```text
GET    /v1/projects/{project_id}/datasets/{dataset_id}/validation
POST   /v1/projects/{project_id}/datasets/{dataset_id}/validation/retry
GET    /v1/audit-events
GET    /v1/outbox-events
```

The first implementation does not need to build all UI surfaces, but the domain model and migrations should avoid choices that block these API groups.

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
  "project_id": "6cbce9cd-7d78-48dc-b89d-f13d724f3be8",
  "dataset_id": "7af07a93-b4a9-48d5-8f3b-0184d2cc66bd",
  "batch_id": "5e17d62f-1c65-4f49-85c1-7cd78356a582",
  "original_filename": "front_camera.hdf5",
  "file_size_bytes": 5368709120,
  "content_type": "application/x-hdf5",
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

- Caller must have `dataset.upload` or `upload.create` on the project or dataset.
- `project_id` is required for production project-scoped uploads.
- `dataset_id` is recommended when the dataset record is created before upload.
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
  "project_id": "6cbce9cd-7d78-48dc-b89d-f13d724f3be8",
  "dataset_id": "7af07a93-b4a9-48d5-8f3b-0184d2cc66bd",
  "batch_id": "5e17d62f-1c65-4f49-85c1-7cd78356a582",
  "status": "INITIATED",
  "bucket": "robot-data",
  "object_key": "tenants/tnt_123/projects/prj_456/datasets/ds_789/2026/06/10/2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9/front_camera.hdf5",
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
  "project_id": "6cbce9cd-7d78-48dc-b89d-f13d724f3be8",
  "dataset_id": "7af07a93-b4a9-48d5-8f3b-0184d2cc66bd",
  "status": "UPLOADING",
  "bucket": "robot-data",
  "object_key": "tenants/tnt_123/projects/prj_456/datasets/ds_789/2026/06/10/2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9/front_camera.hdf5",
  "original_filename": "front_camera.hdf5",
  "file_size_bytes": 5368709120,
  "part_size_bytes": 67108864,
  "part_count": 80,
  "uploaded_part_count": 41,
  "missing_part_count": 39,
  "paused_at": null,
  "pause_reason": null,
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
- Session status must allow upload, normally `INITIATED` or `UPLOADING`.
- Presign must reject `PAUSED` sessions.
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
- If current status is `PAUSED`, complete may proceed only when all expected parts already exist in object storage.
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
- Abort is allowed from `INITIATED`, `UPLOADING`, `PAUSED`, and `EXPIRED`.
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

### 12.8 Pause upload

```http
POST /v1/uploads/{session_id}/pause
Authorization: Bearer <api_key>
Idempotency-Key: <key>
Content-Type: application/json
```

Request:

```json
{
  "reason": "operator_requested",
  "client_inflight_behavior": "allow_finish"
}
```

Rules:

- Pause is idempotent.
- If already `PAUSED`, return current paused state.
- Pause is allowed from `INITIATED` or `UPLOADING`.
- Pause must reject terminal states and `COMPLETING` / `ABORTING`.
- Pause must not call storage abort.
- Pause must not delete or invalidate already uploaded parts.
- Pause should prevent future presign requests until resume.
- `client_inflight_behavior` is advisory for clients and may be `allow_finish` or `cancel_inflight`.
- The backend cannot guarantee already issued presigned URLs are unused; complete still relies on `ListParts`.

Response:

```json
{
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "status": "PAUSED",
  "paused_at": "2026-06-10T08:45:00Z",
  "pause_reason": "operator_requested"
}
```

### 12.9 Resume upload

```http
POST /v1/uploads/{session_id}/resume
Authorization: Bearer <api_key>
Idempotency-Key: <key>
Content-Type: application/json
```

Request:

```json
{
  "reason": "operator_resumed"
}
```

Rules:

- Resume is idempotent.
- If already `UPLOADING`, return current upload state.
- Resume is allowed from `PAUSED`.
- Resume must reject terminal states and `COMPLETING` / `ABORTING`.
- Resume should not return long-lived storage credentials.
- Resume may return the current session summary, but clients should still reconcile parts and request fresh presigned URLs.
- Resume must not assume old presigned URLs are still valid.

Response:

```json
{
  "session_id": "2d4581a2-1c36-40ee-8b2e-4a225fbe4ce9",
  "status": "UPLOADING",
  "resumed_at": "2026-06-10T09:15:00Z"
}
```

### 12.10 Extend session expiry

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

