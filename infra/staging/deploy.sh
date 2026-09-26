#!/usr/bin/env bash
# INT-345: deploy the staging backend. It is idempotent: re-running it on
# the same commit changes nothing.
#
# SYNTHETIC PATIENTS ONLY. The host is in us-east-1 (HB-I5, HB-L11).
#
# Run as root on the staging host, from infra/staging, after ./init.sh. Run it
# again after every host reboot: OpenBao restarts sealed, and this unseals it.
#
# Its first check, before it touches the host, is that the object-store image
# in lib.sh is set and pinned by digest (owner decision D1; INT-347 records
# the image and its licence). compose runs exactly that value.
#
# What it does:
#   1. Stamps the commit sha and build time, which /version reports.
#   2. Unseals OpenBao and renews the API's periodic token.
#   3. Builds the API, migrates, and re-keys any new migration role.
#   4. Brings the project up and waits for health.
#   5. Probes /healthz and /readyz over public HTTPS.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_object_store_image "$OBJECT_STORE_IMAGE"
require_root
require_tools
load_env
stamp_revision
log "deploying ${INTAKE_GIT_SHA} (image built ${INTAKE_BUILT_AT}) to https://${STAGING_HOSTNAME}"

compose up -d postgres redis openbao
wait_for_openbao
unseal_openbao
renew_api_token

wait_healthy postgres
compose build api
run_migrations
rotate_role_passwords

compose up -d --build --wait --remove-orphans

for path in /healthz /readyz; do
  if ! wait_https "$path"; then
    # /readyz names its checks and their states only: no content (invariant 6)
    body=$(curl -sS --proto '=https' --max-time 10 "https://${STAGING_HOSTNAME}${path}" || true)
    die "https://${STAGING_HOSTNAME}${path} did not answer 2xx; last body: ${body}"
  fi
  log "https://${STAGING_HOSTNAME}${path}: ok"
done

log "deployed ${INTAKE_GIT_SHA}; next: ./smoke.sh"
