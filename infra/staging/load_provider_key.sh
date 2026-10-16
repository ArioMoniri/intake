#!/usr/bin/env bash
# INT-428 (ADR-035): load a hosted-provider API key from SSM Parameter Store
# into this host's OpenBao, at the record the admin console's key-set ceremony
# writes (secret/model-lanes/providers/<provider>).
#
# The three routes read and write the same names:
#   - the owner's terminal (scripts/ops/put_provider_key.sh);
#   - this script, run by that command and by deploy.sh (--if-present);
#   - the console ceremony.
#
# Parameter names, one SecureString per provider in us-east-1 (the account's
# aws/ssm KMS key):
#   /intake/staging/openai_api_key
#   /intake/staging/elevenlabs_api_key
#
# A parameter that exists is the deploy-time source of truth: every deploy
# re-loads it, so a key set only in the console is replaced at the next deploy
# while that parameter exists. To rotate, run put_provider_key.sh, or delete
# the parameter and use the console.
#
# Run as root on the synthetic (staging) host, from infra/staging:
#   ./load_provider_key.sh [--if-present] openai|elevenlabs
#
# The key never appears in a command line, a file or a log line:
#   - It is read with the instance role into one shell variable.
#   - It is piped into `bao kv put ... api_key=-`, which reads it from stdin.
#   - Only "set" or "not set" and the last four characters are printed.
#
# Before it writes, it brings OpenBao in line with the console: a KV v2 engine
# at secret/, and the intake-api policy re-applied from openbao/ (configure_openbao
# does the same on every init.sh run).
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if_present=0
if [[ ${1:-} == --if-present ]]; then
  if_present=1
  shift
fi
provider=${1:-}
case "$provider" in
openai | elevenlabs) ;;
*) die "usage: load_provider_key.sh [--if-present] openai|elevenlabs" ;;
esac
param="/intake/staging/${provider}_api_key"
region=${AWS_REGION:-us-east-1}

require_root
command -v aws >/dev/null 2>&1 || die "missing tool: aws"

if ! value=$(aws ssm get-parameter --region "$region" --name "$param" --with-decryption \
  --query Parameter.Value --output text 2>/dev/null); then
  printf '%s: not set (no parameter %s)\n' "$provider" "$param"
  if [[ $if_present -eq 1 ]]; then
    exit 0
  fi
  exit 1
fi
if ! [[ $value =~ ^[A-Za-z0-9_.-]{20,}$ && ${#value} -le 512 ]]; then
  unset value
  die "the parameter $param is not key-shaped; nothing was written"
fi
last4=${value: -4}

root=$(init_field root_token)
if ! bao_as "$root" secrets list -format=json |
  python3 -c 'import json, sys; sys.exit(0 if "secret/" in json.load(sys.stdin) else 1)'; then
  bao_as "$root" secrets enable -path=secret kv-v2 >/dev/null
  log "kv-v2 engine enabled at secret/"
fi
bao_as "$root" policy write intake-api - <"$STAGING_DIR/openbao/intake-api-policy.hcl" >/dev/null

set_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '%s' "$value" | bao_as "$root" kv put -mount=secret "model-lanes/providers/${provider}" \
  api_key=- last4="$last4" set_at="$set_at" >/dev/null
unset value

stored=$(bao_as "$root" kv get -mount=secret -field=last4 "model-lanes/providers/${provider}" 2>/dev/null || true)
if [[ -n $stored ]]; then
  printf '%s: set · …%s\n' "$provider" "$stored"
else
  printf '%s: not set\n' "$provider"
  exit 1
fi
