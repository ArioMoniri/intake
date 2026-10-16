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
#   6-7. INT-421/INT-378: the admin tier and the live realm's WebAuthn step.
#   8. INT-442/INT-443: the API's egress through the forward proxy, and one
#      scripted clip through the hosted lane.
#   9. INT-481: the telemetry tier. The staff Grafana sends an anonymous
#      caller to Keycloak, the telemetry services are ready, every scrape
#      target and synthetic probe is up, this deploy's marker is stored, the
#      API's alerts route refuses an anonymous caller, and the realm has the
#      committed grafana client.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_root
require_tools
load_env
stamp_revision
stamp_sbom_from_disk

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

# 8. INT-442: the API's egress, from the API's own network position — no
#    direct route out, an unlisted host and the metadata address refused by
#    the forward proxy, and every hosted-model allow-list row tunnelled
if out=$(compose exec -T api python infra/staging/egress_probe.py proxy 2>&1); then
  pass "$(printf '%s' "$out" | tr '\n' ';')"
else
  fail "$(printf '%s' "$out" | tr '\n' ';')"
fi

# 7. INT-443: one scripted question clip through the George route's own
#    wiring, inside the api container; it names the lane that spoke it
#    (elevenlabs, or self_hosted after a vendor failure) and never the text.
#    An unconfigured lane (no allow-list row yet) is reported, not failed:
#    the row is the owner's protected change.
if out=$(compose exec -T api python -m intake_api.george_prebake probe 2>&1); then
  pass "$out"
elif [[ $out == *unconfigured* ]]; then
  pass "clip lane not serving yet: $out"
else
  fail "$out"
fi

# 9. INT-481: the telemetry tier. The staff Grafana is its own origin behind its
#    own login gate, and sends an anonymous caller to the Keycloak login. Each
#    telemetry service answers inside the host. Prometheus scrapes every target
#    and every synthetic probe passes, and it has stored this deploy's
#    `completed` marker. The API's alerts route refuses an anonymous caller. The
#    live realm's grafana client is in its committed shape. Read only.
grafana_host="grafana.${STAGING_HOSTNAME}"
redirect=$(curl -sS -o /dev/null -w '%{http_code} %{redirect_url}' --proto '=https' --max-time 10 \
  "https://${grafana_host}/" || true)
if [[ $redirect =~ ^30[23]\ https://${auth_host//./\\.}/realms/intake/ ]]; then
  pass "https://${grafana_host}/ sends an anonymous caller to the Keycloak login"
else
  fail "https://${grafana_host}/ did not send an anonymous caller to Keycloak (${redirect})"
fi
if curl -sS -o /dev/null -D - --proto '=https' --max-time 10 "https://${grafana_host}/" |
  tr -d '\r' | grep -qi '^x-intake-environment: staging-synthetic-only$'; then
  pass "https://${grafana_host}/ carries the staging header"
else
  fail "https://${grafana_host}/ is missing the staging header"
fi
if compose exec -T prometheus wget -q -O /dev/null http://127.0.0.1:9090/-/ready &&
  compose exec -T alertmanager wget -q -O /dev/null http://127.0.0.1:9093/-/ready &&
  compose exec -T grafana curl -fsS -o /dev/null http://127.0.0.1:3000/api/health; then
  pass "prometheus, alertmanager and grafana are ready inside the host"
else
  fail "a telemetry service is not ready inside the host"
fi
if wait_prom_value 'min(up)' 1 && wait_prom_value 'min(probe_success)' 1; then
  pass "Prometheus scrapes every target and every synthetic probe passes"
else
  fail "a scrape target is down or a synthetic probe fails (Grafana: Staging overview)"
fi
if wait_prom_value "count(deploy_event_timestamp_seconds{stage=\"completed\",head_sha=\"${INTAKE_GIT_SHA}\"})" 1; then
  pass "Prometheus holds the completed deploy marker for ${INTAKE_GIT_SHA}"
else
  fail "Prometheus holds no completed deploy marker for ${INTAKE_GIT_SHA}"
fi
gate=$(curl -sS -w ' %{http_code}' --proto '=https' --max-time 10 "https://${STAGING_HOSTNAME}/admin/alerts" || true)
if [[ $gate =~ (source_ip_refused|unauthorized).*\ (401|403)$ ]]; then
  pass "the API's alerts route refuses an anonymous caller (${gate##* })"
else
  fail "the API's alerts route is not in its configured, refusing state: ${gate}"
fi
if grafana_client check >/dev/null 2>&1; then
  pass "realm ${KEYCLOAK_REALM} has the committed grafana client"
else
  fail "realm ${KEYCLOAK_REALM}: the grafana client is absent or drifted (staff Grafana sign-in is refused)"
fi

if ((failures > 0)); then
  die "smoke: ${failures} check(s) failed"
fi
log "smoke: all checks passed for ${INTAKE_GIT_SHA} at https://${STAGING_HOSTNAME}"
