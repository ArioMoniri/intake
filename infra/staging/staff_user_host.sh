#!/usr/bin/env bash
# INT-538: the host half of scripts/ops/staff_user.sh. It creates one staff
# user in the Keycloak realm `intake` on the synthetic staging host.
#
# The laptop sends this file base64-wrapped in an AWS-RunShellScript command,
# so it reaches the host without a deploy. SSM runs it as root, in one of two
# modes:
#   bash -c "<this file>" staff_user_host probe <parameter> <region>
#   bash -c "<this file>" staff_user_host create <username> <email> <role> <parameter> <region> <org|->
# `probe` only reads. It reports the platform_owners' org, or that none exists
# yet, so the laptop knows whether to ask for an org. No argument is a
# secret. The temporary password waits in the SSM SecureString <parameter>
# until `create` reads it.
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
# platform_owner's org, and an org argument that differs is refused. Only
# when no platform_owner exists does the org come from the argument: the
# slug the owner typed for this very first user, who must be the
# platform_owner. An org is never invented.
#
# Both modes first check that the instance role may read the staff_tmp
# parameters, and name the exact IAM statement to add when it may not.
#
# Output is one line: "staff_user: created", "staff_user: owner-org <org>",
# "staff_user: no-owner", or "staff_user: refused: <why>" with exit 3. No
# credential value and no email is ever printed.
set -euo pipefail
umask 077
# byte-wise character classes: [a-z] is ASCII only, whatever SSM's locale
export LC_ALL=C

USERNAME_SHAPE='^[a-z][a-z0-9._-]{2,63}$'
EMAIL_SHAPE='^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$'
ROLE_SHAPE='^(platform_owner|qms_owner)$'
ORG_SLUG='^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$'
REGION_SHAPE='^[a-z]{2}(-[a-z]+)+-[0-9]$'
# the realm's user-profile validation for org (intake-realm.json)
ORG_SHAPE='^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$'
HEX64='^[0-9a-f]{64}$'
ID_SHAPE='^[A-Za-z0-9-]{1,64}$'
STAFF_TMP=/intake/staging/staff_tmp

ENV_FILE=${INTAKE_STAGING_ENV_FILE:-/etc/intake-staging/.env}
CONTAINER=${INTAKE_KEYCLOAK_CONTAINER:-intake-staging-keycloak-1}
KCADM=/opt/keycloak/bin/kcadm.sh
REALM=intake
# Runs inside the container. The password arrives on its stdin; `read` is a
# builtin, and kcadm reads KC_CLI_PASSWORD from its own environment.
# shellcheck disable=SC2016 # $1 expands inside the container: the --config path
LOGIN='IFS= read -r KC_CLI_PASSWORD && export KC_CLI_PASSWORD && exec /opt/keycloak/bin/kcadm.sh config credentials --config "$1" --server http://localhost:8080 --realm master --user intake-bootstrap'
cfg_dir=""
cfg=""
owner_org=""

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

# The instance role must be allowed to read $STAFF_TMP/*. Without decryption
# the lookup returns only the name, so neither answer carries a secret; a
# parameter that does not exist yet still proves the permission.
check_ssm_read() {
  local found arn role
  found=$(aws ssm get-parameter --region "$region" --name "$param" --query Parameter.Name --output text 2>&1) || true
  case $found in
  "$param" | *ParameterNotFound*) return 0 ;;
  *AccessDenied*)
    arn=$(printf '%s\n' "$found" | grep -oE 'arn:aws:ssm:[a-z0-9-]+:[0-9]{12}:parameter' | head -n 1) || true
    role=$(printf '%s\n' "$found" | grep -oE 'assumed-role/[A-Za-z0-9+=,.@_-]+' | head -n 1) || true
    [[ -n $arn ]] || arn="arn:aws:ssm:$region:<this account>:parameter"
    refuse "the instance role${role:+ ${role#assumed-role/}} may not read $STAFF_TMP/*: add {\"Effect\":\"Allow\",\"Action\":\"ssm:GetParameter\",\"Resource\":\"$arn$STAFF_TMP/*\"} to its policy"
    ;;
  *) refuse "SSM did not answer the lookup of $param" ;;
  esac
}

