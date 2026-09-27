#!/usr/bin/env bash
# The DRILL_* inputs are assigned by the caller (drill_require_adapters checks):
# shellcheck disable=SC2153
#
# INT-202 — the restore drill engine (files/10 §3 "quarterly restore drills
# with evidence"; §9 row `backups`: "[Nc] restores never exercised").
#
# This file only defines. Sourcing it runs nothing and touches no container.
# Two callers source it and supply the adapters below, then call
# run_restore_drill:
#
#   infra/staging/backup.sh drill   the production host, quarterly (systemd)
#   scripts/backup/ci_drill.sh      CI, against a primary it boots itself
#
# so CI exercises the very steps the host runs. The ordered plan is stated in
# intake_platform.backup.drill.plan_restore_drill (the dry run prints it).
#
# Adapters the caller defines:
#   drill_primary_exec CMD...   run CMD in the primary's container as the
#                               postgres user (stdin passes through)
#   drill_python MODULE ARGS... run `python -m MODULE ARGS` where the primary
#                               and OpenBao Transit are reachable
#   drill_host_python ARGS...   run intake_platform/backup/status.py (stdlib)
#   drill_with_cipher CMD...    run CMD with PGBACKREST_REPO1_CIPHER_PASS in
#                               its environment, never in argv
# and these variables:
#   DRILL_TARGET       staging | ci
#   DRILL_IMAGE        the postgres+pgBackRest image the primary runs
#   DRILL_REPO_VOLUME  the docker volume holding the repository
#   DRILL_CONF         host path of infra/backup/pgbackrest.conf
#   DRILL_STATUS_DIR   where the evidence record lands
#   DRILL_CONF_D       (optional) host path of the conf.d include directory
#   DRILL_LABEL        (optional) value of the org.intake.restore-drill label
#                      on every scratch container and volume
#
# PHI discipline (invariants 3 and 6). The restored cluster lives in a named
# volume, runs with --network none and no TCP listener, and reads the
# repository read-only. Verification reads per-table counts and the drill's
# own synthetic canary; no application column is ever selected. The work
# directory holds the canary manifest, counts and clocks only.
set -euo pipefail

DRILL_STANZA="intake"
DRILL_SUPERUSER="intake"
DRILL_APP_DB="intake"
DRILL_CANARY_DB="intake_restore_drill"
DRILL_RPO_BUDGET_S=900
DRILL_RTO_BUDGET_S=14400

# The primary's command. infra/staging/compose.yaml runs exactly this array
# (tests/infra/test_backup_staging.py holds the two equal), and the CI drill
# boots its primary with it, so the drill proves the production settings.
# shellcheck disable=SC2034  # read by scripts/backup/ci_drill.sh and the tests
DRILL_POSTGRES_COMMAND=(
  postgres
  -c archive_mode=on
  -c "archive_command=pgbackrest --stanza=intake archive-push %p"
  -c archive_timeout=60
)

drill_log() { printf '[restore-drill] %s\n' "$*" >&2; }

