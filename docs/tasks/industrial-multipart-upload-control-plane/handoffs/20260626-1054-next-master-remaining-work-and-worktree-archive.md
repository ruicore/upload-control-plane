# Next master handoff: remaining work and worktree archive

Status: accepted
Agent type: master cleanup / next-master preparation
Branch at handoff: main
Started: 2026-06-26 Asia/Shanghai
Finished: 2026-06-26 10:54 Asia/Shanghai

## Scope

- Publish the completed local `main` first.
- Archive and remove accumulated `D:\upload-control-plane-*` worktrees.
- Record the remaining PRD/task work for the next master agent.

## Push status

- `git push origin main` was run before cleanup/doc changes.
- Remote `origin/main` advanced from `4dde0be` to `0ce09cd`.
- This handoff and `.gitignore` archive-directory rule are created after that push and require a follow-up push after commit.

## Worktree archive status

- Added ignored local archive directory rule:
  - `.worktree-archive/`
- Local archive path:
  - `D:\upload-control-plane\.worktree-archive\20260626-archive-worktrees`
- Archive contents:
  - `codex-industrial-upload-branches.bundle`
    - Verified with `git bundle verify`.
    - Contains all `codex/industrial-upload/*` local branches at archive time.
  - `worktrees.json`
  - `worktrees.tsv`
  - `branches.txt`
  - `removed-worktrees.txt`
  - `remove-errors.txt`
  - `residual-upload-control-plane-T07-validation-browser-uploader-after-cors`
- Cleanup result:
  - `git worktree list --porcelain` now shows only the main worktree:
    - `D:/upload-control-plane`
  - No `D:\upload-control-plane-*` directories remain under `D:\`.
  - One old `node_modules/@esbuild/.../esbuild.exe` path initially refused deletion; the residual directory was moved under the ignored archive path above.

## Current implementation status

### Core task chain

- T00-T14 are accepted on local `main` and were pushed at commit `0ce09cd`.
- The latest accepted master handoff before this cleanup is:
  - `20260626-1038-master-handoff-after-T14-gap-repairs-and-T15-backpressure.md`
- The latest final merge handoff for T14 gap repairs is:
  - `20260626-1037-T14-final-main-merge-gap-repairs-accepted.md`
- Final recorded validation after T14/T15 backpressure integration:
  - `uv run ruff check src tests`: passed.
  - `uv run ruff format --check src tests`: passed.
  - `uv run mypy src tests`: passed.
  - focused tests: passed, 49 passed and 1 warning.
  - full tests: passed, 224 passed and 1 warning.

### Important clarification about T15

- There is a T15-labelled backpressure line on `main`, but it is not the PRD's MQTT adapter.
- It should be treated as accepted storage backpressure hardening that was merged into the T14 gap repair work.
- Do not duplicate that slice.
- The actual optional T15 MQTT adapter remains not implemented.

## Remaining work

### 1. Optional T15 EMQX/MQTT control-plane adapter

Status: not implemented.

Only start if MQTT is still desired. It must remain a control-plane ingress/notification layer, not a data plane.

Required implementation scope from the task README:

- MQTT command adapter.
- Topic naming and schema validation.
- Device authentication mapping.
- MQTT request/response correlation.
- MQTT ACL/topic authorization for each device.
- Device credential revocation handling.
- TLS-enabled production configuration.
- QoS and retain policy documentation.

Required validation scope:

- MQTT adapter calls the same application services as HTTP routes.
- MQTT messages never carry file bytes.
- Presigned URL response messages are not retained.
- Duplicate MQTT commands are idempotent.
- Device cannot publish or subscribe outside its authorized topic namespace.
- Disabled or revoked devices are rejected.

Hard constraints:

- MQTT/EMQX must not carry multipart chunks or file bytes.
- MQTT must not compensate for backend, authorization, storage reconciliation, or outbox gaps.
- Presigned URL responses must not be retained or logged with query strings.

### 2. Optional T16 Go uploader

Status: not implemented.

Only start if a Go uploader is still desired after the accepted Python CLI and T14 failure/benchmark work.

Required implementation scope from the task README:

- `go/robot-uploader` module.
- Upload/resume/status support through the same Python backend API.
- Concurrent part upload using goroutines.
- Local manifest compatible with the Python CLI or explicitly versioned.

Required validation scope:

- Go uploader can upload and resume files using the Python backend.
- Benchmark compares Python CLI and Go uploader.
- Go implementation does not bypass the backend or use MinIO credentials.

Hard constraints:

- No backend rewrite in Go.
- No direct MinIO/S3 credentials in the uploader.
- No file-byte proxy through the backend.

### 3. Optional T17 Go edge/control gateway

Status: not implemented and not unlocked unless there is an accepted deployment reason.

The task README explicitly requires:

- T13 accepted.
- A concrete accepted deployment reason.

Possible implementation scope:

- Reverse proxy for control-plane API.
- API key or JWT validation.
- Rate limiting.
- Request ID propagation.
- Explicit no-data-plane-proxying guarantees.

Required validation scope:

- Gateway never proxies file bytes.
- Gateway can be disabled without changing core upload semantics.
- Gateway does not replace backend authorization or storage reconciliation.

Recommendation:

- Do not start T17 unless the user first confirms a real deployment need.

### 4. Final portfolio readiness check

Status: not yet run as a single final acceptance package after cleanup.

Run after T14 and any selected optional tasks, or run now if the user wants to declare the Python-first portfolio complete without optional Go/MQTT/gateway work.

Checklist from task README:

- Docker Compose local run works.
- `uploadctl` can upload, interrupt, resume, pause, resume, reconcile, and complete.
- PostgreSQL exposes expected project, dataset, task, session, part, audit, and outbox metadata.
- MinIO contains completed objects under expected project/dataset key namespaces.
- Permission tests prove hidden/forbidden actions stay inaccessible.
- Device tests prove registered devices can trigger uploads and disabled/revoked devices cannot.
- Dataset lifecycle tests cover soft delete, restore, download authorization, validation persistence, and purge policy behavior.
- Tests cover missing parts, URL expiry recovery, duplicate completion, pause/resume, and abort idempotency.
- Logs, metrics, alerts, audit events, outbox behavior, and runbooks demonstrate operational thinking.
- README clearly states the project is production-oriented but not production-proven.

## Suggested next-master plan

1. Re-check `git status --short --branch` and ensure this handoff commit has been pushed.
2. Ask whether the user wants optional MQTT, Go uploader, or Go gateway.
3. If the user does not want optional components, run the Final Portfolio Readiness Check and record a final accepted handoff.
4. If MQTT is desired, start T15 from the task README scope, not from the already-accepted storage backpressure work.
5. Keep using handoff-first orchestration and medium-reasoning sub agents.
