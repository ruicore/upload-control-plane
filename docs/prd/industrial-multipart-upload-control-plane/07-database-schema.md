# Database Schema

Previous: [API Contracts and Part Sizing](06-api-contracts.md) | Index: [README](README.md) | Next: [Storage Adapter and Object Keys](08-storage-adapter-and-object-keys.md)

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
  'PAUSED',
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

CREATE TYPE dataset_status AS ENUM (
  'CREATED',
  'UPLOAD_PENDING',
  'UPLOADING',
  'PAUSED',
  'PROCESSING',
  'READY',
  'VALIDATION_FAILED',
  'ARCHIVED',
  'DELETED'
);

CREATE TYPE upload_task_status AS ENUM (
  'CREATED',
  'PENDING',
  'PROCESSING',
  'PAUSED',
  'COMPLETED',
  'FAILED',
  'CANCELLED'
);

CREATE TYPE upload_object_status AS ENUM (
  'CREATED',
  'PENDING',
  'UPLOADING',
  'PAUSED',
  'COMPLETING',
  'COMPLETED',
  'FAILED',
  'CANCELLED',
  'SKIPPED_INSTANT_UPLOAD'
);

CREATE TYPE device_status AS ENUM (
  'ACTIVE',
  'DISABLED',
  'REVOKED',
  'DELETED'
);

CREATE TYPE validation_status AS ENUM (
  'NOT_REQUIRED',
  'PENDING',
  'RUNNING',
  'PASSED',
  'FAILED',
  'SKIPPED'
);

CREATE TYPE outbox_status AS ENUM (
  'PENDING',
  'PROCESSING',
  'DELIVERED',
  'FAILED',
  'DEAD_LETTERED'
);

