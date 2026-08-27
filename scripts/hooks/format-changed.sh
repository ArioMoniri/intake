#!/usr/bin/env bash
# PostToolUse (07 §3.8): format the file just edited. Never blocks (always 0).
set -uo pipefail

path=$(python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")')

case "$path" in
  *.py) uv run ruff format "$path" >/dev/null 2>&1 || true ;;
  *.ts|*.tsx|*.js|*.mjs|*.cjs|*.json) pnpm exec prettier --write "$path" >/dev/null 2>&1 || true ;;
esac

exit 0
