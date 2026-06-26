# Mixed Responsibility Audit

Status: active

Recorded for: Phase 1 Task P1-05

## Scope

This report audits mixed responsibilities in the highest-impact hotspot files
from the current unconstrained Codex baseline. It is diagnostic only.

Inputs read:

- `docs/reports/phase-1-baseline/hotspot-files.md`
- `docs/reports/phase-1-baseline/architecture-drift.md`
- `docs/agentic-engineering/experiment-design.md`

Constraints applied:

- No production code was modified.
- No extraction filenames are suggested.
- No refactor plan is proposed.
- Findings use concrete file paths and line ranges.

## File Selection

The selected files are the highest-impact production hotspots because they are
either critical-size application/schema authorities or broad API files already
identified as architecture-drift concentration points.

| Rank | File | Reason selected |
| ---: | --- | --- |
| 1 | `src/upload_control_plane/application/upload_sessions.py` | Largest Python hotspot and central upload runtime lifecycle authority. |
| 2 | `src/upload_control_plane/infrastructure/db/models.py` | Central ORM schema authority spanning many unrelated domains. |
| 3 | `src/upload_control_plane/application/datasets.py` | Critical-size dataset lifecycle and governance application service. |
| 4 | `src/upload_control_plane/api/datasets.py` | Broad API route module combining dataset schemas, routes, permission calls, and response mapping. |
| 5 | `src/upload_control_plane/api/upload_sessions.py` | Broad API route module combining upload runtime schemas, routes, permission calls, idempotency request mapping, and response mapping. |

Test hotspot files were not selected for this task because the requested mixed
concern examples are primarily production architecture concerns.

## Responsibility Maps

### `src/upload_control_plane/application/upload_sessions.py`

| Line range | Responsibility |
| --- | --- |
| 1-49 | Imports and shared `PartListSource` vocabulary, including API auth/error types, SQLAlchemy, domain storage contracts, and ORM models. |
| 52-160 | Runtime result and command dataclasses for status, presign, acknowledgement, part listing, pause, resume, complete, and abort. |
| 163-412 | `UploadSessionRuntimeService` public status, presign, acknowledgement, and part-listing operations. |
| 414-558 | Pause and resume lifecycle orchestration, including idempotency lookup/storage, state changes, related-record sync, events, commits, and failure rollback. |
| 559-781 | Complete and abort lifecycle orchestration, including idempotency, state transitions, storage calls, storage error mapping, related-record sync, and event writes. |
| 783-812 | Upload session loading and row-lock helpers. |
| 813-901 | Storage part observation and listing, including storage pagination, API error mapping, optional reconciliation, part upserts, and events. |
| 903-966 | Complete validation against observed storage parts and missing/unexpected/size-mismatch error shaping. |
| 968-1037 | Upload part persistence helpers and uploaded-part count/list queries. |
| 1039-1062 | Upload event persistence. |
| 1064-1152 | Idempotency record resolution, response persistence, and rollback cleanup. |
| 1154-1364 | Invalid-state errors, completion/abort marking, status restoration after storage failure, missing-part restoration, and related dataset/object/task synchronization. |
| 1366-1478 | Internal result mappers for completed/aborted/session/part/storage-part outputs plus count helper. |
| 1481-1523 | Cross-domain status mapping from upload session state to upload object, upload task, and dataset state. |
| 1526-1597 | JSON serialization/deserialization helpers for idempotent pause, resume, complete, and abort responses. |

Mixed responsibilities:

