# Public Contract Inventory

Status: active

Recorded for: Phase 1 Task P1-06

## Scope

This report records the current public contracts before governed refactoring.
It is an inventory only. It does not change production code, API contracts, or
client code.

Inputs read:

- `docs/agentic-engineering/experiment-design.md`
- `docs/reports/phase-1-baseline/architecture-drift.md`
- `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
- `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`

## Discovery Method

HTTP endpoints were discovered by:

- reading `src/upload_control_plane/main.py` for `include_router` calls and
  root app routes;
- running `uv run python -` to instantiate `create_app()` and inspect
  `fastapi.routing.APIRoute` plus FastAPI `_IncludedRouter.original_router`
  entries;
- cross-checking route decorators and Pydantic DTO classes with AST scans of
  `src/upload_control_plane/api/*.py`.

The current FastAPI version stores included routers on the app as
`_IncludedRouter` entries. Directly filtering `app.routes` for `APIRoute`
returns only root app routes, so the generated table below recursively reads
each included router's `original_router.routes`.

CLI commands were discovered from `[project.scripts]` in `pyproject.toml` and
Typer `@app.command` decorators in `src/upload_control_plane/cli/main.py` and
`src/upload_control_plane/worker/main.py`.

DB-facing artifacts were discovered from `migrations/versions/*.py`,
`src/upload_control_plane/infrastructure/db/models.py`, and domain status enum
modules under `src/upload_control_plane/domain/`.

## FastAPI Routers

`src/upload_control_plane/main.py` currently includes these routers:

| Router module | Router prefix | Tag |
| --- | --- | --- |
| `api.projects` | `/v1/projects` | `projects` |
| `api.datasets` | `/v1/projects/{project_id}` | `datasets` |
| `api.devices` | `/v1/projects/{project_id}/devices` | `devices` |
| `api.upload_tasks` | `/v1/projects/{project_id}/upload-tasks` | `upload-tasks` |
| `api.upload_sessions` | `/v1/uploads` | `upload-sessions` |
| `api.observability` | mixed: `/metrics`, `/v1/projects/{project_id}/audit-events` | `observability` |

Root app routes are also mounted directly in `main.py`:

| Method | Path | Function | Notes |
| --- | --- | --- | --- |
| `GET` | `/healthz` | `healthz` | Health route, included in schema. |
| `GET` | `/internal/auth-smoke` | `auth_smoke` | Internal authentication smoke route, included in schema. |

## Generated Endpoint Table

Generated from `create_app()` route metadata using `uv run python -`.

| Method | Path | Function | Request schema | Response schema | Tags | Schema |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/healthz` | `healthz` |  | `dict` | `health` | yes |
| `GET` | `/internal/auth-smoke` | `auth_smoke` |  | `dict` | `internal` | yes |
| `GET` | `/metrics` | `metrics` |  |  | `observability` | no |
| `GET` | `/v1/projects` | `list_projects` |  | `ProjectListResponse` | `projects` | yes |
| `GET` | `/v1/projects/{project_id}` | `get_project` |  | `ProjectResponse` | `projects` | yes |
| `GET` | `/v1/projects/{project_id}/audit-events` | `list_project_audit_events` |  | `AuditEventListResponse` | `observability` | yes |
| `GET` | `/v1/projects/{project_id}/datasets` | `list_datasets` |  | `DatasetListResponse` | `datasets` | yes |
| `DELETE` | `/v1/projects/{project_id}/datasets/{dataset_id}` | `soft_delete_dataset` |  | `DatasetDetailResponse` | `datasets` | yes |
| `GET` | `/v1/projects/{project_id}/datasets/{dataset_id}` | `get_dataset` |  | `DatasetDetailResponse` | `datasets` | yes |
| `PATCH` | `/v1/projects/{project_id}/datasets/{dataset_id}` | `update_dataset` | `DatasetUpdateRequest` | `DatasetDetailResponse` | `datasets` | yes |
| `POST` | `/v1/projects/{project_id}/datasets/{dataset_id}/archive` | `archive_dataset` |  | `DatasetDetailResponse` | `datasets` | yes |
| `POST` | `/v1/projects/{project_id}/datasets/{dataset_id}/download-url` | `create_download_url` | `DownloadUrlRequest` | `DownloadUrlResponse` | `datasets` | yes |
| `DELETE` | `/v1/projects/{project_id}/datasets/{dataset_id}/purge` | `purge_dataset` | `PurgeDatasetRequest` | `DatasetDetailResponse` | `datasets` | yes |
| `POST` | `/v1/projects/{project_id}/datasets/{dataset_id}/restore` | `restore_dataset` |  | `DatasetDetailResponse` | `datasets` | yes |
| `GET` | `/v1/projects/{project_id}/datasets/{dataset_id}/validation` | `get_dataset_validation` |  | `DatasetValidationResponse` | `datasets` | yes |
| `POST` | `/v1/projects/{project_id}/datasets/{dataset_id}/validation/retry` | `retry_dataset_validation` |  | `RetryValidationResponse` | `datasets` | yes |
| `GET` | `/v1/projects/{project_id}/devices` | `list_devices` |  | `list` | `devices` | yes |
| `POST` | `/v1/projects/{project_id}/devices` | `register_device` | `DeviceRegisterRequest` | `DeviceProvisionResponse` | `devices` | yes |
| `GET` | `/v1/projects/{project_id}/devices/{device_id}` | `get_device` |  | `DeviceResponse` | `devices` | yes |
| `PATCH` | `/v1/projects/{project_id}/devices/{device_id}` | `update_device` | `DeviceUpdateRequest` | `DeviceResponse` | `devices` | yes |
| `POST` | `/v1/projects/{project_id}/devices/{device_id}/credentials/revoke` | `revoke_device_credentials` |  | `DeviceResponse` | `devices` | yes |
| `POST` | `/v1/projects/{project_id}/devices/{device_id}/credentials/rotate` | `rotate_device_credential` | `RotateCredentialRequest` | `DeviceProvisionResponse` | `devices` | yes |
| `POST` | `/v1/projects/{project_id}/devices/{device_id}/disable` | `disable_device` |  | `DeviceResponse` | `devices` | yes |
| `POST` | `/v1/projects/{project_id}/devices/{device_id}/enable` | `enable_device` |  | `DeviceResponse` | `devices` | yes |
| `POST` | `/v1/projects/{project_id}/devices/{device_id}/upload` | `create_device_upload_task` | `UploadTaskCreateRequest` | `UploadTaskCreateResponse` | `devices` | yes |
| `GET` | `/v1/projects/{project_id}/tag-categories` | `list_tag_categories` |  | `TagCategoryListResponse` | `datasets` | yes |
| `POST` | `/v1/projects/{project_id}/tag-categories` | `create_tag_category` | `TagCategoryCreateRequest` | `TagCategoryResponse` | `datasets` | yes |
| `DELETE` | `/v1/projects/{project_id}/tag-categories/{category_id}` | `delete_tag_category` |  |  | `datasets` | yes |
| `PATCH` | `/v1/projects/{project_id}/tag-categories/{category_id}` | `update_tag_category` | `TagCategoryUpdateRequest` | `TagCategoryResponse` | `datasets` | yes |
| `GET` | `/v1/projects/{project_id}/tags` | `list_tags` |  | `TagListResponse` | `datasets` | yes |
| `POST` | `/v1/projects/{project_id}/tags` | `create_tag` | `TagCreateRequest` | `TagResponse` | `datasets` | yes |
| `DELETE` | `/v1/projects/{project_id}/tags/{tag_id}` | `delete_tag` |  |  | `datasets` | yes |
| `PATCH` | `/v1/projects/{project_id}/tags/{tag_id}` | `update_tag` | `TagUpdateRequest` | `TagResponse` | `datasets` | yes |
| `POST` | `/v1/projects/{project_id}/upload-tasks` | `create_upload_task` | `UploadTaskCreateRequest` | `UploadTaskCreateResponse` | `upload-tasks` | yes |
| `GET` | `/v1/uploads/{session_id}` | `get_upload_session` |  | `UploadSessionStatusResponse` | `upload-sessions` | yes |
| `POST` | `/v1/uploads/{session_id}/abort` | `abort_upload_session` | `AbortUploadSessionRequest` | `AbortUploadSessionResponse` | `upload-sessions` | yes |
| `POST` | `/v1/uploads/{session_id}/complete` | `complete_upload_session` | `CompleteUploadSessionRequest` | `CompleteUploadSessionResponse` | `upload-sessions` | yes |
| `GET` | `/v1/uploads/{session_id}/parts` | `list_parts` |  | `ListPartsResponse` | `upload-sessions` | yes |
| `POST` | `/v1/uploads/{session_id}/parts/ack` | `ack_parts` | `AckPartsRequest` | `AckPartsResponse` | `upload-sessions` | yes |
| `POST` | `/v1/uploads/{session_id}/parts/presign` | `presign_parts` | `PresignPartsRequest` | `PresignPartsResponse` | `upload-sessions` | yes |
| `POST` | `/v1/uploads/{session_id}/pause` | `pause_upload_session` | `PauseUploadSessionRequest` | `PauseUploadSessionResponse` | `upload-sessions` | yes |
| `POST` | `/v1/uploads/{session_id}/resume` | `resume_upload_session` | `ResumeUploadSessionRequest` | `ResumeUploadSessionResponse` | `upload-sessions` | yes |

## API Schema Classes

Current request and response DTOs are defined mainly inside route modules.
`DatasetDetailResponse` is defined locally in `api/datasets.py` as a subclass
of `DatasetSummaryResponse`.

| Module | Local API schema classes |
| --- | --- |
| `api.projects` | `ProjectResponse`, `ProjectListResponse` |
| `api.datasets` | `DatasetSummaryResponse`, `DatasetDetailResponse`, `DatasetListResponse`, `DatasetValidationResultResponse`, `DatasetValidationResponse`, `DatasetUpdateRequest`, `DownloadUrlRequest`, `DownloadUrlResponse`, `RetryValidationResponse`, `PurgeDatasetRequest`, `TagCategoryCreateRequest`, `TagCategoryUpdateRequest`, `TagCategoryResponse`, `TagCategoryListResponse`, `TagCreateRequest`, `TagUpdateRequest`, `TagResponse`, `TagListResponse` |
| `api.devices` | `DeviceRegisterRequest`, `DeviceUpdateRequest`, `DeviceCredentialResponse`, `DeviceResponse`, `DeviceProvisionResponse`, `RotateCredentialRequest` |
| `api.upload_tasks` | `UploadTaskObjectCreateRequest`, `UploadTaskCreateRequest`, `UploadTaskCreatedObjectResponse`, `UploadTaskCreateResponse` |
| `api.upload_sessions` | `UploadSessionStatusResponse`, `PresignPartsRequest`, `PresignedPartResponse`, `PresignPartsResponse`, `AckUploadedPartRequest`, `AckPartsRequest`, `AckPartsResponse`, `RuntimePartResponse`, `ListPartsResponse`, `PauseUploadSessionRequest`, `PauseUploadSessionResponse`, `ResumeUploadSessionRequest`, `ResumeUploadSessionResponse`, `CompleteReportedPartRequest`, `CompleteUploadSessionRequest`, `CompleteUploadSessionResponse`, `AbortUploadSessionRequest`, `AbortUploadSessionResponse` |
| `api.observability` | `AuditEventResponse`, `AuditEventListResponse` |

Application/domain schemas that are part of boundary contracts:

| Module | Public-facing or adapter-facing classes |
| --- | --- |
| `application.upload_tasks` | `CreateUploadTaskCommand` |
| `application.upload_sessions` | `PresignRuntimePartsResult`, `AckUploadedPartsResult`, `ListRuntimePartsResult`, `PauseUploadSessionResult`, `ResumeUploadSessionResult`, `CompleteUploadSessionResult`, `AbortUploadSessionResult` |
| `application.datasets` | `DatasetValidationResultItem`, `DatasetValidationStatusResult`, `RetryValidationResult`, `DownloadUrlResult`, `TagCategoryResult`, `TagResult` |
| `domain.storage` | `CreateMultipartUploadRequest`, `CreateMultipartUploadResult`, `PresignUploadPartRequest`, `PresignDownloadObjectRequest`, `ListPartsRequest`, `CompleteMultipartUploadRequest`, `HeadObjectResult`, `HeadObjectRequest`, `DeleteObjectRequest`, `AbortMultipartUploadRequest` |
| `cli.manifest` | `ManifestPart`, `UploadManifest` |

## CLI Contracts

`pyproject.toml` exposes:

| Script | Target |
| --- | --- |
| `uploadctl` | `upload_control_plane.cli.main:app` |
| `upload-worker` | `upload_control_plane.worker.main:app` |

`uploadctl` public commands:

| Command | Function | Public parameters |
| --- | --- | --- |
| `upload` | `upload` | `file`, `--api-url`, `--api-key`, `--project-id`, `--tenant`, `--device-id`, `--source-device-id`, `--task-name`, `--dataset-name`, `--object-name`, `--content-type`, `--part-size`, `--concurrency`, `--manifest`, `--checksum-sha256`, `--compute-sha256`, `--presign-expires-seconds` |
| `resume` | `resume` | `manifest`, `--api-key`, `--concurrency`, `--presign-expires-seconds`, `--force-file-changed`, `--no-complete` |
| `status` | `status` | `session_id`, `--api-url`, `--api-key` |
| `pause` | `pause` | `session_id`, `--api-url`, `--api-key`, `--reason`, `--manifest` |
| `resume-session` | `resume_session` | `session_id`, `--api-url`, `--api-key`, `--reason` |
| `abort` | `abort` | `session_id`, `--api-url`, `--api-key`, `--reason`, `--manifest` |

`upload-worker` operator commands:

| Command | Function | Parameters |
| --- | --- | --- |
| `run-once` | `run_once` | none |
| `validate-datasets` | `validate_datasets` | none |
| `dispatch-outbox` | `dispatch_outbox` | none |
| `reconcile` | `reconcile` | `object_ref` |
| `run` | `run` | none |

## DB-Facing Public Schema Artifacts

Alembic migrations:

| File | Revision | Down revision | Created tables |
| --- | --- | --- | --- |
| `20260624_0001_persistence_base.py` | `20260624_0001` | `None` | none |
| `20260624_0002_core_schema.py` | `20260624_0002` | `20260624_0001` | `tenants`, `storage_policies`, `api_keys`, `projects` |
| `20260624_0003_dataset_governance_schema.py` | `20260624_0003` | `20260624_0002` | `devices`, `datasets`, `tag_categories`, `tags`, `dataset_tags`, `permission_grants` |
| `20260624_0004_upload_lifecycle_schema.py` | `20260624_0004` | `20260624_0003` | `upload_tasks`, `upload_objects`, `upload_sessions`, `upload_parts` |
| `20260624_0005_validation_audit_outbox_idempotency_schema.py` | `20260624_0005` | `20260624_0004` | `dataset_validation_results`, `upload_events`, `audit_events`, `outbox_events`, `idempotency_records` |
| `20260625_0006_device_credentials_schema.py` | `20260625_0006` | `20260624_0005` | `device_credentials` |

ORM model categories from `infrastructure/db/models.py`:

| Category | ORM models | Tables |
| --- | --- | --- |
| Identity, auth, permissions | `Tenant`, `ApiKey`, `PermissionGrant` | `tenants`, `api_keys`, `permission_grants` |
| Project and device registry | `Project`, `Device`, `DeviceCredential` | `projects`, `devices`, `device_credentials` |
| Storage policy | `StoragePolicy` | `storage_policies` |
| Dataset, tags, validation | `Dataset`, `TagCategory`, `Tag`, `DatasetTag`, `DatasetValidationResult` | `datasets`, `tag_categories`, `tags`, `dataset_tags`, `dataset_validation_results` |
| Upload lifecycle | `UploadTask`, `UploadObject`, `UploadSession`, `UploadPart`, `UploadEvent` | `upload_tasks`, `upload_objects`, `upload_sessions`, `upload_parts`, `upload_events` |
| Audit, outbox, idempotency | `AuditEvent`, `OutboxEvent`, `IdempotencyRecord` | `audit_events`, `outbox_events`, `idempotency_records` |

Status and enum fields in ORM models:

| Table/model | Status or enum-like fields |
| --- | --- |
| `tenants` / `Tenant` | `status` text, default `ACTIVE` |
| `storage_policies` / `StoragePolicy` | `status` text, default `ACTIVE` |
| `api_keys` / `ApiKey` | `status` text, default `ACTIVE` |
| `projects` / `Project` | `status` text, default `ACTIVE` |
| `devices` / `Device` | `status` enum `device_status` |
| `datasets` / `Dataset` | `status` enum `dataset_status`, `validation_status` enum `validation_status`, `recovery_status` enum `recovery_status`, `preview_status` text |
| `upload_tasks` / `UploadTask` | `status` enum `upload_task_status` |
| `upload_objects` / `UploadObject` | `status` enum `upload_object_status` |
| `upload_sessions` / `UploadSession` | `status` enum `upload_session_status`, `checksum_mode` text |
| `upload_parts` / `UploadPart` | `status` enum `upload_part_status` |
| `dataset_validation_results` / `DatasetValidationResult` | `status` enum `validation_status` |
| `outbox_events` / `OutboxEvent` | `status` enum `outbox_status` |
| `idempotency_records` / `IdempotencyRecord` | `response_status` integer |

## Upload-Relevant State Machines and Status Enums

Domain enums:

| Domain enum | Values |
| --- | --- |
| `UploadSessionStatus` | `INITIATING`, `INITIATED`, `UPLOADING`, `PAUSED`, `COMPLETING`, `COMPLETED`, `ABORTING`, `ABORTED`, `EXPIRED`, `FAILED` |
| `UploadObjectStatus` | `PENDING`, `UPLOADING`, `PAUSED`, `COMPLETING`, `COMPLETED`, `CANCELING`, `CANCELED`, `EXPIRED`, `FAILED` |
| `UploadTaskStatus` | `PENDING`, `UPLOADING`, `PAUSED`, `COMPLETING`, `COMPLETED`, `CANCELING`, `CANCELED`, `EXPIRED`, `FAILED` |
| `DatasetStatus` | `CREATED`, `UPLOAD_PENDING`, `UPLOADING`, `PAUSED`, `PROCESSING`, `QUARANTINED`, `READY`, `REJECTED`, `ARCHIVED`, `DELETED`, `PURGED` |
| `ValidationStatus` | `NOT_REQUIRED`, `PENDING`, `RUNNING`, `PASSED`, `FAILED`, `SKIPPED` |
| `RecoveryStatus` | `NORMAL`, `RECOVERY_PENDING`, `RECOVERY_VERIFIED`, `RECOVERY_MISSING_OBJECT`, `RECOVERY_METADATA_ONLY`, `RECOVERY_OBJECT_ONLY` |
| `SubjectType` | `user`, `group`, `device`, `api_key` |
| `ResourceType` | `tenant`, `project`, `dataset`, `upload_session`, `upload_task`, `device`, `tag_category`, `tag`, `storage_policy` |
| `PermissionEffect` | `ALLOW`, `DENY` |

Upload session guards in `domain/session_state.py`:

| Guard | Allowed statuses |
| --- | --- |
| `can_presign` | `INITIATED`, `UPLOADING` |
| `can_pause` | `INITIATED`, `UPLOADING`, `PAUSED` |
| `can_resume` | `PAUSED`, `UPLOADING` |
| `can_complete` | `INITIATED`, `UPLOADING`, `PAUSED`, `COMPLETED` |
| `can_abort` | `INITIATED`, `UPLOADING`, `PAUSED`, `EXPIRED`, `ABORTED` |

DB enum values from migrations:

| DB enum | Values |
| --- | --- |
| `upload_session_status` | `INITIATING`, `INITIATED`, `UPLOADING`, `PAUSED`, `COMPLETING`, `COMPLETED`, `ABORTING`, `ABORTED`, `EXPIRED`, `FAILED` |
| `upload_part_status` | `EXPECTED`, `PRESIGNED`, `UPLOADED`, `MISSING`, `FAILED` |
| `dataset_status` | `CREATED`, `UPLOAD_PENDING`, `UPLOADING`, `PAUSED`, `PROCESSING`, `QUARANTINED`, `READY`, `REJECTED`, `ARCHIVED`, `DELETED`, `PURGED` |
| `upload_task_status` | `CREATED`, `PENDING`, `PROCESSING`, `PAUSED`, `COMPLETED`, `FAILED`, `CANCELLED` |
| `upload_object_status` | `CREATED`, `PENDING`, `UPLOADING`, `PAUSED`, `COMPLETING`, `COMPLETED`, `FAILED`, `CANCELLED`, `SKIPPED_INSTANT_UPLOAD` |
| `device_status` | `ACTIVE`, `DISABLED`, `REVOKED`, `DELETED` |
| `validation_status` | `NOT_REQUIRED`, `PENDING`, `RUNNING`, `PASSED`, `FAILED`, `SKIPPED` |
| `recovery_status` | `NORMAL`, `RECOVERY_PENDING`, `RECOVERY_VERIFIED`, `RECOVERY_MISSING_OBJECT`, `RECOVERY_METADATA_ONLY`, `RECOVERY_OBJECT_ONLY` |
| `outbox_status` | `PENDING`, `PROCESSING`, `DELIVERED`, `FAILED`, `DEAD_LETTERED` |
| `permission_effect` | `ALLOW`, `DENY` |

Recorded inventory note: domain aggregate statuses and DB aggregate statuses
are not identical. For example, domain upload task/object enums use
`UPLOADING`, `COMPLETING`, `CANCELING`, `CANCELED`, and `EXPIRED`, while the DB
task/object enums include `CREATED`, `PROCESSING`, `CANCELLED`, and
`SKIPPED_INSTANT_UPLOAD` for objects. This report records the current contract
surface only and does not classify that difference as a bug.

## PRD Contract Expectations Compared to Current Inventory

Known PRD expectations that are easy to compare:

| Area | PRD expectation | Current inventory |
| --- | --- | --- |
| API versioning | Public product APIs under `/v1`. | Product routes are under `/v1`; `/healthz`, `/metrics`, and `/internal/auth-smoke` are unversioned operational/internal routes. |
| Upload task creation | `POST /v1/projects/{project_id}/upload-tasks`. | Implemented as `create_upload_task` with `UploadTaskCreateRequest` and `UploadTaskCreateResponse`. |
| Direct bare upload session creation | Not the product entrypoint. | No generated route creates a bare upload session directly. Runtime session routes operate under `/v1/uploads/{session_id}`. |
| Runtime upload session APIs | Get, presign parts, ack parts, list parts, complete, abort, pause, resume; optional extend. | Get, presign, ack, list, complete, abort, pause, and resume exist. No generated `/extend` endpoint exists. |
| Device APIs | List/create/get/update/disable/enable/credential rotate/device upload. | All listed PRD device APIs exist, plus `POST /credentials/revoke`. |
| Dataset APIs | List/create/get/patch/archive/delete/restore/purge/preview/download-url and bulk operations. | List/get/patch/archive/delete/restore/purge/download-url exist. No generated create, preview, or bulk dataset endpoints are present in this inventory. |
| Tag APIs | Tag categories and tags list/create/patch/delete. | Tag category and tag list/create/patch/delete routes exist under the project route prefix. |
| Project APIs | List/create/get/patch/archive/restore/delete/member management. | Only list and get project routes are present in this inventory. |
| Storage policy APIs | List/create/get/patch/project assignment. | No generated storage policy routes are present. `storage_policies` exists as a DB table and ORM model. |
| Validation/audit APIs | Dataset validation get/retry and audit events. | Dataset validation get/retry and project audit event list exist. |
| Error format | Stable `{"error": ...}` shape with request ID. | `api.errors` and request ID middleware are mounted; this inventory did not execute error responses. |
| Request ID header | All responses include `X-Request-ID`. | Request ID middleware is mounted; this inventory did not execute every route. |
| State-changing idempotency | State-changing client endpoints should accept `Idempotency-Key`. | Upload task creation and upload session state-changing routes use idempotency header dependencies in route modules. This inventory did not exhaustively verify every state-changing endpoint. |
| CLI | `uploadctl upload`, `resume`, `status`, `pause`, `resume-session`, `abort`. | All listed `uploadctl` commands are present. Current `upload` also requires/accepts `--project-id`. |
| Manual uploader | Development-only browser tool, no new API contracts. | Not inventoried as public API here; existing report notes it uses public control-plane APIs and presigned URLs. |

## Validation Notes

Commands used while preparing this report:

```text
Get-Content -Raw docs/agentic-engineering/experiment-design.md
Get-Content -Raw docs/reports/phase-1-baseline/architecture-drift.md
Get-Content -Raw docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md
Get-Content -Raw docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md
rg --files src/upload_control_plane migrations tests docs/reports/phase-1-baseline
rg -n "APIRouter|include_router|@(router|app)\.(get|post|put|patch|delete)|response_model=|class .*\(BaseModel\)|@.*\.command" src/upload_control_plane migrations
uv run python -  # create_app route metadata extraction
python -         # AST scans for API schemas, CLI commands, ORM models, and migrations
```

No production code was modified. No API contracts were changed. No client code
was generated. The only deliverable produced by this task is this report:

- `docs/reports/phase-1-baseline/public-contract-inventory.md`
