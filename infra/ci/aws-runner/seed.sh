#!/usr/bin/env bash
# INT-544 — the cache seed of the intake-aws-ci pool. Runs as root.
#
#   seed.sh stage <url> <sha256>
#       sent over SSM by scripts/ci/aws_runner.sh seed: fetch the owner's inputs
#       bundle (a presigned S3 URL), check it against its sha256, check what it
#       holds, and swap it into SEED_INPUTS. No runner user can read that
#       directory (guard.sh access denies it with the peer paths).
#   seed.sh N refresh
#       cycle.sh's registrar, between two jobs of runner N, after its guards
#       and before its registration: if runner N's seed was not built from the
#       inputs now staged, rebuild it; otherwise check that it is still whole.
#
# Runner N's seed, $CI_ROOT/seed (root-owned; the job unit binds it read-only):
#   current -> gen-<first 16 hex of the inputs bundle's sha256>
#   gen-*/uv/               a uv cache: `uv sync --frozen` of the shipped uv.lock
#   gen-*/pnpm-store/       a pnpm store: `pnpm fetch` of the shipped lockfile
#   gen-*/deid/<tag>.tar.gz the deid NER release asset, checked against its pin
#   gen-*/MANIFEST.sha256   the sha256 of every file above
#   gen-*/SEED              inputs=<bundle sha256> manifest=<sha256 of MANIFEST>
#
# The build runs in the job unit's own sandbox (job_props), as the runner's
# user, in its network namespace: package code that runs while uv builds a
# wheel runs exactly where a job's would. uv and pnpm check every package
# against the hashes in the shipped lockfiles. Root then copies the result,
# owns it, refuses any device, pipe, socket, setuid bit or link that leaves the
# tree, and writes the manifest. Jobs check each file they restore against it
# (scripts/ci/ci_seed.sh).
#
# A refresh that fails removes the seed: the runner then registers without one,
# and its jobs fetch from the network as they did before INT-544.
set -euo pipefail
set +x

INTAKE_AWS_CI_CONF=${INTAKE_AWS_CI_CONF:-/usr/local/lib/intake-aws-ci-runner/runner.conf}
# shellcheck source=guard.sh
. "${BASH_SOURCE[0]%/*}/guard.sh"

say() { printf 'intake-aws-ci seed: %s\n' "$*"; }

is_sha256() { [[ "$1" =~ ^[0-9a-f]{64}$ ]]; }

# $1 a file, $2 the sha256 it must have.
sha256_is() { [ "$(sha256sum "$1" | awk '{ print $1 }')" = "$2" ]; }

# --- stage: the owner's inputs ---------------------------------------------------------

check_inputs() {
  # $1: an unpacked bundle. Lockfiles and manifests only, plus the deid asset.
  local dir=$1 bad
  for f in tree/uv.lock tree/pyproject.toml tree/pnpm-lock.yaml tree/pnpm-workspace.yaml \
    "deid/$SEED_DEID_TAG.tar.gz" REF; do
    [ -f "$dir/$f" ] || {
      say "FAIL: the bundle has no $f"
      return 1
    }
  done
  bad=$(find "$dir" -mindepth 1 ! -type d ! -type f -print -quit)
  if [ -n "$bad" ]; then
    say "FAIL: the bundle holds something that is neither a file nor a directory"
    return 1
  fi
  bad=$(find "$dir/tree" -type f ! -name uv.lock ! -name pnpm-lock.yaml \
    ! -name pnpm-workspace.yaml ! -name pyproject.toml ! -name package.json \
    ! -name .python-version -print -quit)
  if [ -n "$bad" ]; then
    say "FAIL: the bundle's tree holds a file that is not a lockfile or a manifest"
    return 1
  fi
  if ! sha256_is "$dir/deid/$SEED_DEID_TAG.tar.gz" "$SEED_DEID_SHA256"; then
    say "FAIL: the deid asset does not match SEED_DEID_SHA256"
    return 1
  fi
}

