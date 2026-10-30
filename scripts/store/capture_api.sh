#!/usr/bin/env bash
# INT-502: the laptop half of the capture API (infra/staging/capture_api_host.sh).
#
#   scripts/store/capture_api.sh up <port>       start the capture API on the host's loopback
#   scripts/store/capture_api.sh forward <port>  forward the Mac's localhost:8000 to it (stays open)
#   scripts/store/capture_api.sh status          is it running
#   scripts/store/capture_api.sh down            remove it, its database and its Redis index
#
# The host script goes base64-wrapped in an AWS-RunShellScript command, the
# INT-538 pattern, so the host needs no deploy. Only the mode and the port cross
# to the host, and both are checked here first. No secret is ever in the command,
# and the script prints the host's one result line and nothing else. `forward`
# is an SSM port-forwarding session to the host's 127.0.0.1:<port>, so the
# security group stays at 80/443. It listens on the Mac's port 8000, the dev
# API port a development build probes on its Metro host
# (apps/mobile/src/lib/auth/expoApiBase.ts), so the simulator app finds the
# capture API with no configuration change.
set -euo pipefail

region=${AWS_REGION:-us-east-1}
instance=${INTAKE_HOST_INSTANCE_ID:-i-0e489e48739f5de98}
here=$(cd "$(dirname "$0")" && pwd)
host_script=${INTAKE_CAPTURE_HOST_SCRIPT:-$here/../../infra/staging/capture_api_host.sh}

die() {
  printf 'capture_api: %s\n' "$*" >&2
  exit 2
}

[[ $region =~ ^[a-z]{2}(-[a-z]+)+-[0-9]$ ]] || die "AWS_REGION is not an AWS region"
[[ $instance =~ ^i-[0-9a-f]{8,17}$ ]] || die "INTAKE_HOST_INSTANCE_ID is not an EC2 instance id"
mode=${1:-}
port=${2:-}
case $mode in
  up | forward)
    if ! [[ $port =~ ^[0-9]{4,5}$ ]] || ((port < 1024 || port > 65535)); then
      die "$mode needs a port, 1024-65535"
    fi
    ;;
  down | status) port="" ;;
  *) die "usage: capture_api.sh up <port> | forward <port> | status | down" ;;
esac

if [[ $mode == forward ]]; then
  exec aws ssm start-session --region "$region" --target "$instance" \
    --document-name AWS-StartPortForwardingSession \
    --parameters "portNumber=$port,localPortNumber=8000"
fi

private=$(mktemp -d)
trap 'rm -rf "$private"' EXIT
chmod 0700 "$private"
b64=$(base64 <"$host_script" | tr -d '\n')
# The single quotes are literal: the host's shell sees each argument quoted.
# shellcheck disable=SC2016
command="bash -c \"\$(printf %s '$b64' | base64 -d)\" capture_api_host '$mode'${port:+ '$port'}"
printf '{"commands":["%s"]}\n' "${command//\"/\\\"}" >"$private/send.json"
id=$(aws ssm send-command --region "$region" --instance-ids "$instance" \
  --document-name AWS-RunShellScript --comment "INT-502 capture API $mode" \
  --parameters "file://$private/send.json" --query Command.CommandId --output text) ||
  die "SSM did not accept the command; nothing changed on the host"
status=Pending
for _ in $(seq 1 90); do
  status=$(aws ssm get-command-invocation --region "$region" --command-id "$id" \
    --instance-id "$instance" --query Status --output text 2>/dev/null || echo Pending)
  case $status in
    Pending | InProgress | Delayed) sleep 2 ;;
    *) break ;;
  esac
done
out=$(aws ssm get-command-invocation --region "$region" --command-id "$id" \
  --instance-id "$instance" --query StandardOutputContent --output text 2>/dev/null || true)
line=$(printf '%s\n' "$out" | grep -m1 '^capture_api: ' || true)
printf '%s\n' "${line:-capture_api: no result line (SSM status $status)}"
[[ $status == Success ]]
