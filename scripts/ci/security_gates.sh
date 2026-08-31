#!/usr/bin/env bash
# INT-019 — `make security`: the full gate set, locally, in the order
# .github/workflows/security.yml runs it (CLAUDE.md invariant 14; files/10 §8).
#
# ONE LIST, TWO RUNNERS. The GATES array below is the list, and
# tests/ci/test_security_gates.py asserts the workflow declares exactly the
# same ids in the same order. That is what "make security runs the same list
# locally" means as a property rather than as a claim in a README.
#
# NOTHING SKIPS. Every gate ends in PASS or FAIL. A scanner that is not
# installed is a FAIL with its install line — not a skip, not a warning, and
# never `|| true`. A gate that silently no-ops when its tool is missing is
# worse than no gate, because it reports green. Disabling one is on CLAUDE.md's
# stop-and-ask list, so there is deliberately no flag here that turns one off.
#
# The run does not stop at the first failure: every gate runs, and the summary
# at the end says which ones failed and why. Fail-fast would hide the state of
# the other fourteen, and the state of all fifteen is the thing a human needs.
#
# usage: security_gates.sh [gate-id ...]   (default: all of them, in order)
set -uo pipefail
cd "$(dirname "$0")/../.."

GATES=(
  "gitleaks"
  "semgrep"
  "bandit"
  "eslint-security"
  "trivy-fs"
  "trivy-image"
  "trivy-iac"
  "osv-scanner"
  "checkov"
  "licences"
  "sbom"
  "schemathesis"
  "phi-scan"
  "claims-scan"
  "ci-policy"
)

# Pins. A scanner is a dependency like any other: an unpinned one changes its
# verdict without a diff. The workflow pins the same versions.
SEMGREP_VERSION="1.86.0"
BANDIT_VERSION="1.9.4"
CHECKOV_VERSION="3.2.457"
SCHEMATHESIS_VERSION="4.4.2"
GITLEAKS_MIN="8.18"
TRIVY_MIN="0.50"
OSV_MIN="1.9"
SYFT_MIN="1.0"

SBOM_OUT="${SBOM_OUT:-.cache/intake-sbom.spdx.json}"
UVX="uvx --python 3.12"

statuses=()
reasons=()

log() { printf '\n\033[1m=== gate: %s\033[0m\n' "$1"; }

require_tool() {
  # require_tool <binary> <install line>
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is not installed — this gate FAILS closed rather than skipping."
    echo "install: $2"
    return 1
  fi
  return 0
}

# --- the gates ------------------------------------------------------------------------

gate_gitleaks() {
  require_tool gitleaks "https://github.com/gitleaks/gitleaks/releases (>= $GITLEAKS_MIN)" || return 1
  gitleaks dir . --no-banner --redact --exit-code 1 --config scripts/ci/gitleaks.toml
}

gate_semgrep() {
  require_tool uvx "https://docs.astral.sh/uv/ (uv ships uvx)" || return 1
  $UVX --with 'setuptools<81' "semgrep@$SEMGREP_VERSION" scan \
    --config p/ci --error --metrics=off \
    --exclude files --exclude node_modules --exclude .cache \
    --exclude pnpm-workspace.yaml --exclude pyproject.toml
}

gate_bandit() {
  # Baseline, not suppression. Four B314 findings (xml.etree on trusted, schema-
  # constrained input in ehrbase, the SIEM rule loader and the openEHR binding)
  # predate this gate and live in packages/ that INT-019 does not own. bandit's
  # own --baseline reports only what is NEW, so the four are recorded in a file
  # a human has to change on purpose, and a fifth fails the build. The baseline
  # is regenerated with:
  #   uvx bandit@$BANDIT_VERSION -r packages services scripts -ll -ii -q \
  #     --exclude '**/node_modules/**,**/tests/**,**/.venv/**' \
  #     -f json -o scripts/ci/bandit_baseline.json
  require_tool uvx "https://docs.astral.sh/uv/ (uv ships uvx)" || return 1
  if [[ ! -f scripts/ci/bandit_baseline.json ]]; then
    echo "scripts/ci/bandit_baseline.json is missing — the gate cannot tell a new"
    echo "finding from an old one, so it does not pass. Regenerate it (see above)."
    return 1
  fi
  $UVX "bandit@$BANDIT_VERSION" -r packages services scripts -ll -ii -q \
    --exclude '**/node_modules/**,**/tests/**,**/.venv/**' \
    -b scripts/ci/bandit_baseline.json
}

