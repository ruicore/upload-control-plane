# Baseline Hotspot Files

Status: active

Recorded for: Phase 1 Task P1-03

## Scope

This report records hotspot file evidence for the current unconstrained Codex
baseline. It is intentionally limited to observed file size, symbol shape,
apparent responsibilities, mixed-concern signals, and future-agent risk. It
does not propose detailed refactor designs and does not modify production code.

Inputs read:

- `docs/reports/phase-1-baseline/repository-inventory.md`
- `docs/reports/phase-1-baseline/repository-metrics.json`
- `docs/agentic-engineering/experiment-design.md`

## Method

Repository metrics were used as the primary source for file size. Python LOC is
the physical-line metric from `repository-metrics.json`, including blank and
comment lines. Symbol counts were computed with Python AST parsing under the
repo runtime because the codebase uses syntax newer than the system Python.

Inspection boundary:

- Deep inspection: Python files over 500 LOC.
- Secondary hotspot inventory: Python files over 300 LOC.
- Files at or below 300 LOC were not classified as hotspots in this report.

Baseline size facts from `repository-inventory.md`:

| Metric | Value |
| --- | ---: |
| Python files | 98 |
| Max Python LOC | 1597 |
| Median Python LOC | 118.00 |
| Mean Python LOC | 241.22 |
| Python files over 300 LOC | 24 |
| Python files over 500 LOC | 14 |
| Python files over 800 LOC | 6 |
| Python files over 1000 LOC | 4 |

Severity criteria used here:

| Severity | Criteria |
| --- | --- |
| Critical | Production file over 1000 LOC, or central runtime/schema authority where many future changes will converge. |
| High | Production file over 500 LOC, or test file over 800 LOC covering several public behaviors in one place. |
| Medium | File over 400 LOC with a narrower surface, or a 500-800 LOC test file that concentrates setup/fakes plus multiple cases. |
| Low | File over 300 LOC whose size is mainly generated, migration, or localized support evidence. |

## Critical Hotspots

| File | LOC | Classes / functions | Evidence ranges | Primary apparent responsibilities | Signs of mixed concerns | Why it matters for future Codex sessions |
| --- | ---: | ---: | --- | --- | --- | --- |
| `src/upload_control_plane/application/upload_sessions.py` | 1597 | 12 classes / 49 functions | Result dataclasses at lines 53-160; `UploadSessionRuntimeService` at lines 163-1478; JSON/idempotency result helpers at lines 1481-1597. | Runtime upload session status, part presign, uploaded-part acknowledgement, part listing, pause, resume, completion, abort, storage reconciliation, related-record synchronization, and idempotency response persistence. | The same service owns public lifecycle actions at lines 171-781, storage observation/listing at lines 813-901, completion validation at lines 903-966, DB part upsert/load paths at lines 968-1037, event creation at lines 1039-1062, idempotency at lines 1064-1152, and status synchronization at lines 1318-1364. | This is the largest Python file and the main runtime behavior convergence point. Future agents may patch a lifecycle path locally while missing coupled storage, idempotency, event, or related-record status behavior in the same file. |
| `src/upload_control_plane/infrastructure/db/models.py` | 1159 | 20 classes / 0 functions | ORM model classes span lines 25-1159. Examples: `Tenant` lines 25-41, `Dataset` lines 283-409, `UploadTask` lines 559-644, `UploadSession` lines 718-850, `UploadPart` lines 853-911, `OutboxEvent` lines 1083-1126, `IdempotencyRecord` lines 1129-1159. | Central SQLAlchemy schema definitions for tenants, storage policies, API keys, projects, devices, credentials, datasets, tags, permissions, upload tasks, objects, sessions, parts, validation results, upload events, audit events, outbox events, and idempotency records. | One file is the schema authority for authentication, authorization, dataset governance, upload lifecycle, audit/outbox, and idempotency domains. The file is large because many independent tables are declared in one module, not because of function branching. | Future agents changing persistence for one domain must navigate a file containing many other domains. This increases the chance of local schema edits missing adjacent relationship, enum, or index patterns elsewhere in the same module. |
| `src/upload_control_plane/application/datasets.py` | 1036 | 9 classes / 36 functions | Result dataclasses at lines 40-136; `DatasetLifecycleService` at lines 139-998; mapping helpers at lines 1001-1036. | Dataset list/detail, validation result lookup, retry validation, metadata update, download URL creation, archive, soft delete, restore, purge, tag category CRUD, tag CRUD, audit event creation, and purge policy checks. | One service includes read queries at lines 145-233, validation retry at lines 235-320, download signing at lines 368-450, lifecycle state transitions at lines 452-621, tag management at lines 623-766, policy checks at lines 800-844, tag replacement at lines 846-865, and audit writes at lines 970-998. | Dataset behavior is broad and stateful. A future agent may edit lifecycle behavior while missing related validation, storage exposure, tag, or audit rules in the same service. |

