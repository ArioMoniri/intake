#!/usr/bin/env bash
# INT-463, INT-467 — the ExecStart of intake-aws-ci-runner@N.service, for runner
# N of the pool (cycle.sh N). Runs as root and is not sandboxed, so it sees the
# real file system that the guards must check. Each pass of the loop is one
# ephemeral registration, and one job:
#
#   prepare  the guards (layout, disk, access, net); an empty workspace, home
#            and temp; the runner's rootless Docker answering as its user;
#            its detached network namespace attached for the job and proved
#            (guard.sh netns); the runner's cache seed refreshed (seed.sh,
#            INT-544) and the workspace wiped again; a fresh runner tree from
#            the root-owned, sha256-verified distribution; and registration
#            with --ephemeral. The
#            registration token reaches
#            config.sh in ACTIONS_RUNNER_INPUT_TOKEN, never on a command line,
#            and it is never printed. Its source, in order:
#              the registrar   a fresh registration token minted for this pass
#                              with the owner's admin token, read from SSM
#                              (REGISTRAR_PARAM) by this root process only
#              SECRET_DIR/registration-token
#                              a one-hour registration token from
#                              scripts/ci/aws_runner.sh token, the fallback
#   run      `systemctl start --wait intake-aws-ci-job@N.service`: the runner
#            process, as ghrunnerN, inside that unit's sandbox and network
#            namespace. It takes exactly one job and exits.
#   cleanup  every container, volume, network and build cache of this runner's
#            rootless daemon; any image whose tags are not backed by a registry
#            digest of the same repository; every stray process of this
#            runner's user; its runner tree, workspace, home and temp. Then the
#            disk guard. No other runner's daemon, process or file is touched.
# A refused prepare waits RETRY_S and tries again: the runner stays offline
# rather than take a job in a state the guards rejected.
set -uo pipefail
set +x

# shellcheck source=guard.sh
. /usr/local/lib/intake-aws-ci-runner/bin/guard.sh
set +e

instance_env "${1:-}" || exit 2
RETRY_S=30

registrar_token() {
  # The owner's fine-grained token (this repository only, Administration: read
  # and write) is read from SSM with the instance role, which only root on this
  # host can reach: guard.sh rejects the metadata service for the runner user.
  # It goes to curl as a header on stdin, never as an argument, and is unset
  # before this returns. Only the minted registration token leaves.
  local pat token
  pat=$(aws ssm get-parameter --region "$REGISTRAR_REGION" --name "$REGISTRAR_PARAM" \
    --with-decryption --query Parameter.Value --output text 2>/dev/null) || pat=""
  if ! [[ "$pat" =~ ^[A-Za-z0-9_]{20,255}$ ]]; then
    unset pat
    say "the registrar could not read $REGISTRAR_PARAM" >&2
    return 1
  fi
  token=$(printf 'Authorization: Bearer %s\n' "$pat" | curl -fsS -m 30 -X POST \
    -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2022-11-28' -H @- \
    "https://api.github.com/repos/$REPO_SLUG/actions/runners/registration-token" |
    jq -r '.token // empty') || token=""
  unset pat
  if [ -z "$token" ]; then
    say "the registrar's token did not mint a registration token" >&2
    return 1
  fi
  printf '%s' "$token"
}

registration_token() {
  local token=""
  if token=$(registrar_token); then
    # The one-hour hand-over token is stale once the registrar works.
    rm -f "$SECRET_DIR/registration-token"
  elif [ -s "$SECRET_DIR/registration-token" ]; then
    token=$(tr -d '[:space:]' <"$SECRET_DIR/registration-token")
  fi
  if ! [[ "$token" =~ ^[A-Za-z0-9_-]{20,255}$ ]]; then
    return 1
  fi
  printf '%s' "$token"
}

write_runner_env() {
  # The runner exports .env to every job and uses .path as the job's PATH.
  cat >"$CI_ROOT/runner/.env" <<EOF
LANG=C.UTF-8
LC_ALL=C.UTF-8
HOME=$CI_ROOT/home
TMPDIR=/tmp
DOCKER_HOST=unix://$DOCKER_RUN_DIR/docker.sock
ACTIONS_RUNNER_HOOK_JOB_STARTED=$LIB_DIR/bin/job-started.sh
INTAKE_CI_SEED=$CI_ROOT/seed
EOF
  printf '%s\n' "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin" >"$CI_ROOT/runner/.path"
  chown "$RUNNER_USER:$RUNNER_USER" "$CI_ROOT/runner/.env" "$CI_ROOT/runner/.path"
}

