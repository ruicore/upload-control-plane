# Handoff: T09 Dataset Lifecycle API Merge

Status: accepted
Agent type: Merge
Branch: codex/industrial-upload/T09-merge-dataset-lifecycle-api
Worktree: D:\upload-control-plane-T09-merge-dataset-lifecycle-api
Started: 2026-06-25 12:44 +08:00
Finished: 2026-06-25 12:49 +08:00

## Scope

- Intended scope:
  - Create a main-ready merge branch from current `main` at `504dd89b2ee2678d1c06e6a864dbc0f8fc9d583d`.
  - Merge the accepted validation branch `codex/industrial-upload/T09-validation-dataset-lifecycle-api` at `c8720dc428d3945268b76451e0689ea91d28575a`.
  - Preserve the accepted implementation branch content from `f085b8a018badeb63593f980154a2681e85afc0a` through the validation branch.
  - Run the required merged-state verification commands and source scans.
  - Record merge conflicts, service handling, and PRD hard-constraint findings.
- Explicitly out of scope:
  - Pushing the merge branch.
  - Repairing implementation behavior.
  - Merging any branch other than the accepted T09 validation branch.
  - Semantic conflict resolution.
- PRD/task files read:
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `D:\upload-control-plane-T09-implementation-dataset-lifecycle-api\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1237-T09-implementation-dataset-lifecycle-api-accepted.md`
  - `D:\upload-control-plane-T09-validation-dataset-lifecycle-api\docs\tasks\industrial-multipart-upload-control-plane\handoffs\20260625-1243-T09-validation-dataset-lifecycle-api-accepted.md`

## Changes

- Files changed:
  - Merged accepted T09 dataset lifecycle API implementation and validation handoffs.
  - Added this merge handoff.
- Behavior changed:
  - Adds project-scoped dataset lifecycle API and tag API surface from the accepted T09 validation branch.
  - Adds storage adapter support for presigned object download and object delete from the accepted implementation.
  - Adds dev seed permission grants for dataset lifecycle and tag operations.
- Compatibility notes:
  - Merge was based on current `main`/`origin/main` at `504dd89b2ee2678d1c06e6a864dbc0f8fc9d583d`.
  - Merge commit before this handoff: `07ec0b5` (`Merge T09 dataset lifecycle validation`).
  - No merge conflicts occurred.

## Verification

- Commands run:
  - `git status --short; git branch --show-current; git rev-parse HEAD; git rev-parse origin/main`: passed; starting branch was `main`, both HEAD and `origin/main` were `504dd89b2ee2678d1c06e6a864dbc0f8fc9d583d`.
  - `git worktree list`: passed; source implementation and validation worktrees existed at the requested branch heads; no T09 merge worktree existed.
  - `git branch --list codex/industrial-upload/T09-merge-dataset-lifecycle-api codex/industrial-upload/T09-validation-dataset-lifecycle-api codex/industrial-upload/T09-implementation-dataset-lifecycle-api`: passed; only source branches existed before merge branch creation.
  - `git cat-file -t c8720dc428d3945268b76451e0689ea91d28575a` and `git cat-file -t f085b8a018badeb63593f980154a2681e85afc0a`: passed; both are commits.
  - `git worktree add -b codex/industrial-upload/T09-merge-dataset-lifecycle-api D:\upload-control-plane-T09-merge-dataset-lifecycle-api main`: passed.
  - `git merge --no-ff codex/industrial-upload/T09-validation-dataset-lifecycle-api -m "Merge T09 dataset lifecycle validation"`: passed; merge commit `07ec0b5`; no conflicts.
  - `uv run ruff check`: passed; emitted non-blocking `.ruff_cache` access-denied warnings.
  - `uv run ruff format --check`: passed; 71 files already formatted.
  - `uv run mypy src tests`: passed; no issues in 63 source files.
  - `docker compose config --quiet`: passed.
  - `rg -n "include_router|APIRouter|/datasets|download-url|archive|restore|purge|tag-categories|/tags" src\upload_control_plane tests\api\test_dataset_lifecycle_api.py`: passed; dataset router is registered and expected dataset/tag route markers are present.
  - `rg -n "UploadFile|File\(|Form\(|request\.body\(|request\.stream\(|StreamingResponse|FileResponse" src\upload_control_plane`: no matches, exit code 1 as expected.
  - `docker compose ps --format json`: passed; no services were already running for this merge worktree.
  - `docker compose up -d postgres minio minio-init`: attempted; failed because host port `19000` was already allocated by another upload-control-plane worktree's MinIO.
  - `docker ps --format "{{.Names}} {{.Ports}}"`: passed; showed existing parallel upload-control-plane services on default/nearby ports, including default `19000` MinIO and `25432` PostgreSQL.
  - `docker compose down --volumes --remove-orphans`: passed; cleaned up the partial T09 merge stack created by the failed compose attempt.
  - `uv run python scripts/migrate.py`: passed against the already-running default local PostgreSQL service on `localhost:25432`.
  - `Invoke-WebRequest http://localhost:19000/minio/health/live -UseBasicParsing | Select-Object -ExpandProperty StatusCode`: passed; returned `200`.
  - `uv run python scripts/seed_dev.py`: passed; seeded deterministic dev data with 34 permission grants.
  - `uv run pytest`: passed; `164 passed, 1 warning`.
  - `uv run pytest tests/api/test_dataset_lifecycle_api.py -q`: passed; `9 passed, 1 warning`.
  - `git diff --check`: passed before this handoff.
  - `git status --short --branch`: clean before this handoff.
  - `git log --oneline --decorate -5`: passed; confirmed `07ec0b5` merge commit on the merge branch.
