#!/usr/bin/env bash
# INT-511 — the synthetic host follows main (docs/runbooks/staging.md,
# "Following main"). It deploys one commit of main to the AWS host over the
# INT-426 path (S3, a presigned URL, SSM AWS-RunShellScript), smokes it, and
# posts the smoke verdict as the commit status staging-smoke.
#
#   make staging-follow-main [REF=<40-hex sha>] [EVENT=<event>] [DRY_RUN=1]
#   scripts/ci/staging_follow_main.sh --event <schedule|workflow_run|workflow_dispatch|manual>
#       [--ref <sha>] [--dry-run] [--no-status] [--decide]
#
# It runs where an AWS session and an authenticated gh exist: the owner's
# laptop, or the intake-aws-ci runner once the owner installs the staged
# workflow (scripts/ci/staging_follow_main_workflow.yml).
#
#   1. infra/staging/follow-main.conf's trigger decides whether this event
#      deploys (--decide only answers true or false).
#   2. It refuses an unmerged sha (GitHub compare against main) and a red one
#      (its check runs, this job's own excepted). It waits while checks still
#      run.
#   3. It reads the host's /version. It refuses a host that does not declare
#      itself synthetic-only, and a move backwards. A host already on the sha
#      is left alone.
#   4. It runs `git archive` on the sha, and refuses unless the archive's
#      REVISION is the sha, which is what /version will report.
#   5. --dry-run stops here, having printed the plan.
#   6. It uploads the archive, presigns it for 30 minutes and posts `pending`.
#      Over SSM the host verifies the archive and refuses a frozen state
#      (INT-187). It then runs init.sh, deploy.sh and smoke.sh
#      (staging_follow_host.sh).
#   7. It reads the host's verdict, checks /version parity from outside, and
#      posts the status.
#
# Exit: 0 deployed or nothing to do, 1 red, 2 harness error, 3 refused.
# Secrets: the AWS session leaves this machine only as the presigned URL. That
# URL is never printed and never reaches argv. GH_TOKEN reaches only gh. The
# host's secrets stay in /etc/intake-staging; nothing here reads them.
set -euo pipefail
set +x

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLI=(python3 "$REPO_ROOT/scripts/ci/staging_follow_cli.py")
CONF="$REPO_ROOT/infra/staging/follow-main.conf"
SLUG=ArioMoniri/intake
POLL_S=${INTAKE_FOLLOW_POLL_S:-30}

say() { printf '[follow-main] %s\n' "$*" >&2; }
die() {
  say "ERROR: $*"
  exit 2
}
refuse() {
  say "REFUSED ($1): $2"
  exit 3
}
skip() {
  say "nothing to do ($1): $2"
  exit 0
}

shell_args=$("${CLI[@]}" args-shell "$@") || exit 2
eval "$shell_args"
shell_conf=$("${CLI[@]}" conf-shell "$CONF") || exit 2
eval "$shell_conf"

decision=$("${CLI[@]}" decide "$FOLLOW_TRIGGER" "$FOLLOW_EVENT")
if [[ $FOLLOW_DECIDE == 1 ]]; then
  if [[ $decision == run* ]]; then echo true; else echo false; fi
  exit 0
fi
[[ $decision == run* ]] || skip trigger "${decision#skip }"
say "${decision#run }"

tools="git gh curl python3 tar"
[[ $FOLLOW_DRY_RUN == 1 ]] || tools+=" aws"
for tool in $tools; do
  command -v "$tool" >/dev/null || die "missing tool: $tool"
done
gh auth status >/dev/null 2>&1 || die "gh is not authenticated"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# --- 2. merged and green --------------------------------------------------------------------

SHA=$FOLLOW_REF
if [[ -z $SHA ]]; then
  SHA=$(gh api "repos/$SLUG/commits/main" --jq .sha) || die "could not read main's head"
fi
[[ $SHA =~ ^[0-9a-f]{40}$ ]] || die "the target is not a 40-hex sha"
say "target $SHA"

compare=$(gh api "repos/$SLUG/compare/main...$SHA" --jq .status 2>/dev/null) ||
  refuse unmerged "GitHub could not place $SHA on main"
"${CLI[@]}" merged "$compare" || refuse unmerged "$SHA is not on main (compare: ${compare:-none})"

