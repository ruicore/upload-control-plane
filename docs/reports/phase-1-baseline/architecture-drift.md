# Architecture Drift Against PRD

Status: active

Recorded for: Phase 1 Task P1-04

## Scope

This report compares the implemented repository structure against the
PRD-recommended backend architecture and layering rules. It records drift
evidence only. It does not describe any finding as a bug unless a stated
invariant is violated, and it does not propose detailed refactor
implementation.

Inputs read:

- `docs/prd/industrial-multipart-upload-control-plane/README.md`
- `docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md`
- `docs/reports/phase-1-baseline/repository-inventory.md`
- `docs/reports/phase-1-baseline/hotspot-files.md`

## PRD Architecture Baseline

The PRD identifies `11-client-and-backend-implementation.md` as the
implementation-slice owner for backend package layout, config, compose, CLI,
and the development-only uploader
(`docs/prd/industrial-multipart-upload-control-plane/README.md:10-25`).

Section 24.3 recommends a layered backend package under
`src/upload_control_plane/` with `api/`, optional `mqtt/`, `domain/`,
`application/`, `infrastructure/`, `worker/`, and `cli/`
(`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:265-365`).
It also recommends `tests/unit`, `tests/integration`, `tests/e2e`, and
`tests/failure_injection`
(`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:369-373`)
and `tools/manual-uploader` as a development-only browser verification tool
(`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:374-385`).

Section 24.4 states the layering rules used for this comparison:

- `domain` must not import FastAPI, SQLAlchemy, boto3, or MinIO-specific code
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:397-400`).
- `application` may depend on domain interfaces and repositories, while
  `infrastructure` implements repositories and storage adapters
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:400-401`).
- `api` maps HTTP DTOs to application commands
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:402`).
- `cli` and `tools/manual-uploader` must not import backend application
  services
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:405-406`).
- Permission evaluation should live in one application-level authorization
  service, and `permission_grants` remains the database source of truth for
  permissions
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:408-409`).
- Tests should target domain functions without infrastructure whenever
  possible
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:410`).

## Actual Structure Evidence

The baseline inventory records 277 inventoried files, including 52 Python
files under `src/`, 36 Python files under `tests/`, and 15 source files under
`tools/`
(`docs/reports/phase-1-baseline/repository-inventory.md:32-40`).

Tracked source files show these implemented package groups:

- `src/upload_control_plane/api/`
- `src/upload_control_plane/application/`
- `src/upload_control_plane/domain/`
- `src/upload_control_plane/infrastructure/db/`
- `src/upload_control_plane/infrastructure/storage/`
- `src/upload_control_plane/worker/`
- `src/upload_control_plane/cli/`
- `tools/manual-uploader/`

The implemented test groups are `tests/api`, `tests/application`, `tests/cli`,
`tests/domain`, `tests/infrastructure`, `tests/integration`, `tests/scripts`,
and root-level test modules. They do not use the PRD's exact
`tests/unit`, `tests/e2e`, or `tests/failure_injection` directory names.

## Drift Matrix