## High Hotspots

| File | LOC | Classes / functions | Evidence ranges | Primary apparent responsibilities | Signs of mixed concerns | Why it matters for future Codex sessions |
| --- | ---: | ---: | --- | --- | --- | --- |
| `tests/api/test_upload_session_runtime_api.py` | 1151 | 1 class / 36 functions | Runtime API tests at lines 62-901; helper/data cleanup functions at lines 904-1087; `RuntimeFakeObjectStorage` at lines 1090-1151. | API coverage for upload session status, presign, acknowledgement, permissions, tenant isolation, DB/storage/reconcile part listing, pause/resume, complete, checksum handling, and abort behavior. | A single test file combines endpoint behavior, permission changes, storage fakes, DB cleanup, idempotency cases, lifecycle cases, and tenant-isolation checks. | It is a major safety net, but future agents may add more cases to the same file by default, further concentrating runtime API knowledge and slowing targeted test discovery. |
| `tests/api/test_upload_task_api_foundation.py` | 949 | 1 class / 38 functions | Upload task tests at lines 60-631 and 673-687; payload/helpers at lines 634-902; `FakeObjectStorage` at lines 905-949. | API coverage for auth, project permission, single/multi-file task creation, idempotency, request validation, object/session persistence, quotas, KMS policy, storage backpressure, metrics backpressure, and multipart byte-input rejection. | One file holds public API behavior, quota and storage-policy behavior, fake storage behavior, DB cleanup, auth helpers, and payload factories. | Future agents may treat this as the only upload-task contract surface and miss smaller domain or infrastructure tests when making creation-flow changes. |
| `tests/api/test_dataset_lifecycle_api.py` | 926 | 1 class / 32 functions | Dataset API tests at lines 66-689; helper/data cleanup functions at lines 692-871; `DatasetFakeObjectStorage` at lines 874-926. | API coverage for dataset list/detail/update/download, blocked exposure states, validation result access, retry validation, purge confirmation/governance, object lock/legal hold checks, tag category CRUD, tag CRUD, and dataset tag updates. | One file combines dataset lifecycle, validation retry, download permission, purge policy, tag management, storage fakes, and DB cleanup. | Dataset API changes have a wide test surface in one file; future agents may append new scenarios here rather than finding or creating narrower test anchors. |
| `src/upload_control_plane/api/datasets.py` | 789 | 18 classes / 29 functions | Request/response models at lines 35-201; route handlers at lines 205-646; permission and response helpers at lines 649-789. | FastAPI dataset contracts for listing, detail, validation, retry, update, download URL creation, archive, soft delete, restore, purge, tag categories, and tags. | The file combines Pydantic request/response schemas, route handlers, permission loading, service delegation, and response mapping for multiple dataset subdomains. | Public API changes in datasets require careful scanning across schemas, route handlers, permissions, and serializers in one file. |
| `src/upload_control_plane/observability.py` | 760 | 2 classes / 44 functions | Logging formatter lines 47-78; logging utilities lines 81-146; `MetricsRegistry` lines 149-254; operational metric renderers lines 260-760. | JSON log formatting, redaction, route context, in-memory metric registry, storage backpressure counters, Prometheus rendering, and DB-backed operational metrics. | The file mixes logging/redaction utilities, in-process metrics, SQL-backed metric queries, output formatting helpers, and domain-specific metric family rendering. | Future agents adding metrics may copy nearby patterns without noticing redaction constraints, label conventions, or DB query helper behavior in distant sections of the same file. |
| `src/upload_control_plane/application/worker_lifecycle.py` | 743 | 3 classes / 23 functions | Summary/reference dataclasses at lines 43-59; `WorkerLifecycleService` at lines 62-702; helper functions at lines 705-743. | Worker lifecycle run orchestration, expired session aborts, multipart cleanup, recycle-bin retention purge, recovery reconciliation, object-only dataset rebuild, related-record synchronization, upload event writing, and audit writing. | One worker service includes scheduler entrypoint logic, storage cleanup, dataset purge governance, recovery reconciliation, outbox event creation, and audit state serialization. | Background lifecycle behavior touches storage, datasets, sessions, recovery status, and audit/outbox effects. Future agents may validate one path while missing cross-effects in the same service. |
| `src/upload_control_plane/api/upload_sessions.py` | 689 | 18 classes / 24 functions | Request/response models at lines 38-241; route handlers at lines 245-488; loading/permission/response helpers at lines 491-689. | FastAPI upload session contracts for status, presign, acknowledgement, part listing, pause, resume, complete, and abort. | The file combines Pydantic validation, route handlers, actor/session loading, permission checks, part-number resolution, and response mapping. | Runtime API contract changes require coordinated edits across models, handlers, permission helpers, and response helpers in one file. |
| `src/upload_control_plane/application/upload_tasks.py` | 623 | 5 classes / 16 functions | Command/result dataclasses at lines 37-89; `UploadTaskCreationService` at lines 92-503; idempotency/policy/result helpers at lines 506-623. | Upload task creation, idempotency handling, storage-policy selection, quota checks, object/session creation, storage initiation, event writing, and result serialization. | Creation flow includes request semantics, quota validation, storage capabilities, persistence, event emission, idempotency, and JSON response reconstruction. | Future agents adding upload creation behavior may need to reason across business validation, storage initiation, persistence, and idempotency in one service. |

