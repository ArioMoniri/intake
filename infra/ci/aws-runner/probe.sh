#!/usr/bin/env bash
# INT-467 — the isolation probe for the intake-aws-ci pool. Runs as root on the
# host, sent over SSM by scripts/ci/aws_runner.sh probe. It reads no credential
# and prints none.
#
#   probe.sh [N ...]      every runner of POOL_INSTANCES by default
#
# 1. Every runner's daemon publishes the same port, 127.0.0.1:PROBE_PORT, from a
#    container that answers with that runner's name, all at once: the shape of
#    check-integration's fixed ports arriving from several PRs.
# 2. For each runner, a transient unit with exactly its job unit's sandbox
#    (every [Service] line of intake-aws-ci-job@.service with %i resolved; only
#    the command and its lifecycle differ) runs `probe.sh --inside N` as that
#    runner's user, in its network namespace, alongside the others.
# 3. The containers go. Each check prints one line, "ok" when the runner is
#    blocked from what it must not reach and reaches what it must, "FAIL"
#    otherwise. Any FAIL makes the exit status non-zero.
#
# Run it on an idle pool: a runner's post-job wipe removes the probe's
# container and process along with the job's.
set -euo pipefail
set +x

# shellcheck source=guard.sh
. "${BASH_SOURCE[0]%/*}/guard.sh"
set +e

TARGETS=/run/intake-aws-ci-probe.targets
# job_props (guard.sh) gives the job unit's sandbox; the cache seed's build
# (seed.sh) runs in the same one.

# --- outside, as root ------------------------------------------------------------------

staging_tcp() {
  # host:port of every TCP port a staging container exposes, on its first address.
  local id
  for id in $(docker ps -q 2>/dev/null); do
    docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}|{{range $p, $_ := .Config.ExposedPorts}}{{$p}} {{end}}' "$id"
  done | awk -F'|' '{ split($1, ip, " "); n = split($2, port, " ")
    for (i = 1; i <= n; i++) if (port[i] ~ /\/tcp$/) { sub("/tcp", "", port[i]); print ip[1] ":" port[i] } }' |
    sort -u | tr '\n' ' '
}

discover_targets() {
  # What the probe must find blocked, discovered as root, who sees the real
  # file system, and handed to the inside probe in a file it can read. None of
  # it is a secret: addresses, ports and path names.
  local denied="" path
  while IFS= read -r path; do
    case "$path" in
      "$CI_ROOT_BASE" | "$CI_ROOT_BASE"-* | "$DOCKER_RUN_BASE" | "$DOCKER_RUN_BASE"-*) ;;
      *) denied="$denied $path" ;;
    esac
  done < <(sensitive_paths)
  umask 022
  {
    printf 'DENIED_PATHS="%s"\n' "$denied"
    # shellcheck disable=SC2086  # the denied paths are separate arguments
    printf 'SECRET_FILES="%s"\n' "$(find $denied -maxdepth 3 -type f -name 'openbao-init.json' 2>/dev/null | tr '\n' ' ')"
    printf 'STAGING_TCP="%s"\n' "$(staging_tcp)"
    printf 'HOST_IP=%s\n' "$(ip -4 route get 1.1.1.1 | awk '{ for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1) }')"
    printf 'HOST_TCP="%s"\n' "$(ss -Hltn | awk '{ n = split($4, a, ":"); print a[n] }' | sort -un | tr '\n' ' ')"
  } >"$TARGETS"
}

run_inside() {
  # $1: the instance. The job unit's sandbox, as a transient unit.
  local line props=()
  while IFS= read -r line; do
    props+=(-p "$line")
  done < <(job_props "$1")
  systemd-run --quiet --wait --pipe --collect --unit="intake-aws-ci-probe-$1" -p Type=exec \
    "${props[@]}" "$LIB_DIR/bin/probe.sh" --inside "$1" </dev/null
}

