# INTAKE — the Makefile is the single entry point (CLAUDE.md §Commands).
# Targets appear here when the issue that builds them lands; CLAUDE.md describes
# the full end-state surface. check-golden/check-integration join the check
# fan-out with INT-041/INT-059 and the compose integration suite.

COMPOSE := docker compose -f infra/docker-compose.dev.yml

.PHONY: setup check check-py check-ts check-integration dev dev-down clean backlog-status backlog-sync backlog-render deid-model slo-report security safety

setup:
	corepack enable pnpm 2>/dev/null || true
	pnpm install
	uv sync --all-packages
	uv run pre-commit install --install-hooks
	uv run pre-commit install --hook-type commit-msg

check: check-py check-ts

check-integration:
	docker compose -f infra/docker-compose.dev.yml up -d --wait postgres openbao
	POSTGRES_DB=$${POSTGRES_DB:-intake} bash scripts/security/openbao_dev_setup.sh
	OPENBAO_TOKEN=$${OPENBAO_TOKEN:-intake-dev-root} uv run pytest -m integration --no-header -q -p no:cacheprovider -o addopts=""

check-py:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy --strict packages/intake_platform/src
	uv run pytest --cov=packages/intake_platform/src --cov-branch --cov-fail-under=85

check-ts:
	pnpm -r lint
	pnpm -r typecheck
	pnpm -r test

# INT-019 — the security gate set, mirroring .github/workflows/security.yml
# (content staged at scripts/ci/security_workflow.yml until the sanctioned
# ALLOW_PROTECTED=1 placement) tool for tool, pin for pin. Invariant 14: a
# tool absent from PATH FAILS with an install hint — silence is how gates
# rot. cosign/SLSA run in CI on tags only (nothing to sign locally yet).
# semgrep needs setuptools<81 (pkg_resources import; .pre-commit-config).
SEMGREP_VERSION := 1.86.0
BANDIT_VERSION := 1.9.4
CHECKOV_VERSION := 3.3.15
SBOM_OUT := .cache/intake-sbom.spdx.json

security:
	@echo "== [1/11] gitleaks (full history) =="
	@command -v gitleaks >/dev/null 2>&1 || { echo "FAIL: gitleaks not installed — brew install gitleaks (invariant 14: never skip a gate)"; exit 1; }
	gitleaks detect --source . --redact --no-banner
	@echo "== [2/11] semgrep (p/ci, metrics off) =="
	uvx --python 3.12 --with 'setuptools<81' semgrep@$(SEMGREP_VERSION) scan --config p/ci --error --metrics=off --exclude files --exclude pnpm-workspace.yaml --exclude pyproject.toml
	@echo "== [3/11] bandit (first-party python) =="
	uvx --python 3.12 bandit@$(BANDIT_VERSION) -r packages/intake_platform/src scripts -ll -ii
	@echo "== [4/11] trivy fs (fail on CRITICAL,HIGH) =="
	@command -v trivy >/dev/null 2>&1 || { echo "FAIL: trivy not installed — brew install trivy (invariant 14: never skip a gate)"; exit 1; }
	trivy fs --scanners vuln --severity CRITICAL,HIGH --exit-code 1 --skip-dirs node_modules .
	@echo "== [5/11] trivy config (IaC) =="
	trivy config --severity CRITICAL,HIGH --exit-code 1 infra
	@echo "== [6/11] osv-scanner (lockfiles) =="
	@command -v osv-scanner >/dev/null 2>&1 || { echo "FAIL: osv-scanner not installed — brew install osv-scanner (invariant 14: never skip a gate)"; exit 1; }
	osv-scanner scan source -r --skip-git .
	@echo "== [7/11] checkov (infra/) =="
	uvx --python 3.12 checkov@$(CHECKOV_VERSION) --directory infra --quiet --compact
	@echo "== [8/11] licence allow-list (check_licenses.py) =="
	uv run python scripts/ci/check_licenses.py
	@echo "== [9/11] syft SBOM (spdx-json) =="
	@command -v syft >/dev/null 2>&1 || { echo "FAIL: syft not installed — brew install syft (invariant 14: never skip a gate)"; exit 1; }
	syft scan dir:. -o spdx-json=$(SBOM_OUT)
	@echo "SBOM written to $(SBOM_OUT)"
	@echo "== [10/11] PHI-pattern scan (phi_scan.sh) =="
	scripts/ci/phi_scan.sh
	@echo "== [11/11] accuracy-claims scan (claims_scan.sh) =="
	scripts/ci/claims_scan.sh
	@echo "security: all gates green"

# INT-019 — the safety lane that exists today: security invariants + platform
# contract suites. Grows into triage goldens + PolicyGuard + runtime
# invariants as packages/protocols and the voice runtime land (their issues
# extend this target; CLAUDE.md §Commands describes the end state).
safety:
	uv run pytest tests/security tests/platform

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
