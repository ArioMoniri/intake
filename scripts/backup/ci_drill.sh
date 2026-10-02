#!/usr/bin/env bash
# INT-202 — the restore drill in CI, against a primary this script boots.
#
#   scripts/backup/ci_drill.sh --evidence-dir DIR [--characterise-erasure-window]
#
# It builds the production host's Postgres image (infra/staging/
# Dockerfile.postgres: the pinned server plus the pinned pgBackRest), boots a
# primary with the exact archiving command the host runs
# (DRILL_POSTGRES_COMMAND), mounts the same infra/backup/pgbackrest.conf,
# creates the stanza, takes an encrypted full backup into a POSIX repository
# volume, and then runs the same engine the host's quarterly timer runs
# (scripts/backup/drill_lib.sh). The canary is sealed through the dev tier's
# OpenBao Transit, as the host's is through its own.
#
# Everything is synthetic and throwaway: a random repository passphrase and
# database password generated here, never printed, and every container and
# volume removed on exit. Run by tests/infra/test_backup_restore_integration.py
# in the compose CI job (`make check-integration`), or by `make backup-drill-ci`.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=scripts/backup/drill_lib.sh
source "${SCRIPT_DIR}/drill_lib.sh"

EVIDENCE_DIR=""
CHARACTERISE=no
while (($# > 0)); do
  case $1 in
    --evidence-dir)
      EVIDENCE_DIR=${2:?--evidence-dir needs a directory}
      shift 2
      ;;
    --characterise-erasure-window)
      CHARACTERISE=yes
      shift
      ;;
    *)
      printf 'usage: %s --evidence-dir DIR [--characterise-erasure-window]\n' "$0" >&2
      exit 2
      ;;
  esac
done
[[ -n $EVIDENCE_DIR ]] || {
  printf 'usage: %s --evidence-dir DIR [--characterise-erasure-window]\n' "$0" >&2
  exit 2
}
mkdir -p "$EVIDENCE_DIR"

PREFIX="intake-drill-ci-$$"
PRIMARY="${PREFIX}-primary"
DRILL_TARGET="ci"
DRILL_IMAGE="intake-drill-ci/postgres:${PREFIX}"
DRILL_REPO_VOLUME="${PREFIX}-repo"
DRILL_CONF="${REPO_ROOT}/infra/backup/pgbackrest.conf"
DRILL_STATUS_DIR="$EVIDENCE_DIR"
DRILL_LABEL="$PREFIX"
STATUS_PY="${REPO_ROOT}/packages/intake_platform/src/intake_platform/backup/status.py"

if [[ -n ${DRILL_PYTHON:-} ]]; then
  PYTHON=("$DRILL_PYTHON")
else
  PYTHON=(uv run --project "$REPO_ROOT" python)
fi

# 256-bit throwaway secrets, generated here and never printed.
PGBACKREST_REPO1_CIPHER_PASS=$(od -An -tx1 -N32 /dev/urandom | tr -d ' \n')
POSTGRES_PASSWORD=$(od -An -tx1 -N32 /dev/urandom | tr -d ' \n')
export PGBACKREST_REPO1_CIPHER_PASS POSTGRES_PASSWORD
PRIMARY_PORT=""

drill_primary_exec() { docker exec -i -u postgres "$PRIMARY" "$@"; }
drill_with_cipher() { "$@"; }
drill_host_python() { "${PYTHON[@]}" "$STATUS_PY" "$@"; }
drill_python() {
  # the canary seals through the dev tier's OpenBao Transit; its token comes
  # from the caller (make check-integration exports it), never from here
  INTAKE_API_BOOTSTRAP_DB_URL="postgresql+psycopg://intake:${POSTGRES_PASSWORD}@127.0.0.1:${PRIMARY_PORT}/intake" \
    OPENBAO_ADDR="${OPENBAO_ADDR:-http://127.0.0.1:8200}" \
    "${PYTHON[@]}" -m "$@"
}
if [[ -z ${OPENBAO_TOKEN:-} ]]; then
  drill_log "refusing: OPENBAO_TOKEN is unset; the canary seals through the dev tier's Transit engine"
  exit 2
fi
export OPENBAO_TOKEN

# shellcheck disable=SC2329  # invoked by the EXIT trap below
ci_teardown() {
  # this run's scratch containers and volumes only, by their label
  docker ps -aq --filter "label=org.intake.restore-drill=${DRILL_LABEL}" | xargs -r docker rm -f >/dev/null 2>&1 || true
  docker rm -fv "$PRIMARY" >/dev/null 2>&1 || true
  docker volume ls -q --filter "label=org.intake.restore-drill=${DRILL_LABEL}" | xargs -r docker volume rm -f >/dev/null 2>&1 || true
  docker volume rm -f "${PREFIX}-repo" "${PREFIX}-spool" "${PREFIX}-pgdata" >/dev/null 2>&1 || true
  docker image rm -f "$DRILL_IMAGE" >/dev/null 2>&1 || true
}
trap ci_teardown EXIT

drill_log "building ${DRILL_IMAGE} from infra/staging/Dockerfile.postgres"
docker build --quiet -t "$DRILL_IMAGE" -f "${REPO_ROOT}/infra/staging/Dockerfile.postgres" \
  "${REPO_ROOT}/infra/staging" >/dev/null

for volume in repo spool pgdata; do
  docker volume create "${PREFIX}-${volume}" >/dev/null
done
docker run -d --name "$PRIMARY" \
  -e POSTGRES_USER=intake -e POSTGRES_DB=intake -e POSTGRES_PASSWORD -e PGBACKREST_REPO1_CIPHER_PASS \
  -v "${DRILL_CONF}:/etc/pgbackrest/pgbackrest.conf:ro" \
  -v "${PREFIX}-repo:/var/lib/pgbackrest" \
  -v "${PREFIX}-spool:/var/spool/pgbackrest" \
  -v "${PREFIX}-pgdata:/var/lib/postgresql/data" \
  -p 127.0.0.1::5432 \
  "$DRILL_IMAGE" "${DRILL_POSTGRES_COMMAND[@]}" >/dev/null

# Ready on TCP, which the image's init-time server never listens on.
for _ in $(seq 1 90); do
  if docker exec "$PRIMARY" pg_isready -q -h 127.0.0.1 -U intake -d intake 2>/dev/null; then
    break
  fi
  sleep 1
done
docker exec "$PRIMARY" pg_isready -q -h 127.0.0.1 -U intake -d intake ||
  { drill_log "the primary did not become ready"; exit 1; }
PRIMARY_PORT=$(docker port "$PRIMARY" 5432/tcp | head -n 1)
PRIMARY_PORT=${PRIMARY_PORT##*:}

drill_log "stanza-create, check, full backup"
drill_primary_exec pgbackrest "--stanza=${DRILL_STANZA}" stanza-create
drill_primary_exec pgbackrest "--stanza=${DRILL_STANZA}" check
drill_primary_exec pgbackrest "--stanza=${DRILL_STANZA}" --type=full backup

drill_rc=0
run_restore_drill || drill_rc=$?
# the evidence record, pass or fail: it is the drill's output of record
for record in "$EVIDENCE_DIR"/restore-drill-*.json; do
  [[ -f $record ]] && cat "$record"
done

if [[ $CHARACTERISE == yes && -n ${DRILL_WORK:-} ]]; then
  drill_characterise_erasure_window
fi
exit "$drill_rc"
