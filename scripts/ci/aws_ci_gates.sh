#!/usr/bin/env bash
# INT-426 — what runs INSIDE the aws-ci containers (infra/ci/compose.yaml).
#
#   aws_ci_gates.sh prep    root, offline: unpack the bundle at $AWS_CI_SHA into
#                           /work, the de-id model into /work/.cache, and hand
#                           the work and cache volumes to the runner's uid
#   aws_ci_gates.sh gates   uid 10001: install, then every gate in order
#   aws_ci_gates.sh redact  uid 10001: scrub the log, then scan what is left
#
# The gate set is the acceptance list, in its order: edge-plugin, check-py,
# check-ts, check-integration, safety, security. Every gate runs even after one
# fails, so a red status names every red gate rather than the first.
#
# The full log goes to /out, never to stdout: stdout reaches the SSM command
# output, which keeps only gate verdicts. The raw log is deleted once the
# redacted copy exists; the redacted copy is withheld (deleted) when a scanner
# still matches it (CLAUDE.md invariant 6).
set -euo pipefail

GATES=(edge-plugin check-py check-ts check-integration safety security)
GATE_TIMEOUT_S=5400
RAW_LOG=/out/gates.raw.log
LOG_DIR=/out/log
LOG=${LOG_DIR}/aws-ci.log
RESULTS=/out/results.txt
DEID_TARBALL=/deid/deid-tr-ner-v1.tar.gz

say() { printf '[aws-ci] %s\n' "$*"; }

prep() {
  [[ ${AWS_CI_SHA:-} =~ ^[0-9a-f]{40}$ ]] || {
    say "prep: AWS_CI_SHA is not a 40-hex sha"
    exit 2
  }
  git config --global --add safe.directory /work
  git init -q /work
  git -C /work fetch -q /in/repo.bundle '+refs/intake-ci/*:refs/remotes/bundle/*'
  git -C /work -c advice.detachedHead=false checkout -q --detach "${AWS_CI_SHA}"
  [[ "$(git -C /work rev-parse HEAD)" == "${AWS_CI_SHA}" ]]
  if [[ -f ${DEID_TARBALL} ]]; then
    mkdir -p /work/.cache
    tar -xzf "${DEID_TARBALL}" -C /work/.cache
  else
    say "prep: no de-id model on the host; check-py's de-id tests will fail, not skip"
  fi
  chown -R 10001:10001 /work
  chown 10001:10001 /caches/uv /caches/pnpm /caches/trivy /caches/xdg
  say "prep: /work at ${AWS_CI_SHA:0:12}"
}

run_gate() {
  local name=$1 start rc
  shift
  start=$(date +%s)
  printf '\n===== aws-ci gate %s (%s) =====\n' "${name}" "$(date -u +%FT%TZ)" >>"${RAW_LOG}"
  set +e
  timeout --kill-after=60 "${GATE_TIMEOUT_S}" "$@" >>"${RAW_LOG}" 2>&1
  rc=$?
  set -e
  printf 'gate=%s rc=%d seconds=%d\n' "${name}" "${rc}" "$(($(date +%s) - start))" >>"${RESULTS}"
  say "${name}: rc=${rc} ($(($(date +%s) - start)) s)"
}

gates() {
  cd /work
  : >"${RESULTS}"
  : >"${RAW_LOG}"
  {
    printf 'aws-ci on %s\n' "$(git rev-parse HEAD)"
    printf 'uv %s | node %s | pnpm %s\n' "$(uv --version)" "$(node --version)" "$(pnpm --version)"
    printf '%s | gitleaks %s | osv-scanner %s | %s\n' "$(trivy --version | head -1)" "$(gitleaks version)" \
      "$(osv-scanner --version | head -1)" "$(syft version | grep -m1 '^Version')"
    printf 'docker (dind) %s\n' "$(docker version --format '{{.Server.Version}}')"
  } >>"${RAW_LOG}" 2>&1
  # what ci.yml does before its gates: the workspace venv and the pnpm tree
  run_gate setup-uv uv sync --all-packages
  run_gate setup-pnpm pnpm install --frozen-lockfile
  local gate
  for gate in "${GATES[@]}"; do
    run_gate "${gate}" make "${gate}"
  done
}

