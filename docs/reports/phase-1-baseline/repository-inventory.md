# Repository Inventory and Baseline Structural Metrics

Status: active

## Scope

This report records Phase 1 Task P1-02 baseline inventory and structural metrics for the current repository state. It is intentionally limited to inventory and numeric metrics. It does not interpret hotspots deeply, recommend refactors, or change production code.

## Method

- Generated at: `2026-06-26T09:13:33+00:00`
- Repository root: `D:/upload-control-plane`
- Branch: `agentic-standard/phase-1-baseline`
- HEAD: `c021dca8122f34b4c5be15d7d1904e47d989dd13`
- File inventory command: `git ls-files --cached --others --exclude-standard`
- Included scope: tracked files plus non-ignored untracked files in the working tree.
- Excluded scope: ignored files such as `.git` internals, caches, virtualenvs, and build outputs.
- Python LOC definition: physical lines per `.py` file, decoded as UTF-8 with replacement; blank and comment lines included.
- Directory depth definition: for files under `src/`, `tests/`, and `docs/`, depth is the number of directories between that root and the file parent. Files directly under the root have depth `0`.

Current short git status at collection time:

```text
 A docs/reports/phase-1-baseline/README.md
 A docs/reports/phase-1-baseline/git-boundary.md
?? docs/reports/phase-1-baseline/repository-inventory.md
?? docs/reports/phase-1-baseline/repository-metrics.json
```

## Repository Structure Summary

Total inventoried files: **277**

| Top-level path | Files | Extensions |
| --- | --- | --- |
| docs/ | 148 | .json: 1, .md: 147 |
| src/ | 52 | .py: 52 |
| tests/ | 36 | .py: 36 |
| tools/ | 15 | .css: 1, .html: 1, .json: 3, .md: 1, .ts: 9 |
| migrations/ | 7 | .py: 7 |
| scripts/ | 5 | .ps1: 1, .py: 3, [no extension]: 1 |
| .github/ | 1 | .yml: 1 |
| .gitignore | 1 | [no extension]: 1 |
| .pre-commit-config.yaml | 1 | .yaml: 1 |
| .python-version | 1 | [no extension]: 1 |
| CONTRIBUTING.md | 1 | .md: 1 |
| Dockerfile | 1 | [no extension]: 1 |
| LICENSE | 1 | [no extension]: 1 |
| Makefile | 1 | [no extension]: 1 |
| README.md | 1 | .md: 1 |
| alembic.ini | 1 | .ini: 1 |
| docker-compose.yml | 1 | .yml: 1 |
| mkdocs.yml | 1 | .yml: 1 |
| pyproject.toml | 1 | .toml: 1 |
| uv.lock | 1 | .lock: 1 |

## Files by Extension

| Extension | Files |
| --- | --- |
| .css | 1 |
| .html | 1 |
| .ini | 1 |
| .json | 4 |
| .lock | 1 |
| .md | 150 |
| .ps1 | 1 |
| .py | 98 |
| .toml | 1 |
| .ts | 9 |
| .yaml | 1 |
| .yml | 3 |
| [no extension] | 6 |

## Python File Counts and LOC Statistics

Python files: **98**

| Metric | Value |
| --- | --- |
| Max Python LOC | 1597 |
| Median Python LOC | 118.00 |
| Mean Python LOC | 241.22 |

| Threshold | Python files |
| --- | --- |
| > 300 | 24 |
| > 500 | 14 |
| > 800 | 6 |
| > 1000 | 4 |

## Directory Depth Statistics

| Scope | Files | Max depth | Median depth | Mean depth | Files by depth |
| --- | --- | --- | --- | --- | --- |
| src/ | 52 | 3 | 2.00 | 2.08 | 1: 4, 2: 40, 3: 8 |
| tests/ | 36 | 1 | 1.00 | 0.89 | 0: 4, 1: 32 |
| docs/ | 148 | 3 | 3.00 | 2.69 | 0: 4, 1: 6, 2: 22, 3: 116 |

## Top 20 Largest Python Files

| Rank | Path | LOC |
| --- | --- | --- |
| 1 | src/upload_control_plane/application/upload_sessions.py | 1597 |
| 2 | src/upload_control_plane/infrastructure/db/models.py | 1159 |
| 3 | tests/api/test_upload_session_runtime_api.py | 1151 |
| 4 | src/upload_control_plane/application/datasets.py | 1036 |
| 5 | tests/api/test_upload_task_api_foundation.py | 949 |
| 6 | tests/api/test_dataset_lifecycle_api.py | 926 |
| 7 | src/upload_control_plane/api/datasets.py | 789 |
| 8 | src/upload_control_plane/observability.py | 760 |
| 9 | src/upload_control_plane/application/worker_lifecycle.py | 743 |
| 10 | src/upload_control_plane/api/upload_sessions.py | 689 |
| 11 | tests/application/test_worker_lifecycle.py | 669 |
| 12 | src/upload_control_plane/application/upload_tasks.py | 623 |
| 13 | tests/api/test_device_identity_api.py | 519 |
| 14 | tests/api/test_observability.py | 514 |
| 15 | src/upload_control_plane/application/devices.py | 487 |
| 16 | src/upload_control_plane/application/dataset_validation.py | 450 |
| 17 | src/upload_control_plane/infrastructure/storage/s3_minio.py | 430 |
| 18 | src/upload_control_plane/cli/uploader.py | 423 |
| 19 | tests/application/test_dataset_validation_worker.py | 416 |
| 20 | src/upload_control_plane/domain/storage.py | 409 |

## Machine-Readable Output

The matching machine-readable metrics file is `docs/reports/phase-1-baseline/repository-metrics.json`. It was generated from the same collection pass as this Markdown report and includes the full inventoried file list plus per-Python-file LOC records.

## Task Boundary

No production code was modified for this task. The generated deliverables are limited to:

- `docs/reports/phase-1-baseline/repository-inventory.md`
- `docs/reports/phase-1-baseline/repository-metrics.json`
