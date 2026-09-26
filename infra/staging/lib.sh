#!/usr/bin/env bash
# INT-345: helpers shared by init.sh, deploy.sh and smoke.sh.
#
# This file only defines. Sourcing it touches neither docker nor the host;
# tests/infra/test_staging_compose.py sources it to exercise the pure helpers.
#
# Secrets handling, everywhere below:
#   - Generated values live in $ENV_FILE (root, 0600, in a 0700 dir).
#   - OpenBao key shares and the root token live in $INIT_FILE (root, 0600).
#   - A token reaches the bao CLI through the docker CLI's environment.
#   - An unseal key or password reaches its consumer on stdin.
#   - Neither is ever passed in argv, which `ps` shows to every host user.
set -euo pipefail

STAGING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$STAGING_DIR/../.." && pwd)"
STATE_DIR="${INTAKE_STAGING_STATE_DIR:-/etc/intake-staging}"
ENV_FILE="$STATE_DIR/.env"
INIT_FILE="$STATE_DIR/openbao-init.json"
ENV_TEMPLATE="$STAGING_DIR/staging.env.template"
API_IMAGE_REPO="intake-staging/api"
# The restart probe's Transit key. TransitKekProvider names keys tenant-<id>,
# and staging_probe.PROBE_TENANT is "staging-restart-probe".
PROBE_KEK="tenant-staging-restart-probe"

# Every LOGIN role that a migration creates with a committed dev password,
# with the .env key that holds its host-generated replacement. The test
# checks this table against migrations/versions, so a new role cannot keep
# its dev password.
ROLE_PASSWORD_KEYS=(
  "app_rw:PG_APP_RW_PASSWORD"
  "clinician_ro:PG_CLINICIAN_RO_PASSWORD"
  "svc_audit_writer:PG_AUDIT_WRITER_PASSWORD"
  "svc_learning_reader:PG_LEARNING_READER_PASSWORD"
)

log() { printf '[intake-staging] %s\n' "$*" >&2; }
die() {
  printf '[intake-staging] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  [[ ${EUID:-$(id -u)} -eq 0 ]] || die "run as root (sudo): the env file and the unseal keys are root-only"
}

require_tools() {
  local tool
  for tool in docker python3 curl od; do
    command -v "$tool" >/dev/null 2>&1 || die "missing tool: $tool"
  done
  docker compose version >/dev/null 2>&1 || die "missing the docker compose v2 plugin"
}

# The only way this tier calls compose: one project, one root-only env file.
compose() {
  docker compose -p intake-staging --env-file "$ENV_FILE" -f "$STAGING_DIR/compose.yaml" "$@"
}

# --- pure helpers (tested without docker) ----------------------------------------------

gen_secret() {
  # 256 bits from the kernel CSPRNG, as hex: safe inside URLs, SQL and HCL
  od -An -tx1 -N32 /dev/urandom | tr -d ' \n'
  printf '\n'
}

validate_hostname() {
  local host=${1:-}
  if [[ ! $host =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]]; then
    die "not a public hostname: '${host}' (expected <EIP-dashed>.sslip.io)"
  fi
}

revision_sha_from_file() {
  local sha
  sha=$(tr -d '[:space:]' <"$1")
  if [[ ! $sha =~ ^[0-9a-f]{40}$ ]]; then
    log "REVISION is not stamped: ship the tree with git archive, or deploy from a clean git checkout"
    return 1
  fi
  printf '%s\n' "$sha"
}

env_get() {
  local file=$1 key=$2
  [[ -f $file ]] || return 0
  awk -v k="$key" 'index($0, k "=") == 1 { v = substr($0, length(k) + 2) } END { if (v != "") print v }' "$file"
}

env_set() {
  # upsert KEY=VALUE atomically; the file is 0600 before a value is in it
  local file=$1 key=$2 value=$3 tmp
  tmp="$(dirname "$file")/.env.tmp.$$.${RANDOM}"
  # exclusive create (noclobber), 0600 from birth, beside the target so mv is atomic
  (
    umask 077
    set -o noclobber
    : >"$tmp"
  ) || die "could not create $tmp"
  if [[ -f $file ]]; then
    grep -v "^${key}=" "$file" >"$tmp" || true
  fi
  printf '%s=%s\n' "$key" "$value" >>"$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$file"
}

template_keys() {
  sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*$/\1/p' "$ENV_TEMPLATE"
}

# --- host state --------------------------------------------------------------------------

