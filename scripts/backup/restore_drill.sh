#!/usr/bin/env bash
# INT-202 — the automated restore drill (files/10 §3 "quarterly restore drills
# with evidence"; §9 row `backups`; threat [Nc] "restores never exercised,
# discovered during the incident").
#
# Two halves, deliberately separated:
#
#   --dry-run   renders the ordered plan from infra/backup/ and exits. Touches
#               no container runtime, no repository and no cluster. This is
#               what `make backup-drill-dry` and the config gate run, and it
#               is what runs on a host that cannot host the real thing.
#   --run       executes the plan: full backup, expire, point-in-time restore
#               into a volume outside the workspace, per-table row counts,
#               replica check, teardown, evidence written to INTAKE_BACKUP_DIR.
#
# PHI discipline (CLAUDE.md invariants 3 and 6). The restored cluster is
# patient data on disk, so it lands in a named volume and never on a host
# path the workspace can read. Verification counts rows and never projects a
# column. Nothing is decrypted into the repository tree. The evidence file
# holds clocks, budgets and per-table counts — there is no field an
# identifier could occupy.
#
# Secrets (invariant 14). PGBACKREST_REPO1_CIPHER_PASS,
# PGBACKREST_REPO1_S3_KEY, PGBACKREST_REPO1_S3_KEY_SECRET,
# INTAKE_DR_S3_ACCESS_KEY and INTAKE_DR_S3_SECRET_KEY come from OpenBao and
# are exported by the caller. This script neither reads them from a file nor
# prints them.
#
# Retention. PGBACKREST_REPO1_RETENTION_FULL has no default anywhere. files/10
# §3 states RPO 15 min and RTO 4 h and states no retention window, so the
# drill refuses rather than guessing — files/HUMAN_BLOCKERS.md HB-I8.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
INFRA_BACKUP="${REPO_ROOT}/infra/backup"
EVIDENCE_DIR="${INTAKE_BACKUP_DIR:-${REPO_ROOT}/.cache/backups}"
STANZA="${PGBACKREST_STANZA:-intake}"

# --- the planning half (no container runtime is reachable from here) ---------

resolve_python() {
  if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON=("${REPO_ROOT}/.venv/bin/python")
  elif command -v uv >/dev/null 2>&1; then
    PYTHON=(uv run --project "${REPO_ROOT}" python)
  else
    PYTHON=(python3)
  fi
}

require_env() {
  local missing=()
  local name
  for name in "$@"; do
    if [[ -z "${!name:-}" ]]; then
      missing+=("${name}")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    printf 'restore drill: refusing — unset: %s\n' "${missing[*]}" >&2
    printf 'These come from OpenBao (CLAUDE.md invariant 14); export them first.\n' >&2
    return 1
  fi
}

render_plan() {
  resolve_python
  "${PYTHON[@]}" -m intake_platform.backup \
    --infra "${INFRA_BACKUP}" \
    --repo-root "${REPO_ROOT}" \
    --container-memory-bytes "${INTAKE_CONTAINER_MEMORY_BYTES:-0}" \
    "$@"
}

# --- the executing half ------------------------------------------------------

