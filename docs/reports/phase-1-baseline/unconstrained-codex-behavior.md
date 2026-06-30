# Unconstrained Codex Behavior Baseline

Status: active

Recorded for: Phase 1 Task P1-08

## Scope

This document synthesizes the Phase 1 baseline evidence about how Codex behaved
while building this repository before a reusable repository-execution standard
was available.

It is a behavior baseline, not a refactor plan. It does not propose target
modules, extraction steps, ownership changes, test additions, or implementation
fixes. It also does not treat the repository as a failed implementation. The
project charter explicitly frames this repository as a useful baseline whose
core functionality is mostly usable, with FastAPI, PostgreSQL, MinIO multipart
upload behavior, CLI and browser upload tools, migrations, tests,
observability, and documentation already present
(`docs/agentic-engineering/project-charter.md:5-9`).

Inputs read:

- `docs/reports/phase-1-baseline/repository-inventory.md`
- `docs/reports/phase-1-baseline/hotspot-files.md`
- `docs/reports/phase-1-baseline/architecture-drift.md`
- `docs/reports/phase-1-baseline/mixed-responsibility-audit.md`
- `docs/reports/phase-1-baseline/public-contract-inventory.md`
- `docs/reports/phase-1-baseline/testing-baseline.md`
- `docs/agentic-engineering/experiment-design.md`
- `docs/agentic-engineering/project-charter.md`

## Baseline Summary

The unconstrained Codex baseline is best understood as a functional, substantial
implementation with visible structural concentration.

Codex successfully built a real industrial-style upload control plane rather
than a toy example. The public contract inventory records product API routes
under `/v1`, operational routes, upload session runtime routes, device routes,
dataset routes, tag routes, audit routes, DB-facing schema artifacts, and CLI
commands (`docs/reports/phase-1-baseline/public-contract-inventory.md:65-278`).
The testing baseline records 36 Python test files, 225 collected tests, and a
passing `uv run pytest` run with 225 passing tests
(`docs/reports/phase-1-baseline/testing-baseline.md:39-84`).

At the same time, the Phase 1 evidence shows that much of the working system
landed in broad files and flat secondary structures. The repository inventory
records 98 Python files, a maximum Python file size of 1597 LOC, 24 Python
files over 300 LOC, 14 over 500 LOC, 6 over 800 LOC, and 4 over 1000 LOC
(`docs/reports/phase-1-baseline/repository-inventory.md:77-90`). The largest
files are not incidental generated artifacts: the top production hotspots
include upload runtime behavior, ORM schema vocabulary, dataset lifecycle
behavior, API dataset routes, observability, worker lifecycle, upload session
routes, and upload task creation
(`docs/reports/phase-1-baseline/repository-inventory.md:100-115`).

That combination is the point of the baseline. It shows Codex can complete a
coherent, feature-rich system under weak architecture governance, while the
resulting repository also preserves evidence of the natural tendencies that the
later governed execution standard is meant to change.

## What Codex Successfully Achieved

Codex produced a coherent product surface. The current API includes upload
task creation, upload session status/presign/ack/list/complete/abort/pause/
resume routes, device management and device upload entrypoints, dataset
list/detail/update/archive/delete/restore/purge/download-url routes, tag
category and tag routes, project list/get routes, audit-event listing,
`/metrics`, `/healthz`, and an internal auth smoke route
(`docs/reports/phase-1-baseline/public-contract-inventory.md:65-138`).

Codex also produced public command-line affordances. The contract inventory
records `uploadctl` commands for upload, resume, status, pause,
resume-session, and abort, plus `upload-worker` operator commands for
run-once, dataset validation, outbox dispatch, reconciliation, and run
(`docs/reports/phase-1-baseline/public-contract-inventory.md:139-167`).

Codex established persistence and lifecycle vocabulary. The public contract
inventory records Alembic revisions, ORM model categories, table groups,
status fields, upload-related domain enums, and DB enum values
(`docs/reports/phase-1-baseline/public-contract-inventory.md:169-257`).
This matters because the baseline is not merely UI scaffolding or a route
stub; it contains durable state, migrations, lifecycle concepts, and operator
surfaces.

Codex created a meaningful safety net. The testing baseline records domain,
API, application, infrastructure, CLI, integration, script, and root-level test
coverage categories, and the observed `uv run pytest` execution passed with
225 tests (`docs/reports/phase-1-baseline/testing-baseline.md:39-84`). The
same report describes the suite as substantial and runnable, with meaningful
unit, API, application, infrastructure, integration, security/governance, and
failure-scenario coverage
(`docs/reports/phase-1-baseline/testing-baseline.md:179-190`).

