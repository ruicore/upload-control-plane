# Handoff: T06 runtime lifecycle validation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T06-validation-runtime-lifecycle
Worktree: D:\upload-control-plane-T06-validation-runtime-lifecycle
Started: 2026-06-25 11:08 +08:00
Finished: 2026-06-25 11:21 +08:00

## Scope

- Intended scope:
  - Independently validate `bf5b795` on `codex/industrial-upload/T06-implementation-runtime-lifecycle`.
  - Verify T06 runtime lifecycle routes and behavior without changing implementation code.
  - Verify route surface, authorization, storage-authoritative complete, abort behavior, locking evidence, and no file-byte backend endpoint.
  - Run the requested quality gates and real MinIO lifecycle checks where feasible.
- Explicitly out of scope:
  - Fixing implementation defects.
  - Merging to `main`.
  - Implementing T07 Browser, T08 CLI, T09 Dataset lifecycle, workers, observability, MQTT, Go uploader, or Go gateway.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md` T06 section
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0948-master-handoff-after-T06-presign-ack.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0558-T06-merge-runtime-presign-ack-accepted.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1108-T06-implementation-runtime-lifecycle-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/01-non-negotiable-decisions.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/05-state-machine.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/08-storage-adapter-and-object-keys.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1121-T06-validation-runtime-lifecycle-accepted.md`
- Behavior changed:
  - None. This validation agent did not modify implementation code.
- Compatibility notes:
  - The validation branch is based on `codex/industrial-upload/T06-implementation-runtime-lifecycle` at `bf5b795`.

## Verification

- Commands run:
  - `git worktree add -b codex/industrial-upload/T06-validation-runtime-lifecycle ..\upload-control-plane-T06-validation-runtime-lifecycle codex/industrial-upload/T06-implementation-runtime-lifecycle`
  - `uv run ruff check`
  - `uv run ruff format --check`
  - `uv run mypy src tests`
  - `uv run pytest tests/api/test_upload_session_runtime_api.py -q` before DB startup
  - `uv run pytest tests/integration/test_s3_storage_minio.py -q` before MinIO startup
  - `docker compose config --quiet`
  - `docker compose up -d postgres minio minio-init`
  - `make migrate`
  - `make seed-dev`
  - `uv run pytest tests/integration/test_s3_storage_minio.py -q`
  - `uv run pytest tests/api/test_upload_session_runtime_api.py -q`
  - `uv run pytest`
  - `make test`
  - Inline real MinIO lifecycle E2E using public API create/presign, direct `httpx.put` to presigned MinIO URL, API complete, storage head/read evidence, and separate API abort/idempotent abort session.
  - Route surface scan:
    - `rg -n "@router\\.(get|post|put|patch|delete)|APIRouter\\(|include_router|/pause|/resume|/complete|/abort|parts/presign|parts/ack|/v1/uploads" src\\upload_control_plane tests\\api\\test_upload_session_runtime_api.py`
  - File-byte endpoint marker scan:
    - `rg -n "UploadFile|File\\(|Form\\(|multipart/form-data|files=" src\\upload_control_plane`
  - Scope drift scan:
    - `rg -n "T07|T08|T09|manual-uploader|uploadctl|datasets|download-url|MQTT|Go uploader|gateway|device" src\\upload_control_plane tests\\api\\test_upload_session_runtime_api.py`
  - `docker compose down`
- Results:
  - `uv run ruff check`: passed. Ruff emitted cache write warnings on first run after `.venv` creation, but exit code was 0 and all checks passed.
  - `uv run ruff format --check`: passed, 68 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 60 source files.
  - Initial API lifecycle pytest before PostgreSQL startup: 11 skipped, proving DB-dependent tests did not falsely pass without DB.
  - Initial MinIO integration pytest before MinIO startup: 1 skipped, proving storage-dependent test did not falsely pass without MinIO.
  - `docker compose config --quiet`: passed with no output.
  - `docker compose up -d postgres minio minio-init`: passed. Postgres and MinIO were healthy; MinIO exposed host ports `19000` and `19001`.
  - `make migrate`: passed, Alembic upgraded through `20260624_0005`.
  - `make seed-dev`: passed. Seeded permission codes include `project.view`, `dataset.upload`, `upload.create`, `upload.pause`, `upload.resume`, `upload.complete`, and `upload.abort`.
  - `uv run pytest tests/integration/test_s3_storage_minio.py -q`: passed, 1 passed.
  - `uv run pytest tests/api/test_upload_session_runtime_api.py -q`: passed, 11 passed, 1 existing Starlette TestClient deprecation warning.
  - `uv run pytest`: passed, 155 passed, 1 existing Starlette TestClient deprecation warning.
  - `make test`: passed; ruff, format check, mypy, and pytest all passed with pytest result 155 passed.
  - Real MinIO lifecycle E2E passed:
    - Public API created session `cd4524c3-50cc-4cd4-b225-786e6b69ca88`.
    - Public API presigned part 1.
    - Direct PUT to MinIO presigned URL uploaded `67108864` bytes.
    - Public API `GET /parts?source=storage` observed the storage part.
    - Public API complete returned `COMPLETED`.
    - Storage head/read confirmed final object size `67108864` and matching bytes under key `tenants/4f778e62-3eba-59c2-8dab-b51cb66e38e0/projects/020500f8-920c-5a49-bf01-0eca416b8ddf/datasets/b3e4b02c-4613-4589-9898-376b1b2f7cd5/2026/06/25/cd4524c3-50cc-4cd4-b225-786e6b69ca88/validation-real-minio-complete.bin`.
    - Separate abort session `154617e8-325d-45d9-bf1c-6356dc0dfd9a` returned `ABORTED`; retry with same idempotency key returned the same response.
  - Route surface scan found only expected public routes for the current program stage:
    - Existing `GET /v1/projects`, `GET /v1/projects/{project_id}`.
    - Existing `POST /v1/projects/{project_id}/upload-tasks`.
    - T06 runtime routes: `GET /v1/uploads/{session_id}`, `POST /v1/uploads/{session_id}/parts/presign`, `POST /v1/uploads/{session_id}/parts/ack`, `GET /v1/uploads/{session_id}/parts`, `POST /v1/uploads/{session_id}/pause`, `POST /v1/uploads/{session_id}/resume`, `POST /v1/uploads/{session_id}/complete`, `POST /v1/uploads/{session_id}/abort`.
  - File-byte endpoint marker scan in `src/upload_control_plane` returned no matches.
  - Scope drift scan found existing schema/config/domain references for datasets, devices, MQTT config defaults, and object-key paths, but no T07 browser tool, T08 CLI, T09 dataset lifecycle API, download URL API, Go uploader, or gateway implementation.
  - `docker compose down`: passed and removed validation containers/network.
