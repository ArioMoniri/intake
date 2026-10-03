#!/usr/bin/env bash
# INT-463 — the ExecStart of intake-aws-ci-runner.service. Runs as root and is
# not sandboxed, so it sees the real file system that the guards must check.
# Each pass of the loop is one ephemeral runner, and one job:
#
#   prepare  the guards (layout, disk, access, net); a fresh runner tree from
#            the root-owned, sha256-verified distribution; an empty workspace,
#            home and temp; rootless Docker answering as the runner user; and
#            registration with --ephemeral. The registration token reaches
#            config.sh in ACTIONS_RUNNER_INPUT_TOKEN, never on a command line,
#            and it is never printed. Its source, in order:
#              SECRET_DIR/registrar-header    a fine-grained token that may
#                                             mint registration tokens
#                                             (Administration: write, this
#                                             repository only)
#              SECRET_DIR/registration-token  a one-hour registration token
#                                             from scripts/ci/aws_runner.sh token
#   run      `systemctl start --wait intake-aws-ci-job.service`: the runner
#            process, as ghrunner, inside that unit's sandbox. It takes exactly
#            one job and exits.
#   cleanup  every container, volume, network and build cache of the rootless
#            daemon; any image whose tags are not backed by a registry digest
#            of the same repository; every stray process of the runner user;
#            the runner tree, workspace, home and temp. Then the disk guard.
# A refused prepare waits RETRY_S and tries again: the runner stays offline
# rather than take a job in a state the guards rejected.
set -uo pipefail
set +x

# shellcheck source=guard.sh
. /usr/local/lib/intake-aws-ci-runner/bin/guard.sh
set +e

JOB_UNIT=intake-aws-ci-job.service
RETRY_S=30

registration_token() {
  local token=""
  if [ -s "$SECRET_DIR/registrar-header" ]; then
    token=$(curl -fsS -m 30 -X POST \
      -H 'Accept: application/vnd.github+json' \
      -H 'X-GitHub-Api-Version: 2022-11-28' \
      -H @"$SECRET_DIR/registrar-header" \
      "https://api.github.com/repos/$REPO_SLUG/actions/runners/registration-token" |
      jq -r '.token // empty')
    if [ -z "$token" ]; then
      say "the registrar credential did not mint a registration token"
    fi
  fi
  if [ -z "$token" ] && [ -s "$SECRET_DIR/registration-token" ]; then
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
  cp -a "$LIB_DIR/actions-runner-$RUNNER_VERSION/." "$CI_ROOT/runner/" || return 1
  chown -R "$RUNNER_USER:$RUNNER_USER" "$CI_ROOT/runner"
  write_runner_env
  wait_for_docker || return 1

  local token
  if ! token=$(registration_token); then
    say "FAIL: no usable registration credential in $SECRET_DIR. Run scripts/ci/aws_runner.sh token (one hour) or scripts/ci/aws_runner.sh registrar (lasting)."
    return 1
  fi
  # config.sh checks its libraries relative to the working directory.
  if ! (cd "$CI_ROOT/runner" && ACTIONS_RUNNER_INPUT_TOKEN="$token" runuser -u "$RUNNER_USER" -- \
    ./config.sh --unattended --ephemeral --replace --disableupdate \
    --url "$REPO_URL" --name "$RUNNER_NAME" --labels "$RUNNER_LABELS" \
    --work "$CI_ROOT/work" >/dev/null); then
    say "FAIL: GitHub refused the registration (an expired one-hour token, or a revoked registrar credential)"
    return 1
  fi
  unset token
  say "registered $RUNNER_NAME: ephemeral, labels self-hosted, Linux, X64, $RUNNER_LABELS"
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

say "supervisor started"
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
