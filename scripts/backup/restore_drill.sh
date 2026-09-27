#!/usr/bin/env bash
# INT-202 — the restore drill's plan, rendered without running anything.
#
#   scripts/backup/restore_drill.sh --dry-run
#
# Prints the ordered plan intake_platform.backup.drill states, the repository
# and its encryption, the retention and second-location state (both waiting
# on HB-I8), and the buckets the replication plan withholds. It touches no
# container runtime, repository or cluster, so it runs anywhere.
#
# The drill itself runs through scripts/backup/drill_lib.sh:
#   infra/staging/backup.sh drill    on the production host (quarterly timer)
#   scripts/backup/ci_drill.sh       in CI (make backup-drill-ci)
# docs/runbooks/restore-drill.md is the operator's guide.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

resolve_python() {
  if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON=("${REPO_ROOT}/.venv/bin/python")
  elif command -v uv >/dev/null 2>&1; then
    PYTHON=(uv run --project "${REPO_ROOT}" python)
  else
    PYTHON=(python3)
  fi
}

usage() {
  cat <<'USAGE'
usage: scripts/backup/restore_drill.sh --dry-run

  --dry-run  render the ordered drill plan and the backup tier's state

The drill runs on the host (infra/staging/backup.sh drill) and in CI
(scripts/backup/ci_drill.sh). Quarterly per files/10 §3; see
docs/runbooks/restore-drill.md.
USAGE
}

case "${1:-}" in
  --dry-run)
    resolve_python
    "${PYTHON[@]}" -m intake_platform.backup \
      --infra "${REPO_ROOT}/infra/backup" --repo-root "${REPO_ROOT}" --show-replication
    ;;
  -h | --help) usage ;;
  *)
    usage >&2
    exit 2
    ;;
esac
