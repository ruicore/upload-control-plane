# Master Handoff: after T06 runtime lifecycle acceptance

Status: ready-for-next-master
Agent type: Master handoff
Branch: main
Worktree: D:\upload-control-plane
Written: 2026-06-25 11:34 +08:00
Latest pushed commit: e11a4e8

## Purpose

This file is for the next master agent. It records orchestration state after T06 runtime lifecycle implementation, validation, merge, and push completed.

## Operating Constraints

- Follow `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`.
- The master agent coordinates only. Do not directly write implementation code or resolve implementation issues in the main worktree.
- Use sub agents with reasoning effort set to `medium`.
- Each sub agent must use its own independent branch and worktree.
- Do not allow one sub agent to complete the whole remaining program.
- Every implementation, validation, repair, documentation, and merge agent must leave a handoff or recovery document under `docs/tasks/industrial-multipart-upload-control-plane/handoffs/`.
- A task may finish as `accepted`, `partial`, `blocked`, or `rejected`; do not treat the program as all-success or all-failure.
- After validation, the master may start repair automatically when the issue is narrow and does not violate PRD or task product contracts.
- Automatic repair is allowed for environment tools, port conflicts, local config mismatch, format/type/test failures, narrow bugs, missing handoff content, or missing validation evidence.
- Automatic repair is not allowed to relax PRD hard constraints, bypass authorization, bypass storage-authoritative complete, add file-byte proxy paths, or expand the current task scope.
- Redis may be started when a later task needs it.
- Local PostgreSQL may be connected to and modified by sub agents.
- Make is allowed. Local exposed host ports may be changed when there are host conflicts, as long as container-internal contracts remain coherent and docs/configs are updated by a sub agent.

## Current Git State

Last confirmed before writing this file:

- `git status -sb`: `## main...origin/main`
- Local `main` was synchronized with `origin/main` at `e11a4e8`.
- Latest commits before this handoff:
  - `e11a4e8` `记录 T06 runtime lifecycle merge handoff`
  - `1b0bb32` `验证 T06 runtime lifecycle 实现`
  - `bf5b795` `实现 T06 runtime lifecycle actions`
  - `fe9499a` `记录 T06 lifecycle 前 master handoff`

Because this file is being added after that push, the next master should immediately run:

```powershell
git status -sb
git log --oneline --max-count=8
```

If this handoff file is still uncommitted or unpushed, commit and push it as an orchestration handoff before continuing.

## Completed and Accepted Scope

The following task areas have been implemented, validated, merged, and pushed through `e11a4e8`.

| Area | Status | Notes |
|---|---|---|
| T00 Foundation runtime | accepted | Python 3.13/FastAPI runtime, Docker Compose, Make targets. Host defaults: API `18080`, Postgres `25432`, MinIO S3 `19000`, MinIO Console `19001`. |
| T01 Domain kernel | accepted | Pure domain logic for parts, states, dataset exposure, permissions, object key sanitizing, request fingerprinting. |
| T02 Persistence foundation | accepted | SQLAlchemy/Alembic schema and seed data. Alembic head observed as `20260624_0005`. No `upload_batches` or `batch_id`. |
| T03 Authentication/authorization | accepted | `Authorization: Bearer <api_key>` contract, `X-API-Key` rejected, request ID, stable errors, project list/detail, `effective_permissions`. |
| T04 Storage adapter | accepted | `ObjectStorage` protocol, boto3/botocore adapter, internal/public clients, real MinIO multipart integration test. No string rewrite of signed URL host. |
| T05 Upload task creation | accepted | `POST /v1/projects/{project_id}/upload-tasks`, transactional task/object/dataset/session creation, idempotency, audit/upload events, storage multipart initiation. |
| T06 Runtime presign/status/ack segment | accepted | Status, presign, ack, parts list, permission re-evaluation, DB/storage/reconcile parts sources. |
| T06 Runtime lifecycle actions | accepted | Pause, resume, complete, abort, lifecycle idempotency, row-lock based session protection, storage-authoritative complete, missing-parts 409, lifecycle permissions and tenant isolation. |

## T06 Accepted Boundary

Full T06 is now accepted for the planned runtime API scope.

Accepted T06 public routes:

- `GET /v1/uploads/{session_id}`
- `POST /v1/uploads/{session_id}/parts/presign`
- `POST /v1/uploads/{session_id}/parts/ack`
- `GET /v1/uploads/{session_id}/parts`
- `POST /v1/uploads/{session_id}/pause`
- `POST /v1/uploads/{session_id}/resume`
- `POST /v1/uploads/{session_id}/complete`
- `POST /v1/uploads/{session_id}/abort`

Important accepted behavior:

- Presign does not persist the full presigned URL.
- Ack is idempotent and does not mark upload complete.
- Runtime endpoints re-evaluate permissions through the API layer.
- Pause blocks new presign and does not abort storage multipart upload.
- Resume allows fresh presigned URLs when permissions still allow it.
- Complete uses object storage `ListParts` as the authority, not DB ack rows.
- Missing or invalid storage parts return stable `409 upload.missing_parts` and do not call storage complete.
- Abort calls storage abort, is idempotent, and refuses completed sessions.
- Lifecycle actions use `permission_grants` backed permissions:
  - `upload.pause`
  - `upload.resume`
  - `upload.complete`
  - `upload.abort`
