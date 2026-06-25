# Handoff: T09 Dataset Lifecycle API Validation

Status: accepted
Agent type: Validation
Branch: codex/industrial-upload/T09-validation-dataset-lifecycle-api
Worktree: D:\upload-control-plane-T09-validation-dataset-lifecycle-api
Started: 2026-06-25 12:38 +08:00
Finished: 2026-06-25 12:43 +08:00

## Scope

- Intended scope:
  - Independently validate T09 Dataset Product Lifecycle implementation at `f085b8a018badeb63593f980154a2681e85afc0a`.
  - Verify dataset list/search/filter/detail/update/download/archive/delete/restore/purge APIs.
  - Verify dataset exposure gates use `dataset_status`, `validation_status`, and `recovery_status`.
  - Verify authorization uses `permission_grants` and permission codes, including `dataset.download` and lifecycle permissions.
  - Verify download is control-plane presigned URL generation only, with no backend file-byte proxying.
  - Verify purge policy, legal hold, and object lock behavior within current schema limits.
  - Review implementation diff for scope creep and hard constraint violations.
- Explicitly out of scope:
  - Repairing implementation code.
  - Merging to `main`.
  - Pushing any branch.
  - Device credential lifecycle, validation workers, outbox workers, or product UI.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1237-T09-implementation-dataset-lifecycle-api-accepted.md`
  - `docs/prd/industrial-multipart-upload-control-plane/04-domain-model.md`
  - `docs/prd/industrial-multipart-upload-control-plane/06-api-contracts.md`
  - `docs/prd/industrial-multipart-upload-control-plane/07-database-schema.md`
  - `docs/prd/industrial-multipart-upload-control-plane/09-security-governance.md`
  - `docs/prd/industrial-multipart-upload-control-plane/10-retry-resume-completion-lifecycle.md`
  - `docs/prd/industrial-multipart-upload-control-plane/12-observability-testing-failure-modes.md`
  - `docs/prd/industrial-multipart-upload-control-plane/13-implementation-plan.md`
  - `docs/prd/industrial-multipart-upload-control-plane/14-references-and-done.md`

## Changes

- Files changed:
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1243-T09-validation-dataset-lifecycle-api-accepted.md`
- Behavior changed:
  - None. Validation only.
- Compatibility notes:
  - The implementation branch was not repaired or modified.
  - The validation branch was created from the exact requested implementation commit.

## Verification

- Commands run:
  - `git status --short --branch`: clean validation branch before handoff.
  - `git rev-parse --verify f085b8a018badeb63593f980154a2681e85afc0a`: passed.
  - `git worktree add -b codex/industrial-upload/T09-validation-dataset-lifecycle-api D:\upload-control-plane-T09-validation-dataset-lifecycle-api f085b8a018badeb63593f980154a2681e85afc0a`: passed.
  - `git diff --stat main...HEAD`: reviewed; changes were scoped to dataset API/service, storage download/delete adapter additions, seed permissions, router registration, tests, and implementation handoff.
  - `git diff --name-status main...HEAD`: reviewed expected changed files only.
  - `rg -n "UploadFile|File\(|Form\(|request\.body\(|request\.stream\(|StreamingResponse|FileResponse" src\upload_control_plane`: no matches, exit code 1.
  - `uv run ruff check`: passed; emitted non-blocking `.ruff_cache` access-denied warnings.
  - `uv run ruff format --check`: passed, 71 files already formatted.
  - `uv run mypy src tests`: passed, no issues in 63 source files.
  - `docker compose config --quiet`: passed.
  - `git diff --check`: passed.
  - `uv run pytest tests/api/test_dataset_lifecycle_api.py -q`: initially skipped 9 tests before local PostgreSQL was started; rerun after migrate/seed passed, 9 passed.
  - `docker compose up -d postgres`: passed; validation PostgreSQL container became healthy on host port 25432.
  - `uv run python scripts/migrate.py`: passed; upgraded through Alembic head `20260624_0005`.
  - `uv run python scripts/seed_dev.py`: passed; seeded deterministic dev tenant/project/dataset/device and 34 permission grants.
  - `uv run pytest`: passed; 164 passed, 1 warning.
