#!/usr/bin/env bash
# INT-463, INT-467 — operate the intake-aws-ci runner pool on the AWS host from
# the laptop. Needs a live `aws` session (only the owner runs `aws login`) and
# an authenticated `gh`.
#
#   scripts/ci/aws_runner.sh install [--ref <rev>]
#       ships infra/ci/aws-runner at <rev> (default HEAD) to the host as a
#       sha256-pinned archive over S3 + a presigned URL, and runs install.sh
#       as root over SSM. It drains every runner first: each stops once it
#       holds no job, so the command can take as long as the longest job.
#   scripts/ci/aws_runner.sh token
#       mints a one-hour registration token with gh and hands it to the host.
#       Only a fallback: each runner's registrar mints a fresh one before every
#       registration from the owner's admin token in SSM
#       (/intake/staging/gh_runner_admin_pat), which never leaves the host.
#   scripts/ci/aws_runner.sh status
#       each runner's unit states, the GitHub registrations and df; no credential
#   scripts/ci/aws_runner.sh probe [N ...]
#       the isolation probe (probe.sh) on every runner, or on runners N:
#       each one, as its user inside its job sandbox, against staging, the
#       host and the other runners. Run it while the pool is idle.
#   scripts/ci/aws_runner.sh seed [--ref <rev>]
#       INT-544: stages the cache seed's inputs: the lockfiles and manifests at
#       <rev> (default HEAD) and the deid release asset its Makefile pins,
#       checked against that pin. No source file, credential or PHI. They go
#       as one sha256-pinned bundle over S3 + a presigned URL to seed.sh
#       stage; each runner's registrar rebuilds its seed between jobs. No drain.
#   scripts/ci/aws_runner.sh headroom
#       INT-544: reads, and changes nothing: CPU, memory and IO pressure, the
#       pool slice's ceiling and peak, staging's containers, and both disks.
#       What it prints decides how many runners fit (docs/evidence/INT-544.md).
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
  # $1: registration. The credential arrives on stdin.
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
bash \"\$work/infra/ci/aws-runner/install.sh\"" 3600
}

cmd_token() {
  say "minting a one-hour registration token for $REPO_SLUG (not shown)"
  gh api -X POST "repos/$REPO_SLUG/actions/runners/registration-token" --jq .token | hand_over registration
}

cmd_status() {
  # shellcheck disable=SC2016  # expands on the host, from the host's runner.conf
  ssm_run '. /usr/local/lib/intake-aws-ci-runner/runner.conf
for n in $POOL_INSTANCES; do
  echo "runner $n: $(systemctl is-active intake-aws-ci-runner@$n.service intake-aws-ci-dockerd@$n.service intake-aws-ci-diskwatch@$n.timer | tr "\n" " ")"
done
journalctl -u "intake-aws-ci-runner@*" -n 30 --no-pager -o cat | grep -E "^intake-aws-ci|Listening|Running job|completed with result" || true
df -h / /opt/dlami/nvme' 120 || true
  gh api "repos/$REPO_SLUG/actions/runners" --jq '.runners[] | [.name, .status, (.busy|tostring), ([.labels[].name]|join(","))] | @tsv'
}

instances_arg() {
  # The runner numbers on the command line, each checked; none means every runner.
  local n
  for n in "$@"; do
    [[ "$n" =~ ^[1-9]$ ]] || die "'$n' is not a runner number"
  done
  printf '%s' "$*"
}

cmd_probe() {
  local instances
  instances=$(instances_arg "$@")
  ssm_run "$LIB_DIR/bin/probe.sh $instances" 900
}