prepare_state_dir() {
  umask 077
  mkdir -p "$STATE_DIR"
  chown root:root "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  [[ -f $ENV_FILE ]] || : >"$ENV_FILE"
  chown root:root "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

load_env() {
  # Validate that every template key has a value. Shell variables are set
  # only for the values the scripts read; secrets are never exported.
  [[ -f $ENV_FILE ]] || die "$ENV_FILE is missing: run ./init.sh first"
  local key
  while IFS= read -r key; do
    [[ -n $(env_get "$ENV_FILE" "$key") ]] || die "$key is empty in $ENV_FILE: run ./init.sh"
  done < <(template_keys)
  STAGING_HOSTNAME=$(env_get "$ENV_FILE" STAGING_HOSTNAME)
  validate_hostname "$STAGING_HOSTNAME"
}

revision_sha() {
  local sha
  if sha=$(revision_sha_from_file "$STAGING_DIR/REVISION" 2>/dev/null); then
    printf '%s\n' "$sha"
    return 0
  fi
  if ! command -v git >/dev/null 2>&1 || ! git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    die "no git sha: REVISION is not stamped and $REPO_ROOT is not a git checkout (ship it with git archive)"
  fi
  [[ -z $(git -C "$REPO_ROOT" status --porcelain) ]] ||
    die "the checkout has uncommitted changes, so /version would not name what runs"
  git -C "$REPO_ROOT" rev-parse HEAD
}

stamp_revision() {
  # /version = the deployed commit + when its image was built. Reusing the
  # existing image's timestamp keeps a re-deploy of the same sha a no-op.
  local created
  INTAKE_GIT_SHA=$(revision_sha)
  created=$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.created" }}' \
    "$API_IMAGE_REPO:$INTAKE_GIT_SHA" 2>/dev/null || true)
  if [[ -n $created && $created != "<no value>" ]]; then
    INTAKE_BUILT_AT=$created
  else
    INTAKE_BUILT_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  fi
  export INTAKE_GIT_SHA INTAKE_BUILT_AT
}

wait_healthy() {
  local service=$1 id status _
  for _ in $(seq 1 90); do
    id=$(compose ps -q "$service")
    if [[ -n $id ]]; then
      status=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$id")
      [[ $status == healthy ]] && return 0
    fi
    sleep 2
  done
  die "$service did not become healthy within 180 s"
}

# --- OpenBao -----------------------------------------------------------------------------

openbao_container() {
  local id
  id=$(compose ps -q openbao)
  [[ -n $id ]] || die "the openbao container is not running"
  printf '%s\n' "$id"
}

bao_anon() {
  docker exec -i "$(openbao_container)" bao "$@"
}

bao_as() {
  # -e with a bare NAME copies the value from the docker CLI's own environment
  local token=$1
  shift
  BAO_TOKEN="$token" docker exec -i -e BAO_TOKEN "$(openbao_container)" bao "$@"
}

openbao_state() {
  # prints uninitialized | sealed | unsealed; `bao status` exits 2 when sealed
  local json rc=0
  json=$(bao_anon status -format=json 2>/dev/null) || rc=$?
  [[ $rc -eq 0 || $rc -eq 2 ]] || return 1
  python3 -c '
import json, sys
s = json.load(sys.stdin)
print("uninitialized" if not s["initialized"] else ("sealed" if s["sealed"] else "unsealed"))
' <<<"$json"
}

wait_for_openbao() {
  local _
  for _ in $(seq 1 60); do
    openbao_state >/dev/null 2>&1 && return 0
    sleep 2
  done
  die "openbao did not answer within 120 s"
}

init_field() {
  # root_token | unseal_threshold | unseal_key <n>. Written without a newline
  # so the value can be piped straight into the bao CLI.
  python3 -c '
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
if sys.argv[2] == "unseal_key":
    sys.stdout.write(data["unseal_keys_b64"][int(sys.argv[3])])
else:
    sys.stdout.write(str(data[sys.argv[2]]))
' "$INIT_FILE" "$@"
}

initialise_openbao() {
  local state
  state=$(openbao_state) || die "openbao is not answering"
  if [[ $state != uninitialized ]]; then
    [[ -f $INIT_FILE ]] || die "openbao is initialised but $INIT_FILE is missing: its key shares are not on this host"
    log "openbao already initialised"
    return 0
  fi
  [[ ! -e $INIT_FILE ]] ||
    die "$INIT_FILE exists but openbao is uninitialised: refusing to overwrite key shares (see docs/runbooks/staging.md)"
  (
    umask 077
    bao_anon operator init -key-shares=3 -key-threshold=2 -format=json >"$INIT_FILE.tmp"
  )
  chmod 600 "$INIT_FILE.tmp"
  mv -f "$INIT_FILE.tmp" "$INIT_FILE"
  log "openbao initialised: 3 key shares (threshold 2) and the root token are in $INIT_FILE (0600)"
}

unseal_openbao() {
  [[ -f $INIT_FILE ]] || die "$INIT_FILE is missing: run ./init.sh first"
  local state threshold i
  state=$(openbao_state) || die "openbao is not answering"
  case $state in
    unsealed)
      log "openbao already unsealed"
      return 0
      ;;
    uninitialized)
      die "openbao is uninitialised although $INIT_FILE exists: its volume was lost; refusing to guess"
      ;;
  esac
  threshold=$(init_field unseal_threshold)
  for ((i = 0; i < threshold; i++)); do
    init_field unseal_key "$i" | bao_anon write -format=json sys/unseal key=- >/dev/null
  done
  [[ $(openbao_state) == unsealed ]] || die "openbao is still sealed after $threshold key shares"
  log "openbao unsealed"
}

