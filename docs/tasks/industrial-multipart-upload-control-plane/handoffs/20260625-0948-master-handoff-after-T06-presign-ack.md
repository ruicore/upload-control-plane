# Master Handoff: after T06 runtime presign/ack checkpoint

Status: ready-for-next-master
Agent type: Master handoff
Branch: main
Worktree: D:\upload-control-plane
Written: 2026-06-25 09:48 +08:00
Latest pushed commit: 481fdbc

## Purpose

This file is for the next master agent. It records the current orchestration state after the previous master paused. It is not an implementation handoff and does not unlock downstream work by itself.

## Operating Constraints

- Follow `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`.
- The master agent must coordinate only. Do not directly write code or resolve implementation issues in the main worktree.
- Use sub agents with reasoning effort set to `medium`.
- Each sub agent must use its own independent branch and worktree.
- Do not allow one sub agent to complete the whole remaining program.
- Split work by dependency and complexity, even when the task is tightly coupled.
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
- Local `main` is synchronized with `origin/main`.
- Latest commits:
  - `481fdbc` `记录 T06 runtime presign ack merge handoff`
  - `4663025` `提交 T06 runtime presign ack 检查点`
  - `fd53db9` `T05 final merge handoff accepted`
- The push from `a768030` to `481fdbc` succeeded after one transient SSH disconnect retry.

Because this file is being added after that push, the next master should immediately run:

```powershell
git status -sb
git log --oneline --max-count=5
```

If this file is still uncommitted, decide whether to commit it as an orchestration handoff before continuing.

## Completed and Accepted Scope

The following task areas have been implemented, validated, merged, and pushed through `481fdbc`.

| Area | Status | Notes |
|---|---|---|
| T00 Foundation runtime | accepted | Python 3.13/FastAPI runtime, Docker Compose, Make targets. Host defaults: API `18080`, Postgres `25432`, MinIO S3 `19000`, MinIO Console `19001`. |
| T01 Domain kernel | accepted | Pure domain logic for parts, states, dataset exposure, permissions, object key sanitizing, request fingerprinting. |
| T02 Persistence foundation | accepted | SQLAlchemy/Alembic schema and seed data. Alembic head observed as `20260624_0005`. No `upload_batches` or `batch_id`. |
| T03 Authentication/authorization | accepted | `Authorization: Bearer <api_key>` contract, `X-API-Key` rejected, request ID, stable errors, project list/detail, `effective_permissions`. |
| T04 Storage adapter | accepted | `ObjectStorage` protocol, boto3/botocore adapter, internal/public clients, real MinIO multipart integration test. No string rewrite of signed URL host. |
| T05 Upload task creation | accepted | `POST /v1/projects/{project_id}/upload-tasks`, transactional task/object/dataset/session creation, idempotency, audit/upload events, storage multipart initiation. |
| T06 Runtime presign/status/ack segment | accepted | First T06 segment only: status, presign, ack, parts list. |

## T06 Current Boundary

Accepted T06 first segment added:

- `GET /v1/uploads/{session_id}`
- `POST /v1/uploads/{session_id}/parts/presign`
- `POST /v1/uploads/{session_id}/parts/ack`
- `GET /v1/uploads/{session_id}/parts`
- Parts source modes: `source=db`, `source=storage`, and `source=reconcile`

Important behavior from the accepted handoff:

- Presign does not persist the full presigned URL.
- Ack is idempotent and does not mark upload complete.
- Runtime endpoints re-evaluate permissions through the API layer.
- No pause/resume/complete/abort routes were added.
- No FastAPI file-byte endpoint markers were found in `src/upload_control_plane`.

Latest accepted T06 merge handoff:

- `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0558-T06-merge-runtime-presign-ack-accepted.md`

## Not Yet Complete

Full T06 is not complete. These are still pending:

- Pause upload session.
- Resume upload session.
- Complete upload session.
- Abort upload session.
- Lifecycle idempotency.
- Session locking or equivalent concurrency protection.
- Storage-authoritative complete using storage `ListParts`.
- Missing-parts 409 behavior.
- Tenant isolation and permission re-evaluation coverage for lifecycle actions.

