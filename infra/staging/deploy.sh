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
# It passes the API whatever App Attest and SMS keys the operator set in the
# env file, and refuses an Apple team id without all three SMS keys (INT-352,
# docs/runbooks/staging.md, "App Attest and SMS").
#
# What it does:
#   1. Stamps the commit sha and build time, and builds the API image.
#   2. Has syft write an SBOM of that image into the release directory and
#      stamps its sha256. /version reports all three stamps (INT-352, audit
#      F18). No SBOM, no deploy: a failing syft stops the script here.
#   3. Runs the release gate in that image (INT-187). It stops here, before
#      anything restarts, if deploys are frozen from the console, an SLO's
#      error budget is exhausted, or the freeze cannot be read.
#   4. Unseals OpenBao and renews the API's periodic token.
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
load_env
require_sms_with_app_attest
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

wait_healthy postgres
run_migrations
rotate_role_passwords

# INT-421: the staff realm, then its key set, before the api starts reading it
ensure_keycloak_database
compose up -d --no-build --wait keycloak
ensure_staff_webauthn_notes
mirror_keycloak_jwks

# --no-build: the api runs the image build_api_image made and syft described
compose up -d --no-build --wait --remove-orphans
if ((JWKS_CHANGED == 1)); then
  # the API reads the key set once, at start
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
