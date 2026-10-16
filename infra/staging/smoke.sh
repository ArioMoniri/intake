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
#   2. /version names the deployed commit, a build time and the sha256 of the
#      SBOM on disk, and "dev" in any of the three fails (INT-352, audit
#      F18). The api container must run the image that SBOM describes.
#   3. The staging header is on every response, and plain HTTP redirects to
#      HTTPS.
#   4. Inside the api container: INTAKE_ENV is staging, no dev gate is set,
#      and the KEK mode is transit.
#   5. Restart test. A synthetic record is encrypted through the API's own
#      cipher. The api container is restarted and the record must decrypt.
#      Then OpenBao is restarted, which leaves it sealed, and unsealed, and
#      the record must decrypt again. A process-local KEK fails the first
#      step. A KEK that is not on persistent storage fails the second.
#   8. INT-515, the voice tier: the SFU's signalling answers at rtc.<host>
#      and its server API does not; TURN over TLS on 443 answers a STUN
#      Binding for turn.<host> (turn_probe.py, from this host, as a phone
#      dials it); the voice runtime and the SFU mount nothing writable, run
#      read-only and with core dumps off (invariant 3); the runtime is alive;
#      and, when it reports ready, one scripted synthetic turn completes on
#      its lanes. Until its lanes exist (INT-428/442/443) the runtime is not
#      ready and says why, and the turn is reported as skipped, never passed.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_root
require_tools
load_env
stamp_revision
stamp_sbom_from_disk
stamp_voice_runtime_sbom_from_disk

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

# 2. /version is the deployed commit, its build time and the SBOM on disk,
#    never "dev"; and the api runs the image that SBOM describes
version_body=$(https_get /version || true)
sbom_on_disk=$(sha256_of "$SBOM_FILE" || true)
if verdict=$(version_verdict "$INTAKE_GIT_SHA" "$sbom_on_disk" <<<"$version_body"); then
  pass "/version: $verdict"
else
  fail "/version: $verdict"
fi
running_image=$(docker inspect --format '{{.Image}}' "$(compose ps -q api)" 2>/dev/null || true)
if [[ $running_image == "$API_IMAGE_ID" ]]; then
  pass "the api runs the image the SBOM describes (${API_IMAGE_ID})"
else
  fail "the api runs ${running_image:-no container}, not the image the SBOM describes (${API_IMAGE_ID})"
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

# 6. INT-421: the admin tier. The realm is served under its public issuer.
#    Keycloak's admin console and the master realm are not routed. The
#    console's /healthz answers with a CSP. Every other console page needs a
#    Keycloak login. The API's admin gate is configured, and it refuses a
#    caller with no bearer from an unlisted source.
admin_host="admin.${STAGING_HOSTNAME}"
auth_host="auth.${STAGING_HOSTNAME}"
issuer=$(curl -fsS --proto '=https' --max-time 10 \
  "https://${auth_host}/realms/intake/.well-known/openid-configuration" |
  python3 -c 'import json, sys; print(json.load(sys.stdin).get("issuer", ""))' 2>/dev/null || true)
if [[ $issuer == "https://${auth_host}/realms/intake" ]]; then
  pass "realm intake is served under issuer ${issuer}"
else
  fail "realm intake: issuer '${issuer}' is not https://${auth_host}/realms/intake"
fi
for path in /admin/ /realms/master/.well-known/openid-configuration; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --proto '=https' --max-time 10 "https://${auth_host}${path}" || true)
  if [[ $code == 404 ]]; then
    pass "https://${auth_host}${path} is not routed (404)"
  else
    fail "https://${auth_host}${path} answered ${code:-nothing}, not 404"
  fi
done
headers=$(curl -sS -o /dev/null -D - --proto '=https' --max-time 10 "https://${admin_host}/healthz" | tr -d '\r' || true)
if [[ $headers =~ ^HTTP/[0-9.]+\ 200 ]] && grep -qi '^content-security-policy: ' <<<"$headers" &&
  ! grep -i '^content-security-policy: ' <<<"$headers" | grep -q "unsafe-"; then
  pass "https://${admin_host}/healthz -> 200 with a CSP and no unsafe-*"
else
  fail "https://${admin_host}/healthz: no 200, or no strict CSP"
fi
redirect=$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' --proto '=https' --max-time 10 \
  "https://${admin_host}/ops" || true)
