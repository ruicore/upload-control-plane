param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("dev-up", "migrate", "seed-dev", "test", "dev-down")]
    [string] $Command
)

$ErrorActionPreference = "Stop"

$ApiHostPort = if ($env:API_HOST_PORT) { $env:API_HOST_PORT } else { "18080" }
$PostgresHostPort = if ($env:POSTGRES_HOST_PORT) { $env:POSTGRES_HOST_PORT } else { "25432" }
$MinioHostPort = if ($env:MINIO_HOST_PORT) { $env:MINIO_HOST_PORT } else { "19000" }
$MinioConsoleHostPort = if ($env:MINIO_CONSOLE_HOST_PORT) { $env:MINIO_CONSOLE_HOST_PORT } else { "19001" }

function Write-LocalRuntimeUrls {
    Write-Host "API:           http://localhost:$ApiHostPort"
    Write-Host "PostgreSQL:    localhost:$PostgresHostPort"
    Write-Host "MinIO S3 API:  http://localhost:$MinioHostPort"
    Write-Host "MinIO Console: http://localhost:$MinioConsoleHostPort"
}

switch ($Command) {
    "dev-up" {
        docker compose up --build -d
        Write-LocalRuntimeUrls
    }
    "migrate" {
        uv run python scripts/migrate.py
    }
    "seed-dev" {
        uv run python scripts/seed_dev.py
    }
    "test" {
        uv run ruff check
        uv run ruff format --check
        uv run mypy src tests
        uv run pytest
    }
    "dev-down" {
        docker compose down
    }
}
