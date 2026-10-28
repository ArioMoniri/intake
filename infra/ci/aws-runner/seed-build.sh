#!/usr/bin/env bash
# INT-544 — builds one runner's cache seed. seed.sh starts it as the runner's
# user, in the job unit's own sandbox and network namespace, with a time limit:
#
#   seed-build.sh <work>     <work>/in   the owner's lockfiles and manifests
#                            <work>/out  uv/ and pnpm-store/, for seed.sh
#
# It fetches uv and pnpm, checks each against its sha256 in runner.conf, then
# fills a uv cache from uv.lock (`uv sync --frozen`, nothing of the workspace
# itself installed) and a pnpm store from pnpm-lock.yaml (`pnpm fetch`, which
# runs no install script). Both tools check every package against the hashes
# in those lockfiles. No credential is read or needed: every source is public.
set -euo pipefail
set +x

# shellcheck source=runner.conf
. "${INTAKE_AWS_CI_CONF:-/usr/local/lib/intake-aws-ci-runner/runner.conf}"

say() { printf 'intake-aws-ci seed-build: %s\n' "$*"; }

fetch() {
  # $1 url, $2 destination, $3 sha256
  curl -fsSL --retry 3 -o "$2" "$1"
  echo "$3  $2" | sha256sum -c --quiet
}

work=${1:?usage: seed-build.sh <work>}
tools="$work/tools"
mkdir -p "$tools" "$work/out/uv" "$work/out/pnpm-store"

fetch "https://github.com/astral-sh/uv/releases/download/$SEED_UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz" \
  "$tools/uv.tar.gz" "$SEED_UV_SHA256"
tar -xzf "$tools/uv.tar.gz" -C "$tools" --strip-components=1
fetch "https://registry.npmjs.org/@pnpm/linux-x64/-/linux-x64-$SEED_PNPM_VERSION.tgz" \
  "$tools/pnpm.tgz" "$SEED_PNPM_SHA256"
tar -xzf "$tools/pnpm.tgz" -C "$tools" --strip-components=1 package/pnpm

cd "$work/in"
say "uv $SEED_UV_VERSION: uv sync --frozen --all-packages --no-install-workspace"
UV_CACHE_DIR="$work/out/uv" UV_PYTHON_DOWNLOADS=never \
  "$tools/uv" sync --frozen --all-packages --no-install-workspace --quiet
say "pnpm $SEED_PNPM_VERSION: pnpm fetch"
"$tools/pnpm" fetch --store-dir "$work/out/pnpm-store" --reporter=silent
say "done: uv cache $(du -sh "$work/out/uv" | cut -f1), pnpm store $(du -sh "$work/out/pnpm-store" | cut -f1)"
