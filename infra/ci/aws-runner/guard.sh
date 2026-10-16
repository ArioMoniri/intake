#!/usr/bin/env bash
# INT-463, INT-467 — the host guards for one runner of the intake-aws-ci pool.
# Runs as root. The first argument is the runner's instance number.
#
#   guard.sh N layout  the runner's CI tree on the NVMe volume, owned by its user
#   guard.sh N disk    free space on the CI volume and the root disk; prunes the
#                      runner's own image store once, then refuses if still short
#   guard.sh N access  denies the runner's user every staging path and every
#                      other runner's tree (ACL), then proves it as that user
#   guard.sh N net     the runner user's egress: no instance metadata (the
#                      instance role can read every SSM parameter), no staging
#                      container network, no host-local service, no private
#                      range. DNS and the public internet stay open.
#   guard.sh N netns   the runner's job namespace: attaches its rootless daemon's
#                      detached network namespace for the job unit and proves
#                      no port is forwarded to the host and the metadata service
#                      and host loopback are refused from inside it
#   guard.sh N watch   the one-minute disk watchdog: stops the runner's job
#                      before either disk reaches its floor
#
# cycle.sh, install.sh, probe.sh and job-started.sh source this file for the
# same functions. Every check fails closed: a non-zero exit keeps the runner
# from taking a job.
set -euo pipefail
set +x

INTAKE_AWS_CI_CONF=${INTAKE_AWS_CI_CONF:-/usr/local/lib/intake-aws-ci-runner/runner.conf}
# shellcheck source=runner.conf
. "$INTAKE_AWS_CI_CONF"

say() { printf 'intake-aws-ci: %s\n' "$*"; }

# shellcheck disable=SC2034  # the variables are read by the scripts that source this file
instance_env() {
  # $1: the runner's instance number, one of POOL_INSTANCES. Everything one
  # runner must not share with another is derived here and nowhere else.
  local n=${1:-}
  if ! [[ "$n" =~ ^[1-9]$ ]] || [[ " $POOL_INSTANCES " != *" $n "* ]]; then
    say "FAIL: '$n' is not a runner of this pool ($POOL_INSTANCES)"
    return 1
  fi
  INSTANCE=$n
  RUNNER_USER=$RUNNER_USER_PREFIX$n
  RUNNER_NAME=$RUNNER_NAME_PREFIX$n
  CI_ROOT=$CI_ROOT_BASE-$n
  DOCKER_RUN_DIR=$DOCKER_RUN_BASE-$n
  NET_CHAIN=$NET_CHAIN_BASE-$n
  NETNS=$RUNNER_NAME
  SUBID_START=$((SUBID_BASE + (n - 1) * SUBID_COUNT))
  JOB_UNIT=intake-aws-ci-job@$n.service
  DOCKERD_UNIT=intake-aws-ci-dockerd@$n.service
}

free_gb() { df -P -BG "$1" | awk 'NR==2 { gsub("G", "", $4); print $4 }'; }

used_pct() { df -P "$1" | awk 'NR==2 { gsub("%", "", $5); print $5 }'; }

as_runner() { runuser -u "$RUNNER_USER" -- "$@"; }

docker_as_runner() {
  runuser -u "$RUNNER_USER" -- env DOCKER_HOST="unix://$DOCKER_RUN_DIR/docker.sock" docker "$@"
}

docker_up() {
  [ -S "$DOCKER_RUN_DIR/docker.sock" ] && docker_as_runner info >/dev/null 2>&1
}

# --- layout ------------------------------------------------------------------------

guard_layout() {
  if ! findmnt -n "$NVME_MOUNT" >/dev/null; then
    say "FAIL: $NVME_MOUNT is not mounted; the runner never falls back to the root disk"
    return 1
  fi
  # The runner insists on reading every directory above its own, so the
  # runner group may list the CI root; nobody else may.
  install -d -m 0750 -o root -g "$RUNNER_USER" "$CI_ROOT"
  local d
  # The workspace is $CI_ROOT/home/work, under HOME as on GitHub's runners.
  for d in runner home tmp docker dockerhome; do
    install -d -m 0700 -o "$RUNNER_USER" -g "$RUNNER_USER" "$CI_ROOT/$d"
  done
}

