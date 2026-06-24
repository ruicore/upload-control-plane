# Security and Governance

Previous: [Storage Adapter and Object Keys](08-storage-adapter-and-object-keys.md) | Index: [README](README.md) | Next: [Retry, Resume, Completion, and Lifecycle](10-retry-resume-completion-lifecycle.md)

## 17. Security Requirements

### 17.1 Credential handling

- MinIO credentials must live only in backend/worker environment variables or secret store.
- Presigned URLs must be considered bearer tokens.
- Do not log full presigned URLs.
- When logging a URL is unavoidable in debug mode, strip query string.
- API keys must be hashed at rest.
- API responses must not expose MinIO secret values.
- Presigned URLs sent over MQTT must be treated as secret-bearing messages.
- MQTT brokers must not retain presigned URL responses.

### 17.2 Authorization

Every endpoint must validate:

- API key is active.
- Tenant is active.
- Caller tenant owns the task, object, session, or dataset being accessed.
- Caller has the required effective permission code for the target resource.
- Optional device restriction matches `source_device_id`.

Permission codes, not fixed `can_xxx` fields, are the authorization contract.

Suggested permission codes:

```text
project.view
project.update
project.delete
project.members.view
project.members.manage

dataset.create
dataset.view
dataset.update
dataset.upload
dataset.download
dataset.delete
dataset.archive
dataset.restore
dataset.purge
dataset.validate
dataset.quarantine.release
dataset.legal_hold

upload.create
upload.presign
upload.pause
upload.resume
upload.abort
upload.complete

tag.create
tag.update
tag.delete

device.view
device.create
device.update
device.disable
device.credentials.rotate
device.credentials.revoke

storage_policy.view
storage_policy.manage

audit.view
admin.uploads
```

Authorization examples:

| Operation | Required permission | Resource checked |
|---|---|---|
| List visible projects | `project.view` | each project or inherited tenant grant |
| Create dataset under a project | `dataset.create` | project |
| Start upload for a dataset | `dataset.upload` or `upload.create` | project or dataset |
| Request presigned URLs | `upload.presign` | dataset or owning project |
| Pause upload | `upload.pause` | dataset or owning project |
| Resume upload | `upload.resume` | dataset or owning project |
| Abort upload | `upload.abort` | dataset or owning project |
| Complete upload | `upload.complete` | dataset or owning project |
| Download final object | `dataset.download` | dataset or owning project |
| Restore dataset | `dataset.restore` | dataset or owning project |
| Purge dataset | `dataset.purge` | dataset or owning project |
| Manage tags | `tag.create` / `tag.update` / `tag.delete` | project |
| Register device | `device.create` | project |
| Rotate device credentials | `device.credentials.rotate` | device or owning project |
| Manage storage policy | `storage_policy.manage` | tenant or project |
| Manage project members | `project.members.manage` | project |

The frontend may hide buttons based on `effective_permissions`, but the backend must enforce the same permission checks on every endpoint.

Effective permission evaluation:

```text
1. Resolve actor subject ids:
   - direct user subject
   - group subjects, if group support is enabled
   - device subject, for device-triggered uploads
   - api_key subject, for automation
2. Load non-expired grants for the tenant.
3. Include grants that match the target resource or inherited parent resources.
4. Apply explicit DENY grants before ALLOW grants.
5. Return stable permission codes to the caller when the UI needs action visibility.
```

Project list queries must be permission-filtered. A user should only see projects where they have `project.view` through a direct, group, device, API key, or inherited tenant grant.

### 17.3 Presigned URL scope

A part presigned URL should be scoped to exactly one operation:

```text
PUT object_key?partNumber=N&uploadId=...
```

It should not allow listing buckets, deleting objects, reading other objects, or completing multipart upload.

Presigned URL guardrails:

- URLs must be generated from a storage principal with the narrowest practical bucket/prefix permissions.
- URL expiry should be short by default, and storage/bucket policies may impose a stricter maximum signature age when supported.
- Production deployments may restrict presigned URL use to expected network paths, such as private network ranges, VPN egress IPs, or object-storage private endpoints, when the storage provider supports it.
- The backend must record URL issuance as an audit event without storing the full signed query string.
- Signed request headers are part of the contract. If the backend signs `Content-Type`, checksum, server-side-encryption, object-lock, or conditional-write headers, the client must send exactly those headers on the `PUT`.
- Already-issued presigned URLs usually cannot be revoked instantly without storage-side support. Mitigation must rely on short expiry, credential rotation, network-path restrictions, object-key rotation, or a storage deny layer.

### 17.4 Content validation

On initiation:

- Validate file size.
- Validate content type, if allowlist enabled.
- Validate metadata key/value lengths.
- Validate original filename length.
- Validate project ownership and project status.
- Validate dataset ownership and dataset status when `dataset_id` is provided.
- Validate part count.

On completion:

- Validate observed parts match expected part numbers.
- Validate observed sizes match expected part sizes.
- Validate final object metadata if supported.

Dataset exposure rule:

- Upload completion only proves that object storage assembled the final object.
- A completed object may still have `dataset_status = QUARANTINED` or `REJECTED`, `validation_status = PENDING`, `RUNNING`, or `FAILED`, or `recovery_status != NORMAL`.
- Download, preview, training-ingestion, and downstream-processing APIs must check dataset exposure status, not only upload session status.
- Trusted local uploads may be marked `READY` after completion when validation is disabled, but the state model must not make upload `COMPLETED` and dataset `READY` the same concept.

### 17.5 Transport security

Local development may use HTTP for API, MinIO, and MQTT endpoints.