gate_eslint_security() {
  scripts/ci/eslint_security.sh
}

gate_trivy_fs() {
  require_tool trivy "https://github.com/aquasecurity/trivy/releases (>= $TRIVY_MIN)" || return 1
  trivy fs . --scanners vuln,secret --severity CRITICAL,HIGH --exit-code 1 \
    --skip-dirs node_modules --skip-dirs .cache --skip-dirs .venv --no-progress
}

gate_trivy_image() {
  # There is no container image in this repository yet: no Dockerfile, and
  # infra/ composes upstream images only. The gate is armed rather than
  # assumed — the moment a Dockerfile is committed it requires trivy AND a
  # working container runtime, and fails without them.
  local dockerfiles
  dockerfiles=$(git ls-files -- '**/Dockerfile' '**/Dockerfile.*' 'Dockerfile' 'Dockerfile.*')
  if [[ -z "$dockerfiles" ]]; then
    echo "no Dockerfile is tracked — this repository builds no image, so there is"
    echo "no image to scan. The gate stays wired: it requires trivy and a container"
    echo "runtime the moment one is committed."
    return 0
  fi
  echo "images to scan:"
  printf '%s\n' "$dockerfiles"
  require_tool trivy "https://github.com/aquasecurity/trivy/releases (>= $TRIVY_MIN)" || return 1
  require_tool docker "https://docs.docker.com/engine/install/" || return 1
  local df image
  while IFS= read -r df; do
    image="intake-security-scan:$(printf '%s' "$df" | tr '/.' '--')"
    docker build -f "$df" -t "$image" "$(dirname "$df")" || return 1
    trivy image "$image" --severity CRITICAL,HIGH --exit-code 1 --no-progress || return 1
  done <<< "$dockerfiles"
}

gate_trivy_iac() {
  require_tool trivy "https://github.com/aquasecurity/trivy/releases (>= $TRIVY_MIN)" || return 1
  trivy config infra --severity CRITICAL,HIGH --exit-code 1 --no-progress
}

gate_osv_scanner() {
  require_tool osv-scanner "https://github.com/google/osv-scanner/releases (>= $OSV_MIN)" || return 1
  local report status
  report=$(mktemp)
  osv-scanner scan source --format json --lockfile uv.lock --lockfile pnpm-lock.yaml > "$report" 2>&1
  status=$?
  # osv-scanner exits 1 when it finds anything and >1 when it could not run.
  # Only the first is a report to grade; the second is the gate failing closed.
  if [[ $status -gt 1 ]]; then
    echo "osv-scanner could not complete (exit $status) — the vulnerability database"
    echo "was not reachable, so this gate has no result and does not pass."
    tail -5 "$report"
    rm -f "$report"
    return 1
  fi
  python3 scripts/ci/osv_severity_gate.py < "$report"
  status=$?
  rm -f "$report"
  return $status
}

gate_checkov() {
  # Same baseline discipline as bandit. Three findings — CKV_SECRET_4/6 on the
  # documented dev-only credentials in the observability compose profile and the
  # MinIO replication fixture — predate this gate and live in infra/, which
  # INT-019 does not own. Deployed instances take those credentials from
  # OpenBao (files/10 §8). Regenerate by copying infra/ to a scratch directory
  # and running `checkov --directory infra --create-baseline`, then moving the
  # produced .checkov.baseline here: a new misconfiguration still fails.
  require_tool uvx "https://docs.astral.sh/uv/ (uv ships uvx)" || return 1
  if [[ ! -f scripts/ci/checkov_baseline.json ]]; then
    echo "scripts/ci/checkov_baseline.json is missing — the gate cannot tell a new"
    echo "finding from an old one, so it does not pass. Regenerate it (see above)."
    return 1
  fi
  $UVX "checkov@$CHECKOV_VERSION" --directory infra \
    --baseline scripts/ci/checkov_baseline.json --quiet --compact
}

gate_licences() {
  require_tool uv "https://docs.astral.sh/uv/" || return 1
  uv run --no-sync python scripts/ci/check_licenses.py
}

gate_sbom() {
  require_tool syft "https://github.com/anchore/syft/releases (>= $SYFT_MIN)" || return 1
  mkdir -p "$(dirname "$SBOM_OUT")"
  syft scan dir:. --exclude './node_modules/**' --exclude './.venv/**' --exclude './.cache/**' \
    -o "spdx-json=$SBOM_OUT" -q || return 1
  python3 -c "
import json, sys
with open('$SBOM_OUT', encoding='utf-8') as fh:
    doc = json.load(fh)
packages = doc.get('packages', [])
if not packages:
    print('the SBOM lists no package — an empty SBOM is not an SBOM')
    sys.exit(1)
print(f'SBOM: {len(packages)} packages -> $SBOM_OUT')
"
}