run_drill() {
  # Gate first: the plan refuses without a retention window (HB-I8) and the
  # host preflight refuses a machine too small to hold a second cluster
  # (HB-I1 disk, HB-I2 container memory). Both are refusals, not skips: the
  # drill is never quietly shrunk to fit.
  render_plan --enforce-host --show-replication

  require_env \
    PGBACKREST_REPO1_CIPHER_PASS \
    PGBACKREST_REPO1_S3_KEY \
    PGBACKREST_REPO1_S3_KEY_SECRET \
    INTAKE_DR_S3_ENDPOINT \
    INTAKE_DR_S3_ACCESS_KEY \
    INTAKE_DR_S3_SECRET_KEY

  local compose=(docker compose
    -f "${REPO_ROOT}/infra/docker-compose.dev.yml"
    -f "${REPO_ROOT}/infra/docker-compose.backup.yml"
    --profile backup)

  local started_at recovery_target restore_start restore_seconds
  started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  "${compose[@]}" up -d --wait postgres-pitr minio minio-dr

  # The replication plan is rendered from infra/backup/minio-replication.yaml
  # — one source of truth — and applied inside the mc toolbox container.
  render_plan --emit-replication | "${compose[@]}" run --rm -T mc

  "${compose[@]}" run --rm pgbackrest "--stanza=${STANZA}" stanza-create || true
  "${compose[@]}" run --rm pgbackrest "--stanza=${STANZA}" check
  "${compose[@]}" run --rm pgbackrest "--stanza=${STANZA}" --type=full backup
  "${compose[@]}" run --rm pgbackrest \
    "--stanza=${STANZA}" "--repo1-retention-full=${PGBACKREST_REPO1_RETENTION_FULL}" expire

  # Point in time, not "the newest backup": RPO 15 min is only demonstrated by
  # recovering to a moment that is not a backup boundary.
  recovery_target="$(date -u -d '-15 minutes' +'%Y-%m-%d %H:%M:%S+00' 2>/dev/null \
    || date -u -v-15M +'%Y-%m-%d %H:%M:%S+00')"

  restore_start="$(date -u +%s)"
  "${compose[@]}" run --rm pgbackrest \
    "--stanza=${STANZA}" --delta --type=time "--target=${recovery_target}" \
    --target-action=promote --pg1-path=/restore restore
  restore_seconds=$(( $(date -u +%s) - restore_start ))

  # Counts only. The query runs count(*) server-side per public table and
  # returns integers; no column is projected, so no patient value can reach
  # this shell, the drill log or the evidence file.
  local counts
  counts="$("${compose[@]}" run --rm -T --entrypoint psql postgres-pitr \
    --no-psqlrc --tuples-only --no-align --field-separator=: \
    --command "$(render_row_count_sql)")"

  "${compose[@]}" run --rm -T mc -c \
    "mc ls --recursive --summarize intake-dr/intake-pgbackrest >/dev/null"

  write_evidence "${started_at}" "${recovery_target}" "${restore_seconds}" "${counts}"

  "${compose[@]}" run --rm --entrypoint rm pgbackrest -rf /restore
  "${compose[@]}" down --volumes --remove-orphans

  printf 'restore drill: restore completed in %ss (RTO budget 14400s)\n' "${restore_seconds}"
}

render_row_count_sql() {
  resolve_python
  "${PYTHON[@]}" -c 'from intake_platform.backup import ROW_COUNT_SQL; print(ROW_COUNT_SQL)'
}

write_evidence() {
  local started_at="$1" recovery_target="$2" restore_seconds="$3" counts="$4"
  mkdir -p "${EVIDENCE_DIR}"
  resolve_python
  STANZA="${STANZA}" \
  DRILL_STARTED_AT="${started_at}" \
  DRILL_RECOVERY_TARGET="${recovery_target}" \
  DRILL_RESTORE_SECONDS="${restore_seconds}" \
  DRILL_ROW_COUNTS="${counts}" \
  DRILL_EVIDENCE_DIR="${EVIDENCE_DIR}" \
  "${PYTHON[@]}" -m intake_platform.backup.record
}

usage() {
  cat <<'USAGE'
usage: scripts/backup/restore_drill.sh (--dry-run | --run)

  --dry-run  render the ordered plan and the host verdict; change nothing
  --run      execute the drill and write evidence to INTAKE_BACKUP_DIR

Quarterly per files/10 §3. See docs/runbooks/restore-drill.md.
USAGE
}

case "${1:-}" in
  --dry-run) render_plan ;;
  --run)     run_drill ;;
  -h | --help) usage ;;
  *) usage >&2; exit 2 ;;
esac
