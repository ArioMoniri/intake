# INTAKE — the Makefile is the single entry point (CLAUDE.md §Commands).
# Targets appear here when the issue that builds them lands; CLAUDE.md describes
# the full end-state surface. check-golden/check-integration join the check
# fan-out with INT-041/INT-059 and the compose integration suite.

COMPOSE := docker compose -f infra/docker-compose.dev.yml

.PHONY: setup check check-py check-ts check-integration dev dev-down clean backlog-status backlog-sync backlog-render deid-model slo-report release-gate schemas-codegen coverage-matrix protocols-compile clips chaos load safety

setup:
	corepack enable pnpm 2>/dev/null || true
	pnpm install
	uv sync --all-packages
	uv run pre-commit install --install-hooks
	uv run pre-commit install --hook-type commit-msg

check: check-py check-ts

check-integration:
	docker compose -f infra/docker-compose.dev.yml --profile clamav up -d --wait postgres openbao minio clamav hapi
	POSTGRES_DB=$${POSTGRES_DB:-intake} bash scripts/security/openbao_dev_setup.sh
	OPENBAO_TOKEN=$${OPENBAO_TOKEN:-intake-dev-root} uv run pytest -m integration --no-header -q -p no:cacheprovider -o addopts=""

check-py:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy --strict packages/intake_platform/src packages/clinical-schemas/src packages/protocols/src packages/voice-clips/src services/api/src services/voice-runtime/src services/metrics/src
	uv run pytest --cov=packages/intake_platform/src --cov=services/api/src --cov-branch --cov-fail-under=85
	uv run pytest tests/schemas --cov=packages/clinical-schemas/src --cov-branch --cov-fail-under=90 -q -o addopts=""
	uv run pytest tests/protocols tests/safety --cov=packages/protocols/src --cov-branch --cov-fail-under=95 -q -o addopts=""
	uv run pytest tests/safety --cov=packages/protocols/src/protocols/triage --cov-branch --cov-fail-under=100 -q -o addopts=""
	uv run pytest tests/voice --cov=packages/voice-clips/src --cov-branch --cov-fail-under=95 -q -o addopts=""
	uv run pytest tests/voice --cov=services/voice-runtime/src --cov-branch --cov-fail-under=90 -q -o addopts=""
	uv run pytest tests/experience --cov=services/metrics/src --cov-branch --cov-fail-under=90 -q -o addopts=""

# INT-059: the safety fan-out CLAUDE.md names - triage goldens (incl. the
# mutation harness) and the PolicyGuard suite, at their own coverage floors.
# check-py runs these lanes too; this target exists so a change under
# packages/protocols can be cleared without the full fan-out.
safety:
	uv run pytest tests/safety --cov=packages/protocols/src/protocols/triage --cov-branch --cov-fail-under=100 -q -o addopts=""
	uv run python scripts/safety/triage_mutation_report.py
	uv run pytest tests/voice --cov=services/voice-runtime/src --cov-branch --cov-fail-under=90 -q -o addopts=""

check-ts:
	pnpm -r lint
	pnpm -r typecheck
	pnpm -r test

# INT-031: regenerate the committed schema exports (OpenAPI bundle, per-event
# JSON Schemas, generated TS types). tests/schemas/test_roundtrip.py fails
# `make check` whenever these are stale.
schemas-codegen:
	uv run python -m clinical_schemas.codegen

# INT-042: `protocols coverage` — the branch × resolution matrix over
# packages/protocols/taxonomy/branches.yaml (files/09 §6 `taxonomy_coverage`;
# CLAUDE.md invariant 13). Unstrict today: zero packs exist, so the matrix is
# honestly all-MISSING. CI flips to `--strict` once the nine cluster packs
# land (files/09 §2 P1) — then a branch resolving to nothing fails the build.
coverage-matrix:
	uv run protocols coverage

# INT-041: the deterministic emit (files/03 §6 outputs a-e) for one pack.
# PACK and VOICE are required and have no defaults: VOICE keys the clip cache
# (files/03 §4.9.1 row 10 `sha256(text_tr, voice_id)`) and a default would be
# a value chosen once by an engineer for every future build. Includes the tr
# normalisation round-trip gate (CLAUDE.md invariant 22). Refuses on today's
# tree — every pack is L0 and the life-threat sign-off is empty (HB-C1).
protocols-compile:
	@test -n "$(PACK)" && test -n "$(VOICE)" || { echo "usage: make protocols-compile PACK=<pack_id> VOICE=<voice_id>"; exit 2; }
	uv run protocols compile --pack $(PACK) --voice $(VOICE)