wipe_job_state() {
  # The runner tree, workspace and home go entirely. /tmp is bind-mounted into
  # the Docker unit as well, so its directory stays and only its contents go.
  local d
  for d in runner work home; do
    rm -rf --one-file-system "${CI_ROOT:?}/$d"
  done
  if [ -d "$CI_ROOT/tmp" ]; then
    find "${CI_ROOT:?}/tmp" -xdev -mindepth 1 -delete
  fi
  guard_layout
}

# --- disk --------------------------------------------------------------------------

guard_disk() {
  guard_layout
  local ci root pct
  ci=$(free_gb "$CI_ROOT")
  root=$(free_gb /)
  pct=$(used_pct "$CI_ROOT")
  if [ "$ci" -lt "$MIN_FREE_CI_GB" ] || [ "$pct" -ge "$PRUNE_ABOVE_USED_PCT" ]; then
    say "CI volume ${pct}% used, ${ci} GiB free: pruning the runner's image store"
    if docker_up; then
      docker_as_runner system prune -af --volumes >/dev/null 2>&1 || true
    fi
    ci=$(free_gb "$CI_ROOT")
  fi
  if [ "$ci" -lt "$MIN_FREE_CI_GB" ]; then
    say "FAIL: CI volume has ${ci} GiB free (< ${MIN_FREE_CI_GB}); no job is taken"
    return 1
  fi
  if [ "$root" -lt "$MIN_FREE_ROOT_GB" ]; then
    say "FAIL: root disk has ${root} GiB free (< ${MIN_FREE_ROOT_GB}); no job is taken"
    return 1
  fi
  say "disk ok: CI volume ${ci} GiB free, root disk ${root} GiB free"
}

guard_watch() {
  local ci root
  ci=$(free_gb "$CI_ROOT" 2>/dev/null || echo 0)
  root=$(free_gb /)
  if [ "$ci" -lt "$WATCH_FLOOR_CI_GB" ] || [ "$root" -lt "$WATCH_FLOOR_ROOT_GB" ]; then
    say "WATCHDOG: CI volume ${ci} GiB, root disk ${root} GiB free; stopping the running job"
    systemctl kill --kill-whom=all "$JOB_UNIT" || true
    return 1
  fi
}

# --- access ------------------------------------------------------------------------

sensitive_paths() {
  local p
  # Unquoted on purpose: both lists hold globs that must expand here.
  # shellcheck disable=SC2086
  for p in $SENSITIVE_PATHS $PEER_PATHS; do
    if [ "$p" = "$CI_ROOT" ] || [ "$p" = "$DOCKER_RUN_DIR" ]; then
      continue
    fi
    if [ -e "$p" ] || [ -L "$p" ]; then
      printf '%s\n' "$p"
    fi
  done
}

guard_access() {
  if ! id "$RUNNER_USER" >/dev/null 2>&1; then
    say "FAIL: user $RUNNER_USER does not exist"
    return 1
  fi
  local group bad=0 path
  for group in root sudo admin wheel docker adm lxd systemd-journal; do
    if id -nG "$RUNNER_USER" | tr ' ' '\n' | grep -qx "$group"; then
      say "FAIL: $RUNNER_USER is in group $group"
      bad=1
    fi
  done
  while IFS= read -r path; do
    setfacl -m "u:$RUNNER_USER:---" "$path"
    if as_runner test -r "$path"; then
      say "FAIL: $RUNNER_USER can read $path"
      bad=1
    elif [ -d "$path" ] && as_runner test -x "$path"; then
      say "FAIL: $RUNNER_USER can traverse $path"
      bad=1
    fi
  done < <(sensitive_paths)
  if as_runner test -r /var/run/docker.sock || as_runner test -w /var/run/docker.sock; then
    say "FAIL: $RUNNER_USER can reach the host Docker socket"
    bad=1
  fi
  if [ "$bad" -ne 0 ]; then
    return 1
  fi
  say "access ok: $RUNNER_USER is denied $(sensitive_paths | wc -l | tr -d ' ') staging and peer paths and the host Docker socket"
}

