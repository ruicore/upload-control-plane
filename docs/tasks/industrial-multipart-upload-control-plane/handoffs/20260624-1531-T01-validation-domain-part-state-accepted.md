# Handoff: T01 validation for domain part sizing, session state, and aggregate upload status

Status: accepted
Agent type: Validation
Branch: main
Worktree: D:\upload-control-plane
Started: 2026-06-24 15:28 +08:00
Finished: 2026-06-24 15:31 +08:00

## Scope

- Intended scope:
  - Independently validate the T01 first-segment implementation for part sizing/ranges, upload session state machine, and upload task/object aggregate status rules.
  - Confirm the implementation remains pure domain code and does not add upload endpoints, file-byte endpoints, persistence, or storage SDK dependencies.
  - Confirm the implementation handoff evidence is reproducible through the required local quality gates.
- Explicitly out of scope:
  - Modifying implementation code, tests, configuration, README, or PRD files.
  - Validating the later T01 dataset/auth segment: dataset lifecycle/exposure rules, object key sanitizer, request fingerprint generation, and permission-code evaluation remain for the next agent.
  - Validating storage-authoritative completion against real object storage, which belongs to later storage/runtime tasks.
- PRD/task files read:
  - docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md
  - docs/tasks/industrial-multipart-upload-control-plane/README.md
  - docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260624-1528-T01-implementation-domain-part-state-accepted.md
  - docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md
  - docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md
  - docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md
  - docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md
  - docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md
  - src/upload_control_plane/domain/*.py
  - tests/domain/test_parts.py
  - tests/domain/test_session_state.py
  - tests/domain/test_aggregates.py

## Validation Findings

- Part sizing and range rules:
  - `tests/domain/test_parts.py` covers the 5 MiB minimum, 64 MiB default, 5 GiB maximum, and 10,000-part boundary/exceedance cases.
  - `choose_part_size` rejects non-positive file sizes, explicit part sizes below 5 MiB, explicit part sizes above 5 GiB, and files requiring more than 10,000 parts.
  - `get_part_range` uses one-based part numbers and computes first, middle, and smaller final ranges correctly.
- Upload session state machine:
  - Valid transitions match the PRD first-segment needs, including pause/resume, complete, abort, expiry cleanup, and non-terminal to failed.
  - Invalid transitions are rejected through `InvalidStateTransitionError`, including completed-to-uploading, aborted-to-completing, failed-to-uploading, paused-to-completed, and expired-to-uploading.
  - `EXPIRED` is modeled as non-terminal, allowing cleanup to transition to `ABORTING`.
- `PAUSED` semantics:
  - Domain code models `PAUSED` as a scheduling guard: `can_presign(PAUSED)` is false, `can_resume(PAUSED)` is true, `can_complete(PAUSED)` and `can_abort(PAUSED)` are allowed as lifecycle guards.
  - No storage abort, part deletion, hard write lock, or storage SDK call is present in the domain implementation.
- Aggregate status rules:
  - Upload object status is derived only from upload session status.
  - Upload task status is derived only from child upload object statuses.
  - The aggregate helpers do not import or reference dataset status, validation status, recovery status, or `READY`; upload `COMPLETED` is therefore not treated as dataset readiness in this segment.
- Boundary and dependency checks:
  - `rg` found no FastAPI, SQLAlchemy, boto3, botocore, MinIO, HTTP framework, route decorator, `UploadFile`, or file-byte API dependency in `src/upload_control_plane/domain` or `tests/domain`.
  - Whole-repo upload/file-byte route search found only the existing health/config foundation plus the new domain helpers/tests; no upload endpoint or file-byte endpoint was added by this segment.

## Verification

- Commands run:
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest`
  - `make test`
  - `rg -n "FastAPI|APIRouter|@app\.|@router\.|UploadFile|File\(|Form\(|Request\(|StreamingResponse|SQLAlchemy|sqlalchemy|boto3|botocore|minio|MinIO|requests|httpx|aiohttp|starlette" src/upload_control_plane/domain tests/domain`
  - `rg -n "upload|uploads|parts|presign|ack|complete|abort|pause|resume|UploadFile|File\(|bytes|stream" src tests -g "*.py"`
  - `rg -n "5 \* MIB|MIN_PART_SIZE|64 \* MIB|DEFAULT_PART_SIZE|5 \* GIB|MAX_PART_SIZE|MAX_PART_COUNT|10_000|10000" tests/domain/test_parts.py src/upload_control_plane/domain/parts.py`
  - `rg -n "READY|Dataset|dataset|QUARANTINED|REJECTED|RECOVERY|NORMAL" src/upload_control_plane/domain tests/domain`
- Results:
  - `uv run ruff check`: passed; all checks passed.
  - `uv run ruff format --check`: passed; 18 files already formatted.
  - `uv run mypy src tests`: passed; no issues found in 16 source files.
  - `uv run pytest`: passed; 42 tests passed with one existing FastAPI/Starlette TestClient deprecation warning.
  - `make test`: passed; reran ruff, format check, mypy, and pytest successfully.
  - Domain forbidden dependency search: no matches.
  - Upload/file-byte endpoint search: no new upload API or file-byte API route found; matches were domain helpers/tests and existing T00 foundation/config files.
  - Boundary search: confirmed constants and tests for 5 MiB, 64 MiB, 5 GiB, and 10,000-part cases.
  - Dataset readiness search in domain/tests: no matches for dataset readiness/exposure terms in this first-segment implementation.
- Commands not run and why:
  - Docker Compose and live MinIO/PostgreSQL checks were not run because this validation scope is pure domain logic and the required command list did not include service smoke tests.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes: preserved. No upload endpoint, file-byte endpoint, MQTT adapter, or data-plane proxy was added.
- Clients receive no MinIO/S3 credentials: preserved. No presign implementation, storage client, or credential-returning code was added.
- Complete uses object storage ListParts as authority: preserved by not implementing completion infrastructure in this segment. The domain state guard allows complete from eligible states but does not decide storage completion from DB acknowledgements.
- Authorization uses permission_grants: not implemented in this first segment and not weakened. This remains for the next T01 dataset/auth rules agent.
- Internal IDs remain UUIDs: preserved. This segment introduces no persistence identifiers.
- MQTT/Go/edge remain optional and dependency-gated: preserved. No MQTT, Go uploader, or Go gateway code was added.
- Pause is control-plane scheduling state: preserved. `PAUSED` rejects new presign scheduling without implying storage abort, storage suspension, part deletion, or hard locking of already issued URLs.
- Presigned URLs are not persisted or logged: preserved. No presigned URL model, storage adapter, log path, or manifest code was added.

## Risks and Follow-up

- Remaining risks:
  - The broader T01 acceptance item "Tests prove upload COMPLETED is not equivalent to dataset READY" is only satisfied negatively for this first segment: aggregate code has no dataset READY concept. Positive dataset exposure tests must be added by the next T01 dataset/auth rules agent.
  - Aggregate precedence rules are pure-domain and reasonable for this slice, but persistence/API wiring may require additional integration tests once T02/T05 introduce stored task/object rows.
- Known gaps:
  - Dataset lifecycle/exposure rules, object key sanitizer, request fingerprint generation, and permission-code evaluation are not part of this first segment.
  - Storage `ListParts` reconciliation and complete behavior are intentionally deferred to storage/runtime tasks.
- Suggested next agent:
  - T01 Domain dataset/auth rules implementation agent can start.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T01 second agent can build on `src/upload_control_plane/domain/` for dataset lifecycle/exposure, object key sanitizer, request fingerprint, and permission-code evaluation.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