gate_schemathesis() {
  require_tool uvx "https://docs.astral.sh/uv/ (uv ships uvx)" || return 1
  local schema="packages/clinical-schemas/schemas/openapi.json"
  if [[ ! -f "$schema" ]]; then
    echo "$schema is missing — run: make schemas-codegen"
    return 1
  fi
  if [[ -z "${INTAKE_FUZZ_BASE_URL:-}" ]]; then
    echo "INTAKE_FUZZ_BASE_URL is unset, so there is no API to fuzz — this gate"
    echo "FAILS closed rather than passing on an unfuzzed API."
    echo "Schemathesis generates requests and grades responses; a schema on its own"
    echo "grades nothing. Bring the API up and point the gate at it:"
    echo "  make dev  &&  uv run uvicorn intake_api.app:create_app --factory --port 8000"
    echo "  INTAKE_FUZZ_BASE_URL=http://127.0.0.1:8000 make security"
    echo "In CI the api-fuzz job does exactly that (see .github/workflows/security.yml)."
    return 1
  fi
  $UVX "schemathesis@$SCHEMATHESIS_VERSION" run "$schema" \
    --url "$INTAKE_FUZZ_BASE_URL" \
    --checks all \
    --max-examples "${INTAKE_FUZZ_EXAMPLES:-25}" \
    --report junit --report-dir .cache/schemathesis
}

gate_phi_scan() {
  scripts/ci/phi_scan.sh
}

gate_claims_scan() {
  scripts/ci/claims_scan.sh
}

gate_ci_policy() {
  # INT-206's no-PHI-in-CI policy over the six surfaces (fixtures, env, logs,
  # artefacts, cache, runners). `make security` calls it rather than
  # reimplementing it — the Makefile comment on `ci-policy` says exactly that.
  #
  # --scan-environment reads the RUNNER's own variables, which is a CI surface:
  # on a developer machine it reads that developer's shell, where an e-mail
  # address in GIT_CONFIG_VALUE or an editor variable is not a CI leak. So the
  # environment surface is scanned when CI is set, and the other five surfaces
  # — fixtures, logs, artefacts, cache, runners — are scanned everywhere. This
  # is a surface that does not exist locally, not a gate that skips locally.
  require_tool uv "https://docs.astral.sh/uv/" || return 1
  if [[ -n "${CI:-}" ]]; then
    uv run --no-sync python -m intake_platform.ci --scan-environment
  else
    echo "not running under CI: the runner-environment surface does not exist here;"
    echo "the other five surfaces are scanned. CI=1 adds --scan-environment."
    uv run --no-sync python -m intake_platform.ci
  fi
}

# --- runner ----------------------------------------------------------------------------

run_gate() {
  local gate="$1" fn="gate_${1//-/_}"
  log "$gate"
  if ! declare -f "$fn" >/dev/null; then
    statuses+=("FAIL")
    reasons+=("$gate: no implementation — the gate list and the gate bodies disagree")
    echo "no implementation for gate $gate"
    return 1
  fi
  local output status
  output=$("$fn" 2>&1)
  status=$?
  printf '%s\n' "$output"
  if [[ $status -eq 0 ]]; then
    statuses+=("PASS")
    reasons+=("")
  else
    statuses+=("FAIL")
    reasons+=("$(printf '%s' "$output" | tail -3 | tr '\n' ' ')")
  fi
  return $status
}

selected=("${GATES[@]}")
if [[ $# -gt 0 ]]; then
  selected=("$@")
fi

failed=0
for gate in "${selected[@]}"; do
  run_gate "$gate" || failed=$((failed + 1))
done

printf '\n\033[1m=== make security — %d gate(s)\033[0m\n' "${#selected[@]}"
for i in "${!selected[@]}"; do
  printf '%-6s %s\n' "${statuses[$i]}" "${selected[$i]}"
  if [[ "${statuses[$i]}" == "FAIL" ]]; then
    printf '       %s\n' "${reasons[$i]}"
  fi
done

if [[ $failed -gt 0 ]]; then
  printf '\n%d of %d gate(s) FAILED. A gate that cannot run does not pass.\n' \
    "$failed" "${#selected[@]}"
  exit 1
fi
printf '\nall %d gate(s) PASS\n' "${#selected[@]}"
