# System Architecture

Previous: [Context, Goals, and Scope](02-context-goals-scope.md) | Index: [README](README.md) | Next: [Domain Model](04-domain-model.md)

## 7. System Architecture

### 7.1 High-level architecture

```text
+--------------------+
| Robot App / CLI    |
| / Edge Device      |
+---------+----------+
          |
          | Control-plane API:
          | init, presign, status, pause, resume, complete, abort
          v
+--------------------------------------------+
| Upload Control Plane API                   |
| FastAPI                                    |
|                                            |
| Responsibilities:                          |
| - AuthN/AuthZ                              |
| - Upload session state machine             |
| - Presigned URL generation                 |
| - Metadata validation                      |
| - Complete / Abort orchestration           |
| - Reconciliation with object storage       |
| - Observability                            |
+---------+-------------------+--------------+
          |                   |
          | SQL metadata       | S3-compatible control APIs
          v                   v
+--------------------+   +--------------------+
| PostgreSQL         |   | MinIO              |
|                    |   |                    |
| - sessions         |   | - multipart upload |
| - parts            |   | - part storage     |
| - batches          |   | - final objects    |
| - events           |   |                    |
+--------------------+   +---------+----------+
                                   ^
                                   | Data-plane direct upload:
                                   | PUT part bytes via presigned URL
                                   |
                         +---------+----------+
                         | Robot App / CLI    |
                         +--------------------+
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
| Upload API | Auth, session creation, presign, status, pause, resume, complete, abort, validation | Accept file bytes |
| Worker | Expire sessions, abort stale storage uploads, reconcile orphan state, async checksum validation | Serve user upload traffic |
| PostgreSQL | Store durable metadata, state, audit events, idempotency records | Store file bytes |
| MinIO | Store multipart parts and final objects | Decide application-level tenant authorization |
| Optional Go uploader | Higher-performance client-side upload implementation | Replace core correctness model |
| Optional Go edge gateway | API routing/auth/rate-limit for control-plane requests | Proxy large file bytes |
| Optional EMQX/MQTT adapter | Device commands, session/presign requests, upload status events, presence | Carry file bytes or duplicate upload domain logic |

---

### 7.4 Optional EMQX/MQTT control-plane adapter

Industrial deployments may include EMQX or another MQTT broker for device coordination. This is useful when terminal devices run on unstable factory Wi-Fi, 4G/5G, intermittent VPNs, or edge networks where command delivery, presence, and reconnect behavior matter.

EMQX/MQTT must be modeled as an optional control-plane adapter, not as a file-transfer data plane.

Two upload entry paths are supported:

```text
Web user selects a file
    -> HTTP API creates upload session and returns presigned URLs
    -> Browser uploads file parts directly to MinIO/S3

Terminal device detects or decides to upload a file
    -> MQTT command requests upload session and presigned URLs
    -> Device uploads file parts directly to MinIO/S3
```

Both paths must call the same application services:

```text
HTTP API Adapter
    -> UploadApplicationService

MQTT Command Adapter
    -> UploadApplicationService

UploadApplicationService
    -> PostgreSQL repositories
    -> ObjectStorage adapter
```

The MQTT adapter must not implement a separate upload state machine. It should translate MQTT commands into application commands such as:

- `create_session`.
- `presign_parts`.
- `acknowledge_part`.
- `get_status`.
- `pause_upload`.
- `resume_upload`.
- `complete_upload`.
- `abort_upload`.

The same validation, authorization, idempotency, audit events, and state transitions must apply regardless of whether a request enters through HTTP or MQTT.

Recommended topic shape:

```text
device/{tenant_id}/{device_id}/upload/request
device/{tenant_id}/{device_id}/upload/response
device/{tenant_id}/{device_id}/upload/progress
device/{tenant_id}/{device_id}/upload/error
```

MQTT messages should include:

- `request_id` or `correlation_id`.
- `tenant_id`.
- `device_id`.
- `idempotency_key` for state-changing commands.
- Command type.
- Bounded metadata payload.

Presigned URL responses over MQTT must be treated as secret-bearing responses. They must be short-lived, scoped to specific part numbers, and never retained by the broker.

The initial product stages may use only HTTP APIs and CLI upload. MQTT support should be added as a later adapter after the core upload correctness model is implemented and tested.

---


