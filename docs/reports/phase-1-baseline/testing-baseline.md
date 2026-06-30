# Testing Safety Net Baseline

Status: active

Recorded for: Phase 1 Task P1-07

## Scope

This report records the current testing safety net and compares it with the
testing expectations in the industrial multipart upload control plane PRD. It
is a baseline gap report only. It does not add tests, modify tests, change
production code, or classify the repository as failing because gaps exist.

Inputs read:

- `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
- `docs/reports/phase-1-baseline/public-contract-inventory.md`
- `docs/agentic-engineering/experiment-design.md`
- `pyproject.toml`
- `Makefile`
- `README.md`
- `tests/**`

## Discovery Method

Test files were counted from Python files under `tests/`, excluding
`__pycache__`. Test command configuration was read from `pyproject.toml`,
`Makefile`, and `README.md`.

The PRD comparison uses Section 28, which defines required unit, integration,
E2E, failure injection, performance, and security/governance tests. The
experiment design requires Phase 1 baseline evidence to include the current
testing safety net, test count by category, tests run, affected test
categories, failure-mode tests, and security/redaction checks, while avoiding a
"failed repository" framing.

## Test File Inventory

Current Python test file count: **36**.

| Test location | Files | Baseline interpretation |
| --- | ---: | --- |
| `tests/domain` | 8 | Mostly unit tests for deterministic domain rules. |
| `tests/api` | 8 | API contract and behavior tests, many backed by FastAPI `TestClient` and database fixtures. |
| `tests/application` | 3 | Application-service and worker behavior tests. |
| `tests/infrastructure` | 9 | Schema, migration, seed, DB session, and S3 adapter tests. |
| `tests/cli` | 2 | CLI command and manifest behavior tests. |
| `tests/integration` | 1 | Explicitly marked external-service MinIO integration test. |
| `tests/scripts` | 1 | Benchmark script helper tests. |
| `tests` root | 4 | Package, config, health, and Phase 13 capability gap tests. |

Pytest collection result: **225 collected tests**.

## Configured Test Commands

`pyproject.toml` configures pytest with:

- `testpaths = ["tests"]`
- strict config and strict markers
- one marker: `integration`, described as requiring external services such as local MinIO

The repository documents this local quality command set:

```text
uv run ruff check
uv run ruff format --check
uv run mypy src tests
uv run pytest
```

`make test` runs the same four commands. For this baseline, the directly
relevant test command run was `uv run pytest`; lint, format, and mypy were not
rerun because this task is documenting the testing safety net rather than
validating a code change.

## Commands Run and Outcomes

| Command | Outcome |
| --- | --- |
| `git status --short --untracked-files=all` | Showed pre-existing untracked `docs/reports/phase-1-baseline/public-contract-inventory.md`; left untouched. |
| `rg --files -g "*test*.py" -g "tests/**" -g "!**/.venv/**" -g "!**/__pycache__/**"` | Listed 36 Python test files under `tests/`. |
| `Get-ChildItem -Path tests -Recurse -File -Filter *.py ...` | Counted test files by directory: 36 total. |
| `uv run pytest --collect-only -q` | Passed collection; `225 tests collected in 1.45s`; emitted one Starlette deprecation warning from FastAPI `TestClient`. |
| `uv run pytest` | Passed; `225 passed, 1 warning in 16.58s`. |

Service availability result:

- The live `uv run pytest` execution passed with no skips.
- The explicit MinIO integration test under `tests/integration/test_s3_storage_minio.py` ran successfully in this environment.
- Several PostgreSQL-backed API/application tests contain skip paths for an unreachable or unmigrated PostgreSQL integration database.
- The MinIO integration test contains a skip path for unavailable bucket access.

This means the baseline safety net was runnable on this machine at the time of
collection, but part of the suite remains service-dependent by design.

## Category Baseline

The current suite is organized primarily by implementation layer and topic, not
by the PRD category names. The mapping below is therefore interpretive and
non-exclusive.

| PRD category | Current evidence | Baseline assessment |
| --- | --- | --- |
| Unit | Strongest in `tests/domain`; also present in config, manifest, benchmark helper, schema-shape, and storage adapter fake tests. | Present. The deterministic domain layer has focused tests for parts, state transitions, datasets, permissions, object keys, fingerprints, aggregates, and storage value objects. |
| Integration | One explicit `pytest.mark.integration` MinIO multipart test. Many API/application tests exercise real database session factories when PostgreSQL is available. | Present, but not fully normalized under a dedicated integration taxonomy. The PRD expects real PostgreSQL and real MinIO integration coverage. |
| E2E | CLI command and manifest tests exist, but collection shows no dedicated `tests/e2e` directory and no full CLI upload/resume/download E2E flow category. | Gap. Current CLI coverage is command/manifest-level, not the PRD's full upload lifecycle E2E strategy. |
| Failure injection | Failure scenarios exist across API/application tests: storage backpressure, KMS provider failure, missing storage parts, checksum mismatch, outbox retry/dead-letter, validation failure, recovery reconciliation, and revoked/disabled credentials. | Partial. Coverage exists as scenario tests, but there is no dedicated failure-injection suite or matrix matching the PRD failure table. |
| Security/governance | Present across auth, permissions, dataset exposure gates, purge retention/object-lock/legal-hold checks, device credential lifecycle, audit redaction, log redaction, manifest redaction, and secret-hash schema tests. | Material coverage exists. Remaining baseline risk is breadth and traceability to the PRD's full security/governance checklist. |
| Contract tests | Present through FastAPI `TestClient` endpoint behavior, CLI command behavior, schema/migration shape tests, and the P1-06 public contract inventory. | Partial. There is useful contract coverage, but no dedicated generated OpenAPI/schema snapshot or public-contract regression suite. |
| Performance | Benchmark helper tests exist under `tests/scripts`. | Limited. The PRD asks for benchmark scripts and benchmark dimensions; this baseline has helper tests, not benchmark result evidence. |

## PRD Comparison

The PRD requires a broad testing strategy:

- Unit tests for part sizing, part ranges, state transitions, dataset lifecycle,
  aggregates, object key sanitizer, request fingerprints, idempotency,
  permissions, storage policy validation, device credentials, tags, outbox
  backoff/dead-letter, missing parts, CLI manifest mutation detection, and
  dataset exposure-state rules.
- Integration tests using real PostgreSQL and real MinIO, including project
  authorization, upload task/session creation, presign, direct MinIO PUT, list
  parts, complete, abort, pause/resume, download URL, dataset lifecycle,
  devices, validation worker, audit/outbox, cleanup, CORS, signed headers,
  checksum, conditional complete, quota, encryption headers, legal hold, and
  recovery.
- E2E tests using CLI for single and multipart uploads, resume after crash, URL
  expiry recovery, duplicate part upload, pause/resume, dataset readiness,
  download, multi-file task completion, device upload, and denied flows.
- Failure injection tests for API timeouts, URL expiry, network failures,
  client crash, pause/resume edge cases, missing parts, duplicate complete,
  abort, DB/storage disagreement, lost complete response, validation failure,
  outbox failure, credential revocation, retention and object-lock denials,
  leaked URLs, KMS outage, storage backpressure, CORS mismatch, checksum
  mismatch, restore loss, orphan objects, and concurrent tag deletion.
- Security/governance tests for metadata limits and secret-looking keys,
  content-type allowlists, object key safety, dataset exposure gates, audit
  events, URL redaction, MQTT topic authorization, stable quota/rate-limit
  error codes, object-lock bypass, and backup/restore rehearsal.

Current tests cover a meaningful subset of those expectations. The biggest
baseline difference is not absence of all safety net coverage; it is that
coverage is concentrated in broad layer-oriented files and does not yet map
one-to-one to the PRD's category strategy.

## Gaps by Category

| Category | Gap | Why it matters for future governed refactors |
| --- | --- | --- |
| Unit | Storage policy validation, device credential overlap windows, tag normalization, and some idempotency conflict rules appear less explicitly separated than the PRD list. | Governed refactors need fast, focused rule tests before moving logic out of broad API/application files. |
| Integration | Only one file is explicitly marked `integration`; PostgreSQL-dependent tests are present but not clearly categorized as integration. | Agents may under-run or misinterpret service-dependent coverage when changing persistence, storage, or transaction boundaries. |
| E2E | No dedicated full CLI upload/resume/download E2E suite is visible. | CLI and manifest refactors can pass unit/API tests while still breaking the real user path across API, MinIO, and local manifest state. |
| Failure injection | Failure coverage is distributed and partial rather than represented as a PRD-mapped failure matrix. | Recovery, retry, and reconciliation behavior is exactly where governed refactors are most likely to need evidence gates. |
| Security/governance | Strong existing coverage for auth, redaction, device credential lifecycle, purge policy, and exposure gates, but not all PRD cases are visible, such as metadata secret-looking keys, MQTT topic authorization, object-lock bypass permission, and backup/restore rehearsal. | These tests protect irreversible or sensitive behavior; gaps should be explicit before broad authorization or lifecycle refactors. |
| Contract tests | Endpoint behavior is tested and contracts are inventoried, but there is no dedicated OpenAPI/public contract snapshot gate. | Future refactors could accidentally rename fields, routes, response schemas, or CLI options while still satisfying internal behavior tests. |
| Performance | Benchmark helper tests exist, but no benchmark execution results or dimensions are recorded in the test suite. | Performance is not a correctness blocker for this baseline, but later claims about industrial suitability need separate benchmark evidence. |

## Most Important Governed-Refactor Risks

1. **Contract drift risk.** The public contract inventory shows many API and
   CLI surfaces, while the tests are broad and behavior-oriented. Before
   endpoint, DTO, or CLI refactors, a governed workflow should preserve current
   public behavior with explicit contract evidence.
2. **Recovery and failure-mode risk.** Upload completion, retry, outbox,
   validation, recovery, credential revocation, and storage backpressure are
   covered in places, but not as a complete failure matrix. These flows should
   receive proportionate evidence gates before extraction or state-machine
   changes.
3. **Service-dependent test clarity risk.** PostgreSQL and MinIO coverage is
   valuable, but the categorization is uneven. Future agents need to know which
   checks require local services and which are fast deterministic checks.
4. **Hotspot test-file risk.** Large API test files are a major safety net, but
   they concentrate many behaviors and helpers. Governed refactors should avoid
   treating a passing broad file as proof that every PRD expectation was
   exercised.
5. **E2E path risk.** The absence of a visible full CLI E2E category is the
   largest gap for proving the end-user upload path across process boundaries.

## Baseline Conclusion

The current test suite is substantial and runnable in the local environment:
36 Python test files, 225 collected tests, and a passing `uv run pytest` run.
It includes meaningful unit, API, application, infrastructure, integration,
security/governance, and failure-scenario coverage.

The PRD expects a more explicit industrial testing strategy than the current
taxonomy provides. The main baseline gaps are dedicated E2E coverage, a
complete PRD-mapped failure-injection matrix, clearer service-dependent
integration categorization, and dedicated public contract regression checks.
These gaps should inform future governed refactor gates; they should not be
treated as evidence that the repository is failed or unusable.

## Task Boundary

No tests were added. No tests were modified. No production code was changed.
The only deliverable produced by this task is:

- `docs/reports/phase-1-baseline/testing-baseline.md`