gh api "repos/$SLUG/commits/$SHA/check-runs?filter=latest&per_page=100" >"$WORK/checks.json" ||
  die "could not read the check runs of $SHA"
checks=$("${CLI[@]}" green <"$WORK/checks.json")
case $checks in
  green\ *) say "checks: ${checks#green }" ;;
  pending\ *) skip pending "${checks#pending }" ;;
  *) refuse not_green "${checks#* }" ;;
esac

# --- 3. the host, as it answers now ---------------------------------------------------------------

VERSION_URL="https://$STAGING_HOSTNAME/version"
fetch_version() {
  curl -fsS --proto '=https' --tlsv1.2 --max-time 15 -D "$WORK/headers" -o "$WORK/version.json" "$VERSION_URL"
}
fetch_version || refuse host_unreadable "$VERSION_URL did not answer"
"${CLI[@]}" synthetic <"$WORK/headers" ||
  refuse not_synthetic "$VERSION_URL does not declare X-Intake-Environment: staging-synthetic-only"
HOST_SHA=$("${CLI[@]}" host-revision <"$WORK/version.json") ||
  refuse host_unreadable "$VERSION_URL names no commit"
[[ $HOST_SHA != "$SHA" ]] || skip up_to_date "the host already runs $SHA"
# Backwards is only a question for a host on main. GitHub's body is read even
# when gh exits 1: a commit it does not hold (422) is off main, not unknown.
lineage_body=$(gh api "repos/$SLUG/compare/main...$HOST_SHA" 2>/dev/null) || true
case $("${CLI[@]}" lineage <<<"$lineage_body") in
  off_main) say "the host runs $HOST_SHA, which is not on main; this deploy puts it back on main" ;;
  on_main)
    ordering=$(gh api "repos/$SLUG/compare/$SHA...$HOST_SHA" --jq .status 2>/dev/null) ||
      refuse unordered "GitHub could not order the host's $HOST_SHA against $SHA"
    where=$("${CLI[@]}" direction "$ordering") || refuse unordered "compare answered '$ordering'"
    [[ $where != backwards ]] || refuse backwards "the host runs $HOST_SHA, which is newer than $SHA"
    [[ $where == forward ]] || refuse unordered "neither $HOST_SHA nor $SHA comes before the other on main"
    say "the host runs $HOST_SHA; this deploy moves it forward along main"
    ;;
  *) refuse unordered "GitHub did not say whether the host's $HOST_SHA is on main" ;;
esac

# --- 4. the archive ---------------------------------------------------------------------------

if ! git -C "$REPO_ROOT" cat-file -e "$SHA^{commit}" 2>/dev/null; then
  if [[ $(git -C "$REPO_ROOT" rev-parse --is-shallow-repository) == true ]]; then
    git -C "$REPO_ROOT" fetch -q --depth=1 origin "$SHA"
  else
    git -C "$REPO_ROOT" fetch -q origin "$SHA"
  fi
fi
git -C "$REPO_ROOT" cat-file -e "$SHA^{commit}" || die "commit $SHA is not available here"
git -C "$REPO_ROOT" archive --format=tar.gz --prefix=intake/ -o "$WORK/release.tgz" "$SHA"
tar -xzOf "$WORK/release.tgz" intake/infra/staging/REVISION >"$WORK/REVISION" 2>/dev/null || : >"$WORK/REVISION"
parity=$("${CLI[@]}" revision-parity "$SHA" <"$WORK/REVISION") || refuse revision_mismatch "$parity"

RUN_ID=$("${CLI[@]}" run-id "$SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")
ARCHIVE_SHA256=$("${CLI[@]}" sha256 "$WORK/release.tgz")
ARCHIVE_BYTES=$(wc -c <"$WORK/release.tgz" | tr -d ' ')
"${CLI[@]}" plan "$SHA" "$RUN_ID" "$FOLLOW_EVENT" "$CONF" "$ARCHIVE_SHA256" "$ARCHIVE_BYTES" "$HOST_SHA"

# --- 5. dry run ------------------------------------------------------------------------------------

if [[ $FOLLOW_DRY_RUN == 1 ]]; then
  say "dry run: nothing uploaded, nothing run on the host, no status posted"
  exit 0
fi

# --- 6. ship and run -------------------------------------------------------------------------------

aws sts get-caller-identity >/dev/null 2>&1 ||
  die "no AWS session: the owner runs 'aws login', or the runner's OIDC role is missing"
