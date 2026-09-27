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
#   3. Unseals OpenBao and renews the API's periodic token.
#   4. Migrates, and re-keys any new migration role.
#   5. Brings the project up on exactly the image the SBOM describes, and
#      waits for health.
#   6. Probes /healthz and /readyz over public HTTPS.
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
stamp_revision
build_api_image
stamp_sbom
log "deploying ${INTAKE_GIT_SHA} (image built ${INTAKE_BUILT_AT}, SBOM ${INTAKE_SBOM_DIGEST}) to https://${STAGING_HOSTNAME}"

compose up -d postgres redis openbao
wait_for_openbao
unseal_openbao
renew_api_token

wait_healthy postgres
run_migrations
rotate_role_passwords

# --no-build: the api runs the image build_api_image made and syft described
compose up -d --no-build --wait --remove-orphans

for path in /healthz /readyz; do
  if ! wait_https "$path"; then
    # /readyz names its checks and their states only: no content (invariant 6)
    body=$(curl -sS --proto '=https' --max-time 10 "https://${STAGING_HOSTNAME}${path}" || true)
    die "https://${STAGING_HOSTNAME}${path} did not answer 2xx; last body: ${body}"
  fi
  log "https://${STAGING_HOSTNAME}${path}: ok"
done

log "deployed ${INTAKE_GIT_SHA}; next: ./smoke.sh"