redact() {
  mkdir -p "${LOG_DIR}"
  local counts=/out/redactions.json clean=1 rc
  if [[ ! -f ${RAW_LOG} ]]; then
    say "redact: no raw log"
    printf 'log_clean=0\n' >/out/log_status
    return 0
  fi
  # The identifier detector is the repository's own (intake_platform.ci); no
  # venv means no detector, and no detector means the log is withheld.
  if [[ -x /work/.venv/bin/python ]] &&
    /work/.venv/bin/python /harness/scripts/ci/aws_ci_lib.py redact <"${RAW_LOG}" >"${LOG}" 2>"${counts}.err"; then
    tail -n 1 "${counts}.err" >"${counts}"
  else
    say "redact: the detector did not run; withholding the log"
    clean=0
  fi
  rm -f "${RAW_LOG}" "${counts}.err"
  if [[ ${clean} == 1 ]]; then
    local config=()
    [[ -f /work/.gitleaks.toml ]] && config=(--config /work/.gitleaks.toml)
    set +e
    gitleaks detect --no-git --source "${LOG_DIR}" "${config[@]}" --redact --no-banner \
      --report-format json --report-path /out/gitleaks-log.json >/out/gitleaks-log.txt 2>&1
    rc=$?
    set -e
    [[ ${rc} == 0 ]] || {
      say "redact: gitleaks still matches the scrubbed log (rc=${rc})"
      clean=0
    }
    set +e
    /work/scripts/ci/phi_scan.sh "${LOG}" >/out/phi-log.txt 2>&1
    rc=$?
    set -e
    [[ ${rc} == 0 ]] || {
      say "redact: the PHI scan still matches the scrubbed log (rc=${rc})"
      clean=0
    }
  fi
  if [[ ${clean} != 1 ]]; then
    rm -f "${LOG}"
  fi
  printf 'log_clean=%s\n' "${clean}" >/out/log_status
  say "redact: log_clean=${clean} counts=$(cat "${counts}" 2>/dev/null || printf '{}')"
}

# INT-429's reachability evidence: is node-forge in either production bundle?
# The export is the one INT-410's release-bundle spec runs (Metro dev=false,
# minified, no bytecode, offline), plus source maps. A module is in a bundle
# exactly when the map lists its path, so the map is the proof and the string
# search is the cross-check. The positive control is that the bundle is the
# real app: thousands of modules and the welcome screen's key.
expo_export() {
  cd /work
  : >"${RAW_LOG}"
  : >"${RESULTS}"
  : >/out/probe.txt
  run_gate setup-pnpm pnpm install --frozen-lockfile
  local platform out
  for platform in ios android; do
    out="/tmp/export-${platform}"
    run_gate "export-${platform}" env CI=1 NODE_ENV=production EAS_BUILD_PROFILE=production \
      EXPO_NO_TELEMETRY=1 EXPO_OFFLINE=1 \
      bash -c "cd apps/mobile && node_modules/.bin/expo export --platform ${platform} --no-bytecode --source-maps --output-dir ${out}"
    python3 - "${out}" "${platform}" <<'PY' >>/out/probe.txt || say "probe: ${platform} was not measured"
import json, pathlib, sys
root, platform = pathlib.Path(sys.argv[1]), sys.argv[2]
maps = [p for p in root.rglob("*.map") if "_expo/static/js" in str(p)]
bundles = [p for p in root.rglob("*") if p.is_file() and p.suffix in {".js", ".hbc"} and "_expo/static/js" in str(p)]
sources = [s for m in maps for s in json.loads(m.read_text(encoding="utf-8")).get("sources", [])]
forge_sources = [s for s in sources if "node-forge" in s or "code-signing-certificates" in s]
text = "".join(b.read_text(encoding="utf-8", errors="replace") for b in bundles)
# the other no-fix advisories of 2 Oct: braces (via micromatch) and
# http-cache-semantics (via cacheable-request); a module path names its package
def count(pkg):
    return sum(1 for s in sources if f"/node_modules/{pkg}/" in s or f"/{pkg}@" in s)
print(
    f"probe=expo-export platform={platform} bundles={len(bundles)} bytes={len(text)} "
    f"modules={len(sources)} forge_modules={len(forge_sources)} "
    f"forge_strings={text.count('node-forge') + text.count('forge.pki')} "
    f"braces_modules={count('braces')} micromatch_modules={count('micromatch')} "
    f"http_cache_semantics_modules={count('http-cache-semantics')} "
    f"real_app={int('welcome.phoneCta' in text)}"
)
PY
  done
  cat /out/probe.txt
}

case "${1:-}" in
  prep) prep ;;
  gates) gates ;;
  redact) redact ;;
  expo-export) expo_export ;;
  *)
    printf 'usage: %s prep|gates|redact|expo-export\n' "$0" >&2
    exit 2
    ;;
esac
