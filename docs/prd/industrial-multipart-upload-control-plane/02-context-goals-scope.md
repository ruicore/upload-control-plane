# Context, Goals, and Scope

Previous: [Non-Negotiable Decisions](01-non-negotiable-decisions.md) | Index: [README](README.md) | Next: [System Architecture](03-system-architecture.md)

## 2. Problem Background

Industrial AI, robotics, autonomous systems, and data-platform workloads often generate large files:

- Robot sensor logs.
- Video streams.
- LiDAR frames.
- ROS bag files.
- Model training datasets.
- Edge-device diagnostic bundles.
- Industrial inspection images.
- Long-running telemetry archives.

These files may be uploaded from unstable environments:

- Factory Wi-Fi.
- 4G / 5G edge networks.
- Robot docking stations.
- Remote sites.
- Intermittent VPN connectivity.
- Devices that may reboot or lose power.

A single large `PUT` upload is fragile. If a 100 GB file fails at 98 GB, restarting the entire upload is unacceptable. A reliable system must upload in independently retryable parts.

S3-compatible multipart upload solves this by splitting an object into parts that can be uploaded independently and then completed into one final object.

---


## 3. Official Behavior and Storage Limits Used by This Design

This project uses S3-compatible Multipart Upload as the baseline protocol.

The design should follow these portability constraints unless explicitly configured otherwise:

| Constraint | Project default |
|---|---:|
| Minimum non-final part size | 5 MiB |
| Recommended minimum practical part size | 64 MiB |
| Maximum portable part size | 5 GiB |
| Maximum number of parts | 10,000 |
| Part number range | 1 to 10,000 |
| Default presigned URL expiry | 15 minutes |
| Maximum presigned URL expiry in this app | 6 hours by policy, configurable |
| Default upload session expiry | 24 hours, configurable |
| Default cleanup grace period | 2 hours after session expiry |

Notes:

- AWS S3 documentation currently specifies multipart limits including 10,000 parts, part numbers from 1 to 10,000, and part size from 5 MiB to 5 GiB with no minimum size for the last part.
- Current AWS S3 multipart limit documentation lists a maximum object size of 48.8 TiB.
- MinIO has its own current documented limits. At the time of this document, MinIO documents a 50 TiB maximum object size, 10,000 parts per upload, and a larger MinIO-specific maximum part size. This project should still default to the stricter S3-compatible part-size ceiling of 5 GiB for portability.
- Multipart upload completion must provide part numbers and ETags in ascending part order.
- Object storage can list parts of an in-progress upload; AWS S3 returns up to 1,000 parts per `ListParts` response, so the adapter must support pagination even if MinIO returns more.
- Storage-native checksums, if enabled, add stricter request/header requirements. In S3, checksum-enabled multipart uploads require consecutive part numbers beginning at 1, and checksum mismatch can fail the upload with `BadDigest`.
- Conditional completion, if supported by the target storage, should use write preconditions such as `If-None-Match: *` to prevent accidental object-key overwrite. The adapter must model storage-specific support and failure behavior explicitly.
- Browser direct upload requires bucket-level CORS rules that match the browser origin, PUT/HEAD methods, and all headers included in the signed request.

References are listed in [References and Completion Criteria](14-references-and-done.md#31-source-references).

---


## 4. Project Name and Positioning

Recommended repository name:

```text
upload-control-plane
```

Alternative names:

```text
industrial-upload-control-plane
resumable-upload-control-plane
robot-data-upload-control-plane
```

Recommended one-line description:

```text
Production-oriented resumable multipart upload control plane for AI and robotics data ingestion, using FastAPI, PostgreSQL, and MinIO.
```

Recommended GitHub topic tags:

```text
multipart-upload
s3
minio
fastapi
postgresql
resumable-upload
large-file-upload
robotics
ai-infrastructure
data-ingestion
observability
```

---


## 5. Goals

### 5.1 Functional goals

The system must support:

1. Creating an upload session for one large file.
2. Creating a batch upload for a logical dataset containing multiple file uploads.
3. Generating presigned URLs for one or more part numbers.
4. Direct client-to-MinIO part upload.
5. Client resume after interruption.
6. Server-side reconciliation using `ListParts`.
7. Completing multipart upload only when all expected parts exist.
8. Pausing and resuming uploads without discarding already uploaded parts.
9. Aborting multipart upload.
10. Expiring stale sessions.
11. Cleaning abandoned multipart uploads.
12. Recording upload lifecycle events.
13. Recording optional client-reported ETags and part checksums.
14. Enforcing tenant/user/device authorization.
15. Enforcing object-key namespace isolation.
16. Managing projects, project members, and project-scoped permissions.
17. Managing datasets as data assets with search, tags, preview metadata, recycle/restore, and purge lifecycle.
18. Managing device registration, device credentials, device status, and device-to-project authorization.
19. Managing upload tasks for multi-file Web/device workflows, including task-level and object-level pause/resume/cancel/retry.
20. Managing storage policies for project/tenant defaults, retention, checksum, presign, and object-key behavior.
21. Providing download control-plane APIs that authorize and issue short-lived presigned download URLs.
22. Running dataset validation and metadata extraction after upload completion.
23. Providing unified audit events for authorization, dataset, device, download, deletion, and upload actions.
24. Providing a durable outbox for recoverable event delivery to EMQX/WebSocket/webhook workers.
25. Providing a CLI uploader for E2E testing and real demonstration.
26. Providing OpenAPI documentation.
27. Providing deterministic local development through Docker Compose.
28. Providing integration tests using real PostgreSQL and real MinIO.
29. Providing failure injection tests.
30. Providing benchmark scripts.

### 5.2 Non-functional goals

The system should demonstrate:

- Reliability under network failure.
- Retry-safe API design.
- Clear state machine ownership.
- High concurrency at the upload data plane because file bytes go directly to MinIO.
- Bounded backend CPU, memory, and network usage.
- Secure credential handling.
- Clear observability.
- Testability.
- Maintainable architecture.
- Future portability to AWS S3, Alibaba OSS, Tencent COS, or other S3-compatible storage.

---


## 6. Non-Goals

The first complete design does not need to implement:

- Browser UI dashboard, although API design should allow it later.
- Real payment or quota billing.
- Real enterprise SSO.
- Multi-region active-active object replication in the initial product stages.
- Custom binary transport protocol.
- tus protocol support.
- Direct backend file streaming upload.
- Virus scanning as a blocking step in the initial product stages.
- Real production deployment to Kubernetes on day one.

Optional future extensions are allowed, but Codex must not implement them before core upload correctness is complete.

Even when a capability is deferred, the design must not block it later. In particular:

- Backup/restore and object replication must have documented extension points even if they are not implemented in Phase 0-4.
- Uploaded datasets should be able to remain quarantined or validation-pending before being exposed for download, training, or downstream processing.
- Storage policies should be able to evolve from local MinIO defaults to production encryption, object-lock, legal-hold, and replication policies without changing upload API contracts.

---