# --- network -----------------------------------------------------------------------

root_docker_subnets() {
  docker network ls -q --filter driver=bridge 2>/dev/null |
    xargs -r docker network inspect --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}' 2>/dev/null |
    tr ' ' '\n' | grep -E '^[0-9.]+/[0-9]+$' | sort -u
}

upstream_resolvers() {
  resolvectl dns 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | sort -u
}

foreign_ports() {
  # Every port something listens on belongs to the host or to staging: no
  # runner forwards a published port to the host (guard_netns proves it).
  ss -Hltun | awk '{ n = split($5, a, ":"); print $1, a[n] }' | sort -u
}

runner_can_connect() {
  # $1 host, $2 port: exit 0 only when the runner user completes a TCP connect.
  # shellcheck disable=SC2016  # $1/$2 expand in the child bash, as intended
  as_runner timeout 4 bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$1" "$2" 2>/dev/null
}

reset_chain() {
  local ipt=$1
  "$ipt" -w -N "$NET_CHAIN" 2>/dev/null || "$ipt" -w -F "$NET_CHAIN"
  if ! "$ipt" -w -C OUTPUT -m owner --uid-owner "$RUNNER_USER" -j "$NET_CHAIN" 2>/dev/null; then
    "$ipt" -w -I OUTPUT 1 -m owner --uid-owner "$RUNNER_USER" -j "$NET_CHAIN"
  fi
}

guard_net() {
  local resolver subnet proto port
  reset_chain iptables
  for resolver in 127.0.0.53 127.0.0.54 $(upstream_resolvers); do
    iptables -w -A "$NET_CHAIN" -d "$resolver" -p udp --dport 53 -j RETURN
    iptables -w -A "$NET_CHAIN" -d "$resolver" -p tcp --dport 53 -j RETURN
  done
  iptables -w -A "$NET_CHAIN" -d 169.254.0.0/16 -j REJECT
  for subnet in $(root_docker_subnets); do
    iptables -w -A "$NET_CHAIN" -d "$subnet" -j REJECT
  done
  for subnet in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10; do
    iptables -w -A "$NET_CHAIN" -d "$subnet" -j REJECT
  done
  while read -r proto port; do
    if [ "$port" = 53 ] || [ -z "$port" ]; then
      continue
    fi
    iptables -w -A "$NET_CHAIN" -d 127.0.0.0/8 -p "$proto" --dport "$port" -j REJECT
  done < <(foreign_ports)

  reset_chain ip6tables
  for subnet in fd00:ec2::/32 fe80::/10 fc00::/7; do
    ip6tables -w -A "$NET_CHAIN" -d "$subnet" -j REJECT
  done
  while read -r proto port; do
    if [ -z "$port" ]; then
      continue
    fi
    ip6tables -w -A "$NET_CHAIN" -d ::1/128 -p "$proto" --dport "$port" -j REJECT
  done < <(foreign_ports)

  # Prove two of the rules as the runner user, not just their presence: a TCP
  # connect, so neither a TLS failure nor an HTTP error can pass for a block.
  if runner_can_connect 169.254.169.254 80; then
    say "FAIL: $RUNNER_USER can reach the instance metadata service"
    return 1
  fi
  if ss -Hltn 'sport = :443' | grep -q . && runner_can_connect 127.0.0.1 443; then
    say "FAIL: $RUNNER_USER can reach a host-local listener"
    return 1
  fi
  say "net ok: $(iptables -w -S "$NET_CHAIN" | grep -c -- '-j REJECT') v4 and $(ip6tables -w -S "$NET_CHAIN" | grep -c -- '-j REJECT') v6 reject rules for $RUNNER_USER"
}

