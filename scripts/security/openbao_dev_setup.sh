#!/usr/bin/env bash
# INT-017 — configure the dev OpenBao: KV v2 (default at secret/), the database
# secrets engine against the compose Postgres with a 24h TTL role, and the
# per-service policies. Idempotent; dev only (the prod path is IaC in P2+).
set -euo pipefail

export BAO_ADDR="${OPENBAO_ADDR:-http://127.0.0.1:8200}"
TOKEN="${OPENBAO_TOKEN:-intake-dev-root}"
BAO="docker exec -e BAO_TOKEN=$TOKEN -e BAO_ADDR=http://127.0.0.1:8200 intake-dev-openbao-1 bao"
# stdin-consuming commands (policy write -) need an interactive exec
BAO_I="docker exec -i -e BAO_TOKEN=$TOKEN -e BAO_ADDR=http://127.0.0.1:8200 intake-dev-openbao-1 bao"

$BAO secrets enable -path=database database 2>/dev/null || true

$BAO write database/config/intake-postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles="intake-api,intake-workers,intake-voice-runtime" \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/${POSTGRES_DB:-intake}?sslmode=disable" \
  username="${POSTGRES_USER:-intake}" \
  password="${POSTGRES_PASSWORD:-intake-dev-only}"

for role in intake-api intake-workers intake-voice-runtime; do
  $BAO write "database/roles/$role" \
    db_name=intake-postgres \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT CONNECT ON DATABASE ${POSTGRES_DB:-intake} TO \"{{name}}\";" \
    default_ttl=24h \
    max_ttl=24h
done

for policy in intake-api intake-workers intake-voice-runtime; do
  $BAO_I policy write "$policy" - <<POLICY
# ${policy}: its own KV subtree + its own dynamic DB role. Least privilege —
# no service reads another service's secrets (files/10 §2).
path "secret/data/${policy#intake-}/*" { capabilities = ["read"] }
path "database/creds/${policy}" { capabilities = ["read"] }
POLICY
done

# INT-032 — the openEHR export tier's CDR credentials. The compose `export`
# profile configures EHRbase with the same dev pair; intake_platform.ehrbase
# reads it from here and from nowhere else (invariant 14), so a machine that
# overrides EHRBASE_USER/EHRBASE_PASSWORD for compose must export the same
# values before running this script.
$BAO kv put secret/ehrbase \
  username="${EHRBASE_USER:-intake-dev}" \
  password="${EHRBASE_PASSWORD:-intake-dev-only}" >/dev/null

# Transit for the identity vault (INT-013); envelope-encryption engine work is INT-014
$BAO secrets enable transit 2>/dev/null || true
$BAO write -f transit/keys/tokenization >/dev/null

# vault DDL + roles on the dev Postgres
docker exec -i intake-dev-postgres-1 psql -U "${POSTGRES_USER:-intake}" -d "${POSTGRES_DB:-intake}" < scripts/security/identity_vault.sql >/dev/null

echo "openbao dev setup complete (kv v2, database 24h roles, 3 policies, transit, identity vault, ehrbase creds)"
