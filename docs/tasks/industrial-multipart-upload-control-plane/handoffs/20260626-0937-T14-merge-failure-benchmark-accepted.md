# T14 Failure Injection and Benchmark Suite merge acceptance

Status: accepted
Agent type: master merge integration
Branch: codex/industrial-upload/T14-merge-failure-benchmark
Base branch: main
Base HEAD before integration: 5bc6060
Final HEAD before this handoff: 4f71f7a
Started: 2026-06-26 09:35 Asia/Shanghai
Finished: 2026-06-26 09:37 Asia/Shanghai

## Scope

- Integrate the accepted T14 failure injection and benchmark work onto the current local `main` lineage.
- Preserve the accepted implementation, rejected validation, repair, and final accepted validation handoffs.
- Avoid reintroducing the parallel old T12/T13 commit lineage from the original T14 worktree.
- Do not push.

## Integration notes

The T14 worktree had been built on a parallel but content-equivalent T12/T13 lineage. The merge branch was created from current local `main` and the T14-only commits were cherry-picked in order:

- `250fee7` -> `20fc3f5` (`test: add failure injection and benchmark suite`)
- `ec92af5` -> `4a0e23d` (`Fix T14 failure benchmark gap facts`)
- `4a6d1c6` -> `6252c69` (`docs: record T14 failure benchmark validation`)
- `660c3e6` -> `9920c16` (`test: repair T14 quota backpressure gap`)
- `17eb714` -> `4f71f7a` (`docs: accept T14 repair2 validation`)

Cherry-pick completed without conflicts.

## Accepted evidence

- Failure injection/regression suite covers:
  - presign expiry bounds and expired session rejection;
  - duplicate complete idempotency;
  - missing storage part despite DB ack;
  - permission revocation before complete;
  - device credential revocation/disable/expiration;
  - validation failure without deleting objects or exposing datasets;
  - outbox delivery failure not rolling back committed domain state;
  - retention, object-lock, and legal-hold purge denial;
  - CORS signed-header mismatch;
  - storage-native checksum mismatch;
  - quota rejection before storage multipart initiation;
  - worker lifecycle reconciliation classification.
- Benchmark script defaults to `512MiB`, supports dry-run, uses sparse file creation by default, and delegates upload to the existing CLI path.
- Benchmark path remains API create/presign/ack/complete plus direct storage PUT; no MinIO credentials and no backend byte proxy were added.
- `docs/benchmarks.md` contains local prerequisites, commands, and a report template without signed URL query examples or credentials.
- No Phase 14 MQTT, Go uploader, or gateway scope was implemented.

## Validation

- `git diff --check`
  - Passed with no output.
- `uv run ruff check src tests`
  - Passed: `All checks passed!`
- `uv run ruff format --check src tests`
  - Passed: `87 files already formatted`.
- `uv run mypy src tests`
  - Passed: `Success: no issues found in 87 source files`.
- Focused T14 suite:
  - Command included quota tests, upload runtime tests, CORS, validation worker, outbox, device identity, observability, S3 storage, benchmark script tests, phase gap xfails, purge tests, and worker lifecycle tests.
  - Passed: `55 passed, 3 xfailed, 1 warning`.
- Full pytest:
  - Passed: `214 passed, 3 xfailed, 1 warning`.
- Benchmark dry-run:
  - Command: `uv run python scripts\benchmark_upload.py --dry-run --size 1MiB --file .benchmarks\tiny-ci-merge.bin`
  - Passed and generated temp file was removed.
- `docker compose config --quiet`
  - Passed with no output.
- Backend file-byte/proxy scan:
  - Passed: no matches.
- Byte-read/download route scan:
  - Reviewed expected matches only: benchmark size parsing and deterministic local file generation, outbox byte payload rejection, test helper writes, storage integration tests, and API dependency names.
- Credential/signed marker scan:
  - Reviewed expected matches only: redaction constants/tests, internal storage config fields, one-time device credential tests/API shape, storage presign implementation, and dataset download URL API names.
- Signed-query scan:
  - Reviewed expected matches only: existing negative redaction tests, PRD examples, storage-domain tests, observability fake URLs, and older T07 handoff smoke text. No new signed-query examples in `docs/benchmarks.md` or `scripts/benchmark_upload.py`.

## Remaining gaps and risks

- Backpressure rejection remains a real missing product path and is tracked by a narrow xfail.
- KMS unavailable rejection remains a Phase 13 capability gap.
- Completed dataset automated restore/rebuild remains a capability gap beyond current lifecycle reconciliation classification coverage.
- Live 512 MiB benchmark was not executed; dry-run was executed and documented.
- Full pytest still emits the existing `StarletteDeprecationWarning`.

## Final state

- T14 is ready for local `main` fast-forward from `5bc6060` after this handoff commit.
- No push was performed.