## Medium Hotspots

| File | LOC | Classes / functions | Evidence ranges | Primary apparent responsibilities | Signs of mixed concerns | Why this matters for future Codex sessions |
| --- | ---: | ---: | --- | --- | --- | --- |
| `tests/application/test_worker_lifecycle.py` | 669 | 2 classes / 26 functions | Worker behavior tests at lines 60-389; graph helper at lines 392-504; cleanup/fake storage at lines 507-669. | Tests for expired-session aborts, completed-session guard, recycle retention purge, recovery reconciliation, object metadata restoration, and object-only dataset rebuild. | Behavior tests share graph setup, cleanup, outbox inspection, and fake storage in one file. | Worker changes may be tested here, but the breadth can obscure which setup is required for each lifecycle scenario. |
| `tests/api/test_device_identity_api.py` | 519 | 1 class / 24 functions | Device API tests at lines 59-312; helpers at lines 315-472; `DeviceFakeObjectStorage` at lines 475-519. | Tests for device registration, secret exposure limits, device upload task creation, credential disabling, rotation, expiry, and source device metadata. | Combines identity, credential lifecycle, upload-task creation, auth headers, cleanup, and storage fake behavior. | Device-related changes can affect both identity and upload flows; the single test file is useful but broad. |
| `tests/api/test_observability.py` | 514 | 1 class / 27 functions | Observability tests at lines 74-284; helper functions at lines 287-462; `ObservabilityFakeObjectStorage` at lines 465-514. | Tests for Prometheus metric output, required metric family coverage, backpressure metric labels, request logging context, audit endpoint permission, and redaction. | Combines metrics, logging, audit endpoint behavior, DB setup, settings overrides, and fake storage. | Observability changes may need several unrelated-looking assertions in one file to remain aligned. |
| `src/upload_control_plane/application/devices.py` | 487 | 4 classes / 16 functions | Result dataclasses at lines 36-65; `DeviceService` at lines 68-487. | Device registration, device detail/list/update, enable/disable, credential provisioning, rotation/revocation, credential authentication, and device upload command construction. | Device identity and credential lifecycle share a service with upload-command assembly. | Future agents may change credential behavior without noticing upload-entry behavior in the same service. |
| `src/upload_control_plane/application/dataset_validation.py` | 450 | 9 classes / 16 functions | Validation dataclasses/protocols at lines 25-84; HDF5 extractor at lines 87-152; error type at lines 155-167; `DatasetValidationWorkerService` at lines 170-423; helpers at lines 426-450. | Dataset validation worker, metadata extraction, file inspection hook, validation error recording, dataset state transition, and validation summary. | Validation orchestration, file metadata extraction, hook abstraction, error shaping, DB updates, and state mapping coexist in one file. | Future validation changes may cross worker behavior and extraction semantics; the file is not huge, but it carries multiple roles. |
| `src/upload_control_plane/infrastructure/storage/s3_minio.py` | 430 | 1 class / 25 functions | Client builders at lines 56-108; `S3ObjectStorage` at lines 111-303; response/error/option mapping helpers at lines 306-430. | S3/MinIO client construction, multipart upload operations, presigning, listing, completion, abort/delete/head behavior, error mapping, encryption/object-lock/checksum option mapping. | Adapter operations and provider-specific mapping helpers are colocated with client construction. | Provider changes can require scanning both operation methods and mapping helpers; missing one can create runtime drift. |
| `src/upload_control_plane/cli/uploader.py` | 423 | 3 classes / 18 functions | Options/outcome dataclasses at lines 36-62; `MultipartUploader` at lines 68-325; validation/payload/progress/retry helpers at lines 328-423. | CLI upload orchestration, create-task payload construction, file hashing, part upload concurrency, part acknowledgement, completion, retry delay, and progress output. | Local file validation, API calls, concurrency, progress rendering, retry behavior, and payload shaping are colocated. | Future CLI changes may accidentally couple user-facing output, retry behavior, and upload protocol details. |
| `src/upload_control_plane/domain/storage.py` | 409 | 27 classes / 31 functions | Storage errors at lines 14-60; validation helpers at lines 63-90; request/result dataclasses at lines 94-372; `ObjectStorage` protocol at lines 376-409. | Storage domain errors, request/result value objects, validation helpers, and object storage protocol definition. | Many storage concepts share one domain module, but most are small dataclasses or protocol definitions rather than complex behavior. | This is a vocabulary hotspot: future agents should treat it as a central contract file, not as an implementation file. |
| `src/upload_control_plane/api/devices.py` | 402 | 6 classes / 12 functions | Request/response models at lines 47-100; route handlers at lines 104-356; permission/response helpers at lines 359-402. | FastAPI device contracts for list/register/get/update/enable/disable/rotate/revoke and device upload task creation. | Device admin APIs and device upload entrypoint share schemas, routes, permission helper, and response mappers. | Device authorization changes may affect both management routes and upload creation routes. |

