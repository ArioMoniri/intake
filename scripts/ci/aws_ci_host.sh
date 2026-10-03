#!/usr/bin/env bash
# INT-426 — the host half of aws-ci. SSM runs it as root on the AWS host, from
# a harness the laptop shipped and sha256-verified (scripts/ci/aws_ci_lib.py,
# ssm_parameters). It never runs from the tree under test: a pull request
# cannot change the harness that judges it.
#
#   aws_ci_host.sh --run-id <id> --sha <40 hex> --bundle-url <https> \
#                  --bundle-sha256 <64 hex> --deid-url <https|''> --deid-sha256 <64 hex>
#   aws_ci_host.sh --upload --run-id <id> --put-url <https>
#
# A run:
#   1. takes one of $AWS_CI_SLOTS slots (flock), so concurrent runs never share
#      a dind image store or a cache;
#   2. fetches the git bundle (the PR head, full history: `make security`
#      runs gitleaks over the history) and verifies it;
#   3. keeps the pinned de-id model in a host cache, verified against the
#      Makefile's sha at the sha under test;
#   4. builds the runner image once per Dockerfile digest;
#   5. runs prep, then the gates, then redaction, as the compose project
#      intake-ci-<run id> (infra/ci/compose.yaml) with every container
#      capped and weighted below the live stack;
#   6. always tears down: inside dind every container, network and volume
#      goes, and `down -v` removes the run's own volume and network. The image
#      store and the caches stay; they are per-slot and hold no run state.
# stdout carries only verdict lines: SSM keeps the first 24,000 characters.
# The full log stays under the run dir (0700) until --upload sends the
# redacted copy, or the age sweep removes it two days later.
set -euo pipefail
set +x

STATE=/var/lib/intake-ci
SLOTS=${AWS_CI_SLOTS:-2}
MIN_FREE_GB=${AWS_CI_MIN_FREE_GB:-25}
SLOT_WAIT_S=10800
HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEID_NAME="deid-tr-ner-v1.tar.gz"

say() { printf '[aws-ci %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die() {
  say "ERROR: $*"
  exit 2
}

RUN_ID="" SHA="" BUNDLE_URL="" BUNDLE_SHA256="" DEID_URL="" DEID_SHA256="" PUT_URL="" UPLOAD=0 MODE=gates
while [[ $# -gt 0 ]]; do
  case $1 in
    --run-id) RUN_ID=$2 ;;
    --sha) SHA=$2 ;;
    --bundle-url) BUNDLE_URL=$2 ;;
    --bundle-sha256) BUNDLE_SHA256=$2 ;;
    --deid-url) DEID_URL=$2 ;;
    --deid-sha256) DEID_SHA256=$2 ;;
    --put-url) PUT_URL=$2 ;;
    --mode) MODE=$2 ;;
    --upload)
      UPLOAD=1
      shift
      continue
      ;;
    *) die "unknown argument" ;;
  esac
  shift 2
done

[[ $RUN_ID =~ ^[a-z0-9-]{1,64}$ ]] || die "bad run id"
RUN_DIR="$STATE/runs/$RUN_ID"
[[ $HARNESS == "$RUN_DIR/harness" ]] || die "the harness must run from its own run dir"

