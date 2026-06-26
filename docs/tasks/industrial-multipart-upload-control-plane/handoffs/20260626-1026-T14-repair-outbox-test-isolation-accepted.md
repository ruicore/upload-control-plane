# T14 Repair Outbox Test Isolation - Accepted

## Status

Accepted.

## Scope

Repair agent fix for full-suite outbox test isolation on branch
`codex/industrial-upload/T14-merge-gap-repairs` at merge baseline `cd56a51`.

The fix is limited to test cleanup helpers. Product outbox dispatcher semantics are unchanged:
the dispatcher still claims all globally due `PENDING` and `FAILED` outbox events.

## Diagnosis

`tests/application/test_outbox.py::test_successful_delivery_and_repeated_runs_are_idempotent`
expected a single claimed event, but full-suite execution could leave due outbox rows from
earlier API tests in the shared PostgreSQL test database. The dispatcher correctly claimed
those rows, producing summaries such as `(13, 13, 0, 0)`.

The isolation gap was in upload API cleanup helpers: they removed upload tasks, objects,
sessions, datasets, audit events, and idempotency records, but did not remove outbox rows
whose `aggregate_id` referenced those test-owned records. Later lifecycle/recovery flows
could leave due `dataset.recovery_reconcile` outbox events attached to test datasets.

## Changes

- `tests/api/test_upload_task_api_foundation.py`
  - Imports `OutboxEvent`.
  - Collects upload session ids in `_delete_upload_artifacts`.
  - Deletes outbox rows whose `aggregate_id` matches the test-owned task/object/dataset/session ids.
- `tests/api/test_upload_session_runtime_api.py`
  - Imports `OutboxEvent`.
  - Deletes outbox rows for test-owned task/object/dataset/session aggregate ids.
- `tests/api/test_device_identity_api.py`
  - Imports `OutboxEvent`.
  - Deletes outbox rows for test-owned task/object/dataset/session aggregate ids.

No KMS, backpressure, restore/rebuild, file-byte proxy, presigned URL, or credential-handling
code was changed.

## Validation

- `uv run pytest tests/application/test_outbox.py::test_successful_delivery_and_repeated_runs_are_idempotent -q`
  - Passed: `1 passed`.
- `uv run pytest -q`
  - Passed: `220 passed, 1 warning`.
- `uv run ruff check tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/api/test_device_identity_api.py tests/application/test_outbox.py`
  - Passed.
- `uv run ruff format --check tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py tests/api/test_device_identity_api.py tests/application/test_outbox.py`
  - Passed: `4 files already formatted`.
- `git diff --check`
  - Passed.

## Remaining Risk

Other future tests that create outbox rows outside these upload API helpers still need to
clean them by owned aggregate ids or event ids. This repair covers the observed full-suite
failure path without narrowing product dispatcher behavior.
