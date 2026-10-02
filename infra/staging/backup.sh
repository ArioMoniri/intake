#!/usr/bin/env bash
# INT-202: backups on the staging/production host. Run as root from
# infra/staging, after init.sh and deploy.sh (docs/runbooks/restore-drill.md):
#
#   ./backup.sh backup full|diff    one pgBackRest backup, then its record
#   ./backup.sh drill               the restore drill (files/10 §3, quarterly)
#   ./backup.sh status              repository summary and the two ages
#   ./backup.sh install-schedule    systemd timers: daily diff, weekly full,
#                                   quarterly drill
#   ./backup.sh set-retention DAYS  the window HB-I8(a) is waiting for
#   ./backup.sh replicate           object-store replication; refuses until
#                                   HB-I8(b) names the second location
#
# Records land in $STATE_DIR/backup-status: PHI-free JSON (clocks, sizes,
# labels, booleans, per-table counts) that the probes service reads as
# sec_backup_age_min and sec_restore_drill_age_days. The repository
# passphrase stays in the root-only env file and reaches a container only
# through its environment, never argv.
#
# Sourcing this file defines functions and runs nothing;
# tests/infra/test_backup_staging.py exercises them that way.
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
# shellcheck source=SCRIPTDIR/../../scripts/backup/drill_lib.sh
source "$REPO_ROOT/scripts/backup/drill_lib.sh"

STATUS_PY="$REPO_ROOT/packages/intake_platform/src/intake_platform/backup/status.py"
UNIT_DIR="/etc/systemd/system"
UNITS=(
  intake-backup-diff.service intake-backup-diff.timer
  intake-backup-full.service intake-backup-full.timer
  intake-restore-drill.service intake-restore-drill.timer
)

status_py() { python3 "$STATUS_PY" "$@"; }

backup_type() {
  # full or diff, nothing else: the schedule's two kinds
  case ${1:-} in
    full | diff) printf '%s\n' "$1" ;;
    *)
      printf '[intake-staging] ERROR: a backup is full or diff\n' >&2
      return 2
      ;;
  esac
}

retention_days() {
  # the window backup.sh set-retention wrote, or nothing (HB-I8(a) open)
  local file="$PGBACKREST_CONF_D/retention.conf"
  [[ -f $file ]] || return 0
  sed -n 's/^repo1-retention-full=\([0-9][0-9]*\)$/\1/p' "$file"
}

write_retention_conf() {
  # write_retention_conf DIR DAYS: validated against the files/06 §1 ceiling
  # before anything is written, then swapped in atomically
  local dir=$1 days tmp
  days=$(status_py validate-retention "$2") || return 2
  tmp="$dir/.retention.conf.tmp.$$"
  (
    set -o noclobber
    printf '[global]\nrepo1-retention-full=%s\n' "$days" >"$tmp"
  ) || return 2
  chmod 0644 "$tmp"
  mv -f "$tmp" "$dir/retention.conf"
}

require_second_location() {
  # names what is missing, never a value
  local name missing=()
  for name in INTAKE_DR_S3_ENDPOINT INTAKE_DR_S3_ACCESS_KEY INTAKE_DR_S3_SECRET_KEY; do
    [[ -n ${!name:-} ]] || missing+=("$name")
  done
  if ((${#missing[@]} > 0)); then
    printf '[intake-staging] ERROR: refusing to replicate: %s unset. files/10 §3 asks for a second location in Türkiye and no file names one (HB-I8(b)); there is no default and no stand-in.\n' "${missing[*]}" >&2
    return 2
  fi
}

unit_content() {
  # unit_content DIR UNIT: one systemd unit, ExecStart on this checkout
  local dir=$1 unit=$2 what command calendar
  case $unit in
    intake-backup-diff.*) what="pgBackRest differential backup" command="backup diff" calendar="Mon..Sat *-*-* 01:30:00 UTC" ;;
    intake-backup-full.*) what="pgBackRest full backup" command="backup full" calendar="Sun *-*-* 01:30:00 UTC" ;;
    intake-restore-drill.*) what="quarterly restore drill" command="drill" calendar="*-01,04,07,10-01 03:00:00 UTC" ;;
    *) return 2 ;;
  esac
  case $unit in
    *.service)
      printf '[Unit]\nDescription=INTAKE (INT-202): %s\nRequires=docker.service\nAfter=docker.service\n\n' "$what"
      printf '[Service]\nType=oneshot\nExecStart=%s/backup.sh %s\n' "$dir" "$command"
      ;;
    *.timer)
      printf '[Unit]\nDescription=INTAKE (INT-202): %s\n\n' "$what"
      printf '[Timer]\nOnCalendar=%s\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n' "$calendar"
      ;;
  esac
}