- Results:
  - Dataset lifecycle API tests passed against a migrated PostgreSQL database.
  - Full repository test suite passed.
  - The live MinIO integration test passed in this environment.
  - The only warning observed was the existing Starlette `TestClient` deprecation warning.
- Commands not run and why:
  - No repair or mutation commands were run beyond writing this validation handoff.
  - No push command was run because the validation instructions explicitly prohibit pushing.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Accepted. Backend source has no `UploadFile`, `File(...)`, `Form(...)`, `request.body()`, `request.stream()`, `StreamingResponse`, or `FileResponse` matches.
  - Dataset download returns a presigned object URL generated through `ObjectStorage.presign_download_object`; no backend byte streaming path was added.
- Clients receive no MinIO/S3 credentials:
  - Accepted. T09 returns only short-lived presigned GET URLs and does not expose storage access or secret keys.
- Complete uses object storage ListParts as authority:
  - Accepted for T09 validation scope. T09 did not alter T06 completion logic, and the full test suite still covers the existing upload-session runtime tests.
- Authorization uses permission_grants:
  - Accepted. Dataset and tag routes call `AuthorizationService`, which resolves effective permissions from `permission_grants`.
  - Dataset-level checks inherit project grants through the dataset parent project.
  - Dev seed now includes `dataset.download`, `dataset.archive`, `dataset.delete`, `dataset.restore`, `dataset.purge`, and tag permissions for both API key and device subjects.
- Internal IDs remain UUIDs:
  - Accepted. New routes and service code use UUID route/schema values and existing UUID database columns.
- MQTT/Go/edge remain optional and dependency-gated:
  - Accepted. No MQTT, Go uploader, or gateway code was introduced.

## T09 Contract Findings

- Dataset API surface:
  - Accepted. The implementation adds project-scoped dataset list/search/filter/detail/update/download-url/archive/soft-delete/restore/purge routes.
  - Tag category and tag CRUD routes are present under the project API prefix.
- Dataset exposure:
  - Accepted. Download calls `dataset_allows_exposure`, which blocks `QUARANTINED`, `REJECTED`, non-exposable lifecycle states, validation states outside `NOT_REQUIRED`/`PASSED`/`SKIPPED`, and any recovery status other than `NORMAL`.
  - Targeted tests cover blocked `QUARANTINED`, `REJECTED`, validation `FAILED`, and `RECOVERY_MISSING_OBJECT`.
- Download:
  - Accepted. `dataset.download` is required before presign, storage is called only after authorization and exposure checks, `Cache-Control: no-store` is set, and audit events omit signed URL query strings.
- Lifecycle:
  - Accepted. Archive requires `READY`; soft delete hides datasets from normal lists; restore returns to the previous `READY` or `ARCHIVED` state stored in metadata; purge requires `DELETED` state.
- Purge policy:
  - Accepted with schema limitation documented. Purge requires `dataset.purge`, explicit confirmation, deleted timestamp, retention-policy approval, and rejects when the current storage policy has `legal_hold_default` or `object_lock_mode`.
  - Current schema has storage-policy legal hold/object-lock fields but no per-dataset legal hold field and no storage-side legal-hold/head check before delete. The implementation is no weaker than the current schema allows for T09, but future T11/T13 work should add object-state reconciliation or provider metadata checks before production purge.
- Scope creep:
  - Accepted. The diff is large but limited to T09 API/service/test surface plus necessary storage protocol additions for presigned download and object delete.

## Risks and Follow-up

- Remaining risks:
  - Purge is not idempotency-record backed even though PRD 10 says purge must be guarded by idempotency key or explicit purge confirmation token. The implementation uses explicit `confirm_purge`; this is acceptable for the current T09 task wording but should be revisited before production hardening.
  - Purge does not insert outbox events; this remains T11 scope.
  - Per-dataset legal hold cannot be represented in the current schema.
  - Storage-side object-lock/legal-hold metadata is not queried before delete; only storage policy fields are enforced.
- Known gaps:
  - No dataset preview API, bulk rename, bulk metadata, or bulk tag APIs; these are outside T09 acceptance as written.
  - Tag delete is not audited; T09 audit requirements focused on dataset download/delete/restore/purge and policy denial.
- Suggested next agent:
  - Master review may treat T09 as accepted and unlock T10 if no additional product policy is required.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T10 Device Identity and Device Upload Authorization.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