| Mixed concern | Evidence | Why it matters for Codex execution | Classification |
| --- | --- | --- | --- |
| DTO/result types mixed with service orchestration | Result dataclasses are at lines 52-160 and the lifecycle service spans lines 163-1478. | A future agent editing runtime behavior has to keep application outputs, persistence mutations, storage calls, and public response reconstruction in one context window. This raises the chance of updating behavior without updating the corresponding result shape or idempotent replay path. | Agent-context concern. |
| Idempotency mixed with upload lifecycle | Pause/resume/complete/abort call `_resolve_idempotency` and `_store_idempotency_response` throughout lines 414-781, while idempotency persistence lives at lines 1064-1152 and JSON replay helpers live at lines 1526-1597. | Codex may patch a lifecycle branch and miss the replay contract for the same operation because the lifecycle branch, record locking, rollback cleanup, and JSON result reconstruction are separated inside one long file rather than being visible as one small concept. | Agent-context concern. |
| Storage reconciliation mixed with HTTP/API error mapping | Storage list/reconcile methods catch `StorageError` and raise `ApiError` at lines 813-875; complete validation raises `ApiError` at lines 903-966. | Application code currently owns storage observation, reconciliation writes, and HTTP-shaped error payloads. Agents changing storage behavior need API error semantics in memory at the same time. | Agent-context and human readability concern. |
| Upload lifecycle mixed with related aggregate synchronization | Lifecycle methods call `_sync_related_records` at lines 452-454, 526-530, 613-617, 731-735, and final synchronization logic mutates `UploadObject`, `Dataset`, and `UploadTask` at lines 1318-1364. | A local change to session state can silently imply object, dataset, task, validation, and counter behavior. This is high risk for Codex because the correct edit surface is wider than the public method being changed. | Agent-context concern. |
| Event writing mixed with state transitions | `_add_event` is called inside presign/ack/lifecycle/reconcile flows and implemented at lines 1039-1062. | Agents may preserve the state change but omit or misalign the event trail because event creation is embedded as side effects throughout lifecycle code. | Human readability and agent-context concern. |

### `src/upload_control_plane/infrastructure/db/models.py`

| Line range | Responsibility |
| --- | --- |
| 1-22 | ORM imports and declarative base import. |
| 25-41 | Tenant schema. |
| 44-112 | Storage policy schema. |
| 114-140 | API key schema. |
| 142-188 | Project schema. |
| 190-281 | Device and device credential schemas. |
| 283-410 | Dataset schema, including upload, validation, recovery, preview, labels, and storage object fields. |
| 412-497 | Tag category, tag, and dataset-tag association schemas. |
| 499-557 | Permission grant schema. |
| 559-645 | Upload task schema. |
| 647-717 | Upload object schema. |
| 718-850 | Upload session schema. |
| 853-911 | Upload part schema. |
| 914-969 | Dataset validation result schema. |
| 971-1031 | Upload event schema. |
| 1033-1081 | Audit event schema. |
| 1083-1127 | Outbox event schema. |
| 1129-1159 | Idempotency record schema. |

Mixed responsibilities:

| Mixed concern | Evidence | Why it matters for Codex execution | Classification |
| --- | --- | --- | --- |
| ORM models for unrelated domains in one file | Tenant/storage/auth/project/device/dataset/tag/permission/upload/audit/outbox/idempotency schemas span lines 25-1159. | Codex has to search a single long authority file for unrelated persistence concepts. Edits to one table can be made near many tempting adjacent domain models, increasing accidental context bleed. | Agent-context concern. |
| Dataset governance mixed with upload storage fields | `Dataset` includes dataset lifecycle, validation/recovery, preview, metadata, labels, source-device, and storage object fields at lines 283-410. | Dataset changes require understanding whether a field belongs to governance, upload result materialization, validation, recovery, or UI preview. Agents may infer ownership from proximity rather than from domain intent. | Agent-context and human readability concern. |
| Authorization schema mixed with upload lifecycle schema | `PermissionGrant` is at lines 499-557, immediately followed by `UploadTask` and `UploadObject` at lines 559-717 and `UploadSession` at lines 718-850. | Permission schema is a central security concept but lives beside upload lifecycle state. Codex may treat permission changes as local model additions without checking API/application authorization paths. | Agent-context concern. |
| Operational event schemas mixed with domain state schemas | `UploadEvent`, `AuditEvent`, `OutboxEvent`, and `IdempotencyRecord` occupy lines 971-1159 after upload and validation state schemas. | Durable event, audit, delivery, and replay concerns have different change risk than normal domain rows. Co-location makes the file convenient, but it does not make the responsibilities equivalent. | Human readability concern. |

