#!/usr/bin/env bash
# INT-583 (D35): sync the APNs signing key from SSM Parameter Store into this
# host's OpenBao, at secret/api/apns, the one document the API reads it from
# (CLAUDE.md invariant 14; intake_api.push_apns). The new-device sign-in notice
# is pushed straight to Apple with a token-based connection: an ES256 provider
# token signed with this key. Modelled on netgsm_secrets.sh.
#
# The owner's parameters (Apple Developer account > Certificates, IDs &
# Profiles > Keys, a key with "Apple Push Notifications service (APNs)"):
#   /intake/staging/apns_key_p8    SecureString: the whole AuthKey_<key id>.p8
#                                  file, BEGIN and END lines included
#   /intake/staging/apns_key_id    the key's 10-character Key ID
#   /intake/staging/apns_team_id   the 10-character Team ID (the App ID prefix)
#
# Run it as root on the synthetic (staging) host, from the laptop, then
# redeploy so the API reads the key at boot:
#
#   aws ssm start-session --region us-east-1 --target i-0e489e48739f5de98 --document-name AWS-StartInteractiveCommand --parameters 'command=["sudo /opt/intake/infra/staging/apns_secrets.sh"]'
#
# Nothing is pushed until the owner has also applied the APNs egress row
# (owner-583-apns-egress.patch): without it the API keeps the notice channel
# off (push_channel_unconfigured{reason="egress_refused"}) and never reads the key.
#
# No value reaches an argument list, a file, the env file or the output: each
# is read with the instance role into one shell variable, its shape is checked
# (the shapes intake_api.push_apns.ApnsCredentials accepts) and a refusal names
# the field, never the value; the document goes to `bao kv put` as JSON on
# stdin; stdout carries only `changed` or `unchanged`.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

APNS_KV_PATH="api/apns"
APNS_PARAMETER_PREFIX="/intake/staging/apns_"
APPLE_ID_RE='^[A-Z0-9]{10}$'

apns_trim() {
  local value=$1
  value=${value#"${value%%[![:space:]]*}"}
  value=${value%"${value##*[![:space:]]}"}
  printf '%s' "$value"
}

apns_parameter() {
  # apns_parameter <field>: the decrypted, trimmed value; non-zero when absent
  local value
  value=$(aws ssm get-parameter --region "${AWS_REGION:-us-east-1}" \
    --name "${APNS_PARAMETER_PREFIX}$1" --with-decryption \
    --query Parameter.Value --output text 2>/dev/null) || return 1
  apns_trim "$value"
}

apns_value_ok() {
  # apns_value_ok <field> <value>: the shape the API accepts
  # the PEM armour is assembled from its parts, so this file never holds a
  # whole key header for a secret scanner to read as a key
  local LC_ALL=C field=$1 value=$2 armour="PRIVATE KEY-----"
  case $field in
  key_id | team_id) [[ $value =~ $APPLE_ID_RE ]] ;;
  key_p8) [[ $value == "-----BEGIN ${armour}"* && $value == *"-----END ${armour}" ]] ;;
  *) return 1 ;;
  esac
}

apns_document_json() {
  # stdin: key_p8, key_id and team_id, NUL-separated. stdout: the KV document.
  python3 -c '
import json, sys
key_p8, key_id, team_id = sys.stdin.read().split("\0")
sys.stdout.write(json.dumps({"key_p8": key_p8 + "\n", "key_id": key_id, "team_id": team_id}))
'
}

apns_digest() {
  # stdin: a KV document, bare or inside `bao kv get -format=json`. stdout: a
  # sha256 of its three fields, so two documents compare unprinted.
  python3 -c '
import hashlib, json, sys
try:
    doc = json.load(sys.stdin)
except ValueError:
    doc = None
if isinstance(doc, dict) and isinstance(doc.get("data"), dict):
    doc = doc["data"].get("data")
if not isinstance(doc, dict):
    print("none")
    sys.exit()
fields = [doc.get(n) for n in ("key_p8", "key_id", "team_id")]
print(hashlib.sha256(json.dumps(fields).encode("utf-8")).hexdigest())
'
}

main() {
  [[ $# -eq 0 ]] || die "usage: apns_secrets.sh"
  require_root
  command -v aws >/dev/null 2>&1 ||
    die "missing tool: aws (it reads the SSM parameters with the instance role)"

  local key_p8="" key_id="" team_id="" field missing=() root current wanted
  key_p8=$(apns_parameter key_p8) || missing+=(key_p8)
  key_id=$(apns_parameter key_id) || missing+=(key_id)
  team_id=$(apns_parameter team_id) || missing+=(team_id)
  ((${#missing[@]} == 0)) ||
    die "no readable SSM parameter for ${missing[*]} (${APNS_PARAMETER_PREFIX}<field>, readable by the instance role); nothing was written"
  for field in key_p8 key_id team_id; do
    apns_value_ok "$field" "${!field}" ||
      die "$field is empty or malformed in ${APNS_PARAMETER_PREFIX}${field}; nothing was written"
  done

  root=$(init_field root_token)
  ensure_secret_kv "$root"
  bao_as "$root" policy write intake-api - <"$STAGING_DIR/openbao/intake-api-policy.hcl" >/dev/null
  wanted=$(printf '%s\0%s\0%s' "$key_p8" "$key_id" "$team_id" | apns_document_json | apns_digest)
  current=$( (bao_as "$root" kv get -mount=secret -format=json "$APNS_KV_PATH" 2>/dev/null || printf '{}') | apns_digest)
  if [[ $current == "$wanted" ]]; then
    unset key_p8 key_id team_id
    log "secret/${APNS_KV_PATH}: already holds the SSM values; nothing written"
    printf 'unchanged\n'
    return 0
  fi
  printf '%s\0%s\0%s' "$key_p8" "$key_id" "$team_id" | apns_document_json |
    bao_as "$root" kv put -mount=secret "$APNS_KV_PATH" - >/dev/null
  unset key_p8 key_id team_id
  log "secret/${APNS_KV_PATH}: key_p8, key_id and team_id written from SSM (values not shown); redeploy so the API reads them"
  printf 'changed\n'
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
