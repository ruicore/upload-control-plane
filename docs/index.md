# Upload Control Plane

`upload-control-plane` is a production-oriented resumable multipart upload
control plane for research, media, and field-data ingestion.

The implementation provides a FastAPI control plane, PostgreSQL metadata and
lifecycle state, MinIO/S3-compatible multipart storage, direct-upload clients,
workers, validation, and operational signals. It is designed to production
standards but is not presented as production-proven.

Reader documentation:

- [Resumable Multipart Upload Control Plane PRD](prd/resumable-multipart-upload-control-plane/README.md)
- [Observability and Operations](operations-observability.md)
- [Upload Benchmark Guide](benchmarks.md)
