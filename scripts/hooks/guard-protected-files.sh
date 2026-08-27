#!/usr/bin/env bash
# PreToolUse guard for Edit|Write (07 §3.8): hook-protected files change only
# with ALLOW_PROTECTED=1 — invariants are added, not relaxed (07 §F rule 2).
set -euo pipefail

[[ "${ALLOW_PROTECTED:-0}" == "1" ]] && exit 0

path=$(python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")')

PROTECTED=(
  "CLAUDE.md"
  "LOOP.md"
  "docs/DoD.md"
  "docs/TDD.md"
  "packages/protocols/base/red_flags.yaml"
  "packages/protocols/base/life_threat.yaml"
  "services/voice-runtime/talker/tools.py"
  ".github/workflows/security.yml"
  "infra/security/egress-allowlist.yaml"
  "scripts/ci/coverage_thresholds.yaml"
)

for p in "${PROTECTED[@]}"; do
  if [[ "$path" == *"$p" ]]; then
    echo "guard-protected-files: $p is hook-protected. Set ALLOW_PROTECTED=1 only with an ADR (07 §F rule 2)." >&2
    exit 2
  fi
done

if [[ "$path" == *"packages/intake_platform/security/"* ]]; then
  echo "guard-protected-files: packages/intake_platform/security/** is hook-protected." >&2
  exit 2
fi

exit 0
