#!/usr/bin/env bash
# INT-528: sync the Netgsm OTP SMS credentials and the SMS test allow-list
# from SSM Parameter Store into this host's OpenBao, at secret/api/netgsm, the
# one document the API reads them from (CLAUDE.md invariant 14; the owner's
# vendor decision, INT-358). Modelled on scripts/observability/langfuse_secrets.sh,
# for a host whose OpenBao runs in a container and whose values the owner keeps
# in SSM.
#
# The owner's SecureString parameters:
#   /intake/staging/netgsm_usercode    the subscriber number (abone no), 10 digits
#   /intake/staging/netgsm_password    the dedicated API sub-user's password
#   /intake/staging/netgsm_msgheader   the approved sender name, 3 to 11
#                                      characters, spaces allowed ("VIVAX AS")
#   /intake/staging/sms_test_allowlist the only numbers this synthetic host may
#                                      send a code to: Turkish mobiles in E.164,
#                                      separated by commas or spaces
#
# Run it as root on the synthetic (staging) host, from the laptop
# (docs/runbooks/staging.md, "App Attest and SMS"):
#
#   aws ssm start-session --region us-east-1 --target i-0e489e48739f5de98 --document-name AWS-StartInteractiveCommand --parameters 'command=["sudo /opt/intake/infra/staging/netgsm_secrets.sh"]'
#
# Its SSM command carries only this path. deploy.sh runs it with --if-present
# on every deploy, so the parameters stay the source of truth: to rotate,
# change them and deploy.
#
# Modes:
#   (none)        sync: write the document if it differs from OpenBao's
#   --if-present  the same, but a host with none of the four parameters, or
#                 with no aws CLI, is skipped (deploy.sh)
#   --check       read-only: ask Netgsm's sender-name listing whether the
#                 credentials work from this host's address and the sender
#                 name is approved. It writes nothing and sends no SMS.
#
# No value reaches an argument list, a file, the env file or the output:
#   - each is read with the instance role (ssm:GetParameter, kms:Decrypt)
#     into one shell variable, and the whitespace a paste leaves around it is
#     stripped;
#   - its shape is checked (the shapes NetgsmCredentials and SmsTestAllowlist
#     accept) and a refusal names the field, never the value;
#   - the values go to `bao kv put` as one JSON document on stdin, and the
#     credentials to curl (--check) as a --config on stdin; printf is a builtin;
#   - only field names and the allow-list's count reach the log on stderr, and
#     stdout carries only `changed` or `unchanged`, which deploy.sh reads to
#     restart the API.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

NETGSM_PARAMETER_PREFIX="/intake/staging/netgsm_"
SMS_TEST_ALLOWLIST_PARAMETER="/intake/staging/sms_test_allowlist"
NETGSM_MSGHEADER_URL="https://api.netgsm.com.tr/sms/rest/v2/msgheader"
NETGSM_USERCODE_RE='^[0-9]{10}$'
NETGSM_MSGHEADER_RE='^[A-Za-z0-9]([A-Za-z0-9 .-]*[A-Za-z0-9])?$'
TR_MOBILE_E164_RE='^\+905[0-9]{9}$'

have_aws() {
  command -v aws >/dev/null 2>&1
}

