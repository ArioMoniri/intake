#!/usr/bin/env bash
# INT-426 — run the CI gate set for one commit on the AWS host, and post the
# verdict as the GitHub commit status `aws-ci` (docs/ci/aws-ci.md).
#
#   make ci-aws PR=<n>            # an open PR whose branch lives in this repo
#   make ci-aws REF=<40-hex sha>  # any pushed commit, e.g. main's head
#   scripts/ci/aws_ci.sh --pr <n> | --ref <sha> [--no-status]
#
# It uses the deploy path INT-352 established: S3 for the artefacts, presigned
# URLs, and SSM AWS-RunShellScript on the host. The laptop runs no container
# and holds no repository state on the host; the host holds no GitHub token.
#
#   1. Resolve the head sha. A PR from a fork is refused (aws_ci_lib.pr_head).
#   2. Bundle the commit with its history (gitleaks in `make security` reads
#      history), and `git archive` the harness from THIS checkout's HEAD.
#      The harness must be committed, so the run names the harness it used.
#   3. Upload both to the private deploy bucket (objects expire in 7 days)
#      and presign each for 30 minutes.
#   4. Post `aws-ci: pending`, then run scripts/ci/aws_ci_host.sh over SSM
#      and wait.
#   5. Presign a PUT only now, so a long queue never outlives a URL. The host
#      uploads the redacted log, provided the scanners passed it.
#   6. Post the final status, linking the log for as long as the presign lives.
#
# Secrets: the AWS session never leaves this machine except as presigned
# URLs. The GitHub token reaches curl through a config on stdin, never through
# argv. No URL is printed, except the final log link.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIB=(python3 "$REPO_ROOT/scripts/ci/aws_ci_lib.py")
SLUG=ArioMoniri/intake
INSTANCE=${AWS_CI_INSTANCE:-i-0e489e48739f5de98}
REGION=${AWS_CI_REGION:-us-east-1}
BUCKET=${AWS_CI_BUCKET:-onvizit-deploy-artefacts-235229001983}
S3_HOST="$BUCKET.s3.$REGION.amazonaws.com"
HARNESS_PATHS=(scripts/ci/aws_ci_host.sh scripts/ci/aws_ci_gates.sh scripts/ci/aws_ci_lib.py infra/ci)
POLL_S=30
RUN_TIMEOUT_S=14400
LOG_LINK_S=${AWS_CI_LOG_LINK_S:-604800}

say() { printf '[aws-ci] %s\n' "$*" >&2; }
die() {
  say "ERROR: $*"
  exit 2
}

eval "$("${LIB[@]}" parse-args "$@")"

for tool in aws gh git curl python3; do
  command -v "$tool" >/dev/null || die "missing tool: $tool"
done
aws sts get-caller-identity >/dev/null 2>&1 ||
  die "the AWS session has expired; the owner runs 'aws login' (this script never authenticates)"
gh auth status >/dev/null 2>&1 || die "gh is not authenticated"
git -C "$REPO_ROOT" diff --quiet HEAD -- "${HARNESS_PATHS[@]}" ||
  die "commit the harness first: the run must name the harness commit it used"
HARNESS_SHA=$(git -C "$REPO_ROOT" rev-parse HEAD)

if [[ $AWS_CI_KIND == pr ]]; then
  SHA=$(gh pr view "$AWS_CI_VALUE" --repo "$SLUG" --json headRefOid,isCrossRepository,state,headRepositoryOwner |
    "${LIB[@]}" pr-head)
  git -C "$REPO_ROOT" fetch -q origin "pull/$AWS_CI_VALUE/head"
else
  SHA=$AWS_CI_VALUE
  git -C "$REPO_ROOT" cat-file -e "$SHA^{commit}" 2>/dev/null || git -C "$REPO_ROOT" fetch -q origin "$SHA"