log_in() {
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
}

# Sets owner_org to the one org every platform_owner shares, or leaves it
# empty when there is no platform_owner.
read_owner_org() {
  local owners owner this
  owners=$(kc get roles/platform_owner/users --fields id --format csv --noquotes 2>/dev/null) ||
    refuse "Keycloak did not list the platform_owner users"
  while IFS= read -r owner; do
    [[ -n $owner ]] || continue
    [[ $owner =~ $ID_SHAPE ]] || refuse "Keycloak returned a user id of an unexpected shape"
    this=$(kc get "users/$owner" --fields attributes 2>/dev/null |
      python3 -c 'import json, sys
values = (json.load(sys.stdin).get("attributes") or {}).get("org") or []
print(values[0] if len(values) == 1 and isinstance(values[0], str) else "")') ||
      refuse "Keycloak did not return a platform_owner's attributes"
    [[ -n $this ]] || refuse "a platform_owner has no org attribute"
    [[ -z $owner_org || $owner_org == "$this" ]] || refuse "the platform_owners do not share one org"
    owner_org=$this
  done <<<"$owners"
  [[ -z $owner_org || $owner_org =~ $ORG_SHAPE ]] || refuse "the platform_owner's org is not org-shaped (the realm's user-profile rule)"
}

mode=${1:-}
case $mode in
probe)
  [[ $# -eq 3 ]] || refuse "probe expects the parameter and the region"
  param=$2
  region=$3
  [[ $param =~ ^/intake/staging/staff_tmp/[a-z][a-z0-9._-]{2,63}$ ]] || refuse "the parameter is not a staff_tmp one"
  [[ $region =~ $REGION_SHAPE ]] || refuse "the region is not an AWS region"
  check_ssm_read
  log_in
  read_owner_org
  if [[ -n $owner_org ]]; then
    printf 'staff_user: owner-org %s\n' "$owner_org"
  else
    printf 'staff_user: no-owner\n'
  fi
  exit 0
  ;;
create) ;;
*) refuse "the mode is neither probe nor create" ;;
esac

[[ $# -eq 7 ]] || refuse "create expects username, email, role, parameter, region and org"
username=$2
email=$3
role=$4
param=$5
region=$6
org_arg=$7
[[ $username =~ $USERNAME_SHAPE ]] || refuse "the username is not Keycloak-safe"
[[ ${#email} -le 254 && $email =~ $EMAIL_SHAPE && $email != *..* && $email != .* && $email != *.@* ]] ||
  refuse "the email is not an address"
[[ $role =~ $ROLE_SHAPE ]] || refuse "the role is neither platform_owner nor qms_owner"
[[ $param == "$STAFF_TMP/$username" ]] || refuse "the parameter is not this user's"
[[ $region =~ $REGION_SHAPE ]] || refuse "the region is not an AWS region"
[[ $org_arg == - || $org_arg =~ $ORG_SLUG ]] || refuse "the org is not a slug"

check_ssm_read
log_in

existing=$(kc get users -q "username=$username" -q exact=true --fields username --format csv --noquotes 2>/dev/null) ||
  refuse "Keycloak did not answer the username lookup"
[[ -z $existing ]] || refuse "the username $username already exists in realm $REALM"
existing=$(kc get users -q "email=$email" -q exact=true --fields username --format csv --noquotes 2>/dev/null) ||
  refuse "Keycloak did not answer the email lookup"
[[ -z $existing ]] || refuse "that email already belongs to a user in realm $REALM"

read_owner_org
if [[ -n $owner_org ]]; then
  [[ $org_arg == - || $org_arg == "$owner_org" ]] ||
    refuse "a platform_owner exists and the org given differs from theirs"
  org=$owner_org
else
  [[ $role == platform_owner ]] ||
    refuse "no platform_owner exists yet: create the platform_owner first; the second approver joins their org"
  [[ $org_arg != - ]] || refuse "no platform_owner exists and no org was given for the first one"
  org=$org_arg
fi

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
