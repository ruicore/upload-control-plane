# References and Completion Criteria

Previous: [Implementation Plan](13-implementation-plan.md) | Index: [README](README.md)

## 31. Source References

This design is based on storage-provider behavior, MQTT control-plane behavior, upload-security guidance, and observability conventions from the following sources:

1. AWS S3 Multipart Upload Overview
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html

2. AWS S3 Multipart Upload Limits
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html

3. AWS Boto3 `generate_presigned_url`
   https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/generate_presigned_url.html

4. AWS Boto3 `create_multipart_upload`
   https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/create_multipart_upload.html

5. AWS Boto3 `upload_part`
   https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/upload_part.html

6. AWS Boto3 `complete_multipart_upload`
   https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/complete_multipart_upload.html

7. MinIO S3 API compatibility
   https://docs.min.io/aistor/developers/s3-api-compatibility/

8. MinIO Python SDK API reference
   https://docs.min.io/aistor/developers/sdk/python/api/

9. MinIO limits
   https://github.com/minio/minio/blob/master/docs/minio-limits.md

10. AWS S3 lifecycle rule for aborting incomplete multipart uploads
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-abort-incomplete-mpu-lifecycle-config.html

11. AWS S3 abort multipart upload
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/abort-mpu.html

12. EMQX MQTT retained message documentation
   https://docs.emqx.com/en/emqx/latest/messaging/mqtt-retained-message.html

13. EMQX MQTT core concepts
   https://docs.emqx.com/en/emqx/latest/messaging/mqtt-concepts.html

14. EMQX Cloud MQTT client development best practices
   https://docs.emqx.com/en/cloud/latest/best_practices/client_development.html

15. OWASP File Upload Cheat Sheet
   https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html

16. OWASP Web Security Testing Guide: malicious file upload testing
   https://owasp.org/www-project-web-security-testing-guide/v42/4-Web_Application_Security_Testing/10-Business_Logic_Testing/09-Test_Upload_of_Malicious_Files

17. OpenTelemetry semantic conventions
   https://opentelemetry.io/docs/concepts/semantic-conventions/

18. AWS S3 presigned URL usage and guardrails
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html

19. AWS S3 object integrity and checksum behavior
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html

20. AWS S3 CORS behavior
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/cors.html

21. AWS S3 conditional writes
   https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html

22. MinIO object locking and immutability
   https://docs.min.io/aistor/administration/object-locking-and-immutability/

23. MinIO server-side encryption
   https://docs.min.io/aistor/installation/kubernetes/server-side-encryption/

24. MinIO bucket replication
   https://docs.min.io/aistor/administration/replication/bucket-replication/

---


## 32. Definition of Done

The repository can be considered portfolio-ready when:

1. A reader can run the system locally with Docker Compose.
2. A reader can upload a multi-part file to MinIO using `uploadctl`.
3. A reader can interrupt the client and resume successfully.
4. A reader can pause an upload, resume it, reconcile storage state, and complete it.
5. A reader can see project, dataset, upload task, upload session, upload part, audit, and outbox metadata in PostgreSQL.
6. A reader can inspect MinIO and find the completed object under the expected project/dataset key namespace.
7. Permission tests prove that users see only allowed projects and cannot call hidden/forbidden actions.
8. Device tests prove that registered devices can trigger uploads and disabled/revoked devices cannot.
9. Dataset lifecycle tests prove soft delete, restore, download URL authorization, validation result persistence, and purge policy behavior.
10. Tests prove missing part handling, URL expiry recovery, duplicate completion, pause/resume, and abort idempotency.
11. Storage-governance tests or documented runbooks cover CORS, encryption/KMS, object-lock/legal-hold, quota, and restore reconciliation.
12. Security tests prove quarantined/rejected datasets are not downloadable and presigned URLs are redacted from logs/traces/audit/outbox.
13. The README explains why file bytes do not pass through the backend, EMQX/MQTT, or any control-plane service.
14. API docs are available through OpenAPI.
15. Logs, metrics, alerts, audit events, outbox behavior, and runbooks demonstrate operational thinking.
16. The repo clearly states it is production-oriented but not production-proven.

---


## 33. README Narrative

The README should frame the project like this:

```text
This repository implements a production-oriented large-file upload control plane for AI and robotics data ingestion. It uses S3-compatible multipart upload to allow clients to upload file parts directly to object storage while the backend controls authorization, presigned URL generation, session state, completion, abort, cleanup, and observability.

The design intentionally separates the control plane from the data plane: the API service and optional EMQX/MQTT adapter never receive large file bodies. This keeps backend bandwidth and memory usage bounded while allowing browsers, CLI tools, and industrial devices to upload large datasets directly to MinIO/S3 with resumability and parallelism.

The project also models the surrounding industrial data platform concerns: tenants, projects, datasets, upload tasks, device credentials, resource-scoped permissions, storage policies, validation, recycle/restore/purge lifecycle, audit events, and a transactional outbox for recoverable event delivery.
```

Avoid framing it as:

```text
A simple file upload demo.
```

Correct framing:

```text
A production-oriented upload control plane for resumable multipart ingestion.
```

---


## 34. Codex Implementation Rules

Codex must follow these rules:

1. Do not create endpoints that accept file bytes unless explicitly requested later.
2. Do not give the client MinIO credentials.
3. Do not bypass the storage adapter from application services.
4. Do not assume ETag is a full-file MD5 checksum.
5. Do not complete uploads based only on DB ack rows.
6. Always validate tenant ownership.
7. Always keep state transitions explicit and test-covered.
8. Add tests with every new feature.
9. Do not silently change API response shapes after they are introduced.
10. Prefer small, well-named services over one large upload service class.
11. Keep domain logic independent from FastAPI, SQLAlchemy, and boto3.
12. Avoid high-cardinality metric labels.
13. Mask secrets and presigned URL query strings in logs.
14. Make local development deterministic.
15. Treat permission codes and `permission_grants` as the authorization source of truth.
16. Re-evaluate effective permissions on every control-plane request.
17. Record audit events for permission, device credential, download, delete, restore, and purge actions.
18. Insert outbox events in the same transaction as the domain change they describe.
19. Keep Go and MQTT components optional until Python backend, CLI, authorization, and outbox behavior are correct.

---


## 35. Recommended First Codex Task

The first implementation task should be:

```text
Create the repository scaffold for upload-control-plane with FastAPI, PostgreSQL, MinIO Docker Compose, pyproject.toml, ruff, pytest, a health endpoint, configuration loading, and a Makefile. Do not implement upload APIs yet.
```

Acceptance criteria for the first task:

```bash
make dev-up
make test
curl http://localhost:8000/healthz
```

Expected health response:

```json
{
  "status": "ok",
  "service": "upload-control-plane"
}
```

---


## 36. Recommended Second Codex Task

The second task should be:

```text
Implement domain-level part size selection, part range calculation, upload session state machine, and unit tests. Do not add FastAPI upload endpoints yet.
```

Acceptance criteria:

- `choose_part_size` handles explicit and automatic part sizes.
- `get_part_range` handles first, middle, and last parts.
- State transition rules reject invalid transitions.
- Unit tests cover boundary cases around 5 MiB, 64 MiB, 5 GiB, and 10,000 parts.

---


## 37. Final Design Reminder

The core insight of this project is:

```text
Industrial-grade large-file upload is not about making the backend better at receiving huge files.
It is about preventing the backend from receiving huge files at all.

The backend controls authorization and lifecycle.
Object storage handles the data plane.
The client handles slicing, retries, and resume.
```

All implementation decisions must preserve that separation.