These are functional successes. They should remain distinct from the
structural and agent-context risks recorded below.

## Observed Unconstrained Behavior Patterns

### Limited Directory Creation

The implementation did create the main expected package groups: `api`,
`application`, `domain`, `infrastructure`, `worker`, `cli`, and
`tools/manual-uploader`, and the architecture-drift report records this as
alignment evidence (`docs/reports/phase-1-baseline/architecture-drift.md:98-116`).

The secondary structure is more limited. The inventory records `src/` with 52
files, max directory depth 3, median depth 2, and 40 of the 52 files at depth
2. Tests are flatter: 36 files, max depth 1, median depth 1
(`docs/reports/phase-1-baseline/repository-inventory.md:92-98`). The
architecture-drift report records direct route modules under
`src/upload_control_plane/api/` and no tracked
`src/upload_control_plane/api/routes/`
(`docs/reports/phase-1-baseline/architecture-drift.md:86`). It also records
that the implementation uses fewer, broader application services than the PRD
recommended (`docs/reports/phase-1-baseline/architecture-drift.md:88`).

This is not evidence that every missing subdirectory is a bug. It is evidence
that Codex tended to stop once the primary layer existed and the local task
could be completed inside that layer.

Classification: structural debt and agent-context risk.

### Large Files

The size pattern is explicit in the inventory: max Python LOC is 1597, median
Python LOC is 118, mean Python LOC is 241.22, and 14 Python files are over
500 LOC (`docs/reports/phase-1-baseline/repository-inventory.md:77-90`).

The hotspot report identifies the largest production files as central
authorities rather than isolated helpers. `application/upload_sessions.py` is
1597 LOC and owns upload runtime status, presign, acknowledgement, part
listing, pause, resume, completion, abort, storage reconciliation,
related-record synchronization, and idempotency response persistence
(`docs/reports/phase-1-baseline/hotspot-files.md:59`). `infrastructure/db/models.py`
is 1159 LOC and spans identity, storage policy, API keys, projects, devices,
datasets, tags, permissions, upload lifecycle, validation, audit, outbox, and
idempotency models (`docs/reports/phase-1-baseline/hotspot-files.md:60`).
`application/datasets.py` is 1036 LOC and covers dataset reads, validation
retry, metadata update, download URL creation, archive, soft delete, restore,
purge, tag category CRUD, tag CRUD, audit, and purge policy checks
(`docs/reports/phase-1-baseline/hotspot-files.md:61`).

Large files are not automatically wrong. The hotspot report explicitly avoids
that claim and treats the evidence as baseline concentration risk only
(`docs/reports/phase-1-baseline/hotspot-files.md:121-124`). The behavior
signal is that Codex repeatedly extended already-active files until they became
the main convergence points for future work.

Classification: structural debt, agent-context risk, and future maintenance
risk.

### Flattened Secondary Structure

The architecture-drift report records several places where the implementation
uses broad files or direct child modules instead of the PRD's more separated
secondary structure. API routes live directly under `api/` rather than under a
tracked `api/routes/` subdirectory
(`docs/reports/phase-1-baseline/architecture-drift.md:86`). The API dataset
and upload-session modules combine DTOs, route handlers, permission/loading
helpers, and response mappers
(`docs/reports/phase-1-baseline/architecture-drift.md:87`). The infrastructure
package lacks tracked `infrastructure/db/repositories.py`,
`infrastructure/storage/base.py`, `infrastructure/auth/`, and
`infrastructure/messaging/` files or directories
(`docs/reports/phase-1-baseline/architecture-drift.md:91`). The test taxonomy
uses layer/topic folders such as `tests/api`, `tests/application`,
`tests/domain`, and `tests/infrastructure`; it does not use the PRD's exact
`tests/unit`, `tests/e2e`, or `tests/failure_injection` directory names
(`docs/reports/phase-1-baseline/architecture-drift.md:95`).

This pattern matters because secondary structure often carries ownership
signals for future agents. A broad `api/datasets.py` file is locally readable,
but it makes dataset lifecycle, validation, tag management, permissions, and
mapping appear to be one natural edit surface.

Classification: structural debt and agent-context risk.

### Mixed Responsibilities

