# Industrial Multipart Upload Control Plane PRD

This folder is the canonical Codex-readable version of the industrial-grade resumable multipart upload control-plane design. The original single-file document has been split by implementation concern so future agents can load only the relevant slice while preserving the original section numbers.

**Document version:** 1.5
**Document date:** 2026-06-24
**Primary implementation language:** Python 3.13 first; optional Go components later
**Primary object storage:** MinIO, using S3-compatible multipart upload APIs

## Reading Order

| Order | File | Sections | Purpose |
|---:|---|---|---|
| 0 | [Executive Summary](00-executive-summary.md) | 0 | System purpose and production-grade scope |
| 1 | [Non-Negotiable Decisions](01-non-negotiable-decisions.md) | 1 | Hard architecture constraints |
| 2 | [Context, Goals, and Scope](02-context-goals-scope.md) | 2-6 | Background, limits, goals, and non-goals |
| 3 | [System Architecture](03-system-architecture.md) | 7 | Control-plane/data-plane architecture and MQTT adapter |
| 4 | [Domain Model](04-domain-model.md) | 8 | Tenant, project, dataset, task, session, device, policy, audit, outbox |
| 5 | [State Machine](05-state-machine.md) | 9 | Upload status definitions, transitions, and race control |
| 6 | [API Contracts and Part Sizing](06-api-contracts.md) | 10-13 | API contracts, upload APIs, batch APIs, and part math |
| 7 | [Database Schema](07-database-schema.md) | 14 | SQL schema and indexes |
| 8 | [Storage Adapter and Object Keys](08-storage-adapter-and-object-keys.md) | 15-16 | Storage interface, MinIO/S3 behavior, object key strategy |
| 9 | [Security and Governance](09-security-governance.md) | 17 | Auth, presigned URL safety, CORS, KMS, object lock, device credentials |
| 10 | [Retry, Resume, Completion, and Lifecycle](10-retry-resume-completion-lifecycle.md) | 18-22 | Idempotency, resume, completion, cleanup, backup, checksums |
| 11 | [Client and Backend Implementation](11-client-and-backend-implementation.md) | 23-26 | CLI, backend package layout, config, compose |
| 12 | [Observability, Testing, and Failure Modes](12-observability-testing-failure-modes.md) | 27-29 | Logs, metrics, SLOs, tests, required failure handling |
| 13 | [Implementation Plan](13-implementation-plan.md) | 30 | Phased Codex implementation plan |
| 14 | [References and Completion Criteria](14-references-and-done.md) | 31-37 | Source references, definition of done, README narrative, Codex rules |

## Agent Navigation Rules

- Start with this README, then open only the file needed for the current task.
- Preserve the existing section numbers when editing split files; downstream tasks may cite them directly.
- Update this README if files are added, removed, renamed, or if section ownership changes.
- Keep cross-file concepts explicit: API changes usually affect database schema, security, tests, and implementation plan files.
- The root `docs/industrial_multipart_upload_control_plane_design.md` is now only a compatibility entrypoint.