CREATE TYPE permission_effect AS ENUM (
  'ALLOW',
  'DENY'
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

### 14.3 Storage policies

```sql
CREATE TABLE storage_policies (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  provider TEXT NOT NULL DEFAULT 's3_compatible',
  bucket_name TEXT NOT NULL,
  region TEXT NULL,
  endpoint_ref TEXT NULL,
  addressing_style TEXT NOT NULL DEFAULT 'path',
  object_key_template TEXT NOT NULL,
  default_part_size_bytes BIGINT NOT NULL,
  presign_expiry_seconds INTEGER NOT NULL,
  upload_session_expiry_seconds INTEGER NOT NULL,
  retention_days INTEGER NULL,
  checksum_mode TEXT NOT NULL DEFAULT 'CLIENT_REPORTED',
  encryption_mode TEXT NOT NULL DEFAULT 'NONE',
  kms_key_ref TEXT NULL,
  object_lock_mode TEXT NULL,
  object_lock_retention_days INTEGER NULL,
  legal_hold_default BOOLEAN NOT NULL DEFAULT FALSE,
  replication_policy_ref TEXT NULL,
  cors_policy_ref TEXT NULL,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE INDEX idx_storage_policies_tenant_status ON storage_policies(tenant_id, status);
```

Storage policy fields are intentionally broader than the first local MinIO implementation:

- `encryption_mode` may be `NONE`, `SSE_S3`, `SSE_KMS`, or a provider-specific value.
- `kms_key_ref` stores a non-secret key alias or identifier, never raw key material.
- `object_lock_mode` may be `GOVERNANCE`, `COMPLIANCE`, or provider-specific equivalent when object lock is enabled.
- `object_lock_retention_days` and `legal_hold_default` describe storage-level immutability policy, separate from application recycle-bin retention.
- `replication_policy_ref` points to an operator-managed storage replication policy.
- `cors_policy_ref` points to an operator-managed browser direct-upload CORS policy.

The first implementation may leave these optional fields unused, but migrations and service code must not assume that encryption, object lock, retention, CORS, and replication are purely application-local concepts.

### 14.4 API keys

For portfolio implementation, store hashed API keys.

```sql
CREATE TABLE api_keys (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  key_hash TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  subject_id UUID NULL,
  scopes TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  expires_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at TIMESTAMPTZ NULL
);

CREATE INDEX idx_api_keys_tenant_id ON api_keys(tenant_id);
```

Do not store raw API keys.

`scopes` may be used as a coarse API-key guard or bootstrap simplification, but resource-level authorization must be based on effective permission codes from `permission_grants`.

### 14.5 Projects

```sql
CREATE TABLE projects (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  storage_policy_id UUID NULL REFERENCES storage_policies(id),
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NULL,
  status TEXT NOT NULL DEFAULT 'ACTIVE',
  metadata_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  archived_at TIMESTAMPTZ NULL,
  deleted_at TIMESTAMPTZ NULL,
  UNIQUE (tenant_id, slug)
);

CREATE INDEX idx_projects_tenant_status ON projects(tenant_id, status);
```

### 14.6 Datasets

```sql
CREATE TABLE datasets (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NOT NULL REFERENCES projects(id),
  name TEXT NOT NULL,
  status dataset_status NOT NULL DEFAULT 'CREATED',

  original_filename TEXT NULL,
  content_type TEXT NULL,
  file_size_bytes BIGINT NULL,
  checksum_sha256 TEXT NULL,

  bucket_name TEXT NULL,
  object_key TEXT NULL,
  object_etag TEXT NULL,
  object_size_bytes BIGINT NULL,
  object_version_id TEXT NULL,

  source_device_id TEXT NULL,
  validation_status validation_status NOT NULL DEFAULT 'NOT_REQUIRED',
  preview_status TEXT NOT NULL DEFAULT 'NOT_AVAILABLE',
  preview_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  labels TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],

  created_by UUID NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ready_at TIMESTAMPTZ NULL,
  archived_at TIMESTAMPTZ NULL,
  deleted_at TIMESTAMPTZ NULL
);

CREATE INDEX idx_datasets_project_status ON datasets(project_id, status);
CREATE INDEX idx_datasets_tenant_status ON datasets(tenant_id, status);
CREATE INDEX idx_datasets_source_device ON datasets(tenant_id, source_device_id);
CREATE INDEX idx_datasets_validation_status ON datasets(project_id, validation_status);
CREATE UNIQUE INDEX idx_datasets_object_unique
  ON datasets(bucket_name, object_key)
  WHERE object_key IS NOT NULL;
```

Rules:

- A dataset is the business data asset.
- In the first implementation, one dataset corresponds to one final object.
- A dataset should not be overwritten in place after it becomes `READY`.
- If versioning is needed later, add a `dataset_versions` table rather than reusing one dataset row for multiple final objects.
- Dataset visibility and actions are derived from project-level and dataset-level permission grants.

### 14.7 Tags

```sql
CREATE TABLE tag_categories (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  color TEXT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, name)
);

CREATE TABLE tags (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  category_id UUID NULL REFERENCES tag_categories(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  color TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, name)
);

CREATE TABLE dataset_tags (
  dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (dataset_id, tag_id)
);

CREATE INDEX idx_tags_project_category ON tags(project_id, category_id);
```

### 14.8 Devices

```sql
CREATE TABLE devices (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  device_code TEXT NULL,
  device_type TEXT NOT NULL,
  status device_status NOT NULL DEFAULT 'ACTIVE',
  credential_version INTEGER NOT NULL DEFAULT 1,
  credential_hash TEXT NULL,
  last_seen_at TIMESTAMPTZ NULL,
  last_ip TEXT NULL,
  client_version TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, device_code)
);

CREATE TABLE device_project_grants (
  device_id UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  created_by UUID NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (device_id, project_id)
);

CREATE INDEX idx_devices_tenant_status ON devices(tenant_id, status);
```

Device access must still be evaluated through permission grants or device project grants before creating upload tasks or requesting presigned URLs.

### 14.9 Permission grants

Permissions must support resource-scoped authorization. Traditional global roles are not enough because different users may see different projects and have different actions within each project.

Roles may be used as templates for granting permissions, but permission grants are the source of truth.

```sql
CREATE TABLE permission_grants (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),

  subject_type TEXT NOT NULL,
  subject_id UUID NOT NULL,

  resource_type TEXT NOT NULL,
  resource_id UUID NOT NULL,

  permission_code TEXT NOT NULL,
  effect permission_effect NOT NULL DEFAULT 'ALLOW',

  conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
  source TEXT NOT NULL DEFAULT 'manual',

  created_by UUID NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NULL,

  UNIQUE (
    tenant_id,
    subject_type,
    subject_id,
    resource_type,
    resource_id,
    permission_code,
    effect
  )
);

CREATE INDEX idx_permission_grants_subject
  ON permission_grants(tenant_id, subject_type, subject_id);

CREATE INDEX idx_permission_grants_resource
  ON permission_grants(tenant_id, resource_type, resource_id);

CREATE INDEX idx_permission_grants_permission
  ON permission_grants(tenant_id, permission_code);

CREATE INDEX idx_permission_grants_expires_at
  ON permission_grants(expires_at);
```

Allowed `subject_type` values:

```text
user
group
device
api_key
```

Allowed `resource_type` values:

```text
tenant
project
dataset
upload_session
upload_task
device
tag_category
tag
storage_policy
```

Permission inheritance rules:

- Tenant-level grants may apply to all projects and datasets in the tenant.
- Project-level grants may apply to datasets, upload tasks, upload sessions, tags, and devices under that project.
- Dataset-level grants apply only to the specific dataset.
- Device-level grants apply only to device-specific operations such as credential view/rotation.
- Storage-policy-level grants apply only to storage policy view/manage operations.
- Upload-task-level and upload-session-level grants are exceptional and should be avoided unless a narrow operational override is required.
- `DENY` wins over `ALLOW` when both apply at the same or inherited scope.
- Expired grants must be ignored.

Recommended permission code examples:

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
dataset.delete
dataset.download
dataset.archive
dataset.validate
dataset.restore
dataset.purge

upload.create
upload.presign
upload.pause
upload.resume
upload.abort
upload.complete
upload.retry
upload.cancel

tag.create
tag.update
tag.delete

device.view
device.create
device.update
device.disable
device.credentials.view
device.credentials.rotate

storage_policy.view
storage_policy.manage

audit.view
```

Example:

```text
permission_code = dataset.upload
resource_type = project
resource_id = project_123
```

means the subject may upload datasets under `project_123`.

### 14.10 Upload batches

```sql
CREATE TABLE upload_batches (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NULL REFERENCES projects(id),
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
CREATE INDEX idx_upload_batches_project_id ON upload_batches(project_id);
```

### 14.11 Upload tasks

```sql
CREATE TABLE upload_tasks (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NOT NULL REFERENCES projects(id),
  storage_policy_id UUID NULL REFERENCES storage_policies(id),
  status upload_task_status NOT NULL DEFAULT 'CREATED',
  task_initiator TEXT NOT NULL,
  source_device_id UUID NULL REFERENCES devices(id),
  object_count INTEGER NOT NULL DEFAULT 0,
  completed_object_count INTEGER NOT NULL DEFAULT 0,
  failed_object_count INTEGER NOT NULL DEFAULT 0,
  total_size_bytes BIGINT NULL,
  uploaded_size_bytes BIGINT NOT NULL DEFAULT 0,
  idempotency_key TEXT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by UUID NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ NULL,
  cancelled_at TIMESTAMPTZ NULL,
  last_error_code TEXT NULL,
  last_error_message TEXT NULL,
  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX idx_upload_tasks_project_status ON upload_tasks(project_id, status);
CREATE INDEX idx_upload_tasks_source_device ON upload_tasks(tenant_id, source_device_id);
```

### 14.12 Upload objects

```sql
CREATE TABLE upload_objects (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NOT NULL REFERENCES projects(id),
  dataset_id UUID NULL REFERENCES datasets(id),
  upload_task_id UUID NOT NULL REFERENCES upload_tasks(id) ON DELETE CASCADE,
  status upload_object_status NOT NULL DEFAULT 'CREATED',
  object_name TEXT NOT NULL,
  file_size_bytes BIGINT NOT NULL,
  content_type TEXT NULL,
  checksum_sha256 TEXT NULL,
  upload_session_id UUID NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  is_instant_upload BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ NULL,
  last_error_code TEXT NULL,
  last_error_message TEXT NULL
);

CREATE INDEX idx_upload_objects_task_status ON upload_objects(upload_task_id, status);
CREATE INDEX idx_upload_objects_dataset_id ON upload_objects(dataset_id);
```

### 14.13 Upload sessions

```sql
CREATE TABLE upload_sessions (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NULL REFERENCES projects(id),
  dataset_id UUID NULL REFERENCES datasets(id),
  batch_id UUID NULL REFERENCES upload_batches(id),
  upload_task_id UUID NULL REFERENCES upload_tasks(id),
  upload_object_id UUID NULL REFERENCES upload_objects(id),

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
CREATE INDEX idx_upload_sessions_project_id ON upload_sessions(project_id);
CREATE INDEX idx_upload_sessions_dataset_id ON upload_sessions(dataset_id);
CREATE INDEX idx_upload_sessions_task_id ON upload_sessions(upload_task_id);
CREATE INDEX idx_upload_sessions_object_id ON upload_sessions(upload_object_id);
CREATE INDEX idx_upload_sessions_batch_id ON upload_sessions(batch_id);
CREATE INDEX idx_upload_sessions_expires_at ON upload_sessions(expires_at);
CREATE INDEX idx_upload_sessions_storage_upload_id ON upload_sessions(storage_upload_id);
```

### 14.14 Upload parts

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

### 14.15 Dataset validation results

```sql
CREATE TABLE dataset_validation_results (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NOT NULL REFERENCES projects(id),
  dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  status validation_status NOT NULL,
  validator_name TEXT NOT NULL,
  validator_version TEXT NULL,
  extracted_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  errors JSONB NOT NULL DEFAULT '[]'::jsonb,
  started_at TIMESTAMPTZ NULL,
  completed_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_dataset_validation_dataset ON dataset_validation_results(dataset_id, created_at);
CREATE INDEX idx_dataset_validation_status ON dataset_validation_results(project_id, status);
```

### 14.16 Upload events

```sql
CREATE TABLE upload_events (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NULL REFERENCES projects(id) ON DELETE CASCADE,
  dataset_id UUID NULL REFERENCES datasets(id) ON DELETE CASCADE,
  session_id UUID NULL REFERENCES upload_sessions(id) ON DELETE CASCADE,
  batch_id UUID NULL REFERENCES upload_batches(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  actor_type TEXT NOT NULL DEFAULT 'system',
  actor_id TEXT NULL,
  request_id TEXT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_upload_events_project_id ON upload_events(project_id, created_at);
CREATE INDEX idx_upload_events_dataset_id ON upload_events(dataset_id, created_at);
CREATE INDEX idx_upload_events_session_id ON upload_events(session_id, created_at);
CREATE INDEX idx_upload_events_batch_id ON upload_events(batch_id, created_at);
CREATE INDEX idx_upload_events_tenant_type ON upload_events(tenant_id, event_type, created_at);
```

Upload events are specific to upload lifecycle details. Use unified audit events for broader governance actions.

### 14.17 Unified audit events

```sql
CREATE TABLE audit_events (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  project_id UUID NULL REFERENCES projects(id),
  dataset_id UUID NULL REFERENCES datasets(id),
  actor_type TEXT NOT NULL,
  actor_id TEXT NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  result TEXT NOT NULL,
  request_id TEXT NULL,
  ip_address TEXT NULL,
  user_agent TEXT NULL,
  before_state JSONB NULL,
  after_state JSONB NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_events_resource ON audit_events(tenant_id, resource_type, resource_id, created_at);
CREATE INDEX idx_audit_events_actor ON audit_events(tenant_id, actor_type, actor_id, created_at);
CREATE INDEX idx_audit_events_action ON audit_events(tenant_id, action, created_at);
```

### 14.18 Outbox events

```sql
CREATE TABLE outbox_events (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  aggregate_type TEXT NOT NULL,
  aggregate_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL,
  status outbox_status NOT NULL DEFAULT 'PENDING',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  locked_until TIMESTAMPTZ NULL,
  last_error TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ NULL
);

CREATE INDEX idx_outbox_events_status_next_attempt
  ON outbox_events(status, next_attempt_at);

CREATE INDEX idx_outbox_events_aggregate
  ON outbox_events(aggregate_type, aggregate_id, created_at);
```

Outbox events must be inserted in the same transaction as the domain change they describe.

### 14.19 Idempotency records

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

