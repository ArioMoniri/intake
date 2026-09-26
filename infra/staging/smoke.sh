#!/usr/bin/env bash
# INT-345: smoke test for the deployed staging backend. It exits 0 only if
# every check passes.
#
# SYNTHETIC PATIENTS ONLY. The host is in us-east-1 (HB-I5, HB-L11).
#
# Run as root on the staging host, from infra/staging, after ./deploy.sh.
#
# Checks:
#   1. /healthz, /readyz, /metrics and /version answer 200 over public HTTPS.
#   2. /version names the deployed commit and a build time, never "dev".
#   3. The staging header is on every response, and plain HTTP redirects to
#      HTTPS.
#   4. Inside the api container: INTAKE_ENV is staging, no dev gate is set,
#      and the KEK mode is transit.
#   5. Restart test. A synthetic record is encrypted through the API's own
#      cipher. The api container is restarted and the record must decrypt.
#      Then OpenBao is restarted, which leaves it sealed, and unsealed, and
#      the record must decrypt again. A process-local KEK fails the first
#      step. A KEK that is not on persistent storage fails the second.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_root
require_tools
load_env
stamp_revision

failures=0
pass() { log "PASS $*"; }
fail() {
  log "FAIL $*"
  failures=$((failures + 1))
}

# 1. the four endpoints over public HTTPS
for path in /healthz /readyz /metrics /version; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --proto '=https' --tlsv1.2 --max-time 10 \
    "https://${STAGING_HOSTNAME}${path}" || true)
  if [[ $code == 200 ]]; then
    pass "https://${STAGING_HOSTNAME}${path} -> 200"
  else
    detail=""
    if [[ $path == /readyz ]]; then
      # check names and states only (invariant 6)
      detail=" body: $(curl -sS --proto '=https' --max-time 10 "https://${STAGING_HOSTNAME}${path}" || true)"
    fi
    fail "https://${STAGING_HOSTNAME}${path} -> ${code:-no answer}${detail}"
  fi
done

# 2. /version is the deployed commit, never "dev"
version_body=$(https_get /version || true)
if verdict=$(python3 -c '
import json, sys
try:
    v = json.load(sys.stdin)
except ValueError:
    print("not JSON"); sys.exit(1)
problems = []
if v.get("git_sha") != sys.argv[1]:
    problems.append("git_sha %r is not the deployed %s" % (v.get("git_sha"), sys.argv[1]))
if v.get("built_at") in (None, "", "dev"):
    problems.append("built_at is not stamped")
print("; ".join(problems) or "git_sha %s, built_at %s" % (v["git_sha"], v["built_at"]))
sys.exit(1 if problems else 0)
' "$INTAKE_GIT_SHA" <<<"$version_body"); then
  pass "/version: $verdict"
else
  fail "/version: $verdict"
fi

# 3. the staging header, and HTTP -> HTTPS
if curl -sS -o /dev/null -D - --proto '=https' --max-time 10 "https://${STAGING_HOSTNAME}/healthz" |
  tr -d '\r' | grep -qi '^x-intake-environment: staging-synthetic-only$'; then
  pass "X-Intake-Environment: staging-synthetic-only"
else
  fail "the staging header is missing"
fi
redirect=$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' --max-time 10 \
  "http://${STAGING_HOSTNAME}/healthz" || true)
if [[ $redirect =~ ^30[178]\ https:// ]]; then
  pass "plain HTTP redirects to HTTPS"
else
  fail "plain HTTP does not redirect to HTTPS (${redirect})"
fi

# 4. the running API's posture, judged by the API's own settings
if posture=$(compose exec -T api python infra/staging/staging_probe.py env 2>&1); then
  pass "$posture"
else
  fail "$posture"
fi

# 5. restart test: written before a restart, decrypted after it
if packed=$(compose exec -T api python infra/staging/staging_probe.py write); then
  pass "synthetic record encrypted through the API's cipher (transit KEK)"
  compose restart api
  wait_healthy api
  if out=$(printf '%s\n' "$packed" | compose exec -T api python infra/staging/staging_probe.py read 2>&1); then
    pass "after an api restart: $out"
  else
    fail "after an api restart: $out"
  fi
  compose restart openbao
  wait_for_openbao
  unseal_openbao
  wait_healthy openbao
  if out=$(printf '%s\n' "$packed" | compose exec -T api python infra/staging/staging_probe.py read 2>&1); then
    pass "after an OpenBao restart and unseal: $out"
  else
    fail "after an OpenBao restart and unseal: $out"
  fi
else
  fail "could not encrypt the synthetic record"
fi

if ((failures > 0)); then
  die "smoke: ${failures} check(s) failed"
fi
log "smoke: all checks passed for ${INTAKE_GIT_SHA} at https://${STAGING_HOSTNAME}"