stage() {
  local url=${1:-} sha=${2:-} work
  is_sha256 "$sha" || {
    say "FAIL: usage: seed.sh stage <url> <sha256>"
    return 2
  }
  findmnt -n "$NVME_MOUNT" >/dev/null || {
    say "FAIL: $NVME_MOUNT is not mounted"
    return 1
  }
  umask 077
  work=$(mktemp -d -p "$NVME_MOUNT")
  # shellcheck disable=SC2064  # the path is fixed now, on purpose
  trap "rm -rf --one-file-system '$work'" EXIT
  if ! curl -fsS -o "$work/bundle.tar.gz" "$url" ||
    ! sha256_is "$work/bundle.tar.gz" "$sha" ||
    ! install -d -m 0700 "$work/new" ||
    ! tar -xzf "$work/bundle.tar.gz" -C "$work/new" --no-same-owner --no-same-permissions; then
    say "FAIL: the bundle did not download, match $sha or unpack"
    return 1
  fi
  check_inputs "$work/new" || return 1
  printf '%s\n' "$sha" >"$work/new/BUNDLE" &&
    chown -R root:root "$work/new" &&
    chmod -R go-rwx "$work/new" &&
    rm -rf --one-file-system "${SEED_INPUTS:?}.old" || return 1
  if [ -d "$SEED_INPUTS" ]; then
    mv -T "$SEED_INPUTS" "$SEED_INPUTS.old" || return 1
  fi
  mv -T "$work/new" "$SEED_INPUTS" || return 1
  rm -rf --one-file-system "${SEED_INPUTS:?}.old"
  say "staged inputs $sha (commit $(cat "$SEED_INPUTS/REF")); each runner rebuilds its seed between jobs"
}

# --- refresh: one runner's seed --------------------------------------------------------

seed_dir() { printf '%s/seed' "${CI_ROOT:?}"; }

drop_seed() {
  # $1: why. The runner keeps working without a seed.
  rm -rf --one-file-system "$(seed_dir)"
  say "$RUNNER_NAME has no seed: $1"
}

intact() {
  # $1: a generation, $2: the inputs sha256 it must have been built from.
  # Root owns every entry and nobody else may write one; the manifest is the
  # one recorded when it was built. Jobs check the content they restore.
  local gen=$1 inputs=$2 recorded
  [ -f "$gen/SEED" ] && [ -f "$gen/MANIFEST.sha256" ] || return 1
  grep -qx "inputs=$inputs" "$gen/SEED" || return 1
  recorded=$(sed -n 's/^manifest=//p' "$gen/SEED")
  [ "$recorded" = "$(sha256sum "$gen/MANIFEST.sha256" | awk '{ print $1 }')" ] || return 1
  [ -z "$(find "$gen" \( ! -user root -o ! -group root -o \( ! -type l \( -perm -020 -o -perm -002 \) \) \) -print -quit)" ]
}

