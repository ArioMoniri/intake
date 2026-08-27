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

echo "evidence_check: OK ($ev)"