if [[ $redirect =~ ^30[23]\ https://${auth_host//./\\.}/realms/intake/ ]]; then
  pass "https://${admin_host}/ops sends an anonymous caller to the Keycloak login"
else
  fail "https://${admin_host}/ops did not send an anonymous caller to Keycloak (${redirect})"
fi
gate=$(curl -sS -w ' %{http_code}' --proto '=https' --max-time 10 "https://${STAGING_HOSTNAME}/admin/ops" || true)
if [[ $gate =~ (source_ip_refused|unauthorized).*\ (401|403)$ ]]; then
  pass "the API's admin gate is configured and refuses an anonymous caller (${gate##* })"
else
  fail "the API's admin gate is not in its configured, refusing state: ${gate}"
fi

# 7. INT-378: the live realm's WebAuthn step is the session-notes provider, the
#    one that puts aaguid and credential_id into a staff token. Read only.
if staff_flow check >/dev/null 2>&1; then
  pass "realm ${KEYCLOAK_REALM} runs the WebAuthn session-notes provider with the hwk reference"
else
  fail "realm ${KEYCLOAK_REALM}: the WebAuthn step is not the session-notes provider (staff sign-in is refused)"
fi

# 8. INT-515: the voice tier.
rtc_host="rtc.${STAGING_HOSTNAME}"
turn_host="turn.${STAGING_HOSTNAME}"
# 8a. signalling reaches the SFU (it refuses a caller with no token), and the
#     server API is not routed
code=$(curl -sS -o /dev/null -w '%{http_code}' --proto '=https' --max-time 10 "https://${rtc_host}/rtc/validate" || true)
if [[ $code == 401 ]]; then
  pass "https://${rtc_host}/rtc/validate reaches the SFU and refuses a caller with no token (401)"
else
  fail "https://${rtc_host}/rtc/validate answered ${code:-nothing}, not the SFU's 401"
fi
for path in /twirp/livekit.RoomService/ListParticipants /; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --proto '=https' --max-time 10 "https://${rtc_host}${path}" || true)
  if [[ $code == 404 ]]; then
    pass "https://${rtc_host}${path} is not routed (404)"
  else
    fail "https://${rtc_host}${path} answered ${code:-nothing}, not 404"
  fi
done
# 8b. TURN over TLS on 443, from outside, with the TURN name's certificate
if turn=$(python3 "$STAGING_DIR/turn_probe.py" --connect "$STAGING_HOSTNAME" --port 443 --sni "$turn_host" 2>&1); then
  pass "$turn"
else
  fail "$turn"
fi
# 8c. raw audio has nowhere to land: no writable mount, a read-only root and
#     core dumps off, on the runtime and on the SFU (invariant 3)
for service in voice-runtime livekit; do
  id=$(compose ps -q "$service")
  posture=$(docker inspect --format \
    '{{.HostConfig.ReadonlyRootfs}} {{range .HostConfig.Ulimits}}{{if eq .Name "core"}}core={{.Hard}}{{end}}{{end}} {{range .Mounts}}{{if .RW}}rw:{{.Destination}} {{end}}{{end}}' \
    "${id:-none}" 2>/dev/null || true)
  if [[ $posture =~ ^true\ core=0\ *$ ]]; then
    pass "$service: read-only root, core dumps off, no writable mount"
  else
    fail "$service: posture is '${posture:-unreadable}', not a read-only root with core=0 and no writable mount"
  fi
done
# 8d. the runtime is alive; and, when it reports ready, a synthetic turn completes
if alive=$(compose exec -T voice-runtime python infra/staging/voice_probe.py healthz 2>&1); then
  pass "voice-runtime: $alive"
else
  fail "voice-runtime: $alive"
fi
if ready=$(compose exec -T voice-runtime python infra/staging/voice_probe.py readyz 2>&1); then
  pass "voice-runtime /readyz: $ready"
  if turn=$(compose exec -T voice-runtime python infra/staging/voice_probe.py turn 2>&1); then
    pass "voice-runtime /probe/synthetic-turn: $turn"
  else
    fail "voice-runtime /probe/synthetic-turn: $turn"
  fi
else
  # names and states only (invariant 6); not counted: the lanes are not here yet
  log "SKIP the synthetic turn: voice-runtime is ${ready}"
fi

if ((failures > 0)); then
  die "smoke: ${failures} check(s) failed"
fi
log "smoke: all checks passed for ${INTAKE_GIT_SHA} at https://${STAGING_HOSTNAME}"
