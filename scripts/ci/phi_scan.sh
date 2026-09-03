#!/usr/bin/env bash
# INT-019 — PHI-pattern scan (invariant 14; files/10 §6 CI gates).
#
# No-args: scan every tracked file under tests/fixtures/ and docs/ except the
# allow-list (prefix match — the de-id engine's own labeled corpus, which is
# synthetic and checksum-valid BY CONSTRUCTION; see phi_scan_allow.txt).
# With args: scan exactly those paths (used by the gate's own tests).
#
# Patterns: checksum-VALID TCKN (11 digits, validated by tckn_check.py — a
# checksum-invalid digit run is noise, not an identity number), TR mobile
# numbers (+90 5xx / 05xx), TR IBAN (TR + 24 digits, compact or grouped).
#
# Invariant 6 discipline: the scanner never echoes matched content into CI
# logs — it reports file, line number and category only.
# Portable to macOS bash 3.2 (no mapfile).
set -euo pipefail
cd "$(dirname "$0")/../.."

ALLOW_FILE="scripts/ci/phi_scan_allow.txt"
HELPER="scripts/ci/tckn_check.py"

PHONE='(\+90|0090)[ .-]?5[0-9]{2}[ .-]?[0-9]{3}[ .-]?[0-9]{2}[ .-]?[0-9]{2}|(^|[^0-9])05[0-9]{2}[ .-]?[0-9]{3}[ .-]?[0-9]{2}[ .-]?[0-9]{2}([^0-9]|$)'
IBAN='(^|[^A-Z0-9])TR[0-9]{2} ?([0-9]{4} ?){5}[0-9]{2}([^0-9]|$)'
TCKN_CANDIDATE='(^|[^0-9])[1-9][0-9]{10}([^0-9]|$)'

list_targets() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
    return
  fi
  git ls-files -- tests/fixtures docs | while IFS= read -r f; do
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
    [[ -f "$f" ]] || continue
    grep -nE "$PHONE" -- "$f" 2>/dev/null | cut -d: -f1 | while IFS= read -r ln; do
      printf '%s:%s: [PHONE] TR mobile number shape (content withheld)\n' "$f" "$ln"
    done || true
    grep -nE "$IBAN" -- "$f" 2>/dev/null | cut -d: -f1 | while IFS= read -r ln; do
      printf '%s:%s: [TR-IBAN] IBAN shape (content withheld)\n' "$f" "$ln"
    done || true
    grep -nE "$TCKN_CANDIDATE" -- "$f" 2>/dev/null | python3 "$HELPER" | cut -d: -f1 \
      | while IFS= read -r ln; do
      printf '%s:%s: [TCKN] checksum-valid TCKN (content withheld)\n' "$f" "$ln"
    done || true
  done
}

violations=$(scan "$@")

if [[ -n "$violations" ]]; then
  echo "FAIL: PHI-shaped content found (invariant 6/14 — fixtures and docs stay PHI-free):"
  printf '%s\n' "$violations"
  exit 1
fi

echo "OK: no PHI patterns in scanned trees"