link_stays_inside() {
  # $1: a link's directory relative to the tree root, $2: its target. True
  # when the target is relative and, read lexically, never climbs above the
  # root. uv's cache links each wheel to its archive this way (../../archive-v0).
  local dir=$1 target=$2 part depth=0
  case "$target" in /*) return 1 ;; esac
  local -a parts
  IFS=/ read -r -a parts <<<"$dir/$target"
  for part in "${parts[@]}"; do
    case "$part" in
      "" | .) ;;
      ..)
        depth=$((depth - 1))
        [ "$depth" -ge 0 ] || return 1
        ;;
      *) depth=$((depth + 1)) ;;
    esac
  done
}

refuse_unsafe() {
  # $1: a tree just copied and owned by root. Only files, directories and links
  # that stay inside the tree; no setuid or setgid bit.
  local root=${1%/} link
  if [ -n "$(find "$root" ! -type d ! -type f ! -type l -print -quit)" ]; then
    say "FAIL: the build left a device, pipe or socket"
    return 1
  fi
  if [ -n "$(find "$root" \( -perm -4000 -o -perm -2000 \) -print -quit)" ]; then
    say "FAIL: the build left a setuid or setgid file"
    return 1
  fi
  while IFS= read -r -d '' link; do
    link=${link#"$root"/}
    if ! link_stays_inside "$(dirname "$link")" "$(readlink "$root/$link")"; then
      say "FAIL: the build left a link that is absolute or leaves its tree"
      return 1
    fi
  done < <(find "$root" -type l -print0)
}

build_in_job_sandbox() {
  # The job unit's sandbox (job_props), as a transient unit with a time limit.
  local line props=()
  while IFS= read -r line; do
    props+=(-p "$line")
  done < <(job_props "$INSTANCE")
  systemd-run --quiet --wait --pipe --collect --unit="intake-aws-ci-seed-$INSTANCE" \
    -p Type=exec -p "RuntimeMaxSec=$SEED_BUILD_MAX_S" "${props[@]}" \
    "$LIB_DIR/bin/seed-build.sh" /tmp/seed-build </dev/null
}

build() {
  # $1: the inputs sha256. Builds a new generation and points current at it.
  # Every step is checked: refresh calls this in a condition, where errexit
  # does not apply.
  local inputs=$1 dir gen work new manifest
  dir=$(seed_dir)
  gen="gen-${inputs:0:16}"
  work="$CI_ROOT/tmp/seed-build"
  new="$dir/.$gen.new"
  rm -rf --one-file-system "$work" &&
    install -d -m 0700 -o "$RUNNER_USER" -g "$RUNNER_USER" "$work" "$work/out" &&
    cp -a "$SEED_INPUTS/tree" "$work/in" &&
    chown -R "$RUNNER_USER:$RUNNER_USER" "$work/in" || return 1
  say "building $RUNNER_NAME's seed from inputs ${inputs:0:16} (commit $(cat "$SEED_INPUTS/REF"))"
  build_in_job_sandbox || {
    say "FAIL: the build did not finish (journalctl -u intake-aws-ci-seed-$INSTANCE)"
    return 1
  }
  install -d -m 0755 -o root -g root "$dir" &&
    rm -rf --one-file-system "$new" &&
    install -d -m 0755 -o root -g root "$new" "$new/deid" &&
    cp -a "$work/out/uv" "$work/out/pnpm-store" "$new/" &&
    rm -rf --one-file-system "$work" &&
    chown -R -h root:root "$new" &&
    chmod -R u+rwX,go+rX,go-w "$new" || return 1
  refuse_unsafe "$new" || return 1
  install -m 0644 -o root -g root "$SEED_INPUTS/deid/$SEED_DEID_TAG.tar.gz" "$new/deid/" &&
    sha256_is "$new/deid/$SEED_DEID_TAG.tar.gz" "$SEED_DEID_SHA256" || return 1
  (cd "$new" && find . -type f -print0 | sort -z | xargs -0 sha256sum) >"$new/MANIFEST.sha256" &&
    (cd "$new" && sha256sum -c --quiet --strict MANIFEST.sha256) || return 1
  manifest=$(sha256sum "$new/MANIFEST.sha256" | awk '{ print $1 }')
  printf 'inputs=%s\nmanifest=%s\nbuilt=%s\n' "$inputs" "$manifest" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$new/SEED" &&
    chmod 0644 "$new/MANIFEST.sha256" "$new/SEED" &&
    rm -rf --one-file-system "${dir:?}/$gen" &&
    mv -T "$new" "$dir/$gen" &&
    ln -sfn "$gen" "$dir/current.new" &&
    mv -T "$dir/current.new" "$dir/current" || return 1
  find "$dir" -mindepth 1 -maxdepth 1 ! -name "$gen" ! -name current \
    -exec rm -rf --one-file-system {} +
  say "$RUNNER_NAME's seed is $gen: uv $(du -sh "$dir/$gen/uv" | cut -f1), pnpm $(du -sh "$dir/$gen/pnpm-store" | cut -f1), manifest $manifest"
}

refresh() {
  local inputs dir
  dir=$(seed_dir)
  if [ ! -f "$SEED_INPUTS/BUNDLE" ]; then
    drop_seed "no inputs are staged (scripts/ci/aws_runner.sh seed)"
    return 0
  fi
  inputs=$(cat "$SEED_INPUTS/BUNDLE")
  if ! is_sha256 "$inputs"; then
    drop_seed "the staged inputs carry no sha256"
    return 1
  fi
  if [ "$(readlink "$dir/current" 2>/dev/null)" = "gen-${inputs:0:16}" ] &&
    intact "$dir/gen-${inputs:0:16}" "$inputs"; then
    say "$RUNNER_NAME's seed is current (gen-${inputs:0:16})"
    return 0
  fi
  if ! build "$inputs"; then
    rm -rf --one-file-system "$CI_ROOT/tmp/seed-build"
    drop_seed "the build failed"
    return 1
  fi
}

main() {
  if [ "$(id -u)" -ne 0 ]; then
    say "FAIL: seed.sh runs as root"
    return 1
  fi
  if [ "${1:-}" = stage ]; then
    stage "${2:-}" "${3:-}"
    return
  fi
  instance_env "${1:-}" || return 2
  case "${2:-}" in
    refresh) refresh ;;
    *)
      say "usage: seed.sh stage <url> <sha256> | seed.sh N refresh"
      return 2
      ;;
  esac
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
