# Upload Control Plane

`upload-control-plane` is the foundation for a production-oriented resumable multipart upload control plane for AI, robotics, and industrial data ingestion.

The long-term architecture separates the control plane from the data plane. The future API service will manage authorization, upload lifecycle state, presigned URL issuance, completion, abort, cleanup, and observability. File bytes are intended to move directly from clients to S3-compatible object storage such as MinIO, so backend bandwidth and memory remain bounded.

## Repository Status

This repository is currently in the bootstrap phase.

It contains only project structure, development tooling, quality gates, and documentation scaffolding. It does not yet implement upload APIs, database models, object-storage integration, upload workflows, workers, or client functionality.

## Architecture Summary

The planned system will eventually support:

- Multipart and resumable uploads for large industrial datasets.
- Backend-controlled upload session lifecycle.
- Short-lived presigned URL workflows.
- Client-side file slicing and retry behavior.
- PostgreSQL-backed metadata and audit history.
- MinIO or S3-compatible object storage through an adapter boundary.
- Clear operational signals through logging, metrics, and tracing.

These capabilities are intentionally not implemented in the bootstrap repository.

## Development Principles

- Keep file bytes out of the backend control plane.
- Keep domain logic independent from web, database, and storage frameworks.
- Prefer explicit state transitions and retry-safe behavior.
- Treat object storage as authoritative for uploaded parts.
- Preserve strict typing and automated quality gates from the start.
- Add tests with future behavior changes.

## Local Development

Install dependencies with:

```bash
uv sync --group dev --group docs
```

Run quality gates with:

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src tests
uv run pytest
```

Install pre-commit hooks with:

```bash
uv run pre-commit install
```
