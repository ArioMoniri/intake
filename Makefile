# INTAKE — the Makefile is the single entry point (CLAUDE.md §Commands).
# Targets appear here when the issue that builds them lands; CLAUDE.md describes
# the full end-state surface. check-golden/check-integration join the check
# fan-out with INT-041/INT-059 and the compose integration suite.

COMPOSE := docker compose -f infra/docker-compose.dev.yml

.PHONY: setup check check-py check-ts check-integration dev dev-down clean backlog-status backlog-sync backlog-render deid-model slo-report release-gate schemas-codegen

setup:
	corepack enable pnpm 2>/dev/null || true
	pnpm install
	uv sync --all-packages
	uv run pre-commit install --install-hooks
	uv run pre-commit install --hook-type commit-msg

check: check-py check-ts

check-integration:
	docker compose -f infra/docker-compose.dev.yml --profile clamav up -d --wait postgres openbao minio clamav
	POSTGRES_DB=$${POSTGRES_DB:-intake} bash scripts/security/openbao_dev_setup.sh
	OPENBAO_TOKEN=$${OPENBAO_TOKEN:-intake-dev-root} uv run pytest -m integration --no-header -q -p no:cacheprovider -o addopts=""

check-py:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy --strict packages/intake_platform/src packages/clinical-schemas/src packages/protocols/src services/api/src
	uv run pytest --cov=packages/intake_platform/src --cov=services/api/src --cov-branch --cov-fail-under=85
	uv run pytest tests/schemas --cov=packages/clinical-schemas/src --cov-branch --cov-fail-under=90 -q -o addopts=""
	uv run pytest tests/protocols tests/safety --cov=packages/protocols/src --cov-branch --cov-fail-under=95 -q -o addopts=""
	uv run pytest tests/safety --cov=packages/protocols/src/protocols/triage --cov-branch --cov-fail-under=100 -q -o addopts=""

check-ts:
	pnpm -r lint
	pnpm -r typecheck
	pnpm -r test

# INT-031: regenerate the committed schema exports (OpenAPI bundle, per-event
# JSON Schemas, generated TS types). tests/schemas/test_roundtrip.py fails
# `make check` whenever these are stale.
schemas-codegen:
	uv run python -m clinical_schemas.codegen

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

# INT-021: declared SLO table from docs/slo/ + observability/metrics_catalog.yaml.
# Dry mode only — live attainment arrives with the observability deploy (INT-023).
slo-report:
	uv run python scripts/observability/slo_report.py

backlog-status:
	uv run python scripts/backlog/backlog_status.py

backlog-sync:
	uv run python scripts/backlog/sync_issues.py

backlog-render:
	uv run python scripts/backlog/render_backlog.py

clean:
	rm -rf node_modules packages/*/node_modules .venv .pytest_cache .ruff_cache

# INT-022: sweep the synthetic probes once, then run the release gate over the
# self-hosting registry. Blocks (exit 1) while any enabled phi_path component
# lacks a healthy self-hosted fallback — which today is the true state.
PROBE_RESULTS_FILE ?= .cache/probe-results.json

release-gate:
	uv run python -m intake_probes.runner --once --out $(PROBE_RESULTS_FILE)
	uv run python scripts/release/release_gate.py --registry observability/registry.yaml --results $(PROBE_RESULTS_FILE)

# INT-023: local observability stack — compose profile `obs` (Prometheus,
# Grafana, Loki, Tempo, OTel collector, Unleash, Keycloak, GlitchTip).
# Dev tier only: loopback ports, dev-only credentials overridable via env.
# CI never boots it; tests/observability/test_obs_compose.py validates the
# file statically.
OBS_COMPOSE := docker compose -f infra/docker-compose.obs.yml --profile obs

.PHONY: obs obs-down

obs:
	$(OBS_COMPOSE) up -d --build --wait

obs-down:
	$(OBS_COMPOSE) down
