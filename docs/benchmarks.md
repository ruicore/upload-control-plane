# Upload Benchmark Report Template

This benchmark exercises the production upload shape: control-plane API calls create the upload session and presigned part URLs, while file bytes go directly from the benchmark client to object storage with HTTP `PUT`. The backend API never receives file bytes, and the script does not use MinIO access keys or secret keys.

## Local prerequisites

- Docker Compose stack is running with PostgreSQL, API, and MinIO reachable from the host.
- Database migrations and dev seed data have been applied.
- The benchmark caller has a control-plane API key with upload permissions.
- The target project ID is known from the dev seed or local setup.
- MinIO CORS allows `PUT`, required signed headers, and the benchmark origin when using a browser. The Python benchmark performs direct HTTP `PUT` from the script.

## Safe commands

Dry-run with a tiny file, no API calls:

```powershell
uv run python scripts/benchmark_upload.py --dry-run --size 1MiB --file .benchmarks/tiny.bin
```

Run a small smoke benchmark:

```powershell
uv run python scripts/benchmark_upload.py `
  --api-url http://127.0.0.1:8000 `
  --api-key $env:UCP_API_KEY `
  --project-id $env:UCP_PROJECT_ID `
  --size 8MiB `
  --file .benchmarks/smoke-8mib.bin `
  --concurrency 4
```

Run the Phase 13 minimum local benchmark:

```powershell
uv run python scripts/benchmark_upload.py `
  --api-url http://127.0.0.1:8000 `
  --api-key $env:UCP_API_KEY `
  --project-id $env:UCP_PROJECT_ID `
  --size 512MiB `
  --file .benchmarks/benchmark-512mib.bin `
  --concurrency 8
```

By default the script creates a sparse local file with `truncate`, so it does not buffer 512 MiB in memory. Use `--materialize` only when you need non-sparse deterministic bytes; that mode writes in bounded chunks.

## Report fields

- Date/time:
- Git commit:
- Host OS and CPU:
- Docker/MinIO/PostgreSQL versions:
- API URL:
- File size:
- Part size:
- Concurrency:
- Presign expiry:
- Elapsed seconds:
- Throughput MiB/s:
- Session ID:
- API logs reviewed for signed query redaction:
- Storage logs reviewed:
- Notes:

## Expected evidence

- The script output includes `benchmark-complete`, session ID, elapsed seconds, and throughput.
- API logs show control-plane operations only: create task, presign, ack, complete.
- No backend route accepts `UploadFile`, `File`, request body streams, or download byte streams.
- No logs or reports include full presigned URL query strings such as signature, credential, token, `uploadId`, or `partNumber`.