read -r SSM_TIMEOUT_S WAIT_MARGIN_S PRESIGN_S <<<"$("${CLI[@]}" timeouts)"
KEY=$("${CLI[@]}" s3-key "$RUN_ID")
aws s3 cp "$WORK/release.tgz" "s3://$STAGING_BUCKET/$KEY" --only-show-errors --region "$STAGING_REGION"
# the URL lives in one variable and one 0600 file inside a 0700 dir, never in argv
FOLLOW_ARCHIVE_URL=$(aws s3 presign "s3://$STAGING_BUCKET/$KEY" --expires-in "$PRESIGN_S" --region "$STAGING_REGION")
export FOLLOW_ARCHIVE_URL
(umask 077 && "${CLI[@]}" ssm-params "$RUN_ID" "$SHA" "$ARCHIVE_SHA256" >"$WORK/ssm.json")
unset FOLLOW_ARCHIVE_URL

post_status() {
  [[ $FOLLOW_POST_STATUS == 1 ]] || return 0
  gh api "repos/$SLUG/statuses/$SHA" --input "$1" >/dev/null || say "WARNING: could not post the status"
}
plain_status() {
  # every value is validated (context, sha, run id), so plain JSON is safe
  printf '{"state":"%s","context":"%s","description":"%s"}\n' "$1" "$FOLLOW_STATUS_CONTEXT" "$2" >"$WORK/plain.json"
  post_status "$WORK/plain.json"
}
plain_status pending "deploying ${SHA:0:12} to the synthetic host (run $RUN_ID)"

ssm_run() {
  local cid status waited=0 misses=0
  cid=$(aws ssm send-command --region "$STAGING_REGION" --instance-ids "$STAGING_INSTANCE" \
    --document-name AWS-RunShellScript --comment "INT-511 follow-main $RUN_ID" \
    --parameters "file://$WORK/ssm.json" --query Command.CommandId --output text) || return 1
  rm -f "$WORK/ssm.json"
  say "SSM command $cid on $STAGING_INSTANCE (deploy and smoke take several minutes)"
  while :; do
    sleep "$POLL_S"
    waited=$((waited + POLL_S))
    if status=$(aws ssm get-command-invocation --region "$STAGING_REGION" --command-id "$cid" \
      --instance-id "$STAGING_INSTANCE" --query Status --output text 2>/dev/null); then
      misses=0
    else
      # right after send-command the invocation may not exist yet
      misses=$((misses + 1))
      ((misses < 10)) || return 1
      status=Pending
    fi
    case $status in
      Pending | InProgress | Delayed) ;;
      *) break ;;
    esac
    ((waited < SSM_TIMEOUT_S + WAIT_MARGIN_S)) || return 1
  done
  say "SSM command $cid: $status"
  aws ssm get-command-invocation --region "$STAGING_REGION" --command-id "$cid" \
    --instance-id "$STAGING_INSTANCE" --query StandardOutputContent --output text
}
if ! ssm_run >"$WORK/host.txt"; then
  plain_status error "lost the SSM run $RUN_ID; its result is on the host"
  die "lost the SSM command (AWS session expired?); the host run may continue"
fi
sed 's/^/host: /' "$WORK/host.txt" >&2

# --- 7. verdict, parity, status ------------------------------------------------------------------

parity_ok="-" parity_detail="-"
if [[ $("${CLI[@]}" host-state <"$WORK/host.txt") == green ]]; then
  parity_ok=0 parity_detail="$VERSION_URL did not answer"
  if fetch_version; then
    if parity_detail=$("${CLI[@]}" version-parity "$SHA" <"$WORK/version.json"); then
      parity_ok=1
    fi
  fi
  say "/version parity: $parity_detail"
fi
rc=0
"${CLI[@]}" status-payload "$SHA" "$FOLLOW_STATUS_CONTEXT" "$STAGING_HOSTNAME" "$WORK/host.txt" \
  "$parity_ok" "$parity_detail" >"$WORK/status.json" || rc=$?
((rc != 2)) || die "could not build the status"
post_status "$WORK/status.json"
say "status: $(python3 -c 'import json, sys; d = json.load(open(sys.argv[1])); print(d["state"], "-", d["description"])' "$WORK/status.json")"
exit "$rc"
