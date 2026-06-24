# State Machine

Previous: [Domain Model](04-domain-model.md) | Index: [README](README.md) | Next: [API Contracts and Part Sizing](06-api-contracts.md)

## 9. State Machine

### 9.1 Upload session statuses

Use the following states:

```text
INITIATING
INITIATED
UPLOADING
PAUSED
COMPLETING
COMPLETED
ABORTING
ABORTED
EXPIRED
FAILED
```

### 9.2 State definitions

| State | Meaning |
|---|---|
| `INITIATING` | DB record exists, storage multipart upload is being created or persisted |
| `INITIATED` | Storage upload ID exists; no confirmed upload progress yet |
| `UPLOADING` | One or more presigned URLs issued or parts acknowledged/listed |
| `PAUSED` | Upload scheduling is paused; already uploaded parts are preserved and new presign requests are rejected |
| `COMPLETING` | Completion is in progress; presign should be rejected |
| `COMPLETED` | Final object exists; multipart parts are assembled |
| `ABORTING` | Abort is in progress |
| `ABORTED` | Multipart upload has been aborted or considered aborted |
| `EXPIRED` | App-level session expired before completion |
| `FAILED` | Terminal failure requiring manual or automated remediation |

### 9.3 Allowed transitions

| From | To | Trigger |
|---|---|---|
| none | `INITIATING` | UploadTask creation accepted for an UploadObject |
| `INITIATING` | `INITIATED` | Storage create multipart upload succeeded and DB updated |
| `INITIATING` | `FAILED` | Storage create failed permanently |
| `INITIATED` | `UPLOADING` | Presign issued or part acknowledged |
| `UPLOADING` | `UPLOADING` | More parts uploaded, listed, or acknowledged |
| `INITIATED` | `PAUSED` | Pause requested before part upload begins |
| `UPLOADING` | `PAUSED` | Pause requested |
| `PAUSED` | `UPLOADING` | Resume requested |
| `INITIATED` | `COMPLETING` | Complete requested and all parts exist |
| `UPLOADING` | `COMPLETING` | Complete requested and all parts exist |
| `PAUSED` | `COMPLETING` | Complete requested and all parts already exist |
| `COMPLETING` | `COMPLETED` | Storage complete succeeded |
| `COMPLETING` | `FAILED` | Storage complete failed non-retryably |
| `INITIATED` | `ABORTING` | Abort requested or cleanup worker starts abort |
| `UPLOADING` | `ABORTING` | Abort requested or cleanup worker starts abort |
| `PAUSED` | `ABORTING` | Abort requested or cleanup worker starts abort |
| `EXPIRED` | `ABORTING` | Cleanup worker starts abort |
| `ABORTING` | `ABORTED` | Storage abort succeeded or upload no longer exists |
| `INITIATED` | `EXPIRED` | Session expiry reached |
| `UPLOADING` | `EXPIRED` | Session expiry reached |
| `PAUSED` | `EXPIRED` | Session expiry reached |
| any non-terminal | `FAILED` | Internal unrecoverable error |

Terminal states:

```text
COMPLETED
ABORTED
FAILED
```

`EXPIRED` is not terminal because cleanup may transition it to `ABORTING` and then `ABORTED`.

### 9.4 Invalid transitions

Codex must reject:

- `COMPLETED` -> anything else.
- `ABORTED` -> `UPLOADING` or `COMPLETING`.
- `FAILED` -> `UPLOADING` unless an explicit repair endpoint is added later.
- Presign requests for `PAUSED`, `COMPLETING`, `COMPLETED`, `ABORTING`, `ABORTED`, `FAILED`.
- Complete requests for `ABORTING`, `ABORTED`, `EXPIRED`, `FAILED`.
- Resume requests for `COMPLETING`, `COMPLETED`, `ABORTING`, `ABORTED`, `EXPIRED`, `FAILED`.

### 9.5 Race control

Pause, resume, completion, and abort must acquire a session-level lock.

Acceptable implementations:

- PostgreSQL row lock using `SELECT ... FOR UPDATE`.
- PostgreSQL advisory lock keyed by session UUID.
- Optimistic version field with retry, if carefully implemented.

Recommended initial implementation:

- Use `SELECT ... FOR UPDATE` inside transaction for state transition checks.
- Set status to `PAUSED`, `UPLOADING`, `COMPLETING`, or `ABORTING` only after validating the current state while holding the lock.
- Set status to `COMPLETING` or `ABORTING` before calling long-running storage operation.
- Record lifecycle event.
- Perform storage call.
- Re-open transaction and mark final state.

---