configure_openbao() {
  # transit engine, the intake-api policy, the restart-probe KEK and the API's
  # periodic token. The token id is the host-generated OPENBAO_TOKEN, so the
  # env file is complete before OpenBao exists. Each step is create-if-absent.
  local root api_token
  root=$(init_field root_token)
  if ! bao_as "$root" secrets list -format=json |
    python3 -c 'import json, sys; sys.exit(0 if "transit/" in json.load(sys.stdin) else 1)'; then
    bao_as "$root" secrets enable transit >/dev/null
    log "transit engine enabled"
  fi
  bao_as "$root" policy write intake-api - <"$STAGING_DIR/openbao/intake-api-policy.hcl" >/dev/null
  if ! bao_as "$root" read -format=json "transit/keys/${PROBE_KEK}" >/dev/null 2>&1; then
    bao_as "$root" write "transit/keys/${PROBE_KEK}" type=aes256-gcm96 >/dev/null
    log "restart-probe KEK created"
  fi
  api_token=$(env_get "$ENV_FILE" OPENBAO_TOKEN)
  if ! bao_as "$api_token" token lookup >/dev/null 2>&1; then
    printf '%s' "$api_token" | bao_as "$root" write -format=json auth/token/create-orphan \
      id=- policies=intake-api period=768h display_name=intake-api-staging >/dev/null
    log "API token minted (policy intake-api, periodic 768h, orphan)"
  fi
}

renew_api_token() {
  bao_as "$(env_get "$ENV_FILE" OPENBAO_TOKEN)" token renew >/dev/null ||
    die "the API's OpenBao token could not be renewed (expired?): re-run ./init.sh"
}

# --- Postgres ----------------------------------------------------------------------------

run_migrations() {
  # alembic as the owner role, from the api image, on the internal network.
  # The variable expands inside the container, which is where it lives.
  # shellcheck disable=SC2016
  compose run --rm --no-deps -T api \
    sh -c 'INTAKE_DATABASE_URL="$INTAKE_API_BOOTSTRAP_DB_URL" exec alembic upgrade head'
}

rotate_role_passwords() {
  # The SQL travels on stdin. The session also stops Postgres from logging a
  # failing statement, so no generated value reaches the container log.
  local entry role key value sql
  sql="SET log_statement = 'none'; SET log_min_error_statement = 'panic';"$'\n'
  for entry in "${ROLE_PASSWORD_KEYS[@]}"; do
    role=${entry%%:*}
    key=${entry#*:}
    value=$(env_get "$ENV_FILE" "$key")
    [[ $value =~ ^[0-9a-f]{64}$ ]] || die "$key is not a generated secret: run ./init.sh"
    sql+="DO \$\$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '${role}') THEN"
    sql+=" ALTER ROLE ${role} PASSWORD '${value}'; END IF; END \$\$;"$'\n'
  done
  printf '%s' "$sql" | compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U intake -d intake >/dev/null
  log "re-keyed ${#ROLE_PASSWORD_KEYS[@]} database roles away from their committed dev passwords"
}

# --- public HTTPS ------------------------------------------------------------------------

https_get() {
  curl -fsS --proto '=https' --tlsv1.2 --max-time 10 "https://${STAGING_HOSTNAME}$1"
}

wait_https() {
  # certificate issuance can take a minute on the first deploy
  local _
  for _ in $(seq 1 36); do
    https_get "$1" >/dev/null 2>&1 && return 0
    sleep 5
  done
  return 1
}