| ID | Area | PRD expectation | Actual evidence | Classification | Drift note |
| --- | --- | --- | --- | --- | --- |
| D1 | API package shape | `api/` contains shared files plus an `api/routes/` subdirectory with route modules (`11-client...md:282-299`). | Route modules are tracked directly under `src/upload_control_plane/api/`, such as `datasets.py`, `devices.py`, `projects.py`, `upload_sessions.py`, and `upload_tasks.py`. There is no tracked `src/upload_control_plane/api/routes/`. | Agent-context risk; harmless implementation choice unless route ownership keeps growing. | The route surface is flatter than recommended. This is not a stated behavior violation, but future agents looking for PRD route ownership may miss direct children under `api/`. |
| D2 | API schema/route/mapper mixing | `api` maps HTTP DTOs to application commands (`11-client...md:402`), with PRD layout implying route modules under `api/routes/` and separate shared API support files (`11-client...md:282-299`). | `src/upload_control_plane/api/datasets.py` combines request/response models at lines 35-201, route handlers at lines 205-646, and permission/response helpers at lines 649-789 (`docs/reports/phase-1-baseline/hotspot-files.md:70`). `src/upload_control_plane/api/upload_sessions.py` combines request/response models at lines 38-241, route handlers at lines 245-488, and loading/permission/response helpers at lines 491-689 (`docs/reports/phase-1-baseline/hotspot-files.md:73`). | Maintainability risk; agent-context risk. | The API layer still appears to perform HTTP mapping, but DTOs, handlers, authorization calls, and response mapping are concentrated in large route files. This is drift from the PRD's more separated route/support shape. |
| D3 | Application service decomposition | PRD recommends separate service modules for project, dataset, device, tag, upload, upload task, part, completion, abort, storage policy, download, validation, lifecycle, audit, outbox, authorization, and idempotency (`11-client...md:312-330`). | Implemented tracked application modules are broader: `src/upload_control_plane/application/datasets.py`, `devices.py`, `upload_tasks.py`, `upload_sessions.py`, `worker_lifecycle.py`, `dataset_validation.py`, `outbox.py`, and `storage_backpressure.py`. Hotspot evidence records `upload_sessions.py` at 1597 LOC, `datasets.py` at 1036 LOC, `worker_lifecycle.py` at 743 LOC, and `upload_tasks.py` at 623 LOC (`docs/reports/phase-1-baseline/repository-inventory.md:104-115`). | Maintainability risk; agent-context risk. | The implementation uses fewer, broader services than the PRD recommends. This is not a bug by itself, but the hotspot report records multiple responsibilities converging in these files. |
| D4 | Application-to-infrastructure dependency direction | `application` may depend on domain interfaces and repositories, while `infrastructure` implements repositories and storage adapters (`11-client...md:400-401`). | Application files import SQLAlchemy and infrastructure ORM models directly: `src/upload_control_plane/application/datasets.py:8-26`, `dataset_validation.py:9-16`, `devices.py:9-14`, `outbox.py:10-14`, `upload_sessions.py:10-39`, `worker_lifecycle.py:8-24`, and `upload_tasks.py:8-23`. | Potential architecture violation; requires later evidence gate. | The current application layer depends directly on infrastructure persistence models instead of a repository abstraction. Because the PRD uses "may depend" for application dependencies rather than "must not", this should be treated as architecture-drift evidence to gate later design work, not as a confirmed runtime bug. |
| D5 | Authorization ownership | Permission evaluation should live in one application-level authorization service (`11-client...md:408`). | The implemented `AuthorizationService` is in `src/upload_control_plane/api/authorization.py:49`, and routes import/call it from `src/upload_control_plane/api/devices.py:17`, `datasets.py:12`, `upload_sessions.py:12`, `upload_tasks.py:12`, `projects.py:12`, and `observability.py:13`. | Potential architecture violation; agent-context risk. | Permission evaluation is centralized, but it lives in the API package rather than the application package recommended by the PRD. This is structural drift from the stated "application-level" ownership. |
| D6 | Infrastructure decomposition | PRD recommends `infrastructure/db/repositories.py`, `infrastructure/storage/base.py`, optional `infrastructure/messaging/`, and `infrastructure/auth/` (`11-client...md:331-350`). | Tracked infrastructure currently has `src/upload_control_plane/infrastructure/db/base.py`, `migrations.py`, `models.py`, `seed.py`, `session.py`, and `storage/s3_minio.py`; no tracked `infrastructure/db/repositories.py`, `infrastructure/storage/base.py`, `infrastructure/auth/`, or `infrastructure/messaging/`. | Maintainability risk; requires later evidence gate for optional parts. | Missing repository and storage-base files matter because application currently imports ORM models directly. Missing `messaging/` is not drift requiring action because MQTT is marked optional later in the PRD. |
| D7 | Infrastructure model concentration | PRD structure places DB models in `infrastructure/db/models.py`, but also recommends repositories and auth-specific infrastructure modules (`11-client...md:331-350`). | `src/upload_control_plane/infrastructure/db/models.py` has 1159 LOC and 20 ORM classes spanning tenants, policies, API keys, projects, devices, datasets, permissions, upload tasks, objects, sessions, parts, validation, events, audit, outbox, and idempotency (`docs/reports/phase-1-baseline/hotspot-files.md:60`). | Maintainability risk; agent-context risk. | One ORM model file is the schema authority for many domains. This is partly consistent with the PRD's `models.py`, but the absence of repository/auth decomposition increases future navigation load. |
| D8 | Worker package shape | PRD recommends separate worker modules for cleanup, checksum validation, dataset validation, metadata extraction, lifecycle, and outbox dispatch (`11-client...md:351-358`). | The tracked worker package contains `src/upload_control_plane/worker/main.py`; lifecycle behavior is concentrated in `src/upload_control_plane/application/worker_lifecycle.py`, which the hotspot report records at 743 LOC and as owning cleanup, retention purge, recovery reconciliation, object rebuild, events, and audit writes (`docs/reports/phase-1-baseline/hotspot-files.md:72`). | Maintainability risk; requires later evidence gate. | Worker entrypoint code is thinner than the PRD package shape, while worker behavior is concentrated in an application service. This is structural drift, not evidence that worker behavior is incorrect. |
| D9 | Root logging/observability naming | PRD recommends `src/upload_control_plane/logging.py` (`11-client...md:278-281`). | The tracked root package has `src/upload_control_plane/observability.py` and no tracked `src/upload_control_plane/logging.py`. `observability.py` is a 760 LOC hotspot mixing logging utilities, metrics registry, Prometheus rendering, and DB-backed metric queries (`docs/reports/phase-1-baseline/hotspot-files.md:71`). | Harmless implementation choice; maintainability risk if observability keeps expanding. | The naming difference is harmless by itself. The concentration of logging and metrics behavior in one root module is the recorded drift risk. |
| D10 | Test directory taxonomy | PRD recommends `tests/unit`, `tests/integration`, `tests/e2e`, and `tests/failure_injection` (`11-client...md:369-373`) and says tests should target domain functions without infrastructure where possible (`11-client...md:410`). | Actual tracked tests are organized by layer/topic: `tests/api`, `tests/application`, `tests/cli`, `tests/domain`, `tests/infrastructure`, `tests/integration`, `tests/scripts`, plus root test files. Baseline metrics show 36 test files with max depth 1 (`docs/reports/phase-1-baseline/repository-inventory.md:97`). Hotspot evidence records large API test files under `tests/api` (`docs/reports/phase-1-baseline/hotspot-files.md:67-69`). | Agent-context risk; requires later evidence gate. | The test suite has domain tests, which aligns with the layering rule, but the directory taxonomy differs from the PRD and there is no tracked `tests/e2e` or `tests/failure_injection` directory. The API hotspot files suggest public-flow coverage is concentrated in broad files. |
| D11 | Manual uploader file names | PRD recommends Vite browser uploader files including `main.tsx`, `ManualUploader.tsx`, `controlPlaneClient.ts`, `browserMultipartUploader.ts`, `fileParts.ts`, and `uploadState.ts` (`11-client...md:374-385`). | Tracked manual uploader files include `tools/manual-uploader/src/main.ts`, `controlPlaneClient.ts`, `browserMultipartUploader.ts`, `fileParts.ts`, `redaction.ts`, `types.ts`, `styles.css`, and `src/__tests__/...`. | Harmless implementation choice. | The tool exists in the recommended location and has the expected client/uploader/file-part modules. File-name differences such as `main.ts` versus `main.tsx` and `redaction.ts` instead of `uploadState.ts` are structural differences, not architecture violations. |