The mixed-responsibility audit records that the highest-impact production
hotspots combine responsibilities that are likely to be edited together by
Codex: public API contracts, permission checks, application orchestration,
storage adapter calls, ORM persistence, idempotency replay, events, audit, and
cross-aggregate status synchronization
(`docs/reports/phase-1-baseline/mixed-responsibility-audit.md:188-193`).

Concrete examples include upload lifecycle mixed with idempotency, storage
reconciliation, event writing, and related aggregate synchronization in
`application/upload_sessions.py`
(`docs/reports/phase-1-baseline/mixed-responsibility-audit.md:44-72`);
unrelated ORM models sharing one schema authority in
`infrastructure/db/models.py`
(`docs/reports/phase-1-baseline/mixed-responsibility-audit.md:74-104`);
dataset lifecycle mixed with tag administration, storage exposure/deletion,
validation retry, audit, outbox, and purge policy logic in
`application/datasets.py`
(`docs/reports/phase-1-baseline/mixed-responsibility-audit.md:106-130`);
and route modules that repeat a "schema, route, permission, mapper" pattern in
`api/datasets.py` and `api/upload_sessions.py`
(`docs/reports/phase-1-baseline/mixed-responsibility-audit.md:132-178`).

This is not a claim that the code is unusable. The audit says the pattern is
often readable locally, but conceptually broad. The risk is that Codex may
receive a narrow prompt, patch the visible local behavior, and miss a coupled
concern elsewhere in the same long file.

Classification: agent-context risk and future maintenance risk.

### Local Completion Bias

The experiment design hypothesizes that, without explicit repository
governance, Codex tends to extend existing files, concentrate responsibilities,
optimize for immediate task completion, rely on local context, under-produce
durable architecture evidence, and treat documentation as reference material
rather than executable constraint
(`docs/agentic-engineering/experiment-design.md:24-34`).

The Phase 1 reports are consistent with that hypothesis. They do not prove
Codex's internal motivation, but they do show the external result: working
feature flows accumulated inside large services, route modules, ORM models,
and broad test files. The hotspot report explicitly states that the baseline
supports the hypothesis that unconstrained Codex tends to extend existing
files and concentrate multiple responsibilities in large files
(`docs/reports/phase-1-baseline/hotspot-files.md:121-124`). The testing
baseline similarly records substantial coverage while noting that the current
taxonomy does not map one-to-one to the PRD's more explicit testing strategy
(`docs/reports/phase-1-baseline/testing-baseline.md:186-190`).

The behavior signal is practical: Codex got local tasks to completion and
verified many of them, but the resulting structure does not consistently
encode the broader architecture and verification model as executable
constraints for later sessions.

Classification: functional success plus agent-context risk.

### Documentation Not Automatically Converted Into Executable Constraints

The PRD and Phase 0 documents existed as design guidance, but the implemented
shape diverged in several recorded ways. The architecture-drift report records
direct API route modules rather than a tracked `api/routes/` structure,
broader application services than the PRD-recommended service decomposition,
application files importing SQLAlchemy and infrastructure ORM models directly,
authorization centralized in `api/authorization.py` rather than an
application-level service, missing repository/storage-base/auth infrastructure
files, and a test taxonomy that differs from the PRD categories
(`docs/reports/phase-1-baseline/architecture-drift.md:86-95`).

The public contract inventory also records implemented product success and
contract gaps side by side: upload runtime APIs and all listed PRD device APIs
exist, while no generated `/extend` upload-session endpoint, dataset create/
preview/bulk endpoints, storage policy routes, or broader project management
routes are present in the current inventory
(`docs/reports/phase-1-baseline/public-contract-inventory.md:259-278`).

This does not mean the documentation was ignored. It means the documentation
did not function as an enforced execution system. Without governed gates,
Codex could still complete substantial local work while leaving portions of
the documented architecture and test strategy as reference material.

Classification: agent-context risk and future maintenance risk.

## Distinguishing the Risk Types

Functional success means the repository has meaningful implemented behavior.
The strongest evidence is the public API/CLI/DB contract inventory and the
passing 225-test baseline
(`docs/reports/phase-1-baseline/public-contract-inventory.md:65-278`;
`docs/reports/phase-1-baseline/testing-baseline.md:39-84`).

Structural debt means the code organization carries concentration and
navigation costs. The strongest evidence is the large-file distribution,
limited secondary depth, broad application services, flat API route structure,
and concentrated ORM model file
(`docs/reports/phase-1-baseline/repository-inventory.md:77-115`;
`docs/reports/phase-1-baseline/architecture-drift.md:86-95`).

