#!/usr/bin/env bash
# INT-463, INT-467 — install or update the intake-aws-ci runner pool on the AWS
# host: every runner of POOL_INSTANCES. Runs as root over SSM
# (scripts/ci/aws_runner.sh install), from a sha256-verified archive of this
# directory. Idempotent: a second run changes nothing that is already right.
#
#   1. disk first: refuses below 20 GiB free on the root disk, or without the
#      NVMe volume, and prints df before and after
#   2. packages: uidmap + slirp4netns (rootless Docker), acl (the access guard),
#      iproute2 (the job namespace), python3-dev, build-essential and shellcheck
#      (as on GitHub's ubuntu image)
#   3. the drain: every running supervisor is stopped once its runner holds no
#      job (or after DRAIN_TIMEOUT_S), before any script it runs is replaced
#   4. the INT-463 single-runner layout, if present: its user ghrunner holds the
#      subordinate range runner 1 takes, so its units, chain, ACL entries, user
#      and tree go before any runner user is created
#   5. the users: ghrunnerN, system users with no password, no login shell, a
#      subordinate id range each that overlaps no other, and no
#      sudo/docker/adm group
#   6. pinned binaries: actions/runner and gh, each checked against its sha256
#      before it is unpacked
#   7. scripts, units, the slice and the jobs' resolver, then every runner's
#      guards once (fail closed)
#   8. each runner's rootless Docker, proved to answer as its user and to
#      forward nothing to the host (guard.sh netns); then its supervisor and
#      disk watchdog are enabled and started. Each supervisor's registrar mints
#      a registration token before every registration from the owner's admin
#      token in SSM; if that fails it waits, offline. A runner no longer in
#      POOL_INSTANCES stays stopped and disabled.
# It never reads, prints or writes a credential.
set -euo pipefail
set +x

SRC=$(cd "$(dirname "$0")" && pwd)
INTAKE_AWS_CI_CONF=$SRC/runner.conf
# shellcheck source=guard.sh
. "$SRC/guard.sh"

say() { printf 'intake-aws-ci install: %s\n' "$*"; }
die() {
  say "FAIL: $*"
  exit 1
}

[ "$(id -u)" -eq 0 ] || die "run as root"

# A job on this host takes up to about 40 min (check-py, INT-426).
DRAIN_TIMEOUT_S=2700
UNITS="intake-aws-ci.slice intake-aws-ci-runner@.service intake-aws-ci-job@.service intake-aws-ci-dockerd@.service intake-aws-ci-diskwatch@.service intake-aws-ci-diskwatch@.timer"
LEGACY_UNITS="intake-aws-ci-runner.service intake-aws-ci-job.service intake-aws-ci-dockerd.service intake-aws-ci-diskwatch.timer intake-aws-ci-diskwatch.service"

for n in $POOL_INSTANCES; do
  instance_env "$n" >/dev/null || die "POOL_INSTANCES holds '$n', which is not a runner number"
done

