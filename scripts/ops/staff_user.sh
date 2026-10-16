#!/usr/bin/env bash
# INT-538: one laptop command creates a staff user in the Keycloak realm
# `intake` on the synthetic staging host. The owner runs it for themselves
# first (platform_owner), then for the second approver (qms_owner). It
# replaces the manual steps of docs/runbooks/second-admin.md (INT-460), which
# stay there as the fallback.
#
# Usage, from a shell where the AWS CLI is signed in:
#   scripts/ops/staff_user.sh
# It prompts for the username, the email and the role, and takes no argument.
#
# What happens:
#   1. Each answer is checked before anything is sent. The role is
#      platform_owner or qms_owner, nothing else.
#   2. `openssl rand -hex 32` makes the temporary password, and it goes
#      straight into the SSM SecureString /intake/staging/staff_tmp/<username>.
#      It is never an argv element, never printed, never in shell history:
#      the shell's printf builtin writes the put-parameter request into a 0600
#      file in a fresh 0700 directory under $TMPDIR, `aws ssm put-parameter
#      --cli-input-json file://...` reads it, and the file is removed at once.
#      The AWS CLI reads a parameter file twice, so a pipe cannot replace the
#      file. `shred` is not used: macOS has none, and on APFS an overwrite
#      writes new blocks and leaves the old ones, so it would erase nothing.
#      The value is a one-time password. Keycloak makes its first sign-in
#      replace it, and the reveal command deletes the parameter.
#      A parameter that already exists is never overwritten.
#   3. infra/staging/staff_user_host.sh goes to the host base64-wrapped in an
#      AWS-RunShellScript command. Its arguments are the username, the email,
#      the role, the parameter's NAME and the region; no secret travels in
#      the command. On the host it reads the Keycloak bootstrap password
#      locally, reads the temporary password from SSM with the instance role,
#      and creates the user (see that file).
#   4. It prints "created" and the one command that reveals the temporary
#      password once and deletes the parameter. Hand the password over
#      privately (Signal or in person). On a refusal it prints the reason and
#      deletes the unused parameter.
#
# This is an operator action outside the console's four-eyes ceremony. Its
# record is CloudTrail (PutParameter, SendCommand) and the realm's own events.
set -euo pipefail
umask 077

USERNAME_SHAPE='^[a-z][a-z0-9._-]{2,63}$'
EMAIL_SHAPE='^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$'
ROLE_SHAPE='^(platform_owner|qms_owner)$'

die() {
  printf 'staff_user: %s\n' "$*" >&2
  exit 2
}

fail() {
  printf 'staff_user: %s\n' "$*" >&2
  exit 1
}

[[ $# -eq 0 ]] || die "takes no argument: it prompts for the username, email and role"

region=${AWS_REGION:-us-east-1}
instance=${INTAKE_HOST_INSTANCE_ID:-i-0e489e48739f5de98}
[[ $region =~ ^[a-z]{2}(-[a-z]+)+-[0-9]$ ]] || die "AWS_REGION is not an AWS region"
[[ $instance =~ ^i-[0-9a-f]{8,17}$ ]] || die "INTAKE_HOST_INSTANCE_ID is not an EC2 instance id"
host_script="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/infra/staging/staff_user_host.sh"
[[ -f $host_script ]] || fail "missing $host_script"

username=""
email=""
role=""
printf 'username: ' >&2
read -r username || true
[[ -n $username ]] || die "the username is empty"
[[ $username =~ $USERNAME_SHAPE ]] || die "the username must be 3-64 of a-z 0-9 . _ - and start with a letter"
printf 'email: ' >&2
read -r email || true
[[ -n $email ]] || die "the email is empty"
email=$(printf '%s' "$email" | tr '[:upper:]' '[:lower:]')
[[ ${#email} -le 254 && $email =~ $EMAIL_SHAPE && $email != *..* && $email != .* && $email != *.@* ]] ||
  die "the email is not an address"
printf 'role (platform_owner|qms_owner): ' >&2
read -r role || true
[[ -n $role ]] || die "the role is empty"
[[ $role =~ $ROLE_SHAPE ]] || die "the role must be platform_owner or qms_owner"

param="/intake/staging/staff_tmp/$username"
reveal="aws ssm get-parameter --region $region --name $param --with-decryption --query Parameter.Value --output text && aws ssm delete-parameter --region $region --name $param"

private=$(mktemp -d)
trap 'rm -rf "$private"' EXIT
chmod 0700 "$private"

# The temporary password exists only inside this subshell and the 0600 file.
if ! (
  pw=$(openssl rand -hex 32) || exit 1
  [[ $pw =~ ^[0-9a-f]{64}$ ]] || exit 1
  printf '{"Name":"%s","Type":"SecureString","Value":"%s"}' "$param" "$pw" >"$private/put.json"
); then
  fail "openssl did not generate a password; nothing was sent"
fi
put_rc=0
aws ssm put-parameter --region "$region" --cli-input-json "file://$private/put.json" >/dev/null 2>"$private/put.err" || put_rc=$?
rm -f "$private/put.json"
if [[ $put_rc -ne 0 ]]; then
  if grep -q ParameterAlreadyExists "$private/put.err"; then
    printf 'refused: a temporary password for %s is still waiting in SSM; reveal it (which deletes it) first:\n%s\n' "$username" "$reveal"
    exit 3
  fi
  fail "SSM did not store the temporary password (is the AWS CLI signed in?); nothing was sent"
fi

delete_param() {
  aws ssm delete-parameter --region "$region" --name "$param" >/dev/null 2>&1 || true
}

# The host command: this repo's host script, and five plain values. Every value
# was checked above, so none holds a quote, a backslash or a space.
b64=$(base64 <"$host_script" | tr -d '\n')
command="bash -c \"\$(printf %s '$b64' | base64 -d)\" staff_user_host '$username' '$email' '$role' '$param' '$region'"
printf '{"commands":["%s"]}\n' "${command//\"/\\\"}" >"$private/send.json"
if ! command_id=$(aws ssm send-command --region "$region" --instance-ids "$instance" \
  --document-name AWS-RunShellScript --comment "INT-538 staff user" \
  --parameters "file://$private/send.json" --query Command.CommandId --output text); then
  delete_param
  fail "SSM did not accept the host command; the temporary password was deleted"
fi

status=Pending
for _ in $(seq 1 60); do
  status=$(aws ssm get-command-invocation --region "$region" --command-id "$command_id" \
    --instance-id "$instance" --query Status --output text 2>/dev/null || echo Pending)
  case "$status" in
  Pending | InProgress | Delayed) sleep 2 ;;
  *) break ;;
  esac
done
out=$(aws ssm get-command-invocation --region "$region" --command-id "$command_id" \
  --instance-id "$instance" --query StandardOutputContent --output text 2>/dev/null || true)
line=$(printf '%s\n' "$out" | grep -m1 '^staff_user: ' || true)

case "$line" in
"staff_user: created")
  if [[ $status == Success ]]; then
    printf 'created\n%s\n' "$reveal"
    exit 0
  fi
  ;;
"staff_user: refused: "*)
  delete_param
  printf 'refused: %s\n' "${line#staff_user: refused: }"
  exit 3
  ;;
esac
printf 'unknown: host command %s ended %s without a result line; if the user exists, this reveals its temporary password once and deletes it:\n%s\n' "$command_id" "$status" "$reveal"
exit 1