## Low Hotspots

| File | LOC | Classes / functions | Evidence ranges | Primary apparent responsibilities | Signs of mixed concerns | Why this matters for future Codex sessions |
| --- | ---: | ---: | --- | --- | --- | --- |
| `tests/application/test_dataset_validation_worker.py` | 416 | 2 classes / 22 functions | Validation worker tests at lines 57-176; graph helper at lines 179-288; cleanup/fake storage at lines 291-416. | Tests for completed dataset validation, validation failure handling, disabled validation behavior, DB graph setup, and fake object storage. | Test behavior, setup graph construction, cleanup, and fake storage are combined. | Lower risk than broader API tests, but future validation work may keep adding setup-heavy cases here. |
| `tests/application/test_outbox.py` | 363 | 2 classes / 16 functions | Outbox tests at lines 31-255; fake sinks at lines 258-271; helpers at lines 274-363. | Tests for atomic domain write plus outbox append, delivery idempotency, retry scheduling, dead-letter handling, rollback boundaries, and payload redaction. | Outbox delivery behavior, payload safety checks, fake sinks, dataset setup, and cleanup are colocated. | This is a compact but dense contract file; future agents should preserve both delivery and redaction assertions. |
| `migrations/versions/20260624_0004_upload_lifecycle_schema.py` | 334 | 0 classes / 2 functions | `upgrade` lines 27-312; `downgrade` lines 315-334. | Alembic schema migration for upload lifecycle structures. | Large migration body concentrates DDL in one generated/historical file. | It is a size hotspot but not a refactor target during normal feature work; future agents should treat it as historical schema evidence. |
| `migrations/versions/20260624_0003_dataset_governance_schema.py` | 329 | 0 classes / 2 functions | `upgrade` lines 28-307; `downgrade` lines 310-329. | Alembic schema migration for dataset governance structures. | Large migration body concentrates DDL in one generated/historical file. | It is a size hotspot but lower future-edit risk because migrations should usually remain immutable after application. |

## Observations

The largest production hotspots are not isolated utilities. They are central
application or infrastructure authority files:

- Upload runtime behavior concentrates in
  `src/upload_control_plane/application/upload_sessions.py`.
- Dataset lifecycle behavior concentrates in
  `src/upload_control_plane/application/datasets.py`.
- Database schema vocabulary concentrates in
  `src/upload_control_plane/infrastructure/db/models.py`.

The largest test hotspots mirror the production concentration:

- Upload session runtime API coverage is concentrated in
  `tests/api/test_upload_session_runtime_api.py`.
- Upload task creation API coverage is concentrated in
  `tests/api/test_upload_task_api_foundation.py`.
- Dataset lifecycle API coverage is concentrated in
  `tests/api/test_dataset_lifecycle_api.py`.

The baseline therefore supports the experiment-design hypothesis that
unconstrained Codex tends to extend existing files and concentrate multiple
responsibilities in large files. This report records that as baseline evidence
only. It does not claim that every large file is wrong, and it does not
recommend a refactor plan.

## Validation Notes

No production code was changed for this task. The only intended deliverable is:

- `docs/reports/phase-1-baseline/hotspot-files.md`

Checks performed while preparing this report:

```text
Get-Content docs/reports/phase-1-baseline/repository-inventory.md
Get-Content docs/reports/phase-1-baseline/repository-metrics.json
Get-Content docs/agentic-engineering/experiment-design.md
uv run python -  # AST symbol extraction for Python files over 300 LOC
```