drain() {
  # Arguments: "user unit" pairs. Each supervisor is stopped as soon as its user
  # runs no job (no Runner.Worker), or once DRAIN_TIMEOUT_S has passed; its job
  # and Docker units stop with it (PartOf=). bash reads a running script by
  # offset, so no supervisor may run while its scripts are replaced.
  local waited=0 pair user unit
  local pending=("$@") left=()
  while [ "${#pending[@]}" -gt 0 ]; do
    left=()
    for pair in "${pending[@]}"; do
      user=${pair%% *}
      unit=${pair#* }
      if [ "$waited" -lt "$DRAIN_TIMEOUT_S" ] && id "$user" >/dev/null 2>&1 &&
        pgrep -u "$user" -f Runner.Worker >/dev/null; then
        left+=("$pair")
      else
        systemctl stop "$unit" 2>/dev/null || true
        say "stopped $unit after ${waited} s"
      fi
    done
    pending=("${left[@]}")
    if [ "${#pending[@]}" -gt 0 ]; then
      sleep 10
      waited=$((waited + 10))
    fi
  done
}

remove_legacy() {
  # The INT-463 single-runner layout: one user (ghrunner) for every job,
  # untemplated units and the chain INTAKE-AWS-CI-OUT. Runner 1 takes its
  # subordinate id range, so all of it goes before any runner user is created.
  local unit ipt uid path
  for unit in $LEGACY_UNITS; do
    if [ -e "/etc/systemd/system/$unit" ]; then
      systemctl disable --now "$unit" >/dev/null 2>&1 || true
      rm -f "/etc/systemd/system/$unit"
    fi
  done
  systemctl daemon-reload
  if ! id "$LEGACY_RUNNER_USER" >/dev/null 2>&1; then
    return 0
  fi
  uid=$(id -u "$LEGACY_RUNNER_USER")
  for ipt in iptables ip6tables; do
    while "$ipt" -w -D OUTPUT -m owner --uid-owner "$uid" -j "$LEGACY_NET_CHAIN" 2>/dev/null; do :; done
    "$ipt" -w -F "$LEGACY_NET_CHAIN" 2>/dev/null || true
    "$ipt" -w -X "$LEGACY_NET_CHAIN" 2>/dev/null || true
  done
  while IFS= read -r path; do
    setfacl -x "u:$LEGACY_RUNNER_USER" "$path" 2>/dev/null || true
  done < <(sensitive_paths)
  pkill -KILL -u "$LEGACY_RUNNER_USER" 2>/dev/null || true
  for _ in $(seq 1 30); do
    pgrep -u "$LEGACY_RUNNER_USER" >/dev/null || break
    sleep 1
  done
  userdel "$LEGACY_RUNNER_USER"
  sed -i "/^$LEGACY_RUNNER_USER:/d" /etc/subuid /etc/subgid
  rm -rf --one-file-system "${LEGACY_CI_ROOT:?}" "$DOCKER_RUN_BASE"
  say "removed the INT-463 single-runner layout (user $LEGACY_RUNNER_USER, uid $uid, its chain and tree)"
}

# --- 1. disk -----------------------------------------------------------------------
findmnt -n "$NVME_MOUNT" >/dev/null || die "$NVME_MOUNT is not mounted"
root_free=$(df -P -BG / | awk 'NR==2 { gsub("G", "", $4); print $4 }')
[ "$root_free" -ge 20 ] || die "root disk has ${root_free} GiB free (< 20); nothing installed"
say "df before:"
df -h / "$NVME_MOUNT"

# --- 2. packages -------------------------------------------------------------------
missing=()
for pkg in uidmap slirp4netns acl iproute2 python3-dev build-essential jq unzip xz-utils shellcheck; do
  dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
  say "apt install ${missing[*]}"
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
  apt-get update -qq >/dev/null
  apt-get install -y -qq --no-install-recommends "${missing[@]}" >/dev/null
fi

# --- 3. the drain ------------------------------------------------------------------
running=()
if systemctl is-active --quiet intake-aws-ci-runner.service; then
  running+=("$LEGACY_RUNNER_USER intake-aws-ci-runner.service")
fi
for unit in $(systemctl list-units 'intake-aws-ci-runner@*' --all --plain --no-legend | awk '{ print $1 }'); do
  n=${unit#intake-aws-ci-runner@}
  running+=("$RUNNER_USER_PREFIX${n%.service} $unit")
done
if [ "${#running[@]}" -gt 0 ]; then
  drain "${running[@]}"
fi

# --- 4. the single-runner layout ---------------------------------------------------
remove_legacy

# --- 5. the users ------------------------------------------------------------------
for n in $POOL_INSTANCES; do
  instance_env "$n"
  if ! id "$RUNNER_USER" >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --home-dir "$CI_ROOT/home" \
      --shell /usr/sbin/nologin "$RUNNER_USER"
    say "created user $RUNNER_USER"
  fi
  usermod --home "$CI_ROOT/home" --shell /usr/sbin/nologin "$RUNNER_USER"
  passwd -l "$RUNNER_USER" >/dev/null
  for group in sudo admin wheel docker adm lxd systemd-journal; do
    if id -nG "$RUNNER_USER" | tr ' ' '\n' | grep -qx "$group"; then
      gpasswd -d "$RUNNER_USER" "$group" >/dev/null
    fi
  done
  last=$((SUBID_START + SUBID_COUNT - 1))
  grep -q "^$RUNNER_USER:" /etc/subuid || usermod --add-subuids "$SUBID_START-$last" "$RUNNER_USER"
  grep -q "^$RUNNER_USER:" /etc/subgid || usermod --add-subgids "$SUBID_START-$last" "$RUNNER_USER"
  for ids in /etc/subuid /etc/subgid; do
    [ "$(grep "^$RUNNER_USER:" "$ids")" = "$RUNNER_USER:$SUBID_START:$SUBID_COUNT" ] ||
      die "$RUNNER_USER's range in $ids is not $SUBID_START:$SUBID_COUNT"
    overlap=$(awk -F: -v u="$RUNNER_USER" -v s="$SUBID_START" -v c="$SUBID_COUNT" \
      '$1 != u && $2 < s + c && s < $2 + $3 { print $1 }' "$ids")
    [ -z "$overlap" ] || die "$RUNNER_USER's range in $ids overlaps $overlap"
  done
done

# --- 6. pinned binaries ------------------------------------------------------------
install -d -m 0755 -o root -g root "$LIB_DIR" "$LIB_DIR/bin"
stage=$(mktemp -d -p "$NVME_MOUNT")
trap 'rm -rf "${stage:?}"' EXIT

dist="$LIB_DIR/actions-runner-$RUNNER_VERSION"
if [ ! -x "$dist/run.sh" ]; then
  tarball="actions-runner-linux-x64-$RUNNER_VERSION.tar.gz"
  curl -fsSL -o "$stage/$tarball" \
    "https://github.com/actions/runner/releases/download/v$RUNNER_VERSION/$tarball"
  echo "$RUNNER_SHA256  $stage/$tarball" | sha256sum -c --quiet
  install -d -m 0755 "$dist.new"
  tar -xzf "$stage/$tarball" -C "$dist.new"
  chown -R root:root "$dist.new"
  chmod -R go-w "$dist.new"
  rm -rf "${dist:?}"
  mv "$dist.new" "$dist"
  say "actions/runner $RUNNER_VERSION installed (sha256 verified)"
fi
"$dist/bin/installdependencies.sh" >/dev/null 2>&1 || die "the runner's installdependencies.sh failed"
# cycle.sh hands the token over in ACTIONS_RUNNER_INPUT_TOKEN; refuse a
# runner build that would not read it from the environment. .NET keeps string
# literals as UTF-16, hence the interleaved NULs.
grep -a -q -P 'A\x00C\x00T\x00I\x00O\x00N\x00S\x00_\x00R\x00U\x00N\x00N\x00E\x00R\x00_\x00I\x00N\x00P\x00U\x00T\x00_' \
  "$dist/bin/Runner.Listener.dll" || die "this runner build does not read ACTIONS_RUNNER_INPUT_*"

if [ "$(gh --version 2>/dev/null | awk 'NR==1 { print $3 }')" != "$GH_VERSION" ]; then
  tarball="gh_${GH_VERSION}_linux_amd64.tar.gz"
  curl -fsSL -o "$stage/$tarball" \
    "https://github.com/cli/cli/releases/download/v$GH_VERSION/$tarball"
  echo "$GH_SHA256  $stage/$tarball" | sha256sum -c --quiet
  tar -xzf "$stage/$tarball" -C "$stage"
  install -m 0755 -o root -g root "$stage/gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh
  say "gh $GH_VERSION installed (sha256 verified)"
fi

# --- 7. scripts, units, guards -----------------------------------------------------
install -m 0644 -o root -g root "$SRC/runner.conf" "$SRC/daemon.json" "$SRC/resolv.conf" "$LIB_DIR/"
scripts="guard.sh cycle.sh job-started.sh fetch-credential.sh probe.sh"
for script in $scripts; do
  install -m 0755 -o root -g root "$SRC/$script" "$LIB_DIR/bin/$script"
done
for installed in "$LIB_DIR"/bin/*; do
  case " $scripts " in
    *" $(basename "$installed") "*) ;;
    *) rm -f "$installed" ;;
  esac
done
install -d -m 0700 -o root -g root "$SECRET_DIR"
for unit in $UNITS; do
  install -m 0644 -o root -g root "$SRC/$unit" "/etc/systemd/system/$unit"
done
# A Docker unit is started by cycle.sh after the guards, never at boot.
rm -f /etc/systemd/system/multi-user.target.wants/intake-aws-ci-dockerd@*.service
systemctl daemon-reload
for n in $POOL_INSTANCES; do
  "$LIB_DIR/bin/guard.sh" "$n" layout disk access net
done

# --- 8. start ----------------------------------------------------------------------
for n in $POOL_INSTANCES; do
  instance_env "$n"
  systemctl restart "$DOCKERD_UNIT"
  ok=0
  for _ in $(seq 1 60); do
    if docker_as_runner info --format '{{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
      ok=1
      break
    fi
    sleep 2
  done
  [ "$ok" -eq 1 ] || die "rootless Docker did not come up as $RUNNER_USER (journalctl -u $DOCKERD_UNIT)"
  "$LIB_DIR/bin/guard.sh" "$n" netns || die "the job namespace of $RUNNER_NAME failed its guard"
  say "rootless Docker answers as $RUNNER_USER: $(docker_as_runner info --format '{{.ServerVersion}}')"
  systemctl enable --now "intake-aws-ci-diskwatch@$n.timer" >/dev/null 2>&1
  systemctl enable "intake-aws-ci-runner@$n.service" >/dev/null 2>&1
  systemctl restart --no-block "intake-aws-ci-runner@$n.service"
done
for unit in $(systemctl list-unit-files 'intake-aws-ci-runner@*' --plain --no-legend | awk '{ print $1 }') \
  $(systemctl list-units 'intake-aws-ci-runner@*' --all --plain --no-legend | awk '{ print $1 }'); do
  n=${unit#intake-aws-ci-runner@}
  n=${n%.service}
  # The template itself has no instance.
  [ -n "$n" ] || continue
  case " $POOL_INSTANCES " in
    *" $n "*) ;;
    *)
      systemctl disable --now "$unit" "intake-aws-ci-diskwatch@$n.timer" >/dev/null 2>&1 || true
      say "disabled $unit: runner $n is not in the pool"
      ;;
  esac
done
rm -f "$SECRET_DIR/registrar-header"
say "supervisors of $POOL_INSTANCES (re)started; each registrar reads $REGISTRAR_PARAM before every registration"
say "df after:"
df -h / "$NVME_MOUNT"
