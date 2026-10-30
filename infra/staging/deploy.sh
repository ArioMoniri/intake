#!/usr/bin/env bash
# INT-345: deploy the staging backend. It is idempotent: re-running it on
# the same commit changes nothing.
#
# SYNTHETIC PATIENTS ONLY. The host is in us-east-1 (HB-I5, HB-L11).
#
# Run as root on the staging host, from infra/staging, after ./init.sh. Run it
# again after every host reboot: OpenBao restarts sealed, and this unseals it.
#
# Its first checks, before it touches the host, are that the object-store
# image and the SBOM image in lib.sh are set and pinned by digest (owner
# decision D1 and INT-347 record the object store; INT-352 records syft).
# compose and the SBOM step run exactly those values.
#
# Like init.sh, it refuses a host whose active swap is not encrypted before
# OpenBao starts. A reboot can bring swap back, and this is the script that
# unseals OpenBao after one (docs/runbooks/staging.md, "Host memory").
#
# It passes the API whatever App Attest keys the operator set in the env
# file, and refuses an Apple team id unless the API's own token reads the
# whole Netgsm document in OpenBao (INT-352, INT-528; docs/runbooks/staging.md,
# "App Attest and SMS").
#
# What it does:
#   1. Stamps the commit sha and build time, and builds the API image.
#   2. Has syft write an SBOM of that image into the release directory and
#      stamps its sha256. /version reports all three stamps (INT-352, audit
#      F18). No SBOM, no deploy: a failing syft stops the script here.
#   3. Runs the release gate in that image (INT-187). It stops here, before
#      anything restarts, if deploys are frozen from the console, an SLO's
#      error budget is exhausted, or the freeze cannot be read.
#   4. Unseals OpenBao, renews the API's periodic token, loads any
#      hosted-provider key held in SSM Parameter Store into OpenBao (INT-428),
#      syncs the Netgsm values from SSM into OpenBao (INT-528), checks the
#      App Attest pairing, and moves the phone-tokenization key from the env
#      file into OpenBao with the same key material (INT-584, owner decision
#      D38; tokenization_key.sh). That step stops the deploy, with both copies
#      kept, if OpenBao already holds a different key.
#   5. Migrates, and re-keys any new migration role.
#   6. INT-421: makes sure Keycloak's database exists, starts Keycloak (which
#      imports the staff realm on first start), switches the live realm's
#      WebAuthn step to the session-notes provider the image carries (INT-378;
#      an import never re-runs), and mirrors the realm's public key set for the
#      API's admin gate.
#   7. Brings the project up on exactly the image the SBOM describes (and the
#      console image built beside it), and waits for health.
#   8. Probes /healthz and /readyz over public HTTPS.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_object_store_image "$OBJECT_STORE_IMAGE"
require_sbom_image "$SBOM_IMAGE"
require_root
require_tools
require_no_unencrypted_swap
# INT-560: the probes service's two logins, which a host initialised before
# INT-560 lacks; generated once, before load_env checks every template key
ensure_probe_secrets
load_env
ensure_jwks_file
stamp_revision
build_api_image
build_admin_web_image
build_keycloak_image
stamp_sbom
require_release_not_frozen
log "deploying ${INTAKE_GIT_SHA} (image built ${INTAKE_BUILT_AT}, SBOM ${INTAKE_SBOM_DIGEST}) to https://${STAGING_HOSTNAME}"

compose up -d postgres redis openbao
wait_for_openbao
unseal_openbao
renew_api_token
# INT-578: the committed API policy and the OTP pepper, re-asserted on every
# deploy so a host initialised before them gains both before the API starts
ensure_api_openbao
# INT-428 (ADR-035): any hosted-provider key held in SSM Parameter Store
# (/intake/staging/<provider>_api_key) is re-loaded into OpenBao, so the
# terminal route, the deploy and the console read one record. Prints set /
# not set and the last four characters only.
for provider in openai elevenlabs; do
  "$STAGING_DIR/load_provider_key.sh" --if-present "$provider"
done
# INT-528: the owner's SSM parameters are the Netgsm values' source of truth.
# Sync them into OpenBao (a host without them is skipped), then check the
# App Attest pairing against what the API will read, before the API starts.
NETGSM_SYNC=$("$STAGING_DIR/netgsm_secrets.sh" --if-present)
require_sms_with_app_attest
# INT-584 (owner decision D38): the phone-tokenization key, from the env file
# into OpenBao, proven equal (key check value and the synthetic number's
# pseudonym, never printed) before the env copy goes; a different key already
# in OpenBao stops the deploy here. Prints changed or unchanged.
TOKENIZATION_SYNC=$("$STAGING_DIR/tokenization_key.sh")
# INT-580 (D34): the association file the edge serves, from the same team id,
# before the edge is recreated below; none without a team id (fail closed)
write_aasa

wait_healthy postgres
run_migrations
rotate_role_passwords
# INT-560: the probes service's database login (LOGIN and CONNECT only)
ensure_probe_role

# INT-421: the staff realm, then its key set, before the api starts reading it
ensure_keycloak_database
compose up -d --no-build --wait keycloak
ensure_staff_webauthn_notes
mirror_keycloak_jwks

# --no-build: the api runs the image build_api_image made and syft described
compose up -d --no-build --wait --remove-orphans
if ((JWKS_CHANGED == 1)) || [[ $NETGSM_SYNC == changed ]] || [[ $TOKENIZATION_SYNC == changed ]]; then
  # the API reads the key set, the Netgsm document and the tokenization key
  # once, at start
  compose restart api
  wait_healthy api
fi
# INT-421: each release is extracted to its own directory, and a bind mount
# resolves its source when the container is created. A caddy container left
# running therefore keeps the previous release's Caddyfile, and the 2 Oct 2026
# deploy served no admin or auth host for that reason. Recreate the edge, so
# it serves this release's sites.
# caddy declares no healthcheck, so --wait waits for it to be running
compose up -d --no-build --no-deps --force-recreate --wait caddy

for path in /healthz /readyz; do
  if ! wait_https "$path"; then
    # /readyz names its checks and their states only: no content (invariant 6)
    body=$(curl -sS --proto '=https' --max-time 10 "https://${STAGING_HOSTNAME}${path}" || true)
    die "https://${STAGING_HOSTNAME}${path} did not answer 2xx; last body: ${body}"
  fi
  log "https://${STAGING_HOSTNAME}${path}: ok"
done

log "deployed ${INTAKE_GIT_SHA}; next: ./smoke.sh"