# INT-060: pre-synthesise the compiled clip manifests for one voice into the
# MinIO clip cache (files/03 §4.9.1 row 10, keyed sha256(text_tr, voice_id)).
# VOICE is required and has no default, like protocols-compile: the key is
# per-voice, so a default would silently build somebody else's cache. The TTS
# source is also never guessed — set exactly one of INTAKE_TTS_ENDPOINT (a
# self-hosted lane) or INTAKE_TTS_RECORDED_DIR (recorded responses; the CI and
# no-GPU dev path). Refuses on today's tree: no pack compiles yet (HB-C1).
clips:
	@test -n "$(VOICE)" || { echo "usage: make clips VOICE=<voice_id>"; exit 2; }
	uv run intake-clips --voice $(VOICE)

# INT-238: the clamav profile belongs to `dev`, not only to
# check-integration. Document ingest fails closed without a scanner, so a dev
# stack without clamd cannot add a record at all; the API wires ClamAvScanner
# whenever INTAKE_CLAMD_HOST is set (see env.example).
dev:
	$(COMPOSE) --profile clamav up -d --wait

dev-down:
	$(COMPOSE) --profile clamav down

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

# INT-175: self-hosted Langfuse — its own compose file (six containers,
# including a ClickHouse of its own), profile `langfuse`. Secrets come from
# OpenBao via scripts/observability/langfuse_secrets.sh; nothing is defaulted
# in the compose file and nothing is added to env.example (invariant 14).
# CI never boots it; tests/observability/test_langfuse_gate.py validates the
# file statically. HB-I1/HB-I2 block booting it on the owner's laptop.
#
# What reaches this stack is ids, enums and counts and nothing else — the
# boundary is intake_platform.observability.spans, and HB-L6 is why.
LANGFUSE_COMPOSE := docker compose -f infra/docker-compose.langfuse.yml --profile langfuse

.PHONY: langfuse langfuse-down langfuse-seed langfuse-experiment

langfuse-seed:
	scripts/observability/langfuse_secrets.sh --seed

langfuse:
	eval "$$(scripts/observability/langfuse_secrets.sh --export)" && $(LANGFUSE_COMPOSE) up -d --wait

langfuse-down:
	$(LANGFUSE_COMPOSE) down

# The recorded-experiment gate (acceptance: "CI job runs recorded simulator
# experiment and gates on scores"). No model is called: the run file is
# recorded structural output and the gate is arithmetic over it, so this is
# safe in CI, which never calls a live API. The fixture's provenance —
# hand-authored in the simulator's shape, because packages/llm-evals does not
# exist yet — is recorded in docs/evidence/INT-175.md, not glossed.
langfuse-experiment:
	uv run python scripts/observability/langfuse_experiment.py \
	  --run tests/fixtures/experiments/extraction_recorded_run.jsonl \
	  --thresholds observability/experiment_thresholds.yaml

# INT-024: chaos harness (intake_platform.chaos). One first-class experiment
# today: vendor_kill — kill the mock vendor adapter, assert the typed
# fallback decision lands within 2 s and the resilience counters move.
# files/10 §7 schedules these monthly in STAGING; no staging environment
# exists yet, so this target is the standalone entry point and the scheduled
# job arrives with the staging environment (docs/evidence/INT-024.md).
chaos:
	@test -n "$(EXPERIMENT)" || { echo "usage: make chaos EXPERIMENT=vendor_kill"; exit 2; }
	uv run python -m intake_platform.chaos --experiment $(EXPERIMENT)

# INT-024: k6 API smoke against a locally running services/api instance.
# BASE_URL overrides the target (default http://127.0.0.1:8000); export
# INTAKE_DEV_TOKEN_PATIENT to exercise the authed /v1 happy path. The CI job
# ("staging profile") is deferred with the staging environment — the script
# and this target are the real, runnable pieces today.
load:
	@command -v k6 >/dev/null || { echo "k6 is not installed (brew install k6)"; exit 2; }
	k6 run -e BASE_URL=$${BASE_URL:-http://127.0.0.1:8000} scripts/load/k6-smoke.js

# INT-202: backups — pgBackRest PITR (encrypted repository), MinIO replication
# to the second location, and the restore drill. files/10 §8 schedules the
# drill quarterly; `backup-drill-ci` is what that scheduled job calls.
#
# Only `backup-drill-dry` runs on this host. The real drill stands up a second
# Postgres, a second object store and a restore target, which needs more disk
# and more container memory than HB-I1/HB-I2 record as available — the script
# refuses rather than shrinking the drill to fit.
.PHONY: backup-config-check backup-drill-dry backup-drill backup-drill-ci

backup-config-check:
	uv run pytest tests/infra -q -o addopts=""

backup-drill-dry:
	scripts/backup/restore_drill.sh --dry-run

backup-drill:
	scripts/backup/restore_drill.sh --run

backup-drill-ci: backup-config-check
	scripts/backup/restore_drill.sh --run
