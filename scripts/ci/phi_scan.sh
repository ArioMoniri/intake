#!/usr/bin/env bash
# INT-019 — PHI-pattern scan of fixtures and docs (CLAUDE.md invariants 6 and
# 14; files/10 §8 "PHI-pattern scan").
#
# WHAT IT SCANS. With no arguments: every tracked file under tests/fixtures/
# and docs/. With arguments: exactly those paths (how the gate's own tests
# drive it).
#
# WHAT IT LOOKS FOR — the three identifier classes intake_platform.redaction
# handles, in the shapes a Turkish fixture actually carries them:
#   TCKN   11 digits, first non-zero, CHECKSUM-VALID (scripts/ci/tckn_check.py).
#          A checksum-invalid 11-digit run is an order id or a timestamp, not
#          an identity number, and flagging it would train people to ignore the
#          gate. A TCKN is id-shaped — INT-083 found that is exactly how one
#          slips past a "looks like a reference" check — so the checksum, not
#          the shape, is what decides.
#   PHONE  +90/0090 5xx and bare 05xx, spaced, dotted or dashed.
#   IBAN   TR + 24 digits, compact or in four-digit groups.
#
# HOW A FILE IS EXCUSED — one mechanism, not two. INT-206 already declares
# every synthetic corpus CI may read in infra/ci/no-phi-policy.yaml, each
# pinned by sha256, with its origin, provenance and licence. This gate reads
# THAT list rather than keeping a second one that could disagree with it: a
# fixture is excused because a human declared and hashed it, never because it
# sits under a blessed directory. docs/ is outside that policy's scope, so it
# has a prefix allow-list of its own (phi_scan_docs_allow.txt) which may only
# shrink and is pinned by tests/ci/test_security_gates.py.
#
# INVARIANT 6 DISCIPLINE: the scanner never echoes a matched value. It prints
# file, line and category — a gate that quotes what it found has copied PHI
# into a log retained 30 d hot / 1 y cold.
#
# Portable to macOS bash 3.2 (no mapfile, no grep -P).
set -euo pipefail
cd "$(dirname "$0")/../.."

POLICY="infra/ci/no-phi-policy.yaml"
DOCS_ALLOW="scripts/ci/phi_scan_docs_allow.txt"
HELPER="scripts/ci/tckn_check.py"

for required in "$POLICY" "$DOCS_ALLOW" "$HELPER"; do
  if [[ ! -f "$required" ]]; then
    echo "phi_scan: $required is missing — the gate cannot run and will not pass" >&2
    exit 2
  fi
done

PHONE='(\+90|0090)[ .-]?5[0-9]{2}[ .-]?[0-9]{3}[ .-]?[0-9]{2}[ .-]?[0-9]{2}|(^|[^0-9])05[0-9]{2}[ .-]?[0-9]{3}[ .-]?[0-9]{2}[ .-]?[0-9]{2}([^0-9]|$)'
IBAN='(^|[^A-Z0-9])TR[0-9]{2} ?([0-9]{4} ?){5}[0-9]{2}([^0-9]|$)'
TCKN_CANDIDATE='(^|[^0-9])[1-9][0-9]{10}([^0-9]|$)'

# The sha256-pinned synthetic corpora INT-206 declares: exact paths, matched
# exactly. A sibling file dropped next to a declared corpus is NOT excused.
DECLARED_CORPORA=$(sed -n 's/^[[:space:]]*-[[:space:]]*path:[[:space:]]*//p' "$POLICY")

# The docs/ allow-list: prefixes, comments and blank lines dropped.
DOCS_PREFIXES=$(sed -e 's/#.*$//' -e 's/[[:space:]]*$//' "$DOCS_ALLOW" | sed '/^$/d')

is_excused() {
  local f="$1" entry
  while IFS= read -r entry; do
    [[ -n "$entry" && "$f" == "$entry" ]] && return 0
  done <<< "$DECLARED_CORPORA"
  while IFS= read -r entry; do
    [[ -n "$entry" && "$f" == "$entry"* ]] && return 0
  done <<< "$DOCS_PREFIXES"
  return 1
}

list_targets() {
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
    return
  fi
  git ls-files -- tests/fixtures docs | while IFS= read -r f; do
    if ! is_excused "$f"; then printf '%s\n' "$f"; fi
  done
}

# grep exits 1 on "no match", which is the ordinary case here; the explicit
# `|| lines=''` keeps that out of `set -e` without weakening the gate.
report_lines() {
  local file="$1" pattern="$2" label="$3" lines=""
  lines=$(grep -nE "$pattern" -- "$file" 2>/dev/null | cut -d: -f1) || lines=""
  local ln
  for ln in $lines; do
    printf '%s:%s: [%s] shape matched (content withheld)\n' "$file" "$ln" "$label"
  done
}

report_tckn() {
  local file="$1" lines="" ln
  lines=$(grep -nE "$TCKN_CANDIDATE" -- "$file" 2>/dev/null | python3 "$HELPER" | cut -d: -f1) \
    || lines=""
  for ln in $lines; do
    printf '%s:%s: [TCKN] checksum-valid TC Kimlik (content withheld)\n' "$file" "$ln"
  done
}

scan() {
  local f
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    report_lines "$f" "$PHONE" "PHONE"
    report_lines "$f" "$IBAN" "IBAN"
    report_tckn "$f"
  done <<< "$(list_targets "$@")"
}

violations=$(scan "$@")

if [[ -n "$violations" ]]; then
  echo "FAIL: PHI-shaped content found (invariants 6 and 14 — fixtures and docs stay"
  echo "PHI-free; a corpus that legitimately carries identifiers is declared and"
  echo "hashed in $POLICY, never dropped into the tree):"
  printf '%s\n' "$violations"
  exit 1
fi

echo "OK: no PHI patterns outside the declared synthetic corpora"