- No FastAPI file-byte endpoint markers were found in `src/upload_control_plane`.

Accepted T06 handoffs:

- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0558-T06-merge-runtime-presign-ack-accepted.md`
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1108-T06-implementation-runtime-lifecycle-accepted.md`
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1121-T06-validation-runtime-lifecycle-accepted.md`
- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-1131-T06-merge-runtime-lifecycle-accepted.md`

## Validation Evidence

Implementation, validation, and merge agents reported successful validation. The strongest merge evidence:

```powershell
uv run ruff check
uv run ruff format --check
uv run mypy src tests
uv run pytest
make test
docker compose config --quiet
docker compose up -d postgres minio minio-init
make migrate
make seed-dev
uv run pytest tests/integration/test_s3_storage_minio.py -q
uv run pytest tests/api/test_upload_session_runtime_api.py -q
docker compose down
```

Observed results from accepted merge handoff:

- Full pytest with services available: `155 passed`.
- `make test`: passed.
- Targeted MinIO storage integration: `1 passed`.
- Targeted T06 runtime API tests: `11 passed`.
- Inline real MinIO lifecycle smoke:
  - Public API create and presign.
  - Direct `PUT` to MinIO presigned URL.
  - API complete returned `COMPLETED`.
  - Storage head/read confirmed the final object.
  - Separate API abort returned `ABORTED`; retry with the same idempotency key returned the same response.
- Route surface scan found only expected routes for the current stage.
- File-byte endpoint marker scan returned no matches.

## Product Hard Constraints Preserved

- Backend, workers, MQTT, and gateways must not receive file bytes.
- Clients must not receive MinIO/S3 credentials.
- Complete must use object storage `ListParts` as the authority.
- `permission_grants` and permission codes are the authorization source of truth.
- Internal IDs remain UUIDs.
- MQTT, Go uploader, and Go gateway remain optional and dependency-gated.
- Browser/CLI agents must not add backend-only shortcuts that bypass T06.

The accepted T06 work preserves these constraints as of `e11a4e8`.

## Now Unlocked

After this handoff is committed and pushed, the next master may unlock the next dependency layer.

According to `agent-orchestration.md`, after full T06 accepted:

- `T07 Development Manual Browser Uploader` may start.
- `T08 Python CLI Uploader` may start.
- `T09 Dataset Product Lifecycle` may start.

Recommended orchestration:

1. Start T07 and T08 in parallel only if the user wants client tooling immediately.
2. Start T09 in parallel with T07/T08 if product lifecycle is the priority, because it depends on completed upload behavior but not on browser/CLI tooling.
3. Keep T11 and later tasks blocked until their explicit dependencies are accepted.

## Recommended Next Agent Options

Option A: start T07 Browser manual uploader implementation.

- Branch: `codex/industrial-upload/T07-implementation-browser-uploader`
- Worktree: `../upload-control-plane-T07-implementation-browser-uploader`
- Scope:
  - `tools/manual-uploader` Vite app.
  - Public API create/presign/status/pause/resume/complete/abort controls.
  - Browser direct `PUT` to presigned MinIO URL.
  - No manual-uploader-only backend routes.
  - Redact presigned URL query strings from diagnostics.

Option B: start T08 Python CLI uploader implementation.

- Branch: `codex/industrial-upload/T08-implementation-python-cli-uploader`
- Worktree: `../upload-control-plane-T08-implementation-python-cli-uploader`
- Scope:
  - `uploadctl upload/resume/status/pause/resume-session/abort`.
  - Manifest without presigned URLs.
  - Concurrent direct PUT with bounded memory.
  - URL expiry detection and re-presign.

Option C: start T09 Dataset lifecycle implementation.

- Branch: `codex/industrial-upload/T09-implementation-dataset-lifecycle-api`
- Worktree: `../upload-control-plane-T09-implementation-dataset-lifecycle-api`
- Scope:
  - Dataset list/search/detail/update/download URL/archive/delete/restore/purge.
  - Dataset exposure rules using dataset, validation, and recovery states.
  - Audit events and permission gates.

Do not let any of these agents add backend file-byte proxying or bypass T06.

## Known Follow-up

- Dedicated `upload.presign` permission seeding/enforcement remains a later authorization hardening decision. T06 lifecycle added explicit lifecycle permissions, but presign still accepts `dataset.upload` or `upload.create` as documented in earlier handoffs.
- Storage-complete success followed by DB finalization failure is not yet covered by an operator repair/reconcile command or committed regression test. This should be handled in later failure-injection or recovery work, not by weakening storage-authoritative complete.
- Real MinIO lifecycle smoke was run inline by validation/merge agents and recorded in handoffs, but not committed as a regression test.
- Existing Starlette `TestClient` deprecation warning remains.

## Recovery Notes

- If the next master sees `main` not synchronized with `origin/main`, inspect before proceeding and do not overwrite user or agent changes.
- If this handoff is uncommitted, commit and push it as orchestration documentation before launching new implementation agents.
- If local ports conflict, assign new host ports through a sub agent and require docs/config/test evidence.
- If Docker, Postgres, or MinIO are missing or misconfigured, this falls under allowed automatic repair as long as product behavior is unchanged.