netgsm_value_ok() {
  # netgsm_value_ok <field> <value>: the shape the API accepts. The C locale
  # keeps every range ASCII: an unapproved sender is often one with a
  # Turkish letter in it.
  local LC_ALL=C field=$1 value=$2
  case $field in
  usercode) [[ $value =~ $NETGSM_USERCODE_RE ]] ;;
  msgheader) ((${#value} >= 3 && ${#value} <= 11)) && [[ $value =~ $NETGSM_MSGHEADER_RE ]] ;;
  password) [[ -n ${value//[[:space:]]/} ]] ;;
  test_allowlist) [[ -n $(allowlist_numbers "$value") ]] ;;
  *) return 1 ;;
  esac
}

allowlist_numbers() {
  # allowlist_numbers <raw>: the numbers, comma-joined, or nothing at all when
  # the list is empty or one entry is not a Turkish mobile in E.164 (the
  # API's SmsTestAllowlist voids the whole list the same way).
  local LC_ALL=C raw=${1//[,;]/ } token joined=""
  local -a tokens=()
  # word-split on whitespace with globbing off, in a subshell-free way
  local glob_was_off=0
  [[ $- == *f* ]] && glob_was_off=1
  set -f
  # shellcheck disable=SC2206 # splitting on whitespace is the point
  tokens=($raw)
  ((glob_was_off == 1)) || set +f
  ((${#tokens[@]} > 0)) || return 0
  for token in "${tokens[@]}"; do
    [[ $token =~ $TR_MOBILE_E164_RE ]] || return 0
    joined+="${joined:+,}$token"
  done
  printf '%s' "$joined"
}

trim() {
  # the value without the spaces, tabs and newlines a paste leaves around it
  local value=$1
  value=${value#"${value%%[![:space:]]*}"}
  value=${value%"${value##*[![:space:]]}"}
  printf '%s' "$value"
}

ssm_parameter() {
  # ssm_parameter <name>: the decrypted, trimmed value on stdout; non-zero when
  # the parameter is absent or the instance role cannot read it
  local value
  value=$(aws ssm get-parameter --region "${AWS_REGION:-us-east-1}" \
    --name "$1" --with-decryption --query Parameter.Value --output text 2>/dev/null) || return 1
  trim "$value"
}

netgsm_document_json() {
  # stdin: usercode, password, msgheader and test_allowlist, NUL-separated.
  # stdout: the KV document as one JSON object.
  python3 -c '
import json, sys
usercode, password, msgheader, allowlist = sys.stdin.read().split("\0")
sys.stdout.write(json.dumps({"usercode": usercode, "password": password,
                             "msgheader": msgheader, "test_allowlist": allowlist}))
'
}

netgsm_digest() {
  # stdin: a KV document, bare or inside `bao kv get -format=json`. stdout: a
  # sha256 of its four fields, so two documents compare without either
  # value being printed.
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
fields = [doc.get(n) for n in ("usercode", "password", "msgheader", "test_allowlist")]
print(hashlib.sha256(json.dumps(fields).encode("utf-8")).hexdigest())
'
}

netgsm_check_verdict() {
  # stdin: the listing's JSON. $1: the configured sender name. stdout: one
  # line in NetgsmRefusal's vocabulary, never the vendor's text or the list.
  python3 -c '
import json, sys
try:
    doc = json.load(sys.stdin)
except ValueError:
    doc = None
if not isinstance(doc, dict):
    print("refusal=- reason=malformed_response")
    sys.exit()
code = doc.get("code")
code = "%02d" % code if isinstance(code, int) and not isinstance(code, bool) else str(code)
refusals = {"30": "credentials_refused", "70": "parameters_refused",
            "100": "vendor_system_error", "101": "vendor_system_error"}
if code != "00":
    print("refusal=%s vendor_code=%s" % (refusals.get(code, "unknown_vendor_code"), code))
elif sys.argv[1] in (doc.get("msgheaders") or []):
    print("ok: credentials accepted from this host and the sender name is approved")
else:
    print("refusal=sender_refused vendor_code=00: the credentials work, but the sender name in SSM is not among the account approved names")
' "$1"
}

netgsm_check() {
  # netgsm_check <usercode> <password> <msgheader>: read-only. Code 30 is a
  # wrong usercode or password, a sub-user with no API permission, or a
  # request from outside the account's IP restriction (this host's address
  # is its Elastic IP, 3.211.2.143).
  local user=$1 pass=$2 response verdict
  user=${user//\\/\\\\} pass=${pass//\\/\\\\}
  user=${user//\"/\\\"} pass=${pass//\"/\\\"}
  if ! response=$(printf 'user = "%s:%s"\n' "$user" "$pass" |
    curl --silent --show-error --max-time 15 --config - "$NETGSM_MSGHEADER_URL" 2>/dev/null); then
    log "netgsm check: refusal=- reason=unreachable (no answer from api.netgsm.com.tr)"
    return 1
  fi
  verdict=$(printf '%s' "$response" | netgsm_check_verdict "$3")
  log "netgsm check: $verdict"
  [[ $verdict == ok:* ]]
}

main() {
  local mode=sync
  case ${1:-} in
  --if-present) mode=if-present && shift ;;
  --check) mode=check && shift ;;
  esac
  [[ $# -eq 0 ]] || die "usage: netgsm_secrets.sh [--if-present | --check]"
  require_root
  if ! have_aws; then
    if [[ $mode == if-present ]]; then
      log "netgsm: not synced (no aws CLI on this host)"
      printf 'unchanged\n'
      return 0
    fi
    die "missing tool: aws (it reads the SSM parameters with the instance role)"
  fi

  local usercode="" password="" msgheader="" test_allowlist="" field missing=() root current
  usercode=$(ssm_parameter "${NETGSM_PARAMETER_PREFIX}usercode") || missing+=(usercode)
  password=$(ssm_parameter "${NETGSM_PARAMETER_PREFIX}password") || missing+=(password)
  msgheader=$(ssm_parameter "${NETGSM_PARAMETER_PREFIX}msgheader") || missing+=(msgheader)
  test_allowlist=$(ssm_parameter "$SMS_TEST_ALLOWLIST_PARAMETER") || missing+=(test_allowlist)
  if [[ $mode == if-present && ${#missing[@]} -eq 4 ]]; then
    log "netgsm: not synced (no Netgsm or SMS test allow-list parameter on this account)"
    printf 'unchanged\n'
    return 0
  fi
  if [[ $mode == check && ${#missing[@]} -gt 0 ]]; then
    # the check needs the credentials, not the allow-list
    local -a need=()
    for field in "${missing[@]}"; do
      [[ $field == test_allowlist ]] || need+=("$field")
    done
    missing=()
    ((${#need[@]} == 0)) || missing=("${need[@]}")
  fi
  ((${#missing[@]} == 0)) ||
    die "no readable SSM parameter for ${missing[*]} (${NETGSM_PARAMETER_PREFIX}<field> and ${SMS_TEST_ALLOWLIST_PARAMETER}, SecureString, readable by the instance role); nothing was written"
  for field in usercode password msgheader; do
    netgsm_value_ok "$field" "${!field}" ||
      die "$field is empty or malformed in ${NETGSM_PARAMETER_PREFIX}${field}; nothing was written (${ATTEST_SMS_RUNBOOK})"
  done
  if [[ $mode == check ]]; then
    netgsm_check "$usercode" "$password" "$msgheader"
    return
  fi
  test_allowlist=$(allowlist_numbers "$test_allowlist")
  [[ -n $test_allowlist ]] ||
    die "test_allowlist is empty or malformed in ${SMS_TEST_ALLOWLIST_PARAMETER} (Turkish mobiles in E.164, +905...); nothing was written"
  local listed=${test_allowlist//[^,]/}
  listed=$((${#listed} + 1))

  root=$(init_field root_token)
  ensure_secret_kv "$root"
  bao_as "$root" policy write intake-api - <"$STAGING_DIR/openbao/intake-api-policy.hcl" >/dev/null
  current=$( (bao_as "$root" kv get -mount=secret -format=json "$SMS_KV_PATH" 2>/dev/null || printf '{}') | netgsm_digest)
  if [[ $current == "$(printf '%s\0%s\0%s\0%s' "$usercode" "$password" "$msgheader" "$test_allowlist" | netgsm_document_json | netgsm_digest)" ]]; then
    unset usercode password msgheader test_allowlist
    log "secret/${SMS_KV_PATH}: already holds the SSM values; nothing written"
    printf 'unchanged\n'
    return 0
  fi
  printf '%s\0%s\0%s\0%s' "$usercode" "$password" "$msgheader" "$test_allowlist" | netgsm_document_json |
    bao_as "$root" kv put -mount=secret "$SMS_KV_PATH" - >/dev/null
  unset usercode password msgheader test_allowlist

  local unread
  unread=$(sms_document_as_api | sms_missing_fields)
  [[ -z $unread ]] ||
    die "secret/${SMS_KV_PATH} was written, but the API's token reads no value for ${unread}: re-run ./init.sh, then this script (${ATTEST_SMS_RUNBOOK})"
  log "secret/${SMS_KV_PATH}: usercode, password and msgheader written from SSM, with a test allow-list of ${listed} number(s); the API's token reads them (values not shown)"
  printf 'changed\n'
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
