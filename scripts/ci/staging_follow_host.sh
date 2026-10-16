#!/usr/bin/env bash
# INT-511 — the host half of the follow-main job (scripts/ci/staging_follow_main.sh).
# SSM runs it as root on the synthetic host, from the release archive that the
# bootstrap has just fetched and checked against its sha256
# (staging_follow_lib.ssm_parameters). It is the merged commit's own copy, so
# it is reviewed code.
#
#   staging_follow_host.sh --run-id <id> --sha <40 hex> --incoming <dir>
#
# It runs docs/release/production-checklist.md §1 step 4, after four refusals
# that change nothing on the host:
#   1. one run at a time (a lock in its state dir);
#   2. /opt/intake must be a symlink to a release directory (the checklist's
#      layout), so the previous release is always known;
#   3. the archive's REVISION must be the sha, or /version could not name it;
#   4. the release gate (INT-187) must allow a deploy. It asks the running api
#      container before anything changes, because init.sh starts the data tier
#      before deploy.sh's own gate runs. deploy.sh's gate still runs, in the
#      new image.
# Then it moves the release into place, points /opt/intake at it, and runs
# init.sh, deploy.sh and smoke.sh from there, as the checklist does.
#   - init.sh or deploy.sh fails: /opt/intake points back at the previous
#     release. deploy.sh stops before it recreates the api, so the previous
#     release is what serves.
#   - smoke is red: the pointer stays, because deploy.sh restarted onto the
#     new release, and the sha is not recorded as the host's revision.
#   - smoke is green: the sha is recorded in $STATE/revision. Releases beyond
#     the newest three and the previous one are pruned, with their images.
#
# stdout carries only the verdict lines, the gate's lines (codes only),
# smoke's PASS/FAIL lines and deploy's ERROR lines. None of them carries a
# secret (invariant 6). Full step logs stay under $STATE/runs (0700). It never
# reads the host's secrets, which stay with deploy.sh.
#
# Exit: 0 green, 1 red, 2 bad arguments, 3 refused. The last stdout line is
#   follow=verdict state=<green|red|refused> reason=<code>
# Portable to bash 3.2, which the tests run on macOS.
set -euo pipefail
set +x

RELEASES=${INTAKE_FOLLOW_RELEASES:-/opt/onvizit-releases}
CURRENT=${INTAKE_FOLLOW_CURRENT:-/opt/intake}
STATE=${INTAKE_FOLLOW_STATE:-/var/lib/intake-staging-follow}
KEEP_RELEASES=3
COMPOSE_PROJECT=intake-staging
GATE_MODULE=intake_api.admin.release_gate
GATE_EXIT_REFUSED=3
# lib.sh's require_release_not_frozen says this when deploy.sh's gate refuses
FREEZE_LINE="deploys are frozen or the freeze cannot be read"
IMAGES="api admin-web keycloak"

say() { printf '[follow-main] %s\n' "$*" >&2; }
usage() {
  say "ERROR: $*"
  exit 2
}
verdict() {
  printf 'follow=verdict state=%s reason=%s\n' "$1" "$2"
  case $1 in
    green) exit 0 ;;
    red) exit 1 ;;
    *) exit 3 ;;
  esac
}
refuse() {
  say "REFUSED ($1): $2"
  verdict refused "$1"
}

RUN_ID="" SHA="" INCOMING=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --run-id | --sha | --incoming)
      [[ $# -ge 2 ]] || usage "$1 needs a value"
      case $1 in
        --run-id) RUN_ID=$2 ;;
        --sha) SHA=$2 ;;
        *) INCOMING=$2 ;;
      esac
      shift 2
      ;;
    *) usage "unknown argument" ;;
  esac
done
[[ $RUN_ID =~ ^[a-z0-9-]{1,64}$ ]] || usage "bad run id"
[[ $SHA =~ ^[0-9a-f]{40}$ ]] || usage "bad sha"
# the only tree this script may move or delete is the one its bootstrap made
[[ $INCOMING == "$RELEASES/.incoming.$RUN_ID" ]] || usage "the incoming tree is not $RELEASES/.incoming.<run id>"
SOURCE="$INCOMING/intake"
[[ -d $SOURCE ]] || usage "no release tree under the incoming dir"
trap 'rm -rf "$INCOMING"' EXIT

install -d -m 0700 "$STATE" "$STATE/runs"

# --- refusals: nothing on the host has changed yet ---------------------------------

exec 9>"$STATE/lock"
flock -n 9 || refuse lock_busy "another follow-main run holds $STATE/lock"

[[ -L $CURRENT && -d $CURRENT/ ]] ||
  refuse layout "$CURRENT is not a symlink to a release directory (checklist §1 layout); deploy by hand once"
PREVIOUS=$(readlink "$CURRENT")
PREVIOUS_SHA=$(tr -d '[:space:]' <"$CURRENT/infra/staging/REVISION" 2>/dev/null || true)
printf 'follow=preflight check=layout previous=%s\n' "${PREVIOUS_SHA:-unknown}"

revision=$(tr -d '[:space:]' <"$SOURCE/infra/staging/REVISION" 2>/dev/null || true)
[[ $revision == "$SHA" ]] ||
  refuse revision_mismatch "the archive's REVISION is '${revision:0:44}', not $SHA: /version could not name it"