Agent-context risk means a future Codex session may choose the wrong edit
surface or miss coupled behavior because the repository does not encode
boundaries strongly enough. The strongest evidence is the mixed-responsibility
audit: lifecycle, storage, idempotency, audit, event, permission, DTO, mapper,
and persistence concerns are often close enough to be convenient but broad
enough to exceed a narrow prompt's intended scope
(`docs/reports/phase-1-baseline/mixed-responsibility-audit.md:180-184`).

Future maintenance risk means later humans or agents may keep appending to the
same hotspots because the existing structure makes that the path of least
resistance. The strongest evidence is the mirrored concentration in production
and test files: upload runtime, dataset lifecycle, schema vocabulary, and API
coverage all have large convergence files
(`docs/reports/phase-1-baseline/hotspot-files.md:104-124`).

These categories overlap, but they should not be collapsed. A file can be a
functional success and still create agent-context risk. A broad test file can
be a major safety net and still become a future discovery bottleneck.

## Why This Repository Is a Strong Demonstration Case

This repository is strong evidence precisely because it is not a failed toy.
The charter states that a non-working toy project would reveal little about
agentic software engineering, while this repository shows natural Codex
behavior on a real industrial-style system under weak architecture governance
(`docs/agentic-engineering/project-charter.md:5-9`).

The implementation has enough surface area to create real pressure: API
contracts, CLI commands, migrations, storage behavior, device identity,
dataset lifecycle, audit/outbox/idempotency concerns, observability, browser
tooling, and tests. That pressure makes the structural outcome meaningful.
Large files and flattened secondary structure are not artifacts of an empty
repo; they emerged while Codex was delivering real behavior.

The case is also publication-ready because the claims are bounded. Phase 1
does not need to say "Codex wrote bad code." The evidence supports a narrower
and more useful claim: unconstrained Codex can produce a functioning system,
but without executable repository governance it tends to encode success in
large local convergence points. The later governed phases can then test
whether standards change agent behavior, not merely whether a human prefers a
cleaner tree.

## Evidence Map for Later Reuse

| Claim | Evidence |
| --- | --- |
| Repository is functional enough to be a meaningful baseline. | Charter baseline framing and feature list (`docs/agentic-engineering/project-charter.md:5-9`); public contract inventory (`docs/reports/phase-1-baseline/public-contract-inventory.md:65-278`); passing test baseline (`docs/reports/phase-1-baseline/testing-baseline.md:39-84`). |
| Large-file concentration exists. | Python LOC thresholds and top files (`docs/reports/phase-1-baseline/repository-inventory.md:77-115`); critical hotspot descriptions (`docs/reports/phase-1-baseline/hotspot-files.md:55-61`). |
| Secondary structure is flatter than PRD expectations in several places. | Directory depth table (`docs/reports/phase-1-baseline/repository-inventory.md:92-98`); architecture drift D1, D3, D6, and D10 (`docs/reports/phase-1-baseline/architecture-drift.md:86-95`). |
| Mixed responsibilities are concentrated in high-impact files. | Mixed-responsibility selected files and cross-file observations (`docs/reports/phase-1-baseline/mixed-responsibility-audit.md:33-37`; `docs/reports/phase-1-baseline/mixed-responsibility-audit.md:180-184`). |
| Documentation did not automatically become executable constraints. | Experiment hypothesis (`docs/agentic-engineering/experiment-design.md:24-34`); PRD-versus-implementation drift matrix (`docs/reports/phase-1-baseline/architecture-drift.md:86-95`); PRD contract comparison (`docs/reports/phase-1-baseline/public-contract-inventory.md:259-278`). |
| The baseline should not be framed as failure or as a refactor plan. | Experiment-design baseline guidance (`docs/agentic-engineering/experiment-design.md:286-296`); hotspot report limitation (`docs/reports/phase-1-baseline/hotspot-files.md:121-124`). |

## Limits of This Baseline

This document synthesizes observed structure and reports. It does not claim to
measure Codex cognition directly. Terms like "local completion bias" describe
the externally visible pattern: working behavior was completed inside local
files and existing structures, while broader architecture guidance remained
only partially encoded in the repository shape.

This document also does not decide which future refactors are worthwhile.
That belongs to later governed phases with explicit evidence gates. Phase 1's
job is to preserve the unconstrained behavior baseline so the project can
later compare it against governed Codex execution.

## Task Boundary

No production code was modified. No tests were added or changed. This task
produced only:

- `docs/reports/phase-1-baseline/unconstrained-codex-behavior.md`