wait_for_docker() {
  systemctl start "$DOCKERD_UNIT"
  for _ in $(seq 1 60); do
    if docker_up; then
      return 0
    fi
    sleep 2
  done
  say "FAIL: the rootless Docker daemon did not answer within 120 s"
  return 1
}

prepare() {
  guard_layout && guard_disk && guard_access && guard_net || return 1
  wipe_job_state
  wait_for_docker || return 1
  guard_netns || return 1
  # INT-544: the cache seed is rebuilt here, between jobs, when the owner has
  # staged new inputs; it runs in the job's sandbox, so the wipe after it
  # removes whatever the build left. A failed refresh leaves the runner without
  # a seed, never without its next job.
  if ! "$LIB_DIR/bin/seed.sh" "$INSTANCE" refresh; then
    say "the cache seed did not refresh; jobs fetch from the network"
  fi
  wipe_job_state
  cp -a "$LIB_DIR/actions-runner-$RUNNER_VERSION/." "$CI_ROOT/runner/" || return 1
  chown -R "$RUNNER_USER:$RUNNER_USER" "$CI_ROOT/runner"
  write_runner_env

  local token
  if ! token=$(registration_token); then
    say "FAIL: no registration token: the registrar failed and no one-hour token is in $SECRET_DIR (scripts/ci/aws_runner.sh token)."
    return 1
  fi
  # config.sh checks its libraries relative to the working directory.
  if ! (cd "$CI_ROOT/runner" && ACTIONS_RUNNER_INPUT_TOKEN="$token" runuser -u "$RUNNER_USER" -- \
    ./config.sh --unattended --ephemeral --replace --disableupdate \
    --url "$REPO_URL" --name "$RUNNER_NAME" --labels "$RUNNER_LABELS" \
    --work "$CI_ROOT/home/work" >/dev/null); then
    say "FAIL: GitHub refused the registration (an expired one-hour token, or a revoked admin token)"
    return 1
  fi
  unset token
  say "registered $RUNNER_NAME: ephemeral, labels self-hosted, Linux, X64, $RUNNER_LABELS; job namespace $NETNS"
}

drop_unverifiable_images() {
  local id tags digests tag repo keep
  for id in $(docker_as_runner image ls -aq | sort -u); do
    tags=$(docker_as_runner image inspect -f '{{range .RepoTags}}{{.}} {{end}}' "$id")
    digests=$(docker_as_runner image inspect -f '{{range .RepoDigests}}{{.}} {{end}}' "$id")
    keep=1
    if [ -z "${digests// /}" ]; then
      keep=0
    fi
    for tag in $tags; do
      repo=${tag%:*}
      if ! tr ' ' '\n' <<<"$digests" | grep -q "^${repo}@sha256:"; then
        keep=0
      fi
    done
    if [ "$keep" -eq 0 ]; then
      docker_as_runner image rm -f "$id" >/dev/null 2>&1
    fi
  done
}

kill_strays() {
  local pid cgroup
  for pid in $(pgrep -u "$RUNNER_USER"); do
    cgroup=$(cat "/proc/$pid/cgroup" 2>/dev/null) || continue
    case "$cgroup" in
      *"$DOCKERD_UNIT"*) ;;
      *) kill -KILL "$pid" 2>/dev/null ;;
    esac
  done
}

cleanup() {
  local containers
  if docker_up; then
    containers=$(docker_as_runner ps -aq)
    if [ -n "$containers" ]; then
      # shellcheck disable=SC2086
      docker_as_runner rm -f -v $containers >/dev/null
    fi
    docker_as_runner volume prune -af >/dev/null
    docker_as_runner network prune -f >/dev/null
    docker_as_runner builder prune -af >/dev/null
    drop_unverifiable_images
  fi
  kill_strays
  wipe_job_state
  guard_disk >/dev/null || say "disk guard failed after cleanup; the next prepare refuses"
  say "cleanup done: containers, volumes, workspace, home, temp and runner tree removed"
}

say "supervisor of $RUNNER_NAME started"
while :; do
  if prepare; then
    started=$(date +%s)
    systemctl start --wait "$JOB_UNIT"
    lasted=$(($(date +%s) - started))
    say "runner exited after ${lasted} s"
    cleanup
    if [ "$lasted" -lt "$RETRY_S" ]; then
      # An exit this fast took no job; do not spin on GitHub's API.
      sleep "$RETRY_S"
    fi
  else
    cleanup
    sleep "$RETRY_S"
  fi
done