drill_require_adapters() {
  local name missing=()
  for name in drill_primary_exec drill_python drill_host_python drill_with_cipher; do
    declare -F "$name" >/dev/null || missing+=("$name")
  done
  for name in DRILL_TARGET DRILL_IMAGE DRILL_REPO_VOLUME DRILL_CONF DRILL_STATUS_DIR; do
    [[ -n ${!name:-} ]] || missing+=("$name")
  done
  if ((${#missing[@]} > 0)); then
    drill_log "refusing: the caller did not define ${missing[*]}"
    return 2
  fi
}

drill_conf_mounts() {
  # the read-only configuration every scratch container sees
  printf '%s\n' -v "${DRILL_CONF}:/etc/pgbackrest/pgbackrest.conf:ro"
  if [[ -n ${DRILL_CONF_D:-} ]]; then
    printf '%s\n' -v "${DRILL_CONF_D}:/etc/pgbackrest/conf.d:ro"
  fi
}

drill_free_bytes() {
  # free space where docker keeps its volumes, which is where the restore lands
  local root
  root=$(docker info --format '{{.DockerRootDir}}')
  df -B1 --output=avail "$root" | tail -n 1 | tr -d ' '
}

drill_repository_headers() {
  # "<first eight bytes> <path in the repository>" for every repository file:
  # an encrypted repository answers "Salted__" for all of them. The paths are
  # pgBackRest's own names (stanza, archive id, WAL segment, backup label),
  # never data.
  docker run --rm --network none -u postgres \
    -v "${DRILL_REPO_VOLUME}:/var/lib/pgbackrest:ro" \
    --entrypoint sh "$DRILL_IMAGE" -c \
    'cd /var/lib/pgbackrest && find . -type f | head -n 500 | while IFS= read -r f; do printf "%s %s\n" "$(head -c 8 "$f" | tr -c "[:alnum:]_" "?")" "${f#./}"; done'
}

drill_restore_to() {
  # drill_restore_to TARGET VOLUME: a point-in-time restore into a fresh
  # volume from the read-only repository, in a container with no network.
  local target=$1 volume=$2 mounts
  mapfile -t mounts < <(drill_conf_mounts)
  docker volume create --label "org.intake.restore-drill=${DRILL_LABEL:-1}" "$volume" >/dev/null
  docker run --rm --network none -u root -v "${volume}:/restore" \
    --entrypoint install "$DRILL_IMAGE" -d -o postgres -g postgres -m 0700 /restore/pgdata
  drill_with_cipher docker run --rm --network none -u postgres \
    -e PGBACKREST_REPO1_CIPHER_PASS \
    -v "${DRILL_REPO_VOLUME}:/var/lib/pgbackrest:ro" -v "${volume}:/restore" "${mounts[@]}" \
    --entrypoint pgbackrest "$DRILL_IMAGE" \
    "--stanza=${DRILL_STANZA}" --repo=1 --pg1-path=/restore/pgdata \
    --type=time "--target=${target}" --target-action=promote \
    --log-level-console=warn restore
}

drill_start_scratch() {
  # drill_start_scratch CONTAINER VOLUME: replay to the target and promote.
  # Archiving off (a restored cluster that archived would push a second
  # timeline into the production stanza), no TCP listener, no network. The
  # repository is mounted read-only for restore_command's archive-get.
  local container=$1 volume=$2 mounts
  mapfile -t mounts < <(drill_conf_mounts)
  drill_with_cipher docker run -d --name "$container" --label "org.intake.restore-drill=${DRILL_LABEL:-1}" \
    --network none -u postgres -e PGBACKREST_REPO1_CIPHER_PASS \
    -v "${DRILL_REPO_VOLUME}:/var/lib/pgbackrest:ro" -v "${volume}:/restore" "${mounts[@]}" \
    --entrypoint postgres "$DRILL_IMAGE" \
    -D /restore/pgdata -c archive_mode=off -c listen_addresses= >/dev/null
}

drill_scratch_psql() {
  # drill_scratch_psql CONTAINER DATABASE < SQL: unaligned tuples, ':'-separated
  docker exec -i -u postgres "$1" psql -U "$DRILL_SUPERUSER" -d "$2" \
    --no-psqlrc -X -A -t -F: -v ON_ERROR_STOP=1 -q -f -
}

drill_wait_promoted() {
  # drill_wait_promoted CONTAINER: until the scratch cluster leaves recovery,
  # within the RTO budget. A cluster that stops instead (the target was never
  # reached) is a failure; only recovery-progress lines of its log are shown.
  local container=$1 deadline state running
  deadline=$(($(date +%s) + DRILL_RTO_BUDGET_S))
  while (($(date +%s) < deadline)); do
    state=$(docker exec -u postgres "$container" psql -U "$DRILL_SUPERUSER" -d postgres \
      --no-psqlrc -X -A -t -c 'SELECT pg_is_in_recovery()' 2>/dev/null || true)
    [[ $state == f ]] && return 0
    running=$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || echo false)
    if [[ $running != true ]]; then
      drill_log "the scratch cluster stopped before promotion; its recovery log:"
      docker logs --tail 40 "$container" 2>&1 | grep -E 'FATAL|PANIC|recovery|redo|restored log file|consistent' >&2 || true
      return 1
    fi
    sleep 2
  done
  drill_log "the scratch cluster did not promote within ${DRILL_RTO_BUDGET_S}s"
  return 1
}

drill_remove_scratch() {
  # -v: the image declares a data VOLUME, and its anonymous volume goes too
  docker rm -fv "$1" >/dev/null 2>&1 || true
  docker volume rm -f "$2" >/dev/null 2>&1 || true
}

drill_restore_and_dump() {
  # drill_restore_and_dump TARGET NAME RUN_ID OUT: restore to TARGET in a
  # scratch cluster called NAME, dump the canary to OUT, remove the scratch.
  local target=$1 name=$2 run_id=$3 out=$4 rc=0
  drill_restore_to "$target" "$name" || rc=$?
  ((rc == 0)) && { drill_start_scratch "$name" "$name" || rc=$?; }
  ((rc == 0)) && { drill_wait_promoted "$name" || rc=$?; }
  if ((rc == 0)); then
    drill_python intake_platform.backup.canary dump-sql --run-id "$run_id" |
      drill_scratch_psql "$name" "$DRILL_CANARY_DB" >"$out" || rc=$?
  fi
  drill_remove_scratch "$name" "$name"
  return "$rc"
}

run_restore_drill() {
  drill_require_adapters || return 2
  local work started_at run_id walfile sentinel_at target db_bytes free
  local scratch restore_start restore_seconds="" rc=0
  work=$(mktemp -d)
  chmod 700 "$work"
  DRILL_WORK=$work
  started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  drill_log "started ${started_at} (target ${DRILL_TARGET})"

  # 1. the newest backup; none is a refusal
  drill_primary_exec pgbackrest "--stanza=${DRILL_STANZA}" info --output=json >"$work/info.json"
  if ! drill_host_python newest-backup <"$work/info.json" >"$work/backup.json"; then
    drill_log "refusing: no backup to restore from; run a full backup first"
    return 2
  fi
  db_bytes=$(drill_host_python get "$work/backup.json" database_bytes)
  drill_log "newest backup $(drill_host_python get "$work/backup.json" label) ($(drill_host_python get "$work/backup.json" type)), ${db_bytes} bytes"

  # 2. headroom: never leave the host with less free space than the database
  free=$(drill_free_bytes)
  if ! drill_host_python headroom --free-bytes "$free" --database-bytes "$db_bytes"; then
    drill_log "refusing: ${free} bytes free, the drill needs twice the database (${db_bytes} bytes)"
    return 3
  fi

  # 3. the canary: after the backup, so only WAL replay can bring it back
  drill_python intake_platform.backup.canary prepare >"$work/manifest.json"
  run_id=$(drill_host_python get "$work/manifest.json" run_id)
  walfile=$(drill_host_python get "$work/manifest.json" walfile)
  sentinel_at=$(drill_host_python get "$work/manifest.json" sentinel_at)
  target=$(drill_host_python get "$work/manifest.json" recovery_target)
  scratch="intake-restore-drill-${run_id:0:12}"
  drill_log "canary ${run_id:0:12} written; recovery target ${target}"

  # 4. the observed RPO: the sentinel's segment reaches the repository on the
  #    primary's own archive_timeout
  if drill_python intake_platform.backup.canary wait-archived \
    --walfile "$walfile" --since "$sentinel_at" --timeout "$DRILL_RPO_BUDGET_S" >"$work/archive.json"; then
    drill_log "archived: $(drill_host_python get "$work/archive.json" rpo_observed_s)s after the last write"

    # 5. the repository is ciphertext
    drill_repository_headers >"$work/repo_check.txt" || rc=$?
    if grep -v '^Salted__ ' "$work/repo_check.txt" >&2; then
      drill_log "the repository files above do not begin with the cipher header"
    fi

    # 6-8. restore, replay, promote: the observed RTO
    restore_start=$(date +%s)
    if drill_restore_to "$target" "$scratch" &&
      drill_start_scratch "$scratch" "$scratch" &&
      drill_wait_promoted "$scratch"; then
      restore_seconds=$(($(date +%s) - restore_start))
      drill_log "restored and promoted in ${restore_seconds}s"
      # 9. per-table counts of the restored application database; no column
      drill_python intake_platform.backup.canary row-count-sql |
        drill_scratch_psql "$scratch" "$DRILL_APP_DB" >"$work/counts.txt" || rc=$?
      # 10. the canary, checked outside the restored cluster
      drill_python intake_platform.backup.canary dump-sql --run-id "$run_id" |
        drill_scratch_psql "$scratch" "$DRILL_CANARY_DB" >"$work/dump.json" || rc=$?
      drill_python intake_platform.backup.canary verify --manifest "$(cat "$work/manifest.json")" \
        <"$work/dump.json" >"$work/verify.json" || rc=$?
    else
      rc=1
    fi
    # 11. the restored cluster does not outlive the drill
    drill_remove_scratch "$scratch" "$scratch"
  else
    drill_log "the sentinel's segment was not archived within ${DRILL_RPO_BUDGET_S}s"
    rc=1
  fi

  # 12. evidence, whatever happened above: a failed drill is a finding
  local evidence_rc=0 timing=()
  [[ -n $restore_seconds ]] && timing=(--restore-seconds "$restore_seconds")
  drill_host_python drill-record --status-dir "$DRILL_STATUS_DIR" --work-dir "$work" \
    --target "$DRILL_TARGET" --started-at "$started_at" "${timing[@]}" || evidence_rc=$?
  drill_python intake_platform.backup.canary cleanup --run-id "$run_id" || true
  if ((rc != 0 || evidence_rc != 0)); then
    return 1
  fi
  return 0
}

drill_characterise_erasure_window() {
  # CI only. Restore to the moment BEFORE the synthetic erasure and report
  # whether the erased subject opens there. Measures what HB-I8 and INT-037's
  # second ask are about; it is a characterisation, not a pass condition.
  local work=${DRILL_WORK:?run_restore_drill first} run_id before name state
  run_id=$(drill_host_python get "$work/manifest.json" run_id)
  before=$(drill_host_python get "$work/manifest.json" before_erasure)
  name="intake-restore-drill-pre-${run_id:0:8}"
  drill_restore_and_dump "$before" "$name" "$run_id" "$work/dump-before.json"
  state=$(drill_python intake_platform.backup.canary erased-state --run-id "$run_id" <"$work/dump-before.json")
  printf 'erasure window: before the erasure the erased subject is %s\n' "$state"
}