cmd_seed() {
  local ref=HEAD rev tag pin sha key url path files=()
  if [ "${1:-}" = --ref ]; then
    ref=${2:?--ref needs a revision}
  fi
  rev=$(git -C "$ROOT" rev-parse --verify "$ref^{commit}")
  tag=$(git -C "$ROOT" show "$rev:Makefile" | sed -n 's/^DEID_MODEL_TAG := //p')
  pin=$(git -C "$ROOT" show "$rev:Makefile" | sed -n 's/^DEID_MODEL_SHA256 := //p')
  [[ "$tag" =~ ^[a-z0-9-]+$ && "$pin" =~ ^[0-9a-f]{64}$ ]] || die "the Makefile at $rev pins no deid asset"
  SEED_STAGE=$(mktemp -d)
  trap 'rm -rf "$SEED_STAGE"' EXIT
  local stage=$SEED_STAGE
  mkdir -p "$stage/bundle/tree" "$stage/bundle/deid"
  while IFS= read -r path; do
    files+=("$path")
  done < <(git -C "$ROOT" ls-tree -r --name-only "$rev" |
    grep -E '^(uv\.lock|\.python-version|pnpm-lock\.yaml|pnpm-workspace\.yaml)$|(^|/)(pyproject\.toml|package\.json)$' |
    grep -v '^\.claude/')
  git -C "$ROOT" archive --format=tar "$rev" -- "${files[@]}" | tar -x -C "$stage/bundle/tree"
  gh release download "$tag" -R "$REPO_SLUG" -p "$tag.tar.gz" -O "$stage/bundle/deid/$tag.tar.gz"
  [ "$(shasum -a 256 "$stage/bundle/deid/$tag.tar.gz" | awk '{ print $1 }')" = "$pin" ] ||
    die "the $tag release asset does not match the Makefile's pin"
  printf '%s\n' "$rev" >"$stage/bundle/REF"
  COPYFILE_DISABLE=1 tar -C "$stage/bundle" -czf "$stage/bundle.tar.gz" .
  sha=$(shasum -a 256 "$stage/bundle.tar.gz" | awk '{ print $1 }')
  key="ci/aws-runner/seed-$sha.tar.gz"
  aws s3 cp --quiet --region "$REGION" "$stage/bundle.tar.gz" "s3://$BUCKET/$key"
  url=$(aws s3 presign --region "$REGION" "s3://$BUCKET/$key" --expires-in 900)
  say "staging the cache seed's inputs from $(git -C "$ROOT" rev-parse --short "$rev"): ${#files[@]} lockfiles and manifests and $tag (bundle sha256 $sha)"
  ssm_run "$LIB_DIR/bin/seed.sh stage '$url' $sha" 900
}

cmd_headroom() {
  # Read-only. Each line names what it measures; nothing is started or changed.
  # shellcheck disable=SC2016  # expands on the host
  ssm_run 'echo "== cpu: cores, load, pressure"; nproc; cat /proc/loadavg; cat /proc/pressure/cpu
echo "== memory: host, pressure"; free -g; cat /proc/pressure/memory; cat /proc/pressure/io
echo "== the pool slice: ceiling, now and peak since it started"
systemctl show intake-aws-ci.slice -p CPUQuotaPerSecUSec -p MemoryHigh -p MemoryMax -p MemoryCurrent -p MemoryPeak -p CPUUsageNSec -p ActiveEnterTimestamp
cat /sys/fs/cgroup/intake-aws-ci.slice/memory.peak /sys/fs/cgroup/intake-aws-ci.slice/cpu.pressure /sys/fs/cgroup/intake-aws-ci.slice/memory.pressure 2>/dev/null
echo "== staging containers"; docker stats --no-stream --format "{{.Name}} {{.CPUPerc}} {{.MemUsage}}" 2>/dev/null
echo "== disks"; df -h / /opt/dlami/nvme; findmnt -no FSTYPE /opt/dlami/nvme
echo "== the pool"; grep -E "^POOL_INSTANCES=" /usr/local/lib/intake-aws-ci-runner/runner.conf
for d in /opt/dlami/nvme/intake-aws-ci-[0-9]*/seed; do [ -e "$d/current" ] && echo "$d $(readlink "$d/current") $(du -sh "$d/current/" | cut -f1)"; done' 300 || true
}

case "${1:-}" in
  install) cmd_install "${@:2}" ;;
  token) cmd_token ;;
  status) cmd_status ;;
  probe) cmd_probe "${@:2}" ;;
  seed) cmd_seed "${@:2}" ;;
  headroom) cmd_headroom ;;
  *)
    sed -n '2,37p' "$0" >&2
    exit 2
    ;;
esac