fi
git -C "$REPO_ROOT" cat-file -e "$SHA^{commit}" || die "commit $SHA is not available"
gh api "repos/$SLUG/commits/$SHA" --jq .sha >/dev/null || die "commit $SHA is not on GitHub; a status could not attach"

RUN_ID=$("${LIB[@]}" run-id "$SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")
WORK=$(mktemp -d)
cleanup() {
  rm -f "$WORK"/repo.bundle "$WORK"/harness.tgz "$WORK"/*.json "$WORK"/*.txt
  rmdir "$WORK" 2>/dev/null || true
}
trap cleanup EXIT
say "run $RUN_ID: ${AWS_CI_KIND} ${AWS_CI_VALUE} at ${SHA:0:12}, harness ${HARNESS_SHA:0:12}"

REF="refs/intake-ci/$RUN_ID"
git -C "$REPO_ROOT" update-ref "$REF" "$SHA"
git -C "$REPO_ROOT" bundle create -q "$WORK/repo.bundle" "$REF"
git -C "$REPO_ROOT" update-ref -d "$REF"
git -C "$REPO_ROOT" archive --format=tar.gz -o "$WORK/harness.tgz" "$HARNESS_SHA" -- "${HARNESS_PATHS[@]}"
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }

PREFIX="s3://$BUCKET/ci/$RUN_ID"
aws s3 cp --only-show-errors "$WORK/repo.bundle" "$PREFIX/repo.bundle"
aws s3 cp --only-show-errors "$WORK/harness.tgz" "$PREFIX/harness.tgz"
BUNDLE_URL=$(aws s3 presign "$PREFIX/repo.bundle" --expires-in 1800)
HARNESS_URL=$(aws s3 presign "$PREFIX/harness.tgz" --expires-in 1800)

# The pinned de-id model: the release asset's short-lived signed redirect, so
# the host downloads it without a GitHub token. The host verifies it against
# the Makefile's sha at the commit under test, and caches it.
DEID_SHA=$(git -C "$REPO_ROOT" show "$SHA:Makefile" | sed -n 's/^DEID_MODEL_SHA256 := \([0-9a-f]\{64\}\)$/\1/p')
[[ -n $DEID_SHA ]] || die "no DEID_MODEL_SHA256 in the Makefile at $SHA"
ASSET_ID=$(gh api "repos/$SLUG/releases/tags/deid-tr-ner-v1" --jq '.assets[] | select(.name=="deid-tr-ner-v1.tar.gz") | .id')
DEID_URL=$(printf 'header = "Authorization: Bearer %s"\n' "$(gh auth token)" |
  curl -K - -sS -o /dev/null -w '%{redirect_url}' -H 'Accept: application/octet-stream' \
    "https://api.github.com/repos/$SLUG/releases/assets/$ASSET_ID")
[[ $DEID_URL == https://* ]] || DEID_URL=""

post_status() {
  [[ $AWS_CI_POST_STATUS == 1 ]] || return 0
  gh api "repos/$SLUG/statuses/$SHA" --input "$1" >/dev/null
}
printf '{"state":"pending","context":"aws-ci","description":"running on the AWS host (run %s)"}\n' "$RUN_ID" >"$WORK/pending.json"
post_status "$WORK/pending.json"

# The URLs travel through the environment of one python process, never argv.
RUN_ID=$RUN_ID SHA=$SHA HARNESS_URL=$HARNESS_URL BUNDLE_URL=$BUNDLE_URL DEID_URL=$DEID_URL \
  HARNESS_SHA256=$(sha "$WORK/harness.tgz") BUNDLE_SHA256=$(sha "$WORK/repo.bundle") DEID_SHA=$DEID_SHA \
  RUN_TIMEOUT_S=$RUN_TIMEOUT_S MODE=$AWS_CI_MODE python3 -c '
import json, os
e = os.environ
print(json.dumps({
    "run_id": e["RUN_ID"], "sha": e["SHA"],
    "harness_url": e["HARNESS_URL"], "harness_sha256": e["HARNESS_SHA256"],
    "bundle_url": e["BUNDLE_URL"], "bundle_sha256": e["BUNDLE_SHA256"],
    "deid_url": e["DEID_URL"], "deid_sha256": e["DEID_SHA"],
    "timeout_s": int(e["RUN_TIMEOUT_S"]), "mode": e["MODE"],
}))' | "${LIB[@]}" ssm-params >"$WORK/ssm.json"

ssm_run() {
  local params=$1 cid status
  cid=$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
    --document-name AWS-RunShellScript --comment "aws-ci $RUN_ID" \
    --parameters "file://$params" --query Command.CommandId --output text)
  rm -f "$params"
  local waited=0 misses=0
  while :; do
    sleep "$POLL_S"
    waited=$((waited + POLL_S))
    if status=$(aws ssm get-command-invocation --region "$REGION" --command-id "$cid" \
      --instance-id "$INSTANCE" --query Status --output text 2>/dev/null); then
      misses=0
    else
      # Right after send-command the invocation may not exist yet; a run of
      # misses is an expired session, and the host carries on without us.
      misses=$((misses + 1))
      ((misses < 10)) || die "lost the SSM command $cid (AWS session expired?); the host run continues"
      status=Pending
    fi
    case $status in
      Pending | InProgress | Delayed) ;;
      *) break ;;
    esac
    ((waited < RUN_TIMEOUT_S + 600)) || die "SSM command $cid still $status after ${waited} s"
  done
  aws ssm get-command-invocation --region "$REGION" --command-id "$cid" --instance-id "$INSTANCE" \
    --query StandardOutputContent --output text
  say "SSM command $cid: $status"
}

say "running on $INSTANCE (this takes a while; verdict lines follow)"
ssm_run "$WORK/ssm.json" | tee "$WORK/host.txt" >&2
grep -E '^gate=' "$WORK/host.txt" >"$WORK/results.txt" || true
LOG_CLEAN=$(sed -n 's/^log_clean=\([01]\)$/\1/p' "$WORK/host.txt" | tail -1)
SECONDS_RUN=$(sed -n 's/^seconds=\([0-9]*\) .*/\1/p' "$WORK/host.txt" | tail -1)

# Always the second call: it uploads the redacted log when one survived the
# scanners, and in every case clears the run dir on the host.
KEY="ci/logs/$SHA/$RUN_ID.log"
aws configure export-credentials --format process |
  "${LIB[@]}" presign PUT "$S3_HOST" "$KEY" "$REGION" 900 "$(date -u +%Y%m%dT%H%M%SZ)" >"$WORK/put.txt"
"${LIB[@]}" ssm-upload-params "$RUN_ID" <"$WORK/put.txt" >"$WORK/upload.json"
rm -f "$WORK/put.txt"
ssm_run "$WORK/upload.json" >&2
LOG_URL=""
if [[ ${LOG_CLEAN:-0} == 1 ]]; then
  LOG_URL=$(aws s3 presign "s3://$BUCKET/$KEY" --expires-in "$LOG_LINK_S")
fi

if [[ $AWS_CI_MODE != gates ]]; then
  # a probe is a measurement: print it, post no status
  grep -E '^probe=' "$WORK/host.txt" || die "the probe printed no measurement"
  [[ -n $LOG_URL ]] && say "log: $LOG_URL"
  exit 0
fi

"${LIB[@]}" status-payload "$WORK/results.txt" "$LOG_URL" "${LOG_CLEAN:-0}" "${SECONDS_RUN:-0}" >"$WORK/status.json"
post_status "$WORK/status.json"
say "status: $(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["state"], "-", d["description"])' "$WORK/status.json")"
[[ -n $LOG_URL ]] && say "log: $LOG_URL"
python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1]))["state"] == "success" else 1)' "$WORK/status.json"