- Commands not run and why:
  - None from the requested command list were intentionally skipped.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Passed. Runtime API routes are JSON control-plane endpoints only. Source scan for `UploadFile`, FastAPI `File(...)`, `Form(...)`, `multipart/form-data`, and `files=` returned no matches in backend source.
  - The real MinIO E2E sent bytes only with direct PUT to the presigned MinIO URL, not to FastAPI.
- Clients receive no MinIO/S3 credentials:
  - Passed. API responses expose presigned URLs only; seed output prints the dev API key but no MinIO/S3 secret.
- Complete uses object storage ListParts as authority:
  - Passed. Code inspection shows complete transitions to `COMPLETING`, calls storage `list_parts`, validates expected part numbers/sizes, builds `CompletionPart` from storage-observed ETags, and only then calls `complete_multipart_upload`.
  - API test `test_complete_uses_storage_list_parts_not_db_ack_rows_for_missing_parts` passed and proves DB ack rows alone do not allow completion.
  - Real MinIO E2E completed successfully after storage `ListParts` observed the uploaded part.
- Missing storage parts return stable 409 and do not call storage complete:
  - Passed. Focused API test returned `409 upload.missing_parts`, reported missing part 2, and asserted `storage.complete_calls == []`.
- Abort calls storage abort and is idempotent; completed session cannot be aborted:
  - Passed. Focused API test asserted one storage abort call, idempotent repeat response, and `409 upload.invalid_state` for a completed session with no extra abort call.
  - Real MinIO E2E also verified API abort and idempotent retry against a real MinIO-backed session.
- Authorization uses permission_grants:
  - Passed for lifecycle actions. API routes call `_require_runtime_permission` with `upload.pause`, `upload.resume`, `upload.complete`, or `upload.abort`; that delegates to `AuthorizationService.require_any_permission`.
  - Focused API tests passed for lifecycle permission revocation and cross-tenant 404 before permission checks.
- Internal IDs remain UUIDs:
  - Passed. This branch has no schema migration changing internal ID types.
- MQTT/Go/edge remain optional and dependency-gated:
  - Passed. No MQTT adapter, Go uploader, Go gateway, browser uploader, CLI uploader, or dataset lifecycle endpoint was added.
- Session-level locking or equivalent concurrency protection:
  - Passed by code inspection. Lifecycle actions use `_get_session_for_update`, which selects the session with `.with_for_update()` before transition checks for pause, resume, complete, abort, and final mark methods.

## Findings

- No blocking implementation issue found in T06 runtime lifecycle.
- Non-blocking risk: presign still accepts `dataset.upload` or `upload.create` rather than a dedicated `upload.presign` permission. This was already called out by the accepted T06 presign/ack handoff as later authorization hardening; the current validation focus required lifecycle action re-authorization, which is implemented.
- Non-blocking recovery gap: implementation has evidence for restoring `COMPLETING`/`ABORTING` back to the previous active state when storage `ListParts`, storage complete, or storage abort raises `StorageError`. However, there is not yet an explicit operator repair/reconcile command or test for the harder failure where storage complete succeeds but the final DB commit fails. The implementation handoff already records this as later repair/reconcile work from PRD failure modes.

## Risks and Follow-up

- Remaining risks:
  - Add a later failure-injection or repair/reconcile slice for storage-complete-success plus DB-finalization-failure recovery.
  - Consider adding dedicated `upload.presign` permission enforcement after Master decides whether to turn the earlier hardening note into product scope.
- Known gaps:
  - This validation did not add tests or code by design.
  - Real MinIO lifecycle E2E was run as an inline validation script, not added as a committed regression test.
- Suggested next agent:
  - Master review can proceed. If Master accepts the non-blocking recovery and presign-permission follow-ups, a Merge agent can merge T06 lifecycle.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T06 lifecycle can proceed to Master review and Merge agent.
  - T07/T08/T09 should only unlock after Master accepts the validation and merge handoff for full T06.
- If partial:
  - Not applicable.
- If blocked:
  - Not applicable.
- If rejected:
  - Not applicable.