### `src/upload_control_plane/application/datasets.py`

| Line range | Responsibility |
| --- | --- |
| 1-36 | Imports, including API actor/error types, SQLAlchemy, settings, domain state checks, storage contract, and ORM models. |
| 39-136 | Dataset, validation, download URL, tag category, and tag result dataclasses. |
| 139-233 | Dataset list/detail and validation-result read operations. |
| 235-320 | Validation retry orchestration, including state checks, audit write, outbox event write, commit, and result. |
| 322-450 | Dataset update and download URL creation, including exposure checks, storage presign, audit writes, and storage error mapping. |
| 452-621 | Archive, soft delete, restore, and purge lifecycle operations, including storage policy checks, storage delete, audit writes, and storage error mapping. |
| 623-766 | Tag category and tag CRUD operations. |
| 768-895 | Dataset/project/tag loading helpers, purge policy denial logic, dataset-tag replacement, and invalid-state errors. |
| 897-947 | Dataset summary/detail result mapping. |
| 949-998 | Dataset tag lookup, audit-state shape, and audit event persistence. |
| 1001-1036 | Tag and validation result mapping helpers. |

Mixed responsibilities:

| Mixed concern | Evidence | Why it matters for Codex execution | Classification |
| --- | --- | --- | --- |
| DTO/result types mixed with broad service orchestration | Result dataclasses are at lines 39-136 and `DatasetLifecycleService` spans lines 139-998. | Agents changing dataset behavior need to keep several output shapes in view while editing read, validation, lifecycle, storage, tag, audit, and policy branches. | Agent-context concern. |
| Dataset lifecycle mixed with tag administration | Dataset lifecycle operations are at lines 452-621, while tag category/tag CRUD is at lines 623-766. | A future dataset-focused task may append more non-lifecycle behavior into the same service because tags are already colocated with lifecycle, even though the operational risks differ. | Agent-context concern. |
| Storage exposure/deletion mixed with dataset API semantics | Download URL creation at lines 368-450 and purge storage deletion at lines 553-621 both raise HTTP-shaped `ApiError` values and call storage adapters. | Agents editing dataset exposure or purge behavior must reason about storage provider failure semantics and HTTP error payloads inside the same application service. | Agent-context and human readability concern. |
| Validation retry mixed with audit and outbox persistence | Validation retry state changes, audit, outbox, and commit are concentrated at lines 235-320. | Codex may update eligibility or state transitions without preserving the durable audit/outbox side effects because they are embedded in the same method rather than surfaced as an explicit boundary. | Agent-context concern. |
| Purge policy mixed with lifecycle mutation | Purge checks call `_storage_policy_for_project` and `_purge_policy_denial` at lines 568-585, while the policy helper is implemented at lines 800-844 and the final state/storage mutation is at lines 586-621. | Retention/object-lock/legal-hold rules are governance concerns. Their presence inside lifecycle mutation code makes it easier for agents to treat them as local branch conditions instead of durable policy constraints. | Human readability and agent-context concern. |

### `src/upload_control_plane/api/datasets.py`

| Line range | Responsibility |
| --- | --- |
| 1-33 | Imports, router declaration, and shared dependency aliases. |
| 35-201 | Pydantic request/response schemas for dataset list/detail, validation, update, download, purge, tag categories, and tags. |
| 204-239 | Dataset list route, project permission check, service construction, service call, and response mapping. |
| 242-368 | Dataset detail, validation, retry, update, and download routes with dataset permission checks and service calls. |
| 371-466 | Archive, soft delete, restore, and purge routes with dataset permission checks and service calls. |
| 469-646 | Tag category and tag routes with project permission checks and service calls. |
| 649-676 | Project/dataset permission helper functions. |
| 679-789 | Response mapping helpers from application results to API schemas. |

Mixed responsibilities:

