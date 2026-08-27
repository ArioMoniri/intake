# INTAKE — the Makefile is the single entry point (CLAUDE.md §Commands).
# Targets appear here when the issue that builds them lands; CLAUDE.md describes
# the full end-state surface. check-golden/check-integration join the check
# fan-out with INT-041/INT-059 and the compose integration suite.

COMPOSE := docker compose -f infra/docker-compose.dev.yml

.PHONY: setup check check-py check-ts dev dev-down clean

setup:
	corepack enable pnpm 2>/dev/null || true
	pnpm install
	uv sync --all-packages
	uv run pre-commit install --install-hooks
	uv run pre-commit install --hook-type commit-msg

check: check-py check-ts

check-py:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy --strict packages/intake_platform/src
	uv run pytest --cov=packages/intake_platform/src --cov-branch --cov-fail-under=85

check-ts:
	pnpm -r lint
	pnpm -r typecheck
	pnpm -r test

dev:
	$(COMPOSE) up -d --wait

dev-down:
	$(COMPOSE) down

clean:
	rm -rf node_modules packages/*/node_modules .venv .pytest_cache .ruff_cache