# --- the job's network namespace -----------------------------------------------------

attach_netns() {
  # The job unit joins /run/netns/$NETNS (NetworkNamespacePath). It must be the
  # rootless daemon's detached network namespace, where its containers and their
  # published ports live, and never the host's own.
  local pid ns
  pid=$(cat "$DOCKER_RUN_DIR/dockerd-rootless/child_pid" 2>/dev/null) || pid=""
  if ! [[ "$pid" =~ ^[0-9]+$ ]] || [ "$(stat -c %U "/proc/$pid" 2>/dev/null)" != "$RUNNER_USER" ]; then
    say "FAIL: no rootlesskit child of $RUNNER_USER"
    return 1
  fi
  ns=$(readlink "/proc/$pid/ns/net")
  if [ "$ns" = "$(readlink /proc/1/ns/net)" ]; then
    say "FAIL: the rootlesskit child of $RUNNER_USER is in the host network namespace"
    return 1
  fi
  if [ "$ns" != "net:[$(stat -L -c %i "/proc/$pid/root$DOCKER_RUN_DIR/dockerd-rootless/netns" 2>/dev/null)]" ]; then
    say "FAIL: the rootlesskit child of $RUNNER_USER is not in its detached network namespace"
    return 1
  fi
  ip netns delete "$NETNS" 2>/dev/null || true
  ip netns attach "$NETNS" "$pid"
}

netns_can_connect() {
  # $1 host, $2 port: exit 0 only when the runner user, inside its job's
  # network namespace, completes a TCP connect.
  # shellcheck disable=SC2016  # $1/$2 expand in the child bash, as intended
  nsenter --net="/run/netns/$NETNS" runuser -u "$RUNNER_USER" -- \
    timeout 4 bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$1" "$2" 2>/dev/null
}

host_listeners_of_runner() {
  # TCP sockets the runner's user listens on in the host's namespace.
  ss -Hltne | grep -cw "uid:$(id -u "$RUNNER_USER")" || true
}

guard_netns() {
  attach_netns || return 1
  local pid flags flag
  pid=$(cat "$DOCKER_RUN_DIR/dockerd-rootless/child_pid")
  flags=$(tr '\0' ' ' <"/proc/$pid/cmdline")
  for flag in --port-driver=none --disable-host-loopback --detach-netns; do
    if [[ " $flags " != *" $flag "* ]]; then
      say "FAIL: rootlesskit of $RUNNER_USER runs without $flag"
      return 1
    fi
  done
  if [ "$(host_listeners_of_runner)" -ne 0 ]; then
    say "FAIL: $RUNNER_USER listens on the host: a published port would escape its namespace"
    return 1
  fi
  if netns_can_connect 169.254.169.254 80; then
    say "FAIL: $RUNNER_USER can reach the instance metadata service from its job namespace"
    return 1
  fi
  if netns_can_connect 10.0.2.2 22; then
    say "FAIL: $RUNNER_USER can reach the host loopback from its job namespace"
    return 1
  fi
  say "netns ok: $NETNS is $(stat -L -c 'net:[%i]' "/run/netns/$NETNS"), no port forwarded to the host, metadata and host loopback refused"
}

main() {
  if [ "$(id -u)" -ne 0 ]; then
    say "FAIL: guard.sh runs as root"
    return 1
  fi
  instance_env "${1:-}" || return 2
  shift
  if [ $# -eq 0 ]; then
    set -- layout disk access net
  fi
  local step
  for step in "$@"; do
    case "$step" in
      layout) guard_layout ;;
      disk) guard_disk ;;
      access) guard_access ;;
      net) guard_net ;;
      netns) guard_netns ;;
      watch) guard_watch ;;
      *)
        say "unknown guard: $step"
        return 2
        ;;
    esac
  done
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
