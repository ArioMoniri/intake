#!/usr/bin/env bash
# INT-345: one-time host bootstrap for the staging backend. It is idempotent:
# re-running it changes nothing that already exists.
#
# SYNTHETIC PATIENTS ONLY. The host is in us-east-1 (HB-I5, HB-L11).
#
# Run as root on the staging host, from infra/staging:
#   STAGING_HOSTNAME=<EIP-dashed>.sslip.io ./init.sh
#
# Before anything else it refuses a host whose active swap is not encrypted:
# OpenBao 2.6 cannot lock its memory, so its keys must not be paged to disk
# in the clear (docs/runbooks/staging.md, "Host memory").
#
# What it does:
#   1. Creates the root-only state dir and env file, and generates every
#      secret in it here, once: the database and Redis passwords, the
#      object store's root pair, the API's OpenBao token and the OTP tier's
#      tokenization key. It writes the operator's App Attest and SMS keys
#      empty, for the operator to fill (INT-352).
#   2. Starts OpenBao in server mode, initialises it with 3 key shares
#      (threshold 2), and unseals it. The shares and the root token go to a
#      separate root-only file.
#   3. Sets up the transit engine, the intake-api policy, the restart-probe
#      KEK and the API's periodic token.
#   4. Builds the API image, runs the alembic migrations, and re-keys the
#      migration roles away from their committed dev passwords.
#
# Next: ./deploy.sh, then ./smoke.sh.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_root
require_tools
require_no_unencrypted_swap
prepare_state_dir

host=${STAGING_HOSTNAME:-$(env_get "$ENV_FILE" STAGING_HOSTNAME)}
[[ -n $host ]] || die "set STAGING_HOSTNAME=<EIP-dashed>.sslip.io (docs/runbooks/staging.md)"
validate_hostname "$host"
env_set "$ENV_FILE" STAGING_HOSTNAME "$host"
generate_missing_secrets

load_env
stamp_revision

compose up -d postgres redis openbao
wait_for_openbao
initialise_openbao
unseal_openbao
configure_openbao

wait_healthy postgres
compose build api
run_migrations
rotate_role_passwords

log "init complete for https://${STAGING_HOSTNAME} (synthetic patients only)"
log "state: $STATE_DIR (0700): .env and openbao-init.json, both 0600 root"
log "next: ./deploy.sh, then ./smoke.sh"
