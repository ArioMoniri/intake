#!/usr/bin/env bash
# Stop hook (07 §3.8): warn (non-blocking) when the session ends without a
# PROGRESS entry — LOOP.md requires one per iteration.
set -uo pipefail

if git diff --quiet -- docs/PROGRESS.md 2>/dev/null \
  && git diff --cached --quiet -- docs/PROGRESS.md 2>/dev/null \
  && ! git log -1 --name-only --pretty=format: 2>/dev/null | grep -q "^docs/PROGRESS.md$"; then
  echo "warning: docs/PROGRESS.md was not updated this session (LOOP.md requires an entry per iteration)"
fi

exit 0