## Alignment Evidence

- The main package has the PRD's broad layer names: `api`, `application`,
  `domain`, `infrastructure`, `worker`, and `cli`
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:276-365`;
  actual tracked paths under `src/upload_control_plane/`).
- `domain` import checks found no FastAPI, SQLAlchemy, boto3, botocore, or
  MinIO-specific imports under `src/upload_control_plane/domain/`, aligning
  with the domain restriction in PRD 24.4
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:399`).
- `cli` and `tools/manual-uploader` import checks found no imports from
  `upload_control_plane.application`, aligning with PRD 24.4 client-boundary
  rules
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:405-406`;
  actual paths `src/upload_control_plane/cli/` and `tools/manual-uploader/src/`).
- Optional MQTT packages are absent. This is not recorded as drift because the
  PRD labels `mqtt` and `infrastructure.messaging` as optional later
  (`docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md:300-304`,
  `343-346`, `403-407`).

## Classification Summary

| Classification | Deviations |
| --- | --- |
| Harmless implementation choice | D1 in isolation, D9 naming in isolation, D11 |
| Maintainability risk | D2, D3, D6, D7, D8, D9 concentration |
| Agent-context risk | D1, D2, D3, D5, D7, D10 |
| Potential architecture violation | D4, D5 |
| Requires later evidence gate | D4, D6 optional/repository implications, D8, D10 |

## Validation Notes

Commands used while preparing this report:

```text
Get-Content docs/prd/industrial-multipart-upload-control-plane/README.md
Get-Content docs/prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md
Get-Content docs/reports/phase-1-baseline/repository-inventory.md
Get-Content docs/reports/phase-1-baseline/hotspot-files.md
git ls-files src/upload_control_plane tests tools/manual-uploader
rg -n "from upload_control_plane\.(application|infrastructure|api)|import upload_control_plane\.(application|infrastructure|api)|fastapi|sqlalchemy|boto3|botocore|minio" src/upload_control_plane/domain src/upload_control_plane/cli tools/manual-uploader/src
rg -n "from upload_control_plane\.infrastructure|from sqlalchemy" src/upload_control_plane/application src/upload_control_plane/domain
rg -n "AuthorizationService|effective_permissions|permission_grants" src/upload_control_plane/application src/upload_control_plane/api
```

No production code was modified for this task. The only deliverable produced by
this task is:

- `docs/reports/phase-1-baseline/architecture-drift.md`