- Results:
  - Required static checks, type checks, migrations, seed, full pytest, focused T09 pytest, compose config validation, whitespace check, route scan, and file-byte marker scan passed.
  - Full pytest included the live MinIO integration test and passed.
  - The only test warning observed was the existing Starlette `TestClient` deprecation warning.
- Commands not run and why:
  - No push command was run because this merge task explicitly says not to push.

## PRD Hard Constraints Check

- Backend/MQTT receives no file bytes:
  - Preserved. The file-byte endpoint marker scan found no `UploadFile`, `File(...)`, `Form(...)`, `request.body()`, `request.stream()`, `StreamingResponse`, or `FileResponse` matches under `src/upload_control_plane`.
  - Dataset download returns a presigned object URL rather than backend-streamed bytes.
- Clients receive no MinIO/S3 credentials:
  - Preserved. T09 returns short-lived presigned download URLs only; no storage access key or secret key is exposed to clients.
- Complete uses object storage ListParts as authority:
  - Preserved. T09 did not modify upload completion logic; full pytest still passed the T06 runtime coverage.
- Authorization uses permission_grants:
  - Preserved. Dataset and tag APIs use permission codes backed by `permission_grants`; dev seed now includes dataset lifecycle and tag permission grants.
- Internal IDs remain UUIDs:
  - Preserved. New route schemas and service code use UUID IDs and existing UUID database columns.
- MQTT/Go/edge remain optional and dependency-gated:
  - Preserved. No MQTT, Go uploader, or gateway implementation was introduced.

## Risks and Follow-up

- Remaining risks:
  - Purge governance remains limited to the current schema capabilities documented by implementation and validation: storage-policy legal hold/object-lock fields exist, but per-dataset legal hold and storage-side metadata reconciliation are future hardening work.
  - Purge outbox automation remains T11 scope.
  - Because default compose ports were already occupied by parallel upload-control-plane worktrees, this merge validation used the already-running default PostgreSQL and MinIO services after cleaning up the failed partial T09 merge stack.
- Known gaps:
  - None blocking this merge.
- Suggested next agent:
  - Master final review can inspect this merge branch and, if accepted, treat T09 as unlocking T10.

## Recovery Notes

- If accepted, next dependency unlocked:
  - T10 Device Identity and Device Upload Authorization.
- If partial, reusable pieces:
  - Not applicable.
- If blocked, unblock condition:
  - Not applicable.
- If rejected, do not repeat:
  - Not applicable.