if [[ $UPLOAD == 1 ]]; then
  [[ $PUT_URL == https://* ]] || die "the upload URL must be https"
  if [[ -f $RUN_DIR/out/log/aws-ci.log ]]; then
    curl --proto '=https' -fsS -X PUT -H 'Content-Type: text/plain; charset=utf-8' \
      -T "$RUN_DIR/out/log/aws-ci.log" "$PUT_URL" >/dev/null
    say "uploaded the redacted log ($(wc -c <"$RUN_DIR/out/log/aws-ci.log") bytes)"
  else
    say "no redacted log to upload (withheld or absent)"
  fi
  find "$RUN_DIR" -mindepth 1 -delete
  rmdir "$RUN_DIR"
  exit 0
fi

[[ $SHA =~ ^[0-9a-f]{40}$ ]] || die "bad sha"
[[ $MODE == gates || $MODE == expo-export ]] || die "unknown mode"
[[ $BUNDLE_SHA256 =~ ^[0-9a-f]{64}$ && $DEID_SHA256 =~ ^[0-9a-f]{64}$ ]] || die "bad sha256"
[[ $BUNDLE_URL == https://* ]] || die "the bundle URL must be https"
[[ -z $DEID_URL || $DEID_URL == https://* ]] || die "the de-id URL must be https"

if ! command -v docker >/dev/null || ! docker compose version >/dev/null; then
  die "docker with the compose plugin is required"
fi
free_gb=$(df --output=avail -BG / | tail -1 | tr -dc '0-9')
((free_gb >= MIN_FREE_GB)) || die "only ${free_gb} GB free on /; aws-ci needs ${MIN_FREE_GB} GB"

# Sweep run dirs a lost laptop never uploaded. find -delete removes depth first.
find "$STATE/runs" -mindepth 1 -maxdepth 1 -type d -mtime +2 -name '[0-9]*' -print0 |
  while IFS= read -r -d '' old; do find "$old" -delete; done

install -d -m 0700 "$STATE/locks" "$STATE/cache/deid" "$RUN_DIR/in"
install -d -m 0700 -o 10001 -g 10001 "$RUN_DIR/out"
# The bootstrap unpacked the harness under umask 077. It is code, not a secret,
# and the runner (uid 10001) bind-mounts it read-only (measured: run 2 failed
# with "Permission denied" without this).
chmod -R go+rX "$HARNESS"

# Fetch before queueing for a slot: the presigned URLs live 30 minutes, and a
# run that waited 40 minutes for a slot got a 403 (PR 683, 2 Oct).
curl --proto '=https' -fsS -o "$RUN_DIR/in/repo.bundle" "$BUNDLE_URL"
echo "$BUNDLE_SHA256  $RUN_DIR/in/repo.bundle" | sha256sum -c --quiet - || die "bundle sha256 mismatch"

deid="$STATE/cache/deid/$DEID_NAME"
if ! { [[ -f $deid ]] && echo "$DEID_SHA256  $deid" | sha256sum -c --quiet - 2>/dev/null; }; then
  if [[ -n $DEID_URL ]]; then
    # a per-run part file: two runs may fetch at once; mv is atomic
    curl --proto '=https' -fsSL -o "$deid.$RUN_ID.part" "$DEID_URL"
    echo "$DEID_SHA256  $deid.$RUN_ID.part" | sha256sum -c --quiet - || die "de-id model sha256 mismatch"
    mv -f "$deid.$RUN_ID.part" "$deid"
    say "de-id model cached"
  else
    say "no verified de-id model in the cache and no URL; check-py's de-id tests will fail"
  fi
fi

SLOT=""
waited=0
while :; do
  for ((s = 0; s < SLOTS; s++)); do
    exec {lock_fd}>"$STATE/locks/slot$s"
    if flock -n "$lock_fd"; then
      SLOT=$s
      break 2
    fi
    exec {lock_fd}>&-
  done
  ((waited == 0)) && say "every slot is busy; polling until a slot frees"
  ((waited < SLOT_WAIT_S)) || die "no slot within ${SLOT_WAIT_S} s"
  sleep 15
  waited=$((waited + 15))
done
started=$(date +%s)
say "run $RUN_ID on slot $SLOT"

image="intake-ci/runner:$(sha256sum "$HARNESS/infra/ci/Dockerfile.runner" | cut -c1-16)"
if ! docker image inspect "$image" >/dev/null 2>&1; then
  say "building $image"
  docker build -q -t "$image" -f "$HARNESS/infra/ci/Dockerfile.runner" "$HARNESS/infra/ci" >"$RUN_DIR/build.log" 2>&1 ||
    die "runner image build failed (see $RUN_DIR/build.log on the host)"
fi

for v in dind uv pnpm trivy xdg; do
  docker volume create "intake-ci-s$SLOT-$v" >/dev/null
done

export AWS_CI_PROJECT="intake-ci-$RUN_ID" AWS_CI_RUNNER_IMAGE="$image" AWS_CI_RUN_DIR="$RUN_DIR" \
  AWS_CI_DEID_DIR="$STATE/cache/deid" AWS_CI_SHA="$SHA" AWS_CI_SLOT="$SLOT"
compose() { docker compose -f "$HARNESS/infra/ci/compose.yaml" "$@"; }

purge_dind() {
  compose exec -T dind sh -c \
    'docker ps -aq | xargs -r docker rm -fv >/dev/null; docker volume prune -af >/dev/null; docker network prune -f >/dev/null' \
    >/dev/null 2>&1 || true
}
teardown() {
  purge_dind
  compose down -v --remove-orphans --timeout 30 >/dev/null 2>&1 || true
}
trap teardown EXIT

compose run --rm prep
compose up -d --wait dind >/dev/null
purge_dind
set +e
compose run --rm runner bash /harness/scripts/ci/aws_ci_gates.sh "$MODE"
compose run --rm --no-deps runner bash /harness/scripts/ci/aws_ci_gates.sh redact
set -e
teardown
trap - EXIT

seconds=$(($(date +%s) - started))
cat "$RUN_DIR/out/results.txt" 2>/dev/null || true
cat "$RUN_DIR/out/log_status" 2>/dev/null || printf 'log_clean=0\n'
printf 'seconds=%d slot=%d\n' "$seconds" "$SLOT"
say "done in ${seconds} s"
