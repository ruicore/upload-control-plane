# Phase 1 Baseline Summary

Status: active

Recorded for: Phase 1 Task P1-09

## Executive Summary

Phase 1 preserves the current `upload-control-plane` repository as an
unconstrained Codex baseline. The baseline is a functional, substantial
implementation, not a failed prototype: the public contract inventory records
product API routes, operational routes, upload runtime routes, device routes,
dataset routes, tag routes, audit routes, DB-facing schema artifacts, and CLI
commands ([public-contract-inventory.md](public-contract-inventory.md)). The
testing baseline records 36 Python test files, 225 collected tests, and a
passing `uv run pytest` run with 225 passed tests
([testing-baseline.md](testing-baseline.md)).

The same evidence shows concentration risk. The repository inventory records
98 Python files, a maximum Python file size of 1597 LOC, 24 Python files over
300 LOC, 14 over 500 LOC, 6 over 800 LOC, and 4 over 1000 LOC
([repository-inventory.md](repository-inventory.md);
[repository-metrics.json](repository-metrics.json)). The hotspot and
mixed-responsibility reports identify the largest production files as central
authority files for upload runtime behavior, ORM schema vocabulary, dataset
lifecycle behavior, broad API route modules, observability, worker lifecycle,
and upload task creation
([hotspot-files.md](hotspot-files.md);
[mixed-responsibility-audit.md](mixed-responsibility-audit.md)).

The baseline therefore supports the experiment framing: without executable
repository governance, Codex can deliver a coherent system while also tending
to extend existing files, concentrate responsibilities, and leave some PRD
architecture and testing expectations as guidance rather than enforced
constraints ([experiment-design.md](../../agentic-engineering/experiment-design.md);
[architecture-drift.md](architecture-drift.md);
[unconstrained-codex-behavior.md](unconstrained-codex-behavior.md)). Phase 1
does not define Phase 2 standards or prescribe refactors; it consolidates the
before-state evidence that later governed work can compare against
([README.md](README.md); [deliverables.md](../../agentic-engineering/deliverables.md)).

## Baseline Metrics

| Metric | Baseline value | Source | Why it matters for later comparison |
| --- | ---: | --- | --- |
| Baseline branch | `agentic-standard/phase-1-baseline` | [git-boundary.md](git-boundary.md) | Anchors the Phase 1 evidence path. |
| Phase 1 boundary `HEAD` | `c021dca8122f34b4c5be15d7d1904e47d989dd13` | [git-boundary.md](git-boundary.md) | Gives later comparison work a concrete starting commit. |
| Unconstrained baseline tag | `codex-unconstrained-baseline` -> `b75240cf5537dce3342da45be56305c7b02947f1` | [git-boundary.md](git-boundary.md) | Preserves the pre-governance reference point. |
| Inventoried files | 277 | [repository-inventory.md](repository-inventory.md) | Measures repository breadth at baseline. |
| Python files | 98 | [repository-inventory.md](repository-inventory.md) | Defines the structural metric denominator. |
| `src/` Python files | 52 | [repository-inventory.md](repository-inventory.md) | Captures implementation size. |
| `tests/` Python files | 36 | [testing-baseline.md](testing-baseline.md) | Captures test file breadth. |
| Max Python LOC | 1597 | [repository-inventory.md](repository-inventory.md) | Captures the largest file hotspot. |
| Median Python LOC | 118.00 | [repository-inventory.md](repository-inventory.md) | Captures the distribution midpoint. |
| Mean Python LOC | 241.22 | [repository-inventory.md](repository-inventory.md) | Captures average file size. |
| Python files over 300 LOC | 24 | [repository-inventory.md](repository-inventory.md) | Captures broad size concentration. |
| Python files over 500 LOC | 14 | [repository-inventory.md](repository-inventory.md) | Captures high-risk hotspot candidates. |
| Python files over 800 LOC | 6 | [repository-inventory.md](repository-inventory.md) | Captures severe concentration points. |
| Python files over 1000 LOC | 4 | [repository-inventory.md](repository-inventory.md) | Captures critical large-file convergence. |
| Largest production file | `src/upload_control_plane/application/upload_sessions.py`, 1597 LOC | [hotspot-files.md](hotspot-files.md) | Main upload runtime convergence point. |
| Largest schema authority | `src/upload_control_plane/infrastructure/db/models.py`, 1159 LOC | [hotspot-files.md](hotspot-files.md) | Main ORM vocabulary convergence point. |
| Largest test file | `tests/api/test_upload_session_runtime_api.py`, 1151 LOC | [hotspot-files.md](hotspot-files.md) | Main runtime API safety-net convergence point. |
| Pytest collection | 225 tests collected | [testing-baseline.md](testing-baseline.md) | Records current runnable test surface. |
| Pytest outcome | 225 passed, 1 warning | [testing-baseline.md](testing-baseline.md) | Records the baseline safety-net outcome. |
| Generated FastAPI route inventory | Product, operational, and internal routes are listed with method, path, function, request schema, response schema, tags, and schema inclusion. | [public-contract-inventory.md](public-contract-inventory.md) | Defines the public HTTP behavior that future work must preserve or gate. |

