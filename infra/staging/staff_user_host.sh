#!/usr/bin/env bash
# INT-538: the host half of scripts/ops/staff_user.sh. It creates one staff
# user in the Keycloak realm `intake` on the synthetic staging host.
#
# The laptop sends this file base64-wrapped in an AWS-RunShellScript command,
# so it reaches the host without a deploy. SSM runs it as root:
#   bash -c "<this file>" staff_user_host <username> <email> <role> <parameter> <region>
# None of the five arguments is a secret. The temporary password waits in the
# SSM SecureString <parameter> until this script reads it.
#
# Secrets, all three of them:
#   - KEYCLOAK_ADMIN_PASSWORD is read from the host's root-only env file into
#     one variable. It reaches the container on docker exec's stdin, where a
#     bash builtin reads it into KC_CLI_PASSWORD, the variable kcadm (26.0 and
#     later) reads instead of prompting. It is never an argv of any process,
#     and never in the docker CLI's environment.
#   - kcadm keeps its session tokens in a --config file inside a fresh 0700
#     directory in the container. The directory is removed on exit, whatever
#     the outcome.
#   - The temporary password is read from SSM with the instance role into one
#     variable. It reaches kcadm's reset-password on stdin, marked temporary,
#     so the first sign-in must replace it.
#
# The org rule (docs/runbooks/second-admin.md): staff share the
# platform_owner's org. When no platform_owner exists yet, the org is the one
# the realm config names in attributes."intake.first_staff_org"
# (infra/staging/keycloak/intake-realm.json). When it names none, the script
# refuses: an org is never invented.
#
# Output is one line: "staff_user: created", or "staff_user: refused: <why>"
# with exit 3. No credential value and no email is ever printed.
set -euo pipefail
umask 077

USERNAME_SHAPE='^[a-z][a-z0-9._-]{2,63}$'
EMAIL_SHAPE='^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$'
ROLE_SHAPE='^(platform_owner|qms_owner)$'
# the realm's user-profile validation for org (intake-realm.json)
ORG_SHAPE='^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$'
HEX64='^[0-9a-f]{64}$'
ID_SHAPE='^[A-Za-z0-9-]{1,64}$'

ENV_FILE=${INTAKE_STAGING_ENV_FILE:-/etc/intake-staging/.env}
REALM_FILE=${INTAKE_STAFF_REALM_FILE:-/opt/intake/infra/staging/keycloak/intake-realm.json}
CONTAINER=${INTAKE_KEYCLOAK_CONTAINER:-intake-staging-keycloak-1}
KCADM=/opt/keycloak/bin/kcadm.sh
REALM=intake
# Runs inside the container. The password arrives on its stdin; `read` is a
# builtin, and kcadm reads KC_CLI_PASSWORD from its own environment.
# shellcheck disable=SC2016 # $1 expands inside the container: the --config path
LOGIN='IFS= read -r KC_CLI_PASSWORD && export KC_CLI_PASSWORD && exec /opt/keycloak/bin/kcadm.sh config credentials --config "$1" --server http://localhost:8080 --realm master --user intake-bootstrap'
cfg_dir=""
cfg=""

refuse() {
  printf 'staff_user: refused: %s\n' "$*"
  exit 3
}

cleanup() {
  if [[ -n $cfg_dir ]]; then
    docker exec "$CONTAINER" rm -rf -- "$cfg_dir" >/dev/null 2>&1 || true
  fi
}

# One kcadm call on the throwaway session. No -i: stdin stays with this script.
kc() {
  local verb=$1
  shift
  docker exec "$CONTAINER" "$KCADM" "$verb" "$@" --config "$cfg" -r "$REALM"
}

