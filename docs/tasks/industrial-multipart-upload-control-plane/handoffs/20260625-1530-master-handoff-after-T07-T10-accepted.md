# Master Handoff: after T07 and T10 accepted

Status: ready-for-next-master
Agent type: Master handoff / Documentation Agent writing for Master
Branch: main
Worktree: D:\upload-control-plane
Written: 2026-06-25 15:26 +08:00 Asia/Shanghai

## Purpose

This handoff records the current master orchestration state after T07 and T10 were accepted and merged into local `main`. It is written by a Documentation Agent in an independent worktree and branch, following `docs/tasks/industrial-multipart-upload-control-plane/agent-orchestration.md`.

## Current Git State

Last confirmed before writing this file:

- Root worktree: `D:\upload-control-plane`
- Branch: `main`
- Local `main` HEAD: `1e7d3c5`
- `origin/main`: `898549e`
- `git status -sb`: `## main...origin/main [ahead 10]`
- Local `main` has not been pushed.

This documentation handoff is being added from branch `codex/industrial-upload/master-handoff-after-T07-T10` in worktree `D:\upload-control-plane-master-handoff-after-T07-T10`.

## Accepted and Merged

T07 Development Manual Browser Uploader is accepted and merged into local `main`.

Evidence:

- Implementation: `41e16db`
- Repair CORS: `93bb8bb`
- Repair env: `4b90e79`
- Final validation: `9f0cc33`
- Merge branch/commit: `fced193`
- Accepted handoffs:
  - `20260625-1239-T07-implementation-browser-uploader-accepted.md`
  - `20260625-1303-T07-repair-browser-cors-accepted.md`
  - `20260625-1321-T07-repair-cors-settings-env-accepted.md`
  - `20260625-1501-T07-validation-browser-uploader-final-retry-accepted.md`
  - `20260625-1506-T07-merge-browser-uploader-accepted.md`

T10 Device Identity and Device Upload Authorization is accepted and merged into local `main`.

Evidence:

- Implementation: `3496c24`
- Validation: `e6713ca`
- Merge: `1e7d3c5`
- Accepted handoffs:
  - `20260625-1511-T10-implementation-device-identity-accepted.md`
  - `20260625-1517-T10-validation-device-identity-accepted.md`
  - `20260625-1522-T10-merge-device-identity-accepted.md`

## Master Final Verification on Local Main

The master final verification was run on local `main` after T07 and T10 were merged.

Results:

- `git diff --check`: passed.
- `uv run ruff check`: passed.
- `uv run ruff format --check`: passed, `85 files already formatted`.
- `uv run mypy src tests`: passed, no issues in 76 source files.
- `uv run pytest tests/api/test_device_identity_api.py tests/api/test_upload_task_api_foundation.py tests/api/test_upload_session_runtime_api.py -q`: passed, `30 passed, 1 warning`.
- `uv run pytest tests/api/test_cors.py tests/test_config.py -q`: passed, `5 passed, 1 warning`.
- `uv run pytest -q`: passed, `181 passed, 1 warning`.
- `docker compose config --quiet`: passed.
- `tools/manual-uploader` `npm run test`: passed, 2 files / 4 tests passed.
- `tools/manual-uploader` `npm run check`: passed.
- `tools/manual-uploader` `npm run build`: passed.
- Backend file-byte route scan: no matches.
- API/application MinIO/S3 credential exposure scan: no matches.

## Product Hard Constraints Preserved

The following hard constraints remain preserved on local `main` at `1e7d3c5`:

- Backend API service does not receive file bytes.
- MQTT/EMQX does not receive file bytes, does not carry multipart chunks, and is not an object storage proxy.
- Clients, browsers, CLIs, devices, and Go uploaders do not receive MinIO/S3 access keys or secret keys.
- Multipart upload complete remains storage-authoritative through object storage `ListParts` or equivalent storage adapter behavior; DB ack alone does not decide complete.
- `permission_grants` and permission codes remain the authorization source; API key scope does not replace resource-level authorization.
- Internal primary keys and foreign keys remain UUIDs.
- Human-readable slug, device code, storage upload ID, object key, and idempotency key are not internal primary keys.
- MQTT, Go uploader, Go gateway, and edge capabilities remain optional and dependency-gated.
- Pause remains control-plane scheduling state, not storage abort, and does not guarantee freezing already-started PUTs.
- Presigned URLs remain short-lived bearer tokens and are not persisted to manifest, browser local storage, logs, audit, trace, or outbox.
- Go gateway, if later implemented, must remain a control-plane gateway only. It must not proxy file bytes or replace backend authorization or storage complete reconciliation.

## Now Unlocked

- T11 Workers and Lifecycle Automation may start because T10 is accepted.
- T12 waits for T11.
- T15 waits for T10, T11, and T13.
- T16 still waits for T14.
- T17 waits for T13 and an accepted deployment reason.

## Known Residual Risks

- Starlette/TestClient still emits a deprecation warning during the relevant test runs.
- T07 full file-picker browser automation was not run. The accepted evidence instead includes CORS plus live public API/direct MinIO smoke.
- T10 did not add per-device rate limiting.
- T10 did not add the T13 device compromise runbook.
- Presigned URLs issued before device revocation remain usable until their short expiry.

## Recovery Notes

- Local `main` is not pushed. Push `main` only if the user asks.
- Old T07 and T10 worktrees may remain. Inspect `git worktree list` before cleanup.
- Stale Docker containers from previous agents may remain. Inspect `docker ps` before cleanup.
- Do not reset or revert local `main`; it contains accepted T07 and T10 merges ahead of `origin/main`.
- The next master should start by confirming:

```powershell
git status -sb
git rev-parse --short HEAD
git rev-parse --short origin/main
git log --oneline --max-count=16
```