Production and production-like deployments must use TLS for:

- Client -> API.
- Client -> MinIO presigned URL.
- API -> MinIO.
- Device -> MQTT broker.
- MQTT adapter -> MQTT broker.
- Backend services -> broker, storage, and database when crossing an untrusted network boundary.

Required production rules:

- Web deployments must serve the upload application and API over HTTPS.
- Presigned URLs returned to browsers, CLI clients, or devices must use HTTPS endpoints.
- MQTT deployments must use TLS-enabled listener ports.
- Plain MQTT over TCP must not be exposed in production.
- Presigned URL query strings must not appear in access logs, MQTT broker logs, application logs, or trace attributes.
- TLS termination points must be explicit in deployment documentation.

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
MAX_OPEN_UPLOADS_PER_DEVICE
MAX_BYTES_PER_TENANT
MAX_BYTES_PER_PROJECT
MAX_PRESIGN_REQUESTS_PER_MINUTE_PER_TENANT
MAX_PRESIGN_REQUESTS_PER_MINUTE_PER_DEVICE
MAX_VALIDATION_QUEUE_DEPTH
```

Abuse-control behavior:

- When storage latency or error rate crosses configured thresholds, the API should reduce presign batch sizes or reject new uploads with a retryable error.
- Tenant, project, and device quota checks must run before storage multipart initiation.
- Quota failures must not create storage-side multipart uploads.
- Rate-limit responses should include stable error codes and optional `Retry-After`.
- Metrics must expose quota rejects, rate-limit rejects, and backpressure rejects without high-cardinality labels.

### 17.7 Storage encryption, KMS, object lock, and legal hold

Industrial deployments should support encryption-at-rest and retention controls as storage-policy decisions.

Encryption requirements:

- Local development may use no server-side encryption.
- Production storage policies should prefer provider-managed server-side encryption or KMS-backed server-side encryption.
- `SSE_KMS` policy must include a non-secret `kms_key_ref`.
- Raw encryption keys must never be stored in PostgreSQL, logs, manifests, or MQTT payloads.
- KMS access failure must fail storage operations explicitly; the system must not silently downgrade to unencrypted writes.
- Key rotation must be represented as a storage-policy change and audited.

Object-lock and legal-hold requirements:

- Application recycle-bin retention and storage-level WORM retention are separate controls.
- If object lock is enabled, bucket versioning requirements must be documented in deployment runbooks.
- Purge must check storage lock, legal hold, application retention, dataset status, and actor permission before touching object storage.
- Purge denial because of lock or legal hold is a successful policy enforcement event, not an infrastructure error.
- Object-lock bypass capability, if supported by the provider, must require a separate privileged permission and audit event.

### 17.8 Browser direct-upload CORS and signed headers

Browser upload is not only an API problem. It also requires object-storage CORS configuration.

Required CORS design:

- Allowed origins must be explicit in production; wildcard origins are only acceptable for local development.
- Allowed methods must include `PUT` for part upload and `HEAD` when the browser needs object or part metadata.
- Allowed headers must include every header the presigned URL expects the browser to send.
- Exposed headers should include at least `ETag` and any checksum headers that the client needs to persist.
- CORS configuration must not weaken bucket authorization or make objects public.

The backend should expose the required upload headers in `PresignedPartUrl.required_headers`. Browser, CLI, and device clients must treat those headers as mandatory.

### 17.9 Malicious file and unsafe parser controls

The backend does not receive file bytes, but the platform still owns the risk of storing and later processing untrusted content.

Required controls:

- Validate declared content type and original filename, but do not trust them as proof of file safety.
- Store user-provided filenames only as metadata; never use them directly as object keys or local filesystem paths.
- Keep completed datasets out of download, preview, training, and automated processing paths until the configured validation policy allows exposure.
- Run metadata extraction and format parsing in a constrained worker environment because parsers for HDF5, images, archives, logs, or robotics formats may have their own vulnerabilities.
- Add optional malware-scanning or file-inspection hooks as asynchronous validation stages.
- Record validation outcome, validator version, and error details in `dataset_validation_results`.

### 17.10 Device provisioning and credential lifecycle

Device-triggered uploads need a concrete device identity lifecycle.

Required lifecycle:

- Device registration creates an inactive or pending device until a provisioning step binds credentials.
- Credential material must be generated or enrolled through an operator-approved flow.
- Raw credential material may be returned once during provisioning or rotation. Existing credential material must not be readable later through any API.
- Devices should use mTLS/X.509, JWT, or scoped API keys depending on deployment maturity; the selected mode must be explicit in deployment docs.
- Device credentials must have version, issued-at, expires-at, last-used-at, and revoked-at fields.
- Credential rotation must allow a bounded overlap window when needed for offline devices.
- Revocation must reject new control-plane calls and MQTT commands immediately after the control plane observes it.
- Previously issued presigned URLs may remain usable until expiry; operators must pause, abort, or purge according to policy if a device is compromised.
- MQTT ACLs must be aligned with application authorization so one device cannot publish or subscribe to another device's upload topics.

### 17.11 Data classification, privacy, and audit retention

Datasets may contain sensitive industrial, customer, employee, or location data.

The design must support:

- Dataset classification labels such as `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`, or deployment-specific equivalents.
- Metadata rules that reject secrets, credentials, raw tokens, or excessive personal data in user-provided metadata.
- Download audit events that include actor, dataset, purpose if supplied, IP or device identity when available, and result.
- Audit retention policy separate from dataset retention policy.
- Tamper-resistant audit export or replication in production deployments.
- Legal hold and compliance retention that override ordinary purge requests.

---

