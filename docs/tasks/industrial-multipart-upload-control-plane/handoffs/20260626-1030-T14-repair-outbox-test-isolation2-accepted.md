# T14 Repair Outbox Test Isolation 2 - Accepted

## Status

Accepted.

## Scope

Repair agent follow-up on branch `codex/industrial-upload/T14-merge-gap-repairs`.

The change is limited to test cleanup in `tests/application/test_worker_lifecycle.py`.
Product `OutboxDispatcher` semantics are unchanged: due `PENDING` and `FAILED`
outbox rows remain globally claimable.

## Diagnosis

After commit `465b28a`, full-suite reruns could still fail
`tests/application/test_outbox.py::test_successful_delivery_and_repeated_runs_are_idempotent`
because the shared local PostgreSQL test database contained due
`dataset.recovery_reconcile` outbox rows.

The remaining residue came from worker lifecycle recovery tests. Those tests call
`WorkerLifecycleService.reconcile_recovery_status`, which intentionally scans eligible
datasets in the shared test database. If earlier validation smoke artifacts such as
`validation-control-session`, `validation-resume-session`, or `ucp-t08-validation-smoke`
remain in the database, the recovery worker can append `dataset.recovery_reconcile`
outbox rows for those test-owned datasets. The old lifecycle cleanup only removed
outbox rows for `t11-*` dataset/session aggregates, so these recovery rows survived
and were later claimed by the outbox dispatcher test.

## Changes

- `tests/application/test_worker_lifecycle.py`
  - Adds a helper to collect dataset ids for worker-lifecycle recovery outbox cleanup.
  - Keeps domain-row deletion scoped to the existing `t11-*` lifecycle artifacts.
  - Deletes only `OutboxEvent` rows where:
    - `aggregate_type = dataset`
    - `event_type = dataset.recovery_reconcile`
    - `aggregate_id` belongs to lifecycle `t11-*` artifacts or known local validation
      smoke test artifacts with names matching `validation-%` or `ucp-t08-%`.

No product code, dispatcher behavior, T14 repair code, validation code, or merge handoff
was changed.

## Validation

- `uv run pytest tests/application/test_worker_lifecycle.py tests/application/test_outbox.py -q`
  - Passed: `12 passed`.
- Post-combination outbox residue check
  - Returned no outbox rows: `[]`.
- `uv run pytest -q`
  - Passed: `220 passed, 1 warning`.
- `uv run ruff check tests/application/test_worker_lifecycle.py`
  - Passed.
- `uv run ruff format --check tests/application/test_worker_lifecycle.py`
  - Passed: `1 file already formatted`.
- `git diff --check`
  - Passed.

## Remaining Risk

The shared integration database can still accumulate outbox rows if future tests or
manual validation flows create new artifact naming schemes that the worker recovery
scan touches. This repair avoids broad event-type cleanup and covers the observed
residual dataset names while preserving product dispatcher behavior.
