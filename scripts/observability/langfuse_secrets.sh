#!/usr/bin/env bash
# INT-175 — put the Langfuse tier's secrets in the environment, from OpenBao
# (CLAUDE.md invariant 14; files/10 §2, §8).
#
#   eval "$(scripts/observability/langfuse_secrets.sh --export)"
#   docker compose -f infra/docker-compose.langfuse.yml --profile langfuse up -d
#
# `make langfuse` does both. Why a script rather than an .env file: env.example
# is the OpenBao pointer and nothing else — tests/security/test_openbao_wiring.py
# fails the build if it grows a key — and a secret written to a file on disk is
# a secret that outlives the container that needed it.
#
# --seed (dev only) generates the eight values and writes them into the dev
# OpenBao KV at secret/observability/langfuse. It refuses to overwrite: a
# re-seed would rotate ENCRYPTION_KEY out from under an existing ClickHouse
# store and make every stored span undecryptable.
#
# --export reads them back and prints `export NAME=value` lines. Nothing is
# echoed unless you ask for the export.
set -euo pipefail
cd "$(dirname "$0")/../.."

BAO_ADDR_VALUE="${OPENBAO_ADDR:-http://127.0.0.1:8200}"
TOKEN="${OPENBAO_TOKEN:-}"
KV_PATH="secret/observability/langfuse"

# The exact names infra/docker-compose.langfuse.yml interpolates. Keeping the
# list here and asserting it in tests/observability/test_langfuse_gate.py is
# what stops the two drifting.
KEYS=(
  LANGFUSE_POSTGRES_PASSWORD
  LANGFUSE_CLICKHOUSE_PASSWORD
  LANGFUSE_REDIS_PASSWORD
  LANGFUSE_S3_ACCESS_KEY_ID
  LANGFUSE_S3_SECRET_ACCESS_KEY
  LANGFUSE_SALT
  LANGFUSE_ENCRYPTION_KEY
  LANGFUSE_NEXTAUTH_SECRET
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
    echo "Rotating ENCRYPTION_KEY orphans every span already in ClickHouse." >&2
    exit 1
  fi
  args=()
  for key in "${KEYS[@]}"; do
    # ENCRYPTION_KEY must be exactly 32 bytes of hex, per Langfuse's docs.
    args+=("$key=$(openssl rand -hex 32)")
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
