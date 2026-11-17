#!/usr/bin/env bash
# INT-502: a throwaway capture API on the synthetic host, for the App Store
# screenshots, and its teardown.
#
# The App Store frames come from the real app on the iOS simulator. A simulator
# cannot run App Attest, and the public API rightly refuses it. This script
# therefore runs a SECOND API container beside the public one, for the length of
# one capture session, and removes it afterwards. The owner's rule of 29 Oct 2026
# applies: nothing server-side runs on the Mac.
#
# What the capture instance is, and what it is not:
#   - It runs the image the public API runs now, and only if that image carries
#     the synthetic data class baked in (INTAKE_DEPLOYMENT_DATA_CLASS=synthetic).
#   - INTAKE_ENV=dev, with these on this one container only: process-local KEKs
#     (file-dev), unattested devices (INTAKE_DEV_ALLOW_UNATTESTED) and the dev OTP
#     peek. The dev delivery adapter records an event and sends no SMS, so it is
#     a mock: Netgsm, OpenBao, the SMS proxy and the egress proxy are not wired.
#   - Its own database (intake_capture) in the existing Postgres, and its own
#     Redis database index (7). The public API's database, Redis index, env file
#     and gates are never touched. Neither are the host's tokenization key or
#     any secret it does not need: the tokenization key here is fresh for the run.
#   - It is published on 127.0.0.1:<port> only, so the security group stays at
#     80/443. The laptop reaches it through an SSM port forward
#     (scripts/store/capture_api.sh forward). Its second network is a bridge
#     without IP masquerade, so the published port works but the container has
#     no route off the host.
#
# The laptop sends this file in an AWS-RunShellScript command
# (scripts/store/capture_api.sh), so it needs no deploy. SSM runs it as root:
#   bash -c "<this file>" capture_api_host up <port>
#   bash -c "<this file>" capture_api_host down
#   bash -c "<this file>" capture_api_host status
#
# Secrets: the database role passwords and the Redis password are read from the
# root-only env file into variables. They reach the container through a 0600 env file under a 0700
# directory in /run, which is deleted as soon as `docker run` has read it. They
# are never in an argv, and never printed.
#
# Output is one line: "capture_api: up 127.0.0.1:<port> <image>",
# "capture_api: down", "capture_api: running|absent", or
# "capture_api: refused: <why>" with exit 3.
set -euo pipefail
umask 077
export LC_ALL=C

ENV_FILE=${INTAKE_STAGING_ENV_FILE:-/etc/intake-staging/.env}
RUN_DIR=${INTAKE_CAPTURE_RUN_DIR:-/run/intake-capture}
API=intake-staging-api-1
PG=intake-staging-postgres-1
REDIS=intake-staging-redis-1
BACKEND=intake-staging_backend
CONTAINER=intake-capture-api
NETWORK=intake-capture
LABEL=intake.capture=INT-502
DB=intake_capture
REDIS_INDEX=7
IMAGE_SHAPE='^intake-staging/api:[0-9a-f]{40}$'
# The container's env file. Global, so the EXIT trap can still name it after up returns.
ENVFILE="$RUN_DIR/capture.env"
trap 'rm -f "$ENVFILE"' EXIT

refuse() {
  printf 'capture_api: refused: %s\n' "$*"
  exit 3
}

env_value() {
  local key=$1 line
  line=$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1) || true
  printf '%s' "${line#*=}"
}

redis_index() {
  # The password reaches redis-cli in its environment (REDISCLI_AUTH), not argv.
  local password=$1
  shift
  printf '%s' "$password" | docker exec -i "$REDIS" sh -c \
    'IFS= read -r REDISCLI_AUTH; export REDISCLI_AUTH; exec redis-cli -n "$0" "$@"' \
    "$REDIS_INDEX" "$@" >/dev/null
}

ours() {
  # The container exists and carries our label; anything else of that name is
  # not ours to touch.
  local label
  label=$(docker inspect --format '{{index .Config.Labels "intake.capture"}}' "$CONTAINER" 2>/dev/null) ||
    return 1
  [[ $label == "${LABEL#*=}" ]] || refuse "a container named $CONTAINER exists without label $LABEL"
}