printf 'follow=preflight check=revision ok\n'

freeze_preflight() {
  # The gate's own rule, read from the deployment's own store, in the api that
  # serves now: exit 0 allowed, 3 refused, anything else did not run.
  local ids id out line rc=0
  ids=$(docker ps -q --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
    --filter label=com.docker.compose.service=api 2>/dev/null || true)
  if [[ $(printf '%s\n' "$ids" | awk 'NF' | wc -l | tr -d ' ') != 1 ]]; then
    refuse gate_unavailable "not exactly one running api to read the freeze from"
  fi
  id=$(printf '%s' "$ids" | tr -d '[:space:]')
  out=$(docker exec "$id" python -m "$GATE_MODULE" 2>&1) || rc=$?
  while IFS= read -r line; do
    if [[ -n $line ]]; then printf 'gate: %s\n' "$line"; fi
  done <<<"$out"
  printf 'follow=preflight check=freeze rc=%d\n' "$rc"
  if ((rc == GATE_EXIT_REFUSED)); then
    refuse frozen "the release gate refuses: deploys are frozen, or the freeze cannot be read (docs/runbooks/deploy-freeze.md)"
  elif ((rc != 0)); then
    refuse gate_unavailable "the release gate did not run (exit $rc)"
  fi
}
freeze_preflight

# --- the deploy -------------------------------------------------------------------------

point_at() {
  # a new link beside the old one, renamed over it: never a moment without one
  python3 -c '
import os, sys
target, link = sys.argv[1], sys.argv[2]
fresh = link + ".follow-new"
if os.path.lexists(fresh):
    os.unlink(fresh)
os.symlink(target, fresh)
os.replace(fresh, link)
' "$1" "$CURRENT"
}

step() {
  # step <name>: the checklist's ./<name>.sh, from the release /opt/intake names
  local name=$1 log="$STATE/runs/$RUN_ID-$1.log" rc=0 started
  started=$(date +%s)
  (cd "$CURRENT/infra/staging" && bash "./$name.sh") >"$log" 2>&1 || rc=$?
  printf 'follow=step name=%s rc=%d seconds=%d\n' "$name" "$rc" "$(($(date +%s) - started))"
  grep -E '^\[intake-staging\] (PASS|FAIL|ERROR)' "$log" | sed "s/^/$name: /" || true
  return "$rc"
}

restore() {
  point_at "$PREVIOUS"
  say "$CURRENT points back at $PREVIOUS"
}

epoch=$(date +%s)
while [[ -e $RELEASES/$SHA-$epoch ]]; do epoch=$((epoch + 1)); done
RELEASE="$RELEASES/$SHA-$epoch"
mv "$SOURCE" "$RELEASE"
point_at "$RELEASE"
printf 'follow=switch from=%s to=%s\n' "${PREVIOUS##*/}" "${RELEASE##*/}"

if ! step init; then
  restore
  verdict red init_failed
fi
if ! step deploy; then
  restore
  if grep -qF "$FREEZE_LINE" "$STATE/runs/$RUN_ID-deploy.log"; then
    refuse frozen "deploy.sh's own release gate refused in the new image; nothing was restarted"
  fi
  verdict red deploy_failed
fi
if ! step smoke; then
  printf '%s\n' "$SHA" >"$STATE/last_red"
  verdict red smoke_red
fi

printf '%s\n' "$SHA" >"$STATE/revision.new"
mv -f "$STATE/revision.new" "$STATE/revision"
printf 'follow=revision sha=%s release=%s\n' "$SHA" "${RELEASE##*/}"

# --- prune: the newest releases and the previous one stay, with their images -----------

releases_newest_first() {
  local dir name
  for dir in "$RELEASES"/*-*; do
    name=${dir##*/}
    if [[ $name =~ ^[0-9a-f]{40}-[0-9]+$ ]]; then printf '%s %s\n' "${name##*-}" "$name"; fi
  done | sort -k1,1nr | awk '{ print $2 }'
}

prune() {
  local name sha image refs n=0 kept=" $PREVIOUS_SHA $SHA " doomed=""
  while IFS= read -r name; do
    [[ -n $name ]] || continue
    n=$((n + 1))
    if ((n <= KEEP_RELEASES)) || [[ $name == "${PREVIOUS##*/}" ]]; then
      kept+="${name%-*} "
    else
      doomed+="$name "
    fi
  done < <(releases_newest_first)
  for name in $doomed; do
    rm -rf "${RELEASES:?}/$name"
    sha=${name%-*}
    [[ $kept == *" $sha "* ]] && continue
    refs=""
    for image in $IMAGES; do refs+="intake-staging/$image:$sha "; done
    # shellcheck disable=SC2086 # refs is a list of plain image references
    docker image rm $refs >/dev/null 2>&1 || say "kept images of ${sha:0:12} (in use, or already gone)"
  done
  find "$STATE/runs" -type f -mtime +30 -exec rm -f {} + 2>/dev/null || true
  find "$RELEASES" -maxdepth 1 -name '.incoming.*' -mtime +1 -exec rm -rf {} + 2>/dev/null || true
  printf 'follow=prune removed=%s\n' "$(printf '%s' "$doomed" | wc -w | tr -d ' ')"
}
prune

verdict green smoke_green