probe_outside() {
  local n out fails=0
  [ "$(id -u)" -eq 0 ] || {
    say "FAIL: probe.sh runs as root"
    return 1
  }
  # shellcheck disable=SC2086  # the pool is a list of words
  [ $# -gt 0 ] || set -- $POOL_INSTANCES
  for n in "$@"; do
    instance_env "$n" || return 2
  done
  discover_targets
  for n in "$@"; do
    instance_env "$n"
    docker_as_runner rm -f "intake-probe-$n" >/dev/null 2>&1
    if docker_as_runner run -d --name "intake-probe-$n" -p "127.0.0.1:$PROBE_PORT:8080" "$PROBE_IMAGE" \
      sh -c "mkdir -p /w && echo $RUNNER_NAME >/w/id && exec httpd -f -p 8080 -h /w" >/dev/null 2>&1; then
      say "ok      $RUNNER_NAME: publishes 127.0.0.1:$PROBE_PORT while the others do"
    else
      say "FAIL    $RUNNER_NAME: cannot publish 127.0.0.1:$PROBE_PORT"
      fails=$((fails + 1))
    fi
    if ip netns exec "$NETNS" ss -Hltn "sport = :$PROBE_PORT" | grep -q .; then
      say "ok      $RUNNER_NAME: 127.0.0.1:$PROBE_PORT listens in $NETNS"
    else
      say "FAIL    $RUNNER_NAME: 127.0.0.1:$PROBE_PORT is not in $NETNS"
      fails=$((fails + 1))
    fi
  done
  if ss -Hltn "sport = :$PROBE_PORT" | grep -q .; then
    say "FAIL    the host listens on :$PROBE_PORT: a published port escaped"
    fails=$((fails + 1))
  else
    say "ok      the host listens on no :$PROBE_PORT"
  fi
  out=$(mktemp -d)
  for n in "$@"; do
    run_inside "$n" >"$out/$n" 2>&1 &
  done
  wait
  for n in "$@"; do
    cat "$out/$n"
    fails=$((fails + $(grep -c '^FAIL' "$out/$n")))
    if ! grep -q '^probe done' "$out/$n"; then
      say "FAIL    intake-aws-ci-$n: the inside probe did not finish"
      fails=$((fails + 1))
    fi
    instance_env "$n"
    docker_as_runner rm -f "intake-probe-$n" >/dev/null 2>&1
  done
  rm -rf "$out" "$TARGETS"
  say "probe: $# runners, $fails failed checks"
  [ "$fails" -eq 0 ]
}

# --- inside, as the runner's user in its job sandbox -----------------------------------

ok() { printf 'ok      %s: %s\n' "$RUNNER_NAME" "$*"; }
fail() {
  printf 'FAIL    %s: %s\n' "$RUNNER_NAME" "$*"
}
blocked() {
  local what=$1
  shift
  if "$@" >/dev/null 2>&1; then fail "reached $what"; else ok "blocked $what"; fi
}
reaches() {
  local what=$1
  shift
  if "$@" >/dev/null 2>&1; then ok "reaches $what"; else fail "cannot reach $what"; fi
}
# shellcheck disable=SC2016  # $1/$2 expand in the child bash, as intended
tcp() { timeout 4 bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$1" "$2"; }
in_container() { docker run --rm "$@"; }
listed() { [ -n "$(ls -A "$1" 2>/dev/null)" ]; }

probe_inside() {
  local p t m answer names capeff
  # shellcheck source=/dev/null
  . "$TARGETS"
  if [ "$(id -un)" = "$RUNNER_USER" ]; then ok "runs as $RUNNER_USER (uid $(id -u))"; else fail "runs as $(id -un)"; fi
  capeff=$(awk '/^CapEff/ { print $2 }' /proc/self/status)
  if [ "$capeff" = 0000000000000000 ]; then ok "holds no capability (CapEff 0)"; else fail "CapEff $capeff"; fi
  if [ "$(readlink /proc/self/ns/net)" = "net:[$(stat -L -c %i "/run/netns/$NETNS")]" ]; then
    ok "runs in its network namespace $NETNS"
  else
    fail "runs outside $NETNS"
  fi

  # Staging files, the OpenBao tokens, the host Docker socket, the root disk.
  for p in $DENIED_PATHS; do blocked "listing $p" listed "$p"; done
  for p in $SECRET_FILES; do blocked "reading $p" cat "$p"; done
  blocked "the host Docker socket" curl -fsS -m 4 --unix-socket /var/run/docker.sock http://docker/version
  for p in /usr/local /etc /var/log; do blocked "writing to $p" touch "$p/intake-probe-$INSTANCE"; done
  blocked "writing to its cache seed" touch "$CI_ROOT/seed/intake-probe-$INSTANCE"

  # The network: metadata, staging containers, every host listener.
  blocked "the instance metadata service" tcp 169.254.169.254 80
  for t in $STAGING_TCP; do blocked "staging container $t" tcp "${t%:*}" "${t##*:}"; done
  for p in $HOST_TCP; do
    blocked "host listener $HOST_IP:$p" tcp "$HOST_IP" "$p"
    blocked "host loopback 10.0.2.2:$p" tcp 10.0.2.2 "$p"
    blocked "host-local 127.0.0.1:$p" tcp 127.0.0.1 "$p"
  done

  # The other runners: their trees, their Docker sockets, their published ports.
  blocked "the single-runner tree $CI_ROOT_BASE" listed "$CI_ROOT_BASE"
  for m in $POOL_INSTANCES; do
    [ "$m" = "$INSTANCE" ] && continue
    blocked "runner $m's tree" listed "$CI_ROOT_BASE-$m"
    blocked "runner $m's Docker socket" curl -fsS -m 4 --unix-socket "$DOCKER_RUN_BASE-$m/docker.sock" http://docker/version
  done
  answer=$(curl -fsS -m 4 "http://127.0.0.1:$PROBE_PORT/id" 2>/dev/null)
  if [ "$answer" = "$RUNNER_NAME" ]; then
    ok "127.0.0.1:$PROBE_PORT answers with its own container ($answer)"
  else
    fail "127.0.0.1:$PROBE_PORT answers '$answer'"
  fi
  blocked "a published port at $HOST_IP:$PROBE_PORT" tcp "$HOST_IP" "$PROBE_PORT"
  blocked "a published port at 10.0.2.2:$PROBE_PORT" tcp 10.0.2.2 "$PROBE_PORT"
  names=$(docker ps --format '{{.Names}}' 2>/dev/null | grep '^intake-probe-' | tr '\n' ' ')
  if [ "$names" = "intake-probe-$INSTANCE " ]; then
    ok "its daemon lists only its own probe container"
  else
    fail "its daemon lists '$names'"
  fi

  # What a job needs.
  if docker info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
    ok "reaches its rootless Docker daemon"
  else
    fail "cannot reach a rootless Docker daemon"
  fi
  reaches "DNS (api.github.com)" getent hosts api.github.com
  reaches "public HTTPS (api.github.com)" curl -fsS -m 10 -o /dev/null https://api.github.com/zen
  reaches "a writable /tmp on the NVMe volume" touch "/tmp/intake-probe-$INSTANCE"
  rm -f "/tmp/intake-probe-$INSTANCE"

  # From a container of its daemon.
  blocked "the metadata service from a container" in_container "$PROBE_IMAGE" nc -w 3 169.254.169.254 80
  for t in $STAGING_TCP; do
    blocked "staging $t from a container" in_container "$PROBE_IMAGE" nc -w 3 "${t%:*}" "${t##*:}"
  done
  blocked "the host $HOST_IP:22 from a container" in_container "$PROBE_IMAGE" nc -w 3 "$HOST_IP" 22
  blocked "the host loopback from a container" in_container "$PROBE_IMAGE" nc -w 3 10.0.2.2 22
  reaches "public HTTPS from a container" in_container "$PROBE_IMAGE" wget -q -T 10 -O /dev/null https://api.github.com/zen
  blocked "the host Docker socket from a container" \
    in_container -v /var/run/docker.sock:/s "$PROBE_IMAGE" test -w /s
  for p in $DENIED_PATHS; do
    blocked "a bind mount of $p" in_container -v "$p:/x:ro" "$PROBE_IMAGE" sh -c 'ls -A /x | grep -q .'
  done
  for p in $SECRET_FILES; do
    blocked "$p through a bind mount of /" in_container -v /:/host:ro "$PROBE_IMAGE" cat "/host$p"
  done
  echo "probe done: $RUNNER_NAME"
}

main() {
  if [ "${1:-}" = --inside ]; then
    instance_env "${2:-}" || return 2
    probe_inside
    return 0
  fi
  probe_outside "$@"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
