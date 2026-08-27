#!/usr/bin/env bash
# Run inside a devcontainer/VM — this bypasses permission prompts. Verify flags with `claude --help` first.
set -euo pipefail
MAX="${1:-5}"
for i in $(seq 1 "$MAX"); do
  echo "=== INTAKE LOOP $i/$MAX $(date -Iseconds) ==="
  claude -p "$(cat PROMPT.md)" --dangerously-skip-permissions --max-turns 80 --output-format text || true
  if grep -q "LOOP_STATUS: DONE" <(awk "/^### /{n++} n<=1" <(tac docs/PROGRESS.md) ); then echo "Backlog complete."; exit 0; fi
  if grep -q "LOOP_STATUS: WAITING_HUMAN" <(awk "/^### /{n++} n<=1" <(tac docs/PROGRESS.md) ); then echo "Only human-gated work remains — see docs/backlog/blockers.md, files/HUMAN_BLOCKERS.md and the open PRs."; exit 3; fi
  if grep -q "LOOP_STATUS: BLOCKED" <(awk "/^### /{n++} n<=1" <(tac docs/PROGRESS.md) ); then echo "Blocked — human input needed."; exit 2; fi
done