| Mixed concern | Evidence | Why it matters for Codex execution | Classification |
| --- | --- | --- | --- |
| API schemas mixed with routes | Pydantic schemas span lines 35-201 and route handlers span lines 204-646. | A route change and a contract change live in the same file. Codex may adjust handler behavior without noticing that the schema section carries the public API contract. | Agent-context concern. |
| Routes mixed with permission checks | Route handlers call `_require_dataset_permission`, `_require_project_permission`, or `AuthorizationService` at lines 220-225, 251-253, 298-300, 323-325, 354-356, 453-455, and 477-502. Permission helpers live at lines 649-676. | Agents adding or editing endpoints must pick the right resource scope and permission code from local patterns. The file makes authorization look like route plumbing even though it is a security boundary. | Agent-context concern. |
| Dataset API mixed with tag API | Dataset routes occupy lines 204-466 and tag routes occupy lines 469-646. | The router prefix is project-scoped, but dataset lifecycle and tag management are separate product surfaces. Codex may grow the same file when either surface changes. | Human readability and agent-context concern. |
| HTTP mapping mixed with application result mapping | Route handlers return mapper helpers implemented at lines 679-789. | Agents editing service result fields must update lower-file mappers and upper-file schemas. The dependency is local but distant enough to miss in a long route module. | Agent-context concern. |

### `src/upload_control_plane/api/upload_sessions.py`

| Line range | Responsibility |
| --- | --- |
| 1-35 | Imports, router declaration, authentication dependency alias, and idempotency header dependency. |
| 38-241 | Pydantic request/response schemas and validators for runtime status, presign, acknowledgement, part listing, pause, resume, complete, and abort. |
| 244-359 | Status, presign, acknowledgement, and part-list routes with owned-session loading, permission checks, service calls, and response mapping. |
| 362-488 | Pause, resume, complete, and abort routes with owned-session loading, permission checks, request path/body idempotency mapping, service calls, and response mapping. |
| 491-545 | Owned-session loading and runtime permission helper functions. |
| 547-578 | Part-number selection and request limit validation helper. |
| 581-689 | Response mapping helpers from application results to API schemas. |

Mixed responsibilities:

| Mixed concern | Evidence | Why it matters for Codex execution | Classification |
| --- | --- | --- | --- |
| API schemas mixed with routes | Request/response schemas and validators span lines 38-241; route handlers span lines 244-488. | Public contract validation and handler orchestration are colocated. Codex may change one part of the runtime API while missing coupled validators or response models above it. | Agent-context concern. |
| Routes mixed with permission checks and ownership checks | Routes call `_load_owned_session` and `_require_runtime_permission` throughout lines 252-281, 309-315, 344-350, 373-379, 438-444, and 470-476; helpers are at lines 491-545. | Permission target selection changes depending on whether a session has a dataset or project. That is security-sensitive logic embedded in the route file, making local endpoint edits risky for agents. | Agent-context concern. |
| Idempotency request mapping mixed with lifecycle routes | Pause/resume/complete/abort route handlers pass `fastapi_request.url.path`, `request.model_dump(mode="json")`, and `Idempotency-Key` into the service at lines 381-390, 414-422, 446-454, and 478-486. | Idempotency identity depends on HTTP path and body shape, but the persistence/replay logic lives in the application service. Agents changing request schemas or route paths must remember the replay fingerprint contract. | Agent-context concern. |
| HTTP request validation mixed with upload protocol validation | `PresignPartsRequest` and `AckUploadedPartRequest` validators live at lines 58-143, while `_resolve_part_numbers` applies session-specific bounds at lines 547-578. | Protocol correctness is split between Pydantic validation and helper logic below the routes. Codex may update one validation layer and miss the other. | Human readability and agent-context concern. |
| Response mapping mixed with route orchestration | Response mappers are at lines 581-689 and depend on application result classes imported at lines 15-27. | Agents editing application result fields must synchronize API schemas and mapper helpers across separated regions of the same large file. | Agent-context concern. |

