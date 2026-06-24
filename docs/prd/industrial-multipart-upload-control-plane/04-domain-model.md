# Domain Model

Previous: [System Architecture](03-system-architecture.md) | Index: [README](README.md) | Next: [State Machine](05-state-machine.md)

## 8. Core Domain Model

### 8.0 Project and dataset hierarchy

The production domain hierarchy is:

```text
Tenant / Organization
  +-- Project
        +-- Dataset
              +-- UploadTask
                    +-- UploadObject / UploadSession
                          +-- UploadPart
```

Definitions:

- Tenant / Organization is the top-level isolation boundary for customers, business units, or deployments.
- Project is the collaboration, authorization, quota, retention, and governance boundary.
- Dataset is a single independently governed data asset. For the first product model, one dataset should correspond to one final uploaded file, such as one `.hdf5` object.
- UploadTask is a user-facing or device-facing upload job, especially for Web multi-file uploads and task-center UX.
- UploadObject is one file object inside an upload task.
- UploadSession is one transfer attempt or lifecycle for uploading the dataset's file content.
- UploadPart is a multipart transport fragment.

Project-level permission grants should be the default data-scope mechanism. Dataset-level grants may be added for exceptions, but the first implementation should avoid complex per-dataset override behavior unless required.

### 8.1 Upload batch

An upload batch groups multiple file upload sessions into one logical bulk-import or ingestion job.

Example:

```text
Batch: robot-run-2026-06-10-shanghai-factory-line-3
  - front_camera.mp4
  - rear_camera.mp4
  - lidar.bin
  - robot_state.jsonl
  - diagnostics.zip
```

A batch is optional. A file upload can exist without a batch. A batch is not the same as a dataset.

For the first production-oriented model:

- A project contains many datasets.
- A dataset usually owns one active upload session.
- A batch may create multiple datasets and upload sessions under one project.

### 8.2 Project management

A project is the primary governance boundary.

It owns:

- Tenant ID.
- Name and slug.
- Status: active, archived, or deleted.
- Project members and their permission grants.
- Default storage policy.
- Default dataset metadata schema.
- Quota and retention settings.
- Device grants.

Project operations should support:

- Create / update / archive / restore / delete.
- List visible projects based on `project.view`.
- Manage members.
- Manage default storage policy.
- Expose `effective_permissions` for the current actor.

### 8.3 Dataset management

A dataset is a durable data asset, not merely an upload session.

It owns:

- Project ID.
- Dataset name and display name.
- Dataset status.
- Original filename and content type.
- Final object location.
- Size and checksum metadata.
- Tags and labels.
- Source device and collector/user metadata.
- Validation status and extracted metadata summary.
- Lifecycle timestamps: created, ready, archived, deleted, purged.

Dataset operations should support:

- Create dataset under a project.
- List/search/filter datasets.
- Get dataset details.
- Update display metadata.
- Batch rename.
- Batch update collector/device metadata.
- Batch attach/remove tags.
- Soft delete to recycle bin.
- Restore from recycle bin.
- Purge after authorization and retention checks.
- Generate short-lived download URL after checking `dataset.download`.

The first implementation may keep one dataset equal to one final object. If dataset versioning becomes required, add `dataset_versions` rather than overwriting a ready dataset row.

### 8.4 Upload task and upload object

UploadSession remains the storage-protocol lifecycle for one final object. UploadTask is the product-level job that a Web console, CLI, or device sees.

Recommended hierarchy:

```text
UploadTask
  +-- UploadObject
        +-- UploadSession
              +-- UploadPart
```

UploadTask owns:

- Project ID.
- Initiator: web console, CLI, device, API.
- Storage policy.
- Overall status and progress.
- Aggregate bytes, object count, failed count, completed count.
- Pause/resume/cancel/retry at task level.

UploadObject owns:

- Dataset ID.
- Object name and file size.
- Per-object status.
- Per-object retries and error details.
- Pause/resume/cancel/retry at object level.

For single-file flows, the API may create one task containing one object. This keeps the task center and retry model consistent.

### 8.5 Device registry

Industrial terminals and robots must be first-class subjects, not only free-text `source_device_id` values.

A device owns:

- Tenant ID and project authorization.
- Device name and device code.
- Device type.
- Status: active, disabled, revoked, deleted.
- Credential material or credential reference.
- Last seen timestamp.
- Last known IP, client version, and metadata.

Device operations should support:

- Register device.
- Rotate credentials.
- Disable / enable / revoke.
- View connection and upload status.
- Grant device access to projects.
- Trigger upload from device local data.

Device credentials and device credential views must be audited.

### 8.6 Storage policies

A storage policy defines where and how objects are stored.

It owns:

- Storage provider and endpoint reference.
- Bucket.
- Region.
- Addressing style.
- Default part size.
- Presign expiry policy.
- Upload session expiry policy.
- Retention policy.
- Checksum policy.
- Encryption policy.
- Object key template.
- Whether it is the tenant or project default.

Projects should reference a default storage policy. Upload tasks may explicitly select a policy if the actor has permission.

### 8.7 Dataset validation and metadata extraction

After upload completion, the system should optionally run validation and metadata extraction.

For robotics and industrial data, extracted metadata may include:

- File format: HDF5, MCAP, ROS bag, DB3, video, zip, diagnostics.
- Duration and time range.
- Source device.
- Topic/sensor list.
- Frame count or message count.
- Dropped-message count.
- Clock gaps.
- Out-of-order count.
- Schema version.
- Preview availability.

Validation failures should not corrupt upload correctness. They should transition the dataset to `VALIDATION_FAILED` or keep it in `PROCESSING` with a visible error, depending on policy.

### 8.8 Lifecycle, recycle bin, and retention

Industrial data platforms need explicit lifecycle governance.

Required concepts:

- Soft delete: dataset hidden from normal lists but restorable.
- Restore: restore soft-deleted dataset before purge.
- Purge: irreversible delete of metadata and object storage, subject to permission and retention policy.
- Archive: retained but not actively editable.
- Retention policy: project or tenant rule preventing early purge.
- Incomplete multipart cleanup: abort expired in-progress upload sessions.

Purge must be a separate, audited operation. It must not be triggered by upload abort.

### 8.9 Unified audit and event outbox

Upload lifecycle events are necessary but not sufficient. The platform should also record unified audit events for:

- Login and token use.
- Permission and member changes.
- Dataset create/update/download/archive/delete/restore/purge.
- Device registration, disable/enable, credential view, credential rotation.
- Storage policy changes.
- Upload task pause/resume/cancel/retry.
- Validation job results.

For recoverable event delivery, use a database outbox:

```text
Transactional domain write
  -> append outbox event in same DB transaction
  -> worker publishes to EMQX / WebSocket / webhook / notification sink
  -> mark outbox event delivered or retry later
```

Outbox events are not the source of truth; PostgreSQL domain tables are.

### 8.10 Upload session

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

### 8.11 Upload part

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

### 8.12 Storage object

The final completed object is represented by:

- Bucket.
- Object key.
- Object size.
- Storage ETag.
- Optional version ID.
- Optional checksum.
- Completed timestamp.

### 8.13 Upload lifecycle event

Every important action should create an audit event:

- `upload.initiated`
- `upload.presign_issued`
- `upload.part_acknowledged`
- `upload.parts_reconciled`
- `upload.pause_requested`
- `upload.paused`
- `upload.resume_requested`
- `upload.resumed`
- `upload.complete_requested`
- `upload.completed`
- `upload.abort_requested`
- `upload.aborted`
- `upload.expired`
- `upload.cleanup_failed`
- `upload.failed`

Events are append-only.

---


