#!/usr/bin/env bash
# PreToolUse guard for Bash (07 §3.8): block destructive git, bulk staging,
# curl|sh, and .env writes. Reads the tool call as JSON on stdin; exit 2 blocks.
set -euo pipefail

cmd=$(python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")')

block() {
  echo "guard-bash: blocked ($1). See CLAUDE.md §How we work / LOOP.md Guardrails." >&2
  exit 2
}

[[ "$cmd" =~ rm[[:space:]]+-[a-zA-Z]*rf ]] && block "rm -rf"
[[ "$cmd" =~ git[[:space:]]+push[[:space:]].*(--force|-f[[:space:]]) ]] && block "git push --force"
[[ "$cmd" =~ git[[:space:]]+reset[[:space:]]+--hard ]] && block "git reset --hard"
[[ "$cmd" =~ git[[:space:]]+add[[:space:]]+(-A|--all|\.[[:space:]]*$) ]] && block "bulk git add — stage explicit paths"
[[ "$cmd" =~ curl[^|]*\|[[:space:]]*(ba)?sh ]] && block "curl | sh"
[[ "$cmd" =~ (\>|\>\>|tee[[:space:]]+(-a[[:space:]]+)?)[[:space:]]*\.env([[:space:]]|$) ]] && block "write to .env"

exit 0
