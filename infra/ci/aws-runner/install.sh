#!/usr/bin/env bash
# INT-463 — install or update the intake-aws-ci GitHub Actions runner on the AWS
# host. Runs as root over SSM (scripts/ci/aws_runner.sh install), from a
# sha256-verified archive of this directory. Idempotent: a second run changes
# nothing that is already right.
#
#   1. disk first: refuses below 20 GiB free on the root disk, or without the
#      NVMe volume, and prints df before and after
#   2. packages: uidmap + slirp4netns (rootless Docker), acl (the access guard),
#      python3-dev, build-essential and shellcheck (as on GitHub's ubuntu image)
#   3. the user: ghrunner, a system user with no password, no login shell, a
#      subordinate id range, and no sudo/docker/adm group
#   4. pinned binaries: actions/runner and gh, each checked against its sha256
#      before it is unpacked
#   5. scripts, units and the slice, then the guards once (fail closed)
#   6. starts rootless Docker and proves it answers as ghrunner, then enables
#      and (re)starts the supervisor and the disk watchdog. The supervisor's
#      registrar mints a registration token before every registration from the
#      owner's admin token in SSM; if that fails it waits, offline.
# It never reads, prints or writes a credential.
set -euo pipefail
set +x

SRC=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=runner.conf
. "$SRC/runner.conf"

say() { printf 'intake-aws-ci install: %s\n' "$*"; }
die() {
  say "FAIL: $*"
  exit 1
}

[ "$(id -u)" -eq 0 ] || die "run as root"

# --- 1. disk -----------------------------------------------------------------------
findmnt -n "$NVME_MOUNT" >/dev/null || die "$NVME_MOUNT is not mounted"
root_free=$(df -P -BG / | awk 'NR==2 { gsub("G", "", $4); print $4 }')
[ "$root_free" -ge 20 ] || die "root disk has ${root_free} GiB free (< 20); nothing installed"
say "df before:"
df -h / "$NVME_MOUNT"

# --- 2. packages -------------------------------------------------------------------
missing=()
for pkg in uidmap slirp4netns acl python3-dev build-essential jq unzip xz-utils shellcheck; do
  dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
  say "apt install ${missing[*]}"
  export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
  apt-get update -qq >/dev/null
  apt-get install -y -qq --no-install-recommends "${missing[@]}" >/dev/null
fi

# --- 3. the user -------------------------------------------------------------------
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

# --- 4. pinned binaries ------------------------------------------------------------
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
# prepare.sh hands the token over in ACTIONS_RUNNER_INPUT_TOKEN; refuse a
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

# --- 5. scripts, units, guards -----------------------------------------------------
install -m 0644 -o root -g root "$SRC/runner.conf" "$SRC/daemon.json" "$LIB_DIR/"
scripts="guard.sh cycle.sh job-started.sh fetch-credential.sh"
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
for unit in intake-aws-ci.slice intake-aws-ci-dockerd.service intake-aws-ci-runner.service \
  intake-aws-ci-job.service intake-aws-ci-diskwatch.service intake-aws-ci-diskwatch.timer; do
  install -m 0644 -o root -g root "$SRC/$unit" "/etc/systemd/system/$unit"
done
# The Docker unit is started by cycle.sh after the guards, never at boot.
rm -f /etc/systemd/system/multi-user.target.wants/intake-aws-ci-dockerd.service
systemctl daemon-reload
"$LIB_DIR/bin/guard.sh" layout disk access net

# --- 6. start ----------------------------------------------------------------------
systemctl stop intake-aws-ci-runner.service
systemctl restart intake-aws-ci-dockerd.service
ok=0
for _ in $(seq 1 60); do
  if runuser -u "$RUNNER_USER" -- env DOCKER_HOST="unix://$DOCKER_RUN_DIR/docker.sock" \
    docker info --format '{{.ServerVersion}} {{.SecurityOptions}}' 2>/dev/null | grep -q rootless; then
    ok=1
    break
  fi
  sleep 2
done
[ "$ok" -eq 1 ] || die "rootless Docker did not come up as $RUNNER_USER (journalctl -u intake-aws-ci-dockerd)"
say "rootless Docker answers as $RUNNER_USER: $(runuser -u "$RUNNER_USER" -- env DOCKER_HOST="unix://$DOCKER_RUN_DIR/docker.sock" docker info --format '{{.ServerVersion}}')"
systemctl enable --now intake-aws-ci-diskwatch.timer >/dev/null 2>&1
systemctl enable intake-aws-ci-runner.service >/dev/null 2>&1
systemctl restart --no-block intake-aws-ci-runner.service
rm -f "$SECRET_DIR/registrar-header"
say "supervisor (re)started; its registrar reads $REGISTRAR_PARAM before every registration"
say "df after:"
df -h / "$NVME_MOUNT"
