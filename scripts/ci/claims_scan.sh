#!/usr/bin/env bash
# INT-019 — accuracy-claims scan (CLAUDE.md invariant 20; files/10 §8).
#
# No sensitivity, specificity, AUROC, WER or accuracy figure may appear in
# docs/regulatory/, docs/legal/, patient or clinician copy, marketing, or an
# app-store listing. Measurements live in docs/evidence/ with a date and a
# named corpus and are described as measurements — so docs/evidence/ is
# deliberately NOT scanned, and neither is docs/adr/ (which reasons about the
# policy) or files/ (the historical record).
#
# With no arguments: the claim-sensitive trees that exist today. An absent
# tree is reported on stderr and is not an error — the gate is armed for the
# tree that has not been created yet, which is the point of wiring it now.
# With arguments: exactly those paths (how the gate's own tests drive it).
#
# The Turkish pattern is deliberately narrow. Bare "doğruluk" is ordinary
# legal Turkish ("bilgilerin doğruluğu" — the accuracy OF THE INFORMATION the
# patient supplied, which every KVKK text says); only doğruluk adjacent to a
# percentage or a figure is a performance claim about the product.
#
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
  local tree
  for tree in docs/regulatory docs/legal apps/*/store apps/*/store-listing \
    apps/*/fastlane/metadata; do
    if [[ -d "$tree" ]]; then
      git ls-files -- "$tree"
    else
      echo "note: $tree absent — gate armed, nothing to scan there yet" >&2
    fi
  done
}

report() {
  local file="$1" pattern="$2" flags="$3" hits=""
  hits=$(grep -n"$flags"E "$pattern" -- "$file" 2>/dev/null) || hits=""
  local line
  while IFS= read -r line; do
    [[ -n "$line" ]] && printf '%s:%s\n' "$file" "$line"
  done <<< "$hits"
  # the loop's last test is false whenever the file was clean, which under
  # `set -e` would end the run; the verdict is the collected output, not this.
  return 0
}

scan() {
  local f
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    report "$f" "$ASCII_PAT" "i"
    report "$f" "$TR_PAT" ""
  done <<< "$(list_targets "$@")"
}

violations=$(scan "$@")

if [[ -n "$violations" ]]; then
  echo "FAIL: performance-claim language found (invariant 20 — no accuracy claims;"
  echo "a measurement belongs in docs/evidence/ with a date and a named corpus, and"
  echo "is a measurement, never a property of the product):"
  printf '%s\n' "$violations"
  exit 1
fi

echo "OK: no performance-claim patterns in the scanned trees"
