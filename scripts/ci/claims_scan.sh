#!/usr/bin/env bash
# INT-019 — accuracy-claims scan (invariant 20; ADR-022).
#
# No accuracy claims: no sensitivity, specificity, AUROC, WER or accuracy
# figure may appear in docs/regulatory/, docs/legal/, or app-store copy.
# Measurements live in docs/evidence/ with a date and a named corpus — that
# tree is deliberately NOT scanned.
#
# No-args: scan the claim-sensitive trees that exist today (they barely exist
# yet — the gate existing and armed is the point; an absent tree is reported,
# never an error). With args: scan exactly those paths (the gate's own tests).
#
# The Turkish pattern is deliberately narrow: bare "doğruluk" appears
# legitimately in legal copy ("bilgilerin doğruluğu"); only doğruluk adjacent
# to a percentage or figure is a performance claim.
# Portable to macOS bash 3.2.
set -euo pipefail
cd "$(dirname "$0")/../.."

ASCII_PAT='sensitivit|specificit|auroc|accurac|(^|[^a-zA-Z])[Ww][Ee][Rr]([^a-zA-Z]|$)'
TR_PAT='%[ ]*[0-9]*[ ]*[Dd]oğruluk|[Dd]oğruluk[ ]*(oranı)?[ ]*(%|yüzde)[ ]*[0-9]'

list_targets() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
    return
  fi
  for tree in docs/regulatory docs/legal apps/*/store apps/*/store-listing \
    apps/*/fastlane/metadata; do
    if [[ -d "$tree" ]]; then
      git ls-files -- "$tree"
    else
      echo "note: $tree absent — gate armed, nothing to scan yet" >&2
    fi
  done
}

scan() {
  list_targets "$@" | while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    grep -inHE "$ASCII_PAT" -- "$f" 2>/dev/null || true
    grep -nHE "$TR_PAT" -- "$f" 2>/dev/null || true
  done
}

violations=$(scan "$@")

if [[ -n "$violations" ]]; then
  echo "FAIL: performance-claim language found (invariant 20 — no accuracy claims;"
  echo "measurements belong in docs/evidence/ with a date and a named corpus):"
  printf '%s\n' "$violations"
  exit 1
fi

echo "OK: no performance-claim patterns in scanned trees"