## Top Findings

1. **The repository is a meaningful functional baseline.** Public API, CLI,
   DB schema, state machine, and status-enum surfaces are inventoried in
   [public-contract-inventory.md](public-contract-inventory.md), while the
   test baseline records a passing 225-test run in
   [testing-baseline.md](testing-baseline.md).

2. **Large-file concentration is the clearest structural signal.** The
   inventory records 14 Python files over 500 LOC and 4 over 1000 LOC
   ([repository-inventory.md](repository-inventory.md)). The hotspot report
   shows that the largest production files are central behavior or schema
   authorities, not merely generated or historical artifacts
   ([hotspot-files.md](hotspot-files.md)).

3. **High-impact files mix responsibilities that future agents are likely to
   edit together.** Upload runtime code mixes lifecycle operations,
   idempotency, storage reconciliation, event writing, and cross-aggregate
   synchronization; route files mix schemas, route handlers, permission
   checks, and response mappers; the ORM model file spans many domains
   ([mixed-responsibility-audit.md](mixed-responsibility-audit.md)).

4. **The implemented structure broadly follows the main layer names but drifts
   from several PRD secondary structures.** The architecture drift report
   records broad application services, direct API route modules, application
   imports of infrastructure persistence models, API-package authorization
   ownership, missing repository/storage-base/auth infrastructure modules, and
   a test taxonomy that differs from the PRD categories
   ([architecture-drift.md](architecture-drift.md)).

5. **The safety net is substantial but not yet mapped as an industrial
   verification strategy.** The testing report records meaningful unit, API,
   application, infrastructure, integration, security/governance, and
   failure-scenario coverage, while also recording gaps around dedicated E2E
   coverage, a PRD-mapped failure-injection matrix, service-dependent
   integration categorization, public contract regression checks, and
   benchmark evidence ([testing-baseline.md](testing-baseline.md)).

6. **Documentation existed, but not as executable governance.** Phase 1
   behavior synthesis records that the PRD and Phase 0 documents shaped the
   repository, while later evidence still shows drift between documented
   expectations and current structure
   ([unconstrained-codex-behavior.md](unconstrained-codex-behavior.md);
   [architecture-drift.md](architecture-drift.md);
   [public-contract-inventory.md](public-contract-inventory.md)).

## Strongest Before/After Evidence Points

These are the highest-value baseline facts for later governed comparison. They
are evidence points only, not Phase 2 standards.

