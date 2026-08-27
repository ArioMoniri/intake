#!/usr/bin/env bash
# INT-002 — the zero-placeholder gate (CLAUDE.md invariant 17).
#
# No-args: scan every tracked file except the allow-list (prefix match).
# With args: scan exactly those paths (used by the gate's own tests).
#
# Sole permitted form (invariant 17): a line matching
#   "TODO: <what> requires clinical sign-off"
# inside packages/protocols/** — the compiler refuses to serve such rules.
# Portable to macOS bash 3.2 (no mapfile; no case inside $(...), which 3.2
# cannot parse).
set -euo pipefail
cd "$(dirname "$0")/../.."

PATTERN='TODO|FIXME|XXX|NotImplementedError|pytest\.mark\.skip|xfail|it\.skip|test\.todo|pass  #|lorem|placeholder|dummy|demo-only'
PERMITTED='TODO: .+ requires clinical sign-off'
ALLOW_FILE="scripts/ci/no_placeholders_allow.txt"

list_targets() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
    return
  fi
  git ls-files | while IFS= read -r f; do
    skip=0
    while IFS= read -r p; do
      if [[ -z "$p" || "$p" == \#* ]]; then continue; fi
      if [[ "$f" == "$p"* ]]; then
        skip=1
        break
      fi
    done < "$ALLOW_FILE"
    if [[ $skip -eq 0 ]]; then printf '%s\n' "$f"; fi
  done
}

scan() {
  list_targets "$@" | while IFS= read -r f; do
    grep -nHE "$PATTERN" -- "$f" 2>/dev/null || true
  done | while IFS= read -r line; do
    file="${line%%:*}"
    if [[ "$file" == packages/protocols/* || "$file" == */packages/protocols/* ]]; then
      if printf '%s\n' "$line" | grep -qE "$PERMITTED"; then
        continue
      fi
    fi
    printf '%s\n' "$line"
  done
}

violations=$(scan "$@")

if [[ -n "$violations" ]]; then
  echo "FAIL: placeholder tokens found (invariant 17 — zero placeholders, zero postponement):"
  printf '%s\n' "$violations"
  exit 1
fi

echo "OK: no placeholders"