## Cross-File Observations

| Pattern | Files | Diagnostic note |
| --- | --- | --- |
| API-shaped errors appear in application services | `src/upload_control_plane/application/upload_sessions.py` lines 13-14, 250-256, 847-852, 953-958; `src/upload_control_plane/application/datasets.py` lines 11-12, 395-435, 580-602. | Application services currently emit HTTP-oriented errors directly. This is mainly an agent-context concern because future agents must preserve API behavior while editing application logic. |
| Application services import ORM models directly | `src/upload_control_plane/application/upload_sessions.py` lines 39-47; `src/upload_control_plane/application/datasets.py` lines 26-36. | Direct model access broadens the service edit surface to persistence details. This is an agent-context concern and matches earlier architecture-drift evidence. |
| Route files repeat the pattern "schema, route, permission, mapper" | `src/upload_control_plane/api/datasets.py` lines 35-789; `src/upload_control_plane/api/upload_sessions.py` lines 38-689. | The pattern is consistent and readable locally, but it concentrates public contract, security checks, and mapping in files that future Codex sessions are likely to extend. |
| Idempotency crosses API and application boundaries without a compact local view | `src/upload_control_plane/api/upload_sessions.py` lines 35, 381-390, 414-422, 446-454, 478-486; `src/upload_control_plane/application/upload_sessions.py` lines 1064-1152 and 1526-1597. | The replay key depends on HTTP request details while replay storage lives in application code. This is a high-value agent-context concern because route or schema edits can affect idempotency fingerprints. |
| Upload lifecycle state fans out into dataset, task, object, event, audit, and idempotency concepts | `src/upload_control_plane/application/upload_sessions.py` lines 414-781, 1039-1152, 1318-1364; `src/upload_control_plane/infrastructure/db/models.py` lines 559-1159. | The current implementation is functional but concept-dense. For Codex, the risk is not simply long files; it is that a narrow upload lifecycle prompt may require many distant responsibilities to remain correct. |

## Diagnostic Summary

The top production hotspots are not just long files. They concentrate
responsibilities that are likely to be edited together by Codex under pressure:
public API contracts, permission checks, application orchestration, storage
adapter calls, ORM persistence, idempotency replay, events, audit, and
cross-aggregate status synchronization.

The strongest agent-context concerns are:

- `src/upload_control_plane/application/upload_sessions.py`: upload lifecycle,
  storage reconciliation, idempotency, event writing, and related-record sync
  are all in one service file.
- `src/upload_control_plane/api/upload_sessions.py`: HTTP route shape and
  idempotency fingerprint inputs are close to route handlers but distant from
  application replay logic.
- `src/upload_control_plane/infrastructure/db/models.py`: unrelated domain
  models share one schema authority, making local persistence edits easy to
  overgeneralize.

The strongest human readability concerns are:

- `src/upload_control_plane/application/datasets.py`: dataset lifecycle,
  storage exposure/deletion, validation retry, tag management, audit, and
  policy checks are readable locally but conceptually broad.
- `src/upload_control_plane/api/datasets.py`: dataset and tag API surfaces are
  both readable but concentrated in a single schema/route/permission/mapper
  module.

This report records baseline evidence only. It does not prescribe a target
shape or implementation sequence.

## Validation Notes

Commands used while preparing this report:

```text
Get-Content docs/reports/phase-1-baseline/hotspot-files.md
Get-Content docs/reports/phase-1-baseline/architecture-drift.md
Get-Content docs/agentic-engineering/experiment-design.md
rg -n "^(class|def|@dataclass|    def)" src/upload_control_plane/application/upload_sessions.py src/upload_control_plane/application/datasets.py src/upload_control_plane/infrastructure/db/models.py src/upload_control_plane/api/datasets.py src/upload_control_plane/api/upload_sessions.py
Get-Content with line-number rendering for the selected hotspot files
```

No production code was changed. The only intended deliverable is:

- `docs/reports/phase-1-baseline/mixed-responsibility-audit.md`