render_units() {
  # render_units DIR: every unit, each under a "### name" line
  local dir=${1:-} unit
  if [[ $dir != /* ]]; then
    printf '[intake-staging] ERROR: the units need the absolute path of infra/staging\n' >&2
    return 2
  fi
  for unit in "${UNITS[@]}"; do
    printf '### %s\n' "$unit"
    unit_content "$dir" "$unit"
  done
}

# --- commands ------------------------------------------------------------------------------

cmd_backup() {
  local kind days retention=()
  kind=$(backup_type "${1:-}") || exit 2
  require_root
  require_tools
  load_env
  prepare_backup_dirs
  pgbackrest_exec "--type=${kind}" backup
  days=$(retention_days)
  [[ -n $days ]] && retention=(--retention-days "$days")
  pgbackrest_exec info --output=json | status_py backup-record --status-dir "$BACKUP_STATUS_DIR" "${retention[@]}"
}

# The DRILL_* assignments are the engine's inputs (scripts/backup/drill_lib.sh).
# shellcheck disable=SC2034
cmd_drill() {
  require_root
  require_tools
  load_env
  prepare_backup_dirs
  drill_primary_exec() { compose exec -T -u postgres postgres "$@"; }
  drill_python() { compose exec -T api python -m "$@"; }
  drill_host_python() { status_py "$@"; }
  drill_with_cipher() {
    PGBACKREST_REPO1_CIPHER_PASS="$(env_get "$ENV_FILE" PGBACKREST_REPO1_CIPHER_PASS)" "$@"
  }
  DRILL_TARGET="staging"
  DRILL_IMAGE="$POSTGRES_IMAGE"
  DRILL_REPO_VOLUME="intake-staging_pgbackrest-repo"
  DRILL_CONF="$REPO_ROOT/infra/backup/pgbackrest.conf"
  DRILL_CONF_D="$PGBACKREST_CONF_D"
  DRILL_STATUS_DIR="$BACKUP_STATUS_DIR"
  DRILL_LABEL="intake-staging"
  run_restore_drill
}

cmd_status() {
  require_root
  require_tools
  load_env
  pgbackrest_exec info
  status_py ages --status-dir "$BACKUP_STATUS_DIR"
}

cmd_install_schedule() {
  local unit
  require_root
  command -v systemctl >/dev/null 2>&1 || die "missing tool: systemctl (the schedule is three systemd timers)"
  render_units "$STAGING_DIR" >/dev/null
  for unit in "${UNITS[@]}"; do
    unit_content "$STAGING_DIR" "$unit" >"$UNIT_DIR/$unit"
    chmod 0644 "$UNIT_DIR/$unit"
  done
  systemctl daemon-reload
  systemctl enable --now intake-backup-diff.timer intake-backup-full.timer intake-restore-drill.timer
  log "schedule installed: daily diff, weekly full, quarterly drill (systemctl list-timers 'intake-*')"
}

cmd_set_retention() {
  require_root
  prepare_backup_dirs
  write_retention_conf "$PGBACKREST_CONF_D" "${1:-}" || exit 2
  log "retention set to $(retention_days) days; pgBackRest expires older backups after the next backup"
}

cmd_replicate() {
  local plan minio
  require_root
  require_tools
  require_second_location || exit 2
  load_env
  # rendered from infra/backup/minio-replication.yaml in the api image; the
  # clear-text documents bucket is withheld there (files/06 §3)
  plan=$(compose exec -T api python -m intake_platform.backup \
    --infra infra/backup --repo-root /app --emit-replication)
  minio=$(compose ps -q minio)
  [[ -n $minio ]] || die "the minio container is not running"
  printf '%s\n' "$plan" | MINIO_ENDPOINT="http://127.0.0.1:9000" docker exec -i \
    -e MINIO_ENDPOINT -e INTAKE_DR_S3_ENDPOINT -e INTAKE_DR_S3_ACCESS_KEY -e INTAKE_DR_S3_SECRET_KEY \
    "$minio" sh -eu
  log "replication rules applied to the second location"
}

usage() {
  sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
  printf 'usage: backup.sh backup full|diff | drill | status | install-schedule | set-retention DAYS | replicate\n' >&2
}

main() {
  case ${1:-} in
    backup) cmd_backup "${2:-}" ;;
    drill) cmd_drill ;;
    status) cmd_status ;;
    install-schedule) cmd_install_schedule ;;
    set-retention) cmd_set_retention "${2:-}" ;;
    replicate) cmd_replicate ;;
    *)
      usage
      exit 2
      ;;
  esac
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
