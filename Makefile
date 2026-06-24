.PHONY: dev-up migrate seed-dev test dev-down

dev-up:
	docker compose up --build -d

migrate:
	uv run python scripts/migrate.py

seed-dev:
	uv run python scripts/seed_dev.py

test:
	uv run ruff check
	uv run ruff format --check
	uv run mypy src tests
	uv run pytest

dev-down:
	docker compose down
