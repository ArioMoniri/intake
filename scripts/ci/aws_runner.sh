#!/usr/bin/env bash
# INT-463 — operate the intake-aws-ci GitHub Actions runner on the AWS host
# from the laptop. Needs a live `aws` session (only the owner runs `aws login`)
# and an authenticated `gh`.
#
#   scripts/ci/aws_runner.sh install [--ref <rev>]
#       ships infra/ci/aws-runner at <rev> (default HEAD) to the host as a
#       sha256-pinned archive over S3 + a presigned URL, and runs install.sh
#       as root over SSM
#   scripts/ci/aws_runner.sh token
#       mints a one-hour registration token with gh and hands it to the host
#   scripts/ci/aws_runner.sh registrar
#       reads a fine-grained token (this repository only, Administration:
#       read and write) from stdin and hands it to the host, so the runner
#       re-registers after every job without a laptop
#   scripts/ci/aws_runner.sh status
#       unit states, the GitHub registration and df; no credential
#
# A credential never appears on a command line, in an SSM command, in a log or
# in the repository. It travels from a pipe into SSM Parameter Store as a
# SecureString under a one-off name. The SSM command names only that
# parameter. The host reads it with its instance role, and the parameter is
# deleted when the command returns, whatever its outcome.
set -euo pipefail
set +x

INSTANCE=${AWS_CI_INSTANCE:-i-0e489e48739f5de98}
REGION=${AWS_CI_REGION:-us-east-1}
BUCKET=${AWS_CI_BUCKET:-onvizit-deploy-artefacts-235229001983}
REPO_SLUG=ArioMoniri/intake
LIB_DIR=/usr/local/lib/intake-aws-ci-runner
ROOT=$(cd "$(dirname "$0")/../.." && pwd)

say() { printf 'aws_runner: %s\n' "$*" >&2; }
die() {
  say "FAIL: $*"
  exit 1
}

ssm_run() {
  # $1: a shell script body (no secret in it), $2: timeout in seconds.
  local body=$1 timeout=${2:-900} params cid status
  params=$(python3 -c 'import json, sys; print(json.dumps({"commands": [sys.argv[1]], "executionTimeout": [sys.argv[2]]}))' "$body" "$timeout")
  cid=$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
    --document-name AWS-RunShellScript --comment "INT-463 intake-aws-ci runner" \
    --parameters "$params" --query Command.CommandId --output text)
  while :; do
    status=$(aws ssm get-command-invocation --region "$REGION" --command-id "$cid" \
      --instance-id "$INSTANCE" --query Status --output text 2>/dev/null || echo Pending)
    case "$status" in
      Pending | InProgress | Delayed) sleep 5 ;;
      *) break ;;
    esac
  done
  aws ssm get-command-invocation --region "$REGION" --command-id "$cid" --instance-id "$INSTANCE" \
    --query '[StandardOutputContent, StandardErrorContent]' --output text
  [ "$status" = Success ]
}

hand_over() {
  # $1: registration|registrar. The credential arrives on stdin.
  local kind=$1 name rc=0 private
  name="/intake/aws-ci-runner/$kind-$(date -u +%Y%m%d%H%M%S)-$RANDOM"
  # The aws CLI cannot read a parameter file from a pipe, so the request lives
  # for about a second in a 0600 file inside a private 0700 directory, outside
  # the repository, and is removed before anything else runs.
  private=$(mktemp -d)
  chmod 0700 "$private"
  (
    umask 077
    python3 -c '
import json, re, sys
value = sys.stdin.read().strip()
if not re.fullmatch(r"[A-Za-z0-9_-]{20,255}", value):
    sys.exit("aws_runner: the credential on stdin does not have the expected shape")
json.dump({"Name": sys.argv[1], "Type": "SecureString", "Overwrite": True, "Value": value}, sys.stdout)
' "$name" >"$private/request.json"
  ) || {
    rm -rf "$private"
    return 1
  }
  aws ssm put-parameter --region "$REGION" --cli-input-json "file://$private/request.json" >/dev/null || rc=$?
  rm -rf "$private"
  if [ "$rc" -ne 0 ]; then
    return "$rc"
  fi
  ssm_run "$LIB_DIR/bin/fetch-credential.sh $kind $name" 120 || rc=$?
  aws ssm delete-parameter --region "$REGION" --name "$name" >/dev/null 2>&1 || true
  return "$rc"
}

cmd_install() {
  local ref=HEAD sha key url
  if [ "${1:-}" = --ref ]; then
    ref=${2:?--ref needs a revision}
  fi
  ARCHIVE=$(mktemp)
  trap 'rm -f "$ARCHIVE"' EXIT
  local archive=$ARCHIVE
  git -C "$ROOT" archive --format=tar.gz "$ref" infra/ci/aws-runner >"$archive"
  sha=$(shasum -a 256 "$archive" | awk '{ print $1 }')
  key="ci/aws-runner/$sha.tar.gz"
  aws s3 cp --quiet --region "$REGION" "$archive" "s3://$BUCKET/$key"
  url=$(aws s3 presign --region "$REGION" "s3://$BUCKET/$key" --expires-in 900)
  say "installing infra/ci/aws-runner at $(git -C "$ROOT" rev-parse --short "$ref") (archive sha256 $sha)"
  ssm_run "set -eu
work=\$(mktemp -d)
trap 'rm -rf \"\$work\"' EXIT
curl -fsS -o \"\$work/r.tar.gz\" '$url'
echo '$sha  '\"\$work/r.tar.gz\" | sha256sum -c --quiet
tar -xzf \"\$work/r.tar.gz\" -C \"\$work\"
bash \"\$work/infra/ci/aws-runner/install.sh\"" 1800
}

cmd_token() {
  say "minting a one-hour registration token for $REPO_SLUG (not shown)"
  gh api -X POST "repos/$REPO_SLUG/actions/runners/registration-token" --jq .token | hand_over registration
}

cmd_registrar() {
  [ ! -t 0 ] || die "pipe the token on stdin, e.g. pbpaste | scripts/ci/aws_runner.sh registrar"
  hand_over registrar
}

cmd_status() {
  ssm_run "systemctl is-active intake-aws-ci-dockerd.service intake-aws-ci-runner.service intake-aws-ci-diskwatch.timer || true
journalctl -u intake-aws-ci-runner.service -n 15 --no-pager -o cat | grep -E '^intake-aws-ci|Listening|Running job|completed with result' || true
df -h / /opt/dlami/nvme" 120 || true
  gh api "repos/$REPO_SLUG/actions/runners" --jq '.runners[] | [.name, .status, (.busy|tostring), ([.labels[].name]|join(","))] | @tsv'
}

case "${1:-}" in
  install) cmd_install "${@:2}" ;;
  token) cmd_token ;;
  registrar) cmd_registrar ;;
  status) cmd_status ;;
  *)
    sed -n '2,20p' "$0" >&2
    exit 2
    ;;
esac
