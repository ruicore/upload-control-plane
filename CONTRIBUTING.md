# Contributing

This repository is in bootstrap phase. Contributions should preserve the foundation for a production-oriented Python project without introducing upload application behavior before the relevant design slice is approved.

## Development Setup

Use Python 3.13 and `uv`.

```bash
uv sync --group dev --group docs
```

The repository uses dependency groups for local tooling:

- `dev` for Ruff, MyPy, Pytest, and pre-commit.
- `docs` for MkDocs Material.

## Pre-commit

Install hooks after syncing dependencies:

```bash
uv run pre-commit install
```

Run all hooks manually with:

```bash
uv run pre-commit run --all-files
```

## Quality Standards

Before opening a pull request, run:

```bash
uv run ruff check
uv run ruff format --check
uv run mypy src tests
uv run pytest
```

New implementation work should include focused tests. Domain behavior should remain independent from framework and infrastructure concerns unless a later architecture decision explicitly changes that boundary.

## Scope Discipline

Do not add upload APIs, database models, MinIO integration, workers, or client upload workflows as incidental changes. Those belong in future implementation phases with their own tests and review.
