#!/usr/bin/env bash
# INT-019 — the eslint-security gate (files/10 §8 "ESLint security rules").
#
# Installs the pinned eslint-plugin-security into .cache/ (gitignored; not a
# workspace dependency, see the header of eslint-security.config.mjs), runs
# every recommended rule at `error` over every tracked JS/TS file, and hands
# the JSON report to scripts/ci/eslint_security_gate.py, which fails on a new
# or increased finding.
#
# --update regenerates the debt baseline. That is a deliberate act with a diff.
#
# Fails closed: no pnpm, no node_modules, a failed plugin install or an ESLint
# crash each stop the gate rather than passing it.
set -euo pipefail
cd "$(dirname "$0")/../.."

ESLINT_SECURITY_VERSION="3.0.1"
PLUGIN_ROOT=".cache/eslint-security"
PLUGIN_ENTRY="$PLUGIN_ROOT/node_modules/eslint-plugin-security/package.json"

if ! command -v pnpm >/dev/null 2>&1; then
  echo "eslint-security: pnpm is not installed — install: corepack enable pnpm" >&2
  exit 1
fi
if [[ ! -d node_modules ]]; then
  echo "eslint-security: node_modules is absent — install: pnpm install --frozen-lockfile" >&2
  exit 1
fi

installed=""
if [[ -f "$PLUGIN_ENTRY" ]]; then
  installed=$(node -p "require('./$PLUGIN_ENTRY').version")
fi
if [[ "$installed" != "$ESLINT_SECURITY_VERSION" ]]; then
  mkdir -p "$PLUGIN_ROOT"
  npm install --no-save --no-audit --no-fund --prefix "$PLUGIN_ROOT" \
    "eslint-plugin-security@$ESLINT_SECURITY_VERSION" >/dev/null
fi
if [[ ! -f "$PLUGIN_ENTRY" ]]; then
  echo "eslint-security: eslint-plugin-security@$ESLINT_SECURITY_VERSION did not install" >&2
  echo "install: npm install --no-save --prefix $PLUGIN_ROOT \\" >&2
  echo "  eslint-plugin-security@$ESLINT_SECURITY_VERSION" >&2
  exit 1
fi

files=$(git ls-files -- '*.ts' '*.tsx' '*.js' '*.jsx' '*.mjs' '*.cjs' \
  | grep -v '/node_modules/' | grep -v '/dist/')
if [[ -z "$files" ]]; then
  echo "eslint-security: no JS/TS file is tracked — the gate scanned nothing" >&2
  exit 1
fi

report=$(mktemp)
trap 'rm -f "$report"' EXIT

# ESLint exits 1 when it reports an error, which is the ordinary case while the
# baseline is non-empty; the verdict belongs to the gate script, so the exit
# code is captured rather than allowed to end the run. An ESLint *crash* (exit
# 2, or an empty report) is a different thing and fails below.
set +e
# shellcheck disable=SC2086
pnpm exec eslint --no-config-lookup --config scripts/ci/eslint-security.config.mjs \
  -f json $files > "$report" 2>/tmp/eslint-security.err
status=$?
set -e
if [[ $status -gt 1 ]]; then
  echo "eslint-security: ESLint exited $status — the scan did not complete" >&2
  cat /tmp/eslint-security.err >&2
  exit 1
fi

python3 scripts/ci/eslint_security_gate.py "$@" < "$report"
