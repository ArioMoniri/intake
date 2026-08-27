# INTAKE — the Makefile is the single entry point (CLAUDE.md §Commands).
# Targets appear here when the issue that builds them lands; CLAUDE.md describes
# the full end-state surface. check-golden/check-integration join the check
# fan-out with INT-041/INT-059 and the compose integration suite.

COMPOSE := docker compose -f infra/docker-compose.dev.yml

.PHONY: setup check check-py check-ts dev dev-down clean backlog-status backlog-sync backlog-render deid-model

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

# INT-015: the pinned NER de-id artefact (names/addresses tier). Fetched from
# the repo's own release — no vendor — and verified against the pinned sha
# before extraction. Tests fail (not skip) without it.
DEID_MODEL_TAG := deid-tr-ner-v1
DEID_MODEL_SHA256 := d4faec572e37f81697fa25500230acc060fd8517443e226227a2b11630f5bcb9

deid-model:
	@test -f .cache/$(DEID_MODEL_TAG)/config.json && echo "deid model present" || ( \
	  mkdir -p .cache && \
	  gh release download $(DEID_MODEL_TAG) -R ArioMoniri/intake -p "$(DEID_MODEL_TAG).tar.gz" -O .cache/$(DEID_MODEL_TAG).tar.gz --clobber && \
	  uv run python -c "import hashlib,sys; h=hashlib.sha256(open('.cache/$(DEID_MODEL_TAG).tar.gz','rb').read()).hexdigest(); sys.exit(0 if h=='$(DEID_MODEL_SHA256)' else sys.stderr.write('sha mismatch: '+h) or 1)" && \
	  tar -xzf .cache/$(DEID_MODEL_TAG).tar.gz -C .cache && rm .cache/$(DEID_MODEL_TAG).tar.gz )

backlog-status:
	uv run python scripts/backlog/backlog_status.py

backlog-sync:
	uv run python scripts/backlog/sync_issues.py

backlog-render:
	uv run python scripts/backlog/render_backlog.py

clean:
	rm -rf node_modules packages/*/node_modules .venv .pytest_cache .ruff_cache
