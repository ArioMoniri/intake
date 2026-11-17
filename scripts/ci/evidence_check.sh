#!/usr/bin/env bash
# INT-002 — the evidence gate. A PR is not reviewable without the recorded
# red run: a test that never failed proves nothing (docs/TDD.md rule 1).
#
# Usage: evidence_check.sh "<pr title>" "<pr body>" [evidence_dir]
set -euo pipefail

title="${1:?usage: evidence_check.sh <pr-title> <pr-body> [evidence-dir]}"
body="${2:?usage: evidence_check.sh <pr-title> <pr-body> [evidence-dir]}"
evdir="${3:-docs/evidence}"

fail() {
  echo "evidence_check: FAIL — $1"
  exit 1
}

if ! printf '%s' "$title" | grep -qE '^INT-[0-9]{3}: .+'; then
  fail "PR title must be 'INT-xxx: <title>' (got: $title)"
fi
issue=$(printf '%s' "$title" | grep -oE '^INT-[0-9]{3}')

if ! printf '%s' "$body" | grep -qE 'Closes #[0-9]+'; then
  fail "PR body must contain 'Closes #<n>'"
fi

ev="$evdir/$issue.md"
[[ -f "$ev" ]] || fail "missing evidence file $ev"
grep -qiE 'red run' "$ev" || fail "$ev has no red-run section"
grep -qiE 'green run' "$ev" || fail "$ev has no green-run section"
grep -qiE 'make check' "$ev" || fail "$ev records no gate output (make check)"

# INT-020 — "missing link fails evidence_check": the files/10 §9 row link
# (`Sec-Row: <row>`, CLAUDE.md invariant 16). check_sec_row_linkage.py is the
# one implementation, stdlib-only so the bare runner's python3 runs it; the
# gates job also runs it as its own named step. SEC_ROW_ISSUES and
# SEC_ROW_THREAT_MODEL point it at fixtures in tests only.
linkage=(python3 "$(dirname "$0")/check_sec_row_linkage.py" "$title" "$body")
if [[ -n "${SEC_ROW_ISSUES:-}" ]]; then
  linkage+=(--issues "$SEC_ROW_ISSUES")
fi
if [[ -n "${SEC_ROW_THREAT_MODEL:-}" ]]; then
  linkage+=(--threat-model "$SEC_ROW_THREAT_MODEL")
fi
if ! link_out=$("${linkage[@]}"); then
  fail "files/10 §9 row link — ${link_out#sec_row_linkage: FAIL — }"
fi

echo "evidence_check: OK ($ev)"