| Comparison area | Baseline evidence to preserve | Detailed report |
| --- | --- | --- |
| Structural concentration | 98 Python files; max 1597 LOC; 14 files over 500 LOC; 4 files over 1000 LOC. | [repository-inventory.md](repository-inventory.md) |
| Hotspot convergence | Upload runtime, ORM models, dataset lifecycle, API dataset routes, observability, worker lifecycle, upload session routes, and upload task creation are major production hotspots. | [hotspot-files.md](hotspot-files.md) |
| Mixed edit surfaces | Runtime lifecycle, storage, idempotency, audit/event, DTO, mapper, permission, and persistence concerns are concentrated in a few files. | [mixed-responsibility-audit.md](mixed-responsibility-audit.md) |
| Architecture drift | Main package layers exist, but several PRD-recommended secondary boundaries are absent or broader than expected. | [architecture-drift.md](architecture-drift.md) |
| Public contract surface | Current HTTP endpoints, DTO classes, CLI commands, Alembic revisions, ORM model groups, and status enums are inventoried before refactor. | [public-contract-inventory.md](public-contract-inventory.md) |
| Verification surface | 36 Python test files; 225 collected and passing tests; material but uneven category coverage. | [testing-baseline.md](testing-baseline.md) |
| Behavioral baseline | Codex delivered a coherent system while accumulating local convergence points and relying on documentation as guidance rather than executable constraints. | [unconstrained-codex-behavior.md](unconstrained-codex-behavior.md) |
| Git boundary | Phase 1 branch, boundary tags, and starting `HEAD` are recorded. | [git-boundary.md](git-boundary.md) |

## Phase 2 Inputs

Phase 2 should use these inputs without treating this document as a standard or
refactor design:

- Use the public contract inventory as the baseline for any future API, CLI,
  DB schema, enum, or state-machine compatibility gate
  ([public-contract-inventory.md](public-contract-inventory.md)).
- Use the hotspot and mixed-responsibility reports to choose where evidence
  gates are most important before changing broad files
  ([hotspot-files.md](hotspot-files.md);
  [mixed-responsibility-audit.md](mixed-responsibility-audit.md)).
- Use the architecture drift report to distinguish harmless implementation
  choices, maintainability risks, agent-context risks, potential architecture
  violations, and items requiring later evidence gates
  ([architecture-drift.md](architecture-drift.md)).
- Use the testing baseline to decide what current verification can prove and
  where future governed changes need stronger or more explicit test evidence
  ([testing-baseline.md](testing-baseline.md)).
- Use the unconstrained behavior baseline as the qualitative before-state for
  later behavioral comparison against governed Codex execution
  ([unconstrained-codex-behavior.md](unconstrained-codex-behavior.md)).

## Complete Phase 1 Report Index

- [README.md](README.md) - Phase 1 directory scope and exclusions.
- [git-boundary.md](git-boundary.md) - Phase 1 branch, tags, and starting
  commit boundary.
- [repository-inventory.md](repository-inventory.md) - repository inventory
  and baseline structural metrics.
- [repository-metrics.json](repository-metrics.json) - machine-readable
  inventory and per-file metric data.
- [hotspot-files.md](hotspot-files.md) - hotspot file evidence and severity
  classification.
- [architecture-drift.md](architecture-drift.md) - PRD architecture comparison
  and drift matrix.
- [mixed-responsibility-audit.md](mixed-responsibility-audit.md) - diagnostic
  responsibility maps for highest-impact production hotspots.
- [public-contract-inventory.md](public-contract-inventory.md) - HTTP, CLI,
  DB-facing, status, and PRD contract inventory.
- [testing-baseline.md](testing-baseline.md) - current test safety net,
  command results, and gap categories.
- [unconstrained-codex-behavior.md](unconstrained-codex-behavior.md) -
  synthesized unconstrained Codex behavior baseline.

## Validation Notes

This summary consolidates prior Phase 1 reports only. It does not modify
production code, create `AGENTS.md`, define Phase 2 standards, add new tests,
or prescribe refactor targets.
