#!/usr/bin/env bash
# INT-428 (ADR-035): put one hosted-provider API key onto the synthetic AWS
# host from the owner's Mac. It is the terminal twin of the admin console's
# key-set ceremony, and ends in the same OpenBao record
# (secret/model-lanes/providers/<provider>).
#
# Usage, in a shell that already holds the key:
#   set -a; . ~/.intake-secrets.env; set +a; scripts/ops/put_provider_key.sh openai
#
# The key is read from an environment variable and is never an argument of any
# process, so `ps` cannot show it:
#   - The variable is OPENAI_API_KEY for openai and TTS_ELEVENLABS_API_KEY for
#     elevenlabs (ADR-028's name). KEY_ENV=<NAME> overrides it.
#   - It is written with the shell's printf builtin into a 0600 temp file,
#     which `aws ssm put-parameter --cli-input-json file://...` reads.
#   - It is stored as the SecureString /intake/staging/<provider>_api_key under
#     the account's aws/ssm KMS key. CloudTrail records a SecureString value as
#     hidden, and the temp file is removed on exit.
#
# The host is then sent a command whose only argument is the provider id:
# infra/staging/load_provider_key.sh reads the parameter with the instance role
# and pipes it into OpenBao. deploy.sh re-loads the same parameter on every
# deploy, so the terminal, the deploy and the console agree.
#
# Output is "set · …last4" or "not set", and nothing else of the key.
#
# This route is an operator action outside the console's four-eyes ceremony.
# Its record is CloudTrail (PutParameter, SendCommand), not the console's audit
# chain. Use the console when two people are available.
set -euo pipefail
umask 077

die() {
  printf 'put_provider_key: %s\n' "$*" >&2
  exit 2
}

provider=${1:-}
case "$provider" in
openai) default_env=OPENAI_API_KEY ;;
elevenlabs) default_env=TTS_ELEVENLABS_API_KEY ;;
*) die "usage: put_provider_key.sh openai|elevenlabs (the key is read from the environment)" ;;
esac
[[ $# -eq 1 ]] || die "the key is never an argument: load it into the environment instead"

env_name=${KEY_ENV:-$default_env}
[[ $env_name =~ ^[A-Z_][A-Z0-9_]*$ ]] || die "KEY_ENV must name an environment variable"
region=${AWS_REGION:-us-east-1}
instance=${INTAKE_HOST_INSTANCE_ID:-i-0e489e48739f5de98}
release_dir=${INTAKE_HOST_STAGING_DIR:-/opt/intake/infra/staging}
param="/intake/staging/${provider}_api_key"

value=${!env_name:-}
if [[ -z $value ]]; then
  printf '%s: not set ($%s is empty in this shell)\n' "$provider" "$env_name"
  exit 3
fi
if ! [[ $value =~ ^[A-Za-z0-9_.-]{20,}$ && ${#value} -le 512 ]]; then
  unset value
  die "the value in \$${env_name} is not key-shaped (20-512 of [A-Za-z0-9_.-]); nothing was sent"
fi
last4=${value: -4}

tmp=$(mktemp)
params=$(mktemp)
trap 'rm -f "$tmp" "$params"' EXIT
# printf is a builtin: the value is never an argv element of any process. The
# key alphabet needs no JSON escaping (checked above).
printf '{"Name":"%s","Type":"SecureString","Overwrite":true,"Value":"%s"}' \
  "$param" "$value" >"$tmp"
unset value
aws ssm put-parameter --region "$region" --cli-input-json "file://$tmp" >/dev/null
rm -f "$tmp"

printf '{"commands":["cd %s && ./load_provider_key.sh %s"]}' "$release_dir" "$provider" >"$params"
command_id=$(aws ssm send-command --region "$region" --instance-ids "$instance" \
  --document-name AWS-RunShellScript --comment "INT-428 load provider key ${provider}" \
  --parameters "file://$params" --query Command.CommandId --output text)

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

# Report the host's status line only when it names the same last four.
if [[ $status == Success ]] && printf '%s\n' "$out" | grep -qxF "${provider}: set · …${last4}"; then
  printf '%s: set · …%s\n' "$provider" "$last4"
else
  printf '%s: not set (host command %s: %s)\n' "$provider" "$command_id" "$status"
  exit 1
fi
