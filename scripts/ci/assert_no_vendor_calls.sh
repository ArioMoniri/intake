#!/usr/bin/env bash
# CI guard (INT-001): no live AI/speech vendor endpoint may be referenced in the
# build. The deleted v1.4 vendor list (07 §6) recirculates — this is the gate
# that stops it. files/ is the historical record and is excluded; everything
# else, including tests and fixtures, is scanned. CI never calls a vendor
# (CLAUDE.md §How we work): recorded fixtures only.
# .claude/skills (--exclude-dir=skills) is vendor-authored agent teaching
# material (Expo's installed skills quote example fetch() calls); it is
# documentation, never on any build or runtime path.
set -euo pipefail

PATTERN='api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|aiplatform\.googleapis\.com|api\.elevenlabs\.io|soniox\.com|api\.inworld\.ai|api\.deepgram\.com|dashscope\.aliyuncs\.com|\.livekit\.cloud'

matches=$(grep -rInE "$PATTERN" \
  --exclude-dir=files \
  --exclude-dir=.git \
  --exclude-dir=node_modules \
  --exclude-dir=.venv \
  --exclude-dir=.claude-flow \
  --exclude-dir=skills \
  --exclude=assert_no_vendor_calls.sh \
  . || true)

# INT-442 / ADR-035 (owner, 3 Oct 2026): the one exception. The two hosted-lane
# vendor hosts may appear in exactly two files: the egress allow-list (the one
# place a vendor endpoint is spelled) and the synthetic proxy's config rendered
# from it. A line there is dropped only when nothing in the pattern remains
# once those two hosts are removed, so any other vendor host in either file,
# and either host in any other file, still fails. Removed when ADR-035 reverts.
EXCEPTION_FILES='^\./(infra/security/egress-allowlist\.yaml|infra/staging/egress/squid\.conf):[0-9]+:'
EXCEPTION_HOSTS='api\.openai\.com|api\.elevenlabs\.io'
if [[ -n "$matches" ]]; then
  kept=""
  while IFS= read -r line; do
    if [[ $line =~ $EXCEPTION_FILES ]] &&
      ! printf '%s' "$line" | sed -E "s/${EXCEPTION_HOSTS}//g" | grep -qE "$PATTERN"; then
      continue
    fi
    kept+="${line}"$'\n'
  done <<<"$matches"
  matches=${kept%$'\n'}
fi

if [[ -n "$matches" ]]; then
  echo "FAIL: live vendor endpoint referenced outside files/ (the historical record):"
  echo "$matches"
  exit 1
fi

echo "OK: no vendor endpoints referenced"