[[ $# -eq 5 ]] || refuse "expected username, email, role, parameter and region"
username=$1
email=$2
role=$3
param=$4
region=$5
[[ $username =~ $USERNAME_SHAPE ]] || refuse "the username is not Keycloak-safe"
[[ ${#email} -le 254 && $email =~ $EMAIL_SHAPE && $email != *..* && $email != .* && $email != *.@* ]] ||
  refuse "the email is not an address"
[[ $role =~ $ROLE_SHAPE ]] || refuse "the role is neither platform_owner nor qms_owner"
[[ $param == "/intake/staging/staff_tmp/$username" ]] || refuse "the parameter is not this user's"
[[ $region =~ ^[a-z]{2}(-[a-z]+)+-[0-9]$ ]] || refuse "the region is not an AWS region"

admin_pw=$(awk -v k=KEYCLOAK_ADMIN_PASSWORD 'index($0, k "=") == 1 { v = substr($0, length(k) + 2) } END { if (v != "") print v }' "$ENV_FILE" 2>/dev/null) || true
[[ $admin_pw =~ $HEX64 ]] || refuse "KEYCLOAK_ADMIN_PASSWORD is not readable in the host's env file"

trap cleanup EXIT
cfg_dir=/tmp/kcadm-staff-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')
cfg=$cfg_dir/kcadm.config
docker exec "$CONTAINER" mkdir -m 0700 -- "$cfg_dir" >/dev/null 2>&1 ||
  refuse "the Keycloak container $CONTAINER is not running"
printf '%s\n' "$admin_pw" | docker exec -i "$CONTAINER" bash -c "$LOGIN" kcadm-login "$cfg" >/dev/null 2>&1 ||
  {
    unset admin_pw
    refuse "kcadm could not log in as the bootstrap admin"
  }
unset admin_pw

existing=$(kc get users -q "username=$username" -q exact=true --fields username --format csv --noquotes 2>/dev/null) ||
  refuse "Keycloak did not answer the username lookup"
[[ -z $existing ]] || refuse "the username $username already exists in realm $REALM"
existing=$(kc get users -q "email=$email" -q exact=true --fields username --format csv --noquotes 2>/dev/null) ||
  refuse "Keycloak did not answer the email lookup"
[[ -z $existing ]] || refuse "that email already belongs to a user in realm $REALM"

# The org: the platform_owners' one org, or the realm config's first org.
owners=$(kc get roles/platform_owner/users --fields id --format csv --noquotes 2>/dev/null) ||
  refuse "Keycloak did not list the platform_owner users"
org=""
while IFS= read -r owner; do
  [[ -n $owner ]] || continue
  [[ $owner =~ $ID_SHAPE ]] || refuse "Keycloak returned a user id of an unexpected shape"
  owner_org=$(kc get "users/$owner" --fields attributes 2>/dev/null |
    python3 -c 'import json, sys
values = (json.load(sys.stdin).get("attributes") or {}).get("org") or []
print(values[0] if len(values) == 1 and isinstance(values[0], str) else "")') ||
    refuse "Keycloak did not return a platform_owner's attributes"
  [[ -n $owner_org ]] || refuse "a platform_owner has no org attribute"
  [[ -z $org || $org == "$owner_org" ]] || refuse "the platform_owners do not share one org"
  org=$owner_org
done <<<"$owners"
if [[ -z $org ]]; then
  org=$(python3 -c 'import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        value = (json.load(handle).get("attributes") or {}).get("intake.first_staff_org", "")
except (OSError, ValueError, AttributeError):
    value = ""
print(value if isinstance(value, str) else "")' "$REALM_FILE") || org=""
  [[ -n $org ]] || refuse "no platform_owner exists and the realm config names no org for the first one: the owner sets attributes.\"intake.first_staff_org\" in infra/staging/keycloak/intake-realm.json and deploys"
fi
[[ $org =~ $ORG_SHAPE ]] || refuse "the org is not org-shaped (the realm's user-profile rule)"

tmp_pw=$(aws ssm get-parameter --region "$region" --name "$param" --with-decryption --query Parameter.Value --output text 2>/dev/null) || true
[[ $tmp_pw =~ $HEX64 ]] || {
  unset tmp_pw
  refuse "the temporary password is not in SSM, or is not a generated one"
}

uid=$(kc create users -s "username=$username" -s "email=$email" -s enabled=true -s emailVerified=true \
  -s "attributes.org=[\"$org\"]" -s 'requiredActions=["webauthn-register","UPDATE_PASSWORD"]' -i 2>/dev/null) || {
  unset tmp_pw
  refuse "Keycloak did not create the user"
}
[[ $uid =~ $ID_SHAPE ]] || {
  unset tmp_pw
  refuse "Keycloak returned a user id of an unexpected shape"
}

rollback() {
  unset tmp_pw
  kc delete "users/$uid" >/dev/null 2>&1 || true
  refuse "$1; the user was removed again"
}

kc add-roles --uid "$uid" --rolename "$role" >/dev/null 2>&1 || rollback "the role could not be granted"
printf '{"type":"password","temporary":true,"value":"%s"}' "$tmp_pw" | docker exec -i "$CONTAINER" "$KCADM" update "users/$uid/reset-password" --config "$cfg" -r "$REALM" -n -f - >/dev/null 2>&1 ||
  rollback "the temporary password could not be set"
unset tmp_pw
printf 'staff_user: created\n'
