# Industrial-Grade Resumable Multipart Upload Control Plane

**Status:** Split into a Codex-readable PRD folder.
**Canonical index:** [docs/prd/industrial-multipart-upload-control-plane/README.md](prd/industrial-multipart-upload-control-plane/README.md)
**Document version:** 1.5
**Document date:** 2026-06-24

This file is kept as a compatibility entrypoint for older links. The full design now lives in smaller files under `docs/prd/industrial-multipart-upload-control-plane/` so Codex and future agents can load the relevant slice without reading one very large document.

## Reading Order

| Order | File | Sections |
|---:|---|---|
| 0 | [Executive Summary](prd/industrial-multipart-upload-control-plane/00-executive-summary.md) | 0 |
| 1 | [Non-Negotiable Decisions](prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md) | 1 |
| 2 | [Context, Goals, and Scope](prd/industrial-multipart-upload-control-plane/02-context-goals-scope.md) | 2-6 |
| 3 | [System Architecture](prd/industrial-multipart-upload-control-plane/03-system-architecture.md) | 7 |
| 4 | [Domain Model](prd/industrial-multipart-upload-control-plane/04-domain-model.md) | 8 |
| 5 | [State Machine](prd/industrial-multipart-upload-control-plane/05-state-machine.md) | 9 |
| 6 | [API Contracts and Part Sizing](prd/industrial-multipart-upload-control-plane/06-api-contracts.md) | 10-13 |
| 7 | [Database Schema](prd/industrial-multipart-upload-control-plane/07-database-schema.md) | 14 |
| 8 | [Storage Adapter and Object Keys](prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md) | 15-16 |
| 9 | [Security and Governance](prd/industrial-multipart-upload-control-plane/09-security-governance.md) | 17 |
| 10 | [Retry, Resume, Completion, and Lifecycle](prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md) | 18-22 |
| 11 | [Client and Backend Implementation](prd/industrial-multipart-upload-control-plane/11-client-and-backend-implementation.md) | 23-26 |
| 12 | [Observability, Testing, and Failure Modes](prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md) | 27-29 |
| 13 | [Implementation Plan](prd/industrial-multipart-upload-control-plane/13-implementation-plan.md) | 30 |
| 14 | [References and Completion Criteria](prd/industrial-multipart-upload-control-plane/14-references-and-done.md) | 31-37 |

## Editing Rule

Edit the split PRD files, not this compatibility entrypoint. If a change crosses concerns, update every affected file and the PRD README reading-order table when necessary.
