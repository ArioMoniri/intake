#!/usr/bin/env bash
# INT-463 — the host guards for the intake-aws-ci runner. Runs as root.
#
#   guard.sh layout   the CI tree on the NVMe volume, owned by the runner user
#   guard.sh disk     free space on the CI volume and the root disk; prunes the
#                     runner's image store once, then refuses if still short
#   guard.sh access   denies the runner user every staging path (ACL), then
#                     proves the denial as that user
#   guard.sh net      the runner user's egress: no instance metadata (the
#                     instance role can read every SSM parameter), no staging
#                     container network, no host-local service, no private
#                     range. DNS and the public internet stay open.
#   guard.sh watch    the one-minute disk watchdog: stops a running job before
#                     either disk reaches its floor
#
# cycle.sh sources this file for the same functions. Every
# check fails closed: a non-zero exit keeps the runner from taking a job.
set -euo pipefail
set +x

INTAKE_AWS_CI_CONF=${INTAKE_AWS_CI_CONF:-/usr/local/lib/intake-aws-ci-runner/runner.conf}
# shellcheck source=runner.conf
. "$INTAKE_AWS_CI_CONF"

JOB_UNIT=intake-aws-ci-job.service
# shellcheck disable=SC2034  # used by cycle.sh, which sources this file
DOCKERD_UNIT=intake-aws-ci-dockerd.service
NET_CHAIN=INTAKE-AWS-CI-OUT

say() { printf 'intake-aws-ci: %s\n' "$*"; }

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
  # Unquoted on purpose: SENSITIVE_PATHS holds globs that must expand here.
  # shellcheck disable=SC2086
  for p in $SENSITIVE_PATHS; do
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
  say "access ok: $RUNNER_USER is denied $(sensitive_paths | wc -l | tr -d ' ') staging paths and the host Docker socket"
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
  # Every port something listens on before a job starts belongs to the host
  # or to staging: the runner's own published ports appear only during a job.
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

main() {
  if [ "$(id -u)" -ne 0 ]; then
    say "FAIL: guard.sh runs as root"
    return 1
  fi
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