Because T06 is not fully accepted:

- Do not start T07 Browser uploader yet.
- Do not start T08 Python CLI uploader yet.
- Do not start T09 Dataset lifecycle yet.
- Do not unlock workers, validation, observability, MQTT, Go uploader, or Go gateway work.

## Recommended Next Orchestration

Start with the next T06 lifecycle implementation slice.

Suggested sub agent:

- Task: `T06 Runtime lifecycle actions`
- Agent type: Implementation
- Reasoning: medium
- Depends on:
  - `docs/tasks/industrial-multipart-upload-control-plane/README.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`
  - `docs/tasks/industrial-multipart-upload-control-plane/handoffs/20260625-0558-T06-merge-runtime-presign-ack-accepted.md`
  - PRD files listed for T06 in the task README
- Scope:
  - pause/resume/complete/abort endpoints
  - lifecycle idempotency
  - session concurrency guard
  - storage-authoritative complete with storage `ListParts`
  - missing-parts conflict response
  - tests for lifecycle permissions and tenant isolation
- Explicitly out of scope:
  - browser uploader
  - Python CLI uploader
  - dataset lifecycle
  - workers
  - validation worker
  - observability
  - MQTT
  - Go uploader
  - Go gateway
  - any file-byte proxy endpoint

After implementation:

1. Require implementation handoff.
2. Start independent T06 lifecycle validation agent.
3. If validation is `partial`, `blocked`, or `rejected`, start a repair agent only for allowed repair categories.
4. Re-run validation after repair.
5. Only after validation is `accepted`, use a merge agent to merge and write a merge handoff.
6. Then the master reviews whether full T06 is accepted and whether T07/T08/T09 can be unlocked.

## Validation Commands to Reuse

Known successful commands from the latest accepted merge:

```powershell
uv run ruff check
uv run ruff format --check
uv run mypy src tests
uv run pytest
make test
docker compose config --quiet
docker compose up -d postgres
make migrate
make seed-dev
uv run pytest tests/api/test_upload_session_runtime_api.py -q
docker compose down
```

Useful hard-constraint scans:

```powershell
rg -n "@router\.(get|post|put|patch|delete)|APIRouter\(|include_router|/pause|/resume|/complete|/abort|parts/presign|parts/ack|/v1/uploads" src/upload_control_plane tests/api/test_upload_session_runtime_api.py
rg -n "UploadFile|File\(|Form\(|multipart/form-data|files=" src/upload_control_plane
```

For the next lifecycle work, validation should additionally prove:

- Presign is rejected while paused.
- Resume re-enables presign only when permissions still allow it.
- Abort calls storage abort and is idempotent.
- Complete uses storage `ListParts` as authority, not database ack rows alone.
- Complete returns a stable conflict when storage parts are missing.
- Cross-tenant and unauthorized actors cannot read or mutate sessions.
- Completed/aborted sessions reject incompatible later actions.

## Product Hard Constraints to Preserve

- Backend, workers, MQTT, and gateways must not receive file bytes.
- Clients must not receive MinIO/S3 credentials.
- Complete must use object storage `ListParts` as the authority.
- `permission_grants` and permission codes are the authorization source of truth.
- Internal IDs remain UUIDs.
- MQTT, Go uploader, and Go gateway remain optional and dependency-gated.
- Browser/CLI agents must not add backend-only shortcuts that bypass T06.

## Known Follow-up

- Dedicated `upload.presign` permission seeding/enforcement was called out by the accepted T06 first-segment handoff as later authorization hardening. Do not silently add this as a product contract change unless it is handled in-scope by a sub agent with tests and handoff.

## Recovery Notes

- If the next master sees this file uncommitted, committing it is a documentation/orchestration step, not a product implementation.
- If the worktree is dirty for unrelated reasons, do not revert user or agent changes. Inspect and route through the orchestration process.
- If local ports conflict, assign new host ports through a sub agent and require docs/config/test evidence.
- If make, Redis, Docker, Postgres, or MinIO are missing or misconfigured, this falls under allowed automatic repair as long as product behavior is unchanged.
