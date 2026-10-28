#!/usr/bin/env bash
# INT-544 — restore parts of the runner's cache seed into this job.
#
#   scripts/ci/ci_seed.sh restore <part>...     part: uv | pnpm | deid
#
# The intake-aws-ci registrar keeps a seed per runner (infra/ci/aws-runner/
# seed.sh), root-owned and bound read-only into the job at $INTAKE_CI_SEED. For
# each part asked for, this script:
#   1. checks the seed's manifest against the sha256 its SEED file records, and
#      every file of the part against the manifest (and that no file was added);
#   2. copies the part into the job's own temp, where the tool may write:
#        uv    -> $RUNNER_TEMP/uv-cache, exported as UV_CACHE_DIR
#        pnpm  -> $RUNNER_TEMP/pnpm-store, exported as npm_config_store_dir
#        deid  -> .cache/<tag>/, only if the asset matches this commit's
#                 Makefile pin (DEID_MODEL_TAG, DEID_MODEL_SHA256)
#   3. writes <part>=true to $GITHUB_OUTPUT, so the job skips the GitHub Actions
#      cache for that part; anything else leaves <part>=false.
#
# It never fails a job over the seed. A runner without one, a part that fails a
# check, or a deid pin this commit changed, means <part>=false and the job
# fetches from the network exactly as it did before INT-544. A part that fails
# its manifest is never used, and the job log says so as a warning.
set -euo pipefail
set +x

say() { printf 'ci_seed: %s\n' "$*"; }
warn() { printf '::warning title=cache seed::%s\n' "$*"; }

output() { printf '%s=%s\n' "$1" "$2" >>"${GITHUB_OUTPUT:?ci_seed runs in a GitHub Actions job}"; }

part_dir() {
  case "$1" in
    uv) printf 'uv' ;;
    pnpm) printf 'pnpm-store' ;;
    deid) printf 'deid' ;;
    *) return 1 ;;
  esac
}

seed_whole() {
  # $1: the seed generation. Its manifest is the one recorded at build time.
  local gen=$1 recorded actual
  [ -f "$gen/SEED" ] && [ -f "$gen/MANIFEST.sha256" ] || return 1
  recorded=$(sed -n 's/^manifest=//p' "$gen/SEED")
  actual=$(sha256sum "$gen/MANIFEST.sha256" | awk '{ print $1 }')
  [ -n "$recorded" ] && [ "$recorded" = "$actual" ]
}

part_checked() {
  # $1: the generation, $2: the part's directory. Every file the manifest lists
  # for it matches, and the directory holds no file the manifest does not list.
  local gen=$1 dir=$2 list listed present
  list=$(mktemp)
  grep -F "  ./$dir/" "$gen/MANIFEST.sha256" >"$list" || true
  listed=$(wc -l <"$list" | tr -d ' ')
  present=$(find "$gen/$dir" -type f | wc -l | tr -d ' ')
  if [ "$listed" -eq 0 ] || [ "$listed" != "$present" ] ||
    ! (cd "$gen" && sha256sum -c --quiet --strict "$list" >/dev/null 2>&1); then
    rm -f "$list"
    return 1
  fi
  rm -f "$list"
}

makefile_pin() {
  # $1: DEID_MODEL_TAG or DEID_MODEL_SHA256, read from this commit's Makefile.
  sed -n "s/^$1 := //p" Makefile
}

copy_tree() {
  # $1: the seed directory, $2: the job's copy, $3: the variable that names it.
  # Called in a condition, where errexit does not apply: each step is checked.
  cp -a "$1" "$2" && chmod -R u+w "$2" && printf '%s=%s\n' "$3" "$2" >>"${GITHUB_ENV:?}"
}

restore_deid() {
  # $1: the generation. Only this commit's pinned asset is unpacked.
  local gen=$1 tag pin
  tag=$(makefile_pin DEID_MODEL_TAG)
  pin=$(makefile_pin DEID_MODEL_SHA256)
  if ! [[ "$tag" =~ ^[a-z0-9-]+$ && "$pin" =~ ^[0-9a-f]{64}$ ]] ||
    [ ! -f "$gen/deid/$tag.tar.gz" ] ||
    [ "$(sha256sum "$gen/deid/$tag.tar.gz" | awk '{ print $1 }')" != "$pin" ]; then
    say "the seed's deid asset is not this commit's pin; make deid-model fetches it"
    return 1
  fi
  mkdir -p .cache && tar -xzf "$gen/deid/$tag.tar.gz" -C .cache
}

restore_part() {
  # $1: the part, $2: the generation.
  local part=$1 gen=$2 dir
  dir=$(part_dir "$part")
  if ! part_checked "$gen" "$dir"; then
    warn "the $part part of $(basename "$gen") does not match its manifest; this job fetches it from the network"
    return 1
  fi
  case "$part" in
    uv) copy_tree "$gen/$dir" "${RUNNER_TEMP:?}/uv-cache" UV_CACHE_DIR ;;
    pnpm) copy_tree "$gen/$dir" "${RUNNER_TEMP:?}/pnpm-store" npm_config_store_dir ;;
    deid) restore_deid "$gen" ;;
  esac
}

restore() {
  local seed=${INTAKE_CI_SEED:-} gen="" part
  for part in "$@"; do
    part_dir "$part" >/dev/null || {
      say "unknown part '$part' (uv, pnpm, deid)"
      return 2
    }
  done
  if [ -n "$seed" ] && [ -e "$seed/current" ]; then
    gen="$seed/current"
  fi
  if [ -z "$gen" ]; then
    say "no cache seed on this runner; the job fetches from the network"
  elif ! seed_whole "$gen"; then
    warn "the seed's manifest does not match the sha256 its SEED file records; this job fetches from the network"
    gen=""
  else
    say "seed $(readlink "$gen" || echo current), manifest $(sed -n 's/^manifest=//p' "$gen/SEED")"
  fi
  for part in "$@"; do
    if [ -n "$gen" ] && restore_part "$part" "$gen"; then
      say "$part restored from the seed"
      output "$part" true
    else
      output "$part" false
    fi
  done
}

case "${1:-}" in
  restore) restore "${@:2}" ;;
  *)
    sed -n '2,23p' "$0" >&2
    exit 2
    ;;
esac