up() {
  local port=${1:-}
  if ! [[ $port =~ ^[0-9]{4,5}$ ]] || ((port < 1024 || port > 65535)); then
    refuse "port must be 1024-65535"
  fi
  [[ -r $ENV_FILE ]] || refuse "no env file at $ENV_FILE"
  ! ours || refuse "$CONTAINER is already up; run down first"
  [[ -z $(ss -Hltn "sport = :$port") ]] || refuse "port $port is in use on the host"

  local image
  image=$(docker inspect --format '{{.Config.Image}}' "$API" 2>/dev/null) ||
    refuse "the public API container $API is not running"
  [[ $image =~ $IMAGE_SHAPE ]] || refuse "the public API image is not a pinned release"
  docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$image" |
    grep -qx 'INTAKE_DEPLOYMENT_DATA_CLASS=synthetic' ||
    refuse "the image does not bake the synthetic data class"

  local owner app audit redis_password
  owner=$(env_value POSTGRES_PASSWORD)
  app=$(env_value PG_APP_RW_PASSWORD)
  audit=$(env_value PG_AUDIT_WRITER_PASSWORD)
  redis_password=$(env_value REDIS_PASSWORD)
  local value
  for value in "$owner" "$app" "$audit" "$redis_password"; do
    [[ $value =~ ^[0-9a-f]{64}$ ]] || refuse "the env file lacks a generated database or Redis secret"
  done

  printf "SELECT 'CREATE DATABASE %s OWNER intake' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '%s')\\gexec\n" \
    "$DB" "$DB" | docker exec -i "$PG" psql -v ON_ERROR_STOP=1 -q -U intake -d intake >/dev/null

  docker network inspect "$NETWORK" >/dev/null 2>&1 ||
    docker network create --driver bridge --label "$LABEL" \
      -o com.docker.network.bridge.enable_ip_masquerade=false "$NETWORK" >/dev/null

  mkdir -p "$RUN_DIR"
  chmod 0700 "$RUN_DIR"
  local db="postgres:5432/${DB}"
  {
    printf 'INTAKE_ENV=dev\n'
    printf 'INTAKE_API_KEK_MODE=file-dev\n'
    printf 'INTAKE_DEV_ALLOW_UNATTESTED=explicit-yes\n'
    printf 'INTAKE_DEV_OTP_PEEK=explicit-yes\n'
    printf 'INTAKE_API_DB_URL=postgresql+psycopg://app_rw:%s@%s\n' "$app" "$db"
    printf 'INTAKE_API_AUDIT_DB_URL=postgresql+psycopg://svc_audit_writer:%s@%s\n' "$audit" "$db"
    printf 'INTAKE_API_BOOTSTRAP_DB_URL=postgresql+psycopg://intake:%s@%s\n' "$owner" "$db"
    printf 'INTAKE_REDIS_URL=redis://:%s@redis:6379/%s\n' "$redis_password" "$REDIS_INDEX"
    printf 'INTAKE_TOKENIZATION_KEY=%s\n' "$(openssl rand -hex 32)"
    printf 'INTAKE_API_TRIAGE_TENANT_KIND=synthetic\n'
    printf 'INTAKE_API_TRIAGE_DEPLOYMENT=i-0e489e48739f5de98\n'
    printf 'INTAKE_API_TRIAGE_RULES=files/protocols/base.life_threat.yaml\n'
    printf 'INTAKE_API_TRIAGE_SIGNATURE=packages/protocols/signing/red_rule_set.synthetic.json\n'
  } >"$ENVFILE"

  # The schema first, as the owner role, from the same image (lib.sh run_migrations).
  # shellcheck disable=SC2016
  docker run --rm --network "$BACKEND" --label "$LABEL" --env-file "$ENVFILE" "$image" \
    sh -c 'INTAKE_DATABASE_URL="$INTAKE_API_BOOTSTRAP_DB_URL" exec alembic upgrade head' \
    >/dev/null 2>&1 || refuse "migrating $DB failed"
  docker create --name "$CONTAINER" --label "$LABEL" --restart no \
    --network "$BACKEND" -p "127.0.0.1:${port}:8000" --env-file "$ENVFILE" \
    "$image" >/dev/null
  rm -f "$ENVFILE"
  docker network connect "$NETWORK" "$CONTAINER"
  docker start "$CONTAINER" >/dev/null

  local tries=0
  until curl -fsS -o /dev/null "http://127.0.0.1:${port}/healthz"; do
    tries=$((tries + 1))
    ((tries < 60)) || refuse "the capture API did not answer /healthz; run down"
    sleep 1
  done
  printf 'capture_api: up 127.0.0.1:%s %s\n' "$port" "$image"
}

down() {
  if ours; then
    docker rm -f "$CONTAINER" >/dev/null
  fi
  if docker network inspect "$NETWORK" >/dev/null 2>&1; then
    docker network rm "$NETWORK" >/dev/null
  fi
  [[ -r $ENV_FILE ]] || refuse "no env file at $ENV_FILE"
  printf 'DROP DATABASE IF EXISTS %s WITH (FORCE);\n' "$DB" |
    docker exec -i "$PG" psql -v ON_ERROR_STOP=1 -q -U intake -d intake >/dev/null
  redis_index "$(env_value REDIS_PASSWORD)" FLUSHDB
  rm -rf "$RUN_DIR"
  printf 'capture_api: down\n'
}

status() {
  if ours; then
    printf 'capture_api: running\n'
  else
    printf 'capture_api: absent\n'
  fi
}

[[ ${EUID:-$(id -u)} -eq 0 || -n ${INTAKE_CAPTURE_TEST:-} ]] || refuse "run as root (SSM does)"
case ${1:-} in
  up) up "${2:-}" ;;
  down) down ;;
  status) status ;;
  *) refuse "mode must be up <port>, down or status" ;;
esac
