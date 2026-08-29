#!/usr/bin/env bash
# INT-205 — put the SIEM tier's secrets in the environment, from OpenBao
# (CLAUDE.md invariant 14; files/10 §2, §8).
#
#   eval "$(scripts/security/siem_secrets.sh --export)"
#   docker compose -f infra/docker-compose.siem.yml --profile siem up -d
#
# `make siem` does both. Why a script rather than an .env file: env.example is
# the OpenBao pointer and nothing else — tests/security/test_openbao_wiring.py
# fails the build if it grows a key — and a secret written to a file on disk is
# a secret that outlives the container that needed it.
#
# --seed (dev only) generates the four values and writes them into the dev
# OpenBao KV at secret/security/siem. It refuses to overwrite: re-seeding
# INDEXER_PASSWORD after the indexer has initialised locks the manager out of
# its own alert store.
#
# --export reads them back and prints `export NAME=value` lines. Nothing is
# echoed unless you ask for the export.
set -euo pipefail
cd "$(dirname "$0")/../.."

BAO_ADDR_VALUE="${OPENBAO_ADDR:-http://127.0.0.1:8200}"
TOKEN="${OPENBAO_TOKEN:-}"
KV_PATH="secret/security/siem"

# The exact names infra/docker-compose.siem.yml interpolates. Keeping the list
# here and asserting it in tests/infra/test_siem_feed.py is what stops the two
# drifting — a name added to the compose file and not to this list becomes an
# empty string at `up` time, which is a container that starts with no password.
KEYS=(
  INDEXER_USERNAME
  INDEXER_PASSWORD
  WAZUH_API_USERNAME
  WAZUH_API_PASSWORD
)

usage() {
  echo "usage: $0 --seed | --export" >&2
  exit 2
}

require_token() {
  if [[ -z "$TOKEN" ]]; then
    echo "OPENBAO_TOKEN is unset — this script reads secrets from OpenBao and" >&2
    echo "will not invent them (CLAUDE.md invariant 14)." >&2
    exit 1
  fi
}

bao() {
  BAO_ADDR="$BAO_ADDR_VALUE" BAO_TOKEN="$TOKEN" command bao "$@"
}

seed() {
  require_token
  if bao kv get "$KV_PATH" >/dev/null 2>&1; then
    echo "$KV_PATH already exists — refusing to overwrite." >&2
    echo "Rotating INDEXER_PASSWORD locks the manager out of the alert store." >&2
    exit 1
  fi
  args=()
  for key in "${KEYS[@]}"; do
    case "$key" in
      *USERNAME) args+=("$key=intake-siem") ;;
      *) args+=("$key=$(openssl rand -hex 32)") ;;
    esac
  done
  bao kv put "$KV_PATH" "${args[@]}" >/dev/null
  echo "seeded $KV_PATH with ${#KEYS[@]} values" >&2
}

export_env() {
  require_token
  for key in "${KEYS[@]}"; do
    value="$(bao kv get -field="$key" "$KV_PATH")"
    printf 'export %s=%q\n' "$key" "$value"
  done
}

case "${1:-}" in
  --seed) seed ;;
  --export) export_env ;;
  *) usage ;;
esac
