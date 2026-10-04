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
# The S3-compatible object store for the API's documents and WORM audit
# copies. The owner chose the image on 2026-09-26 (owner decision D1): the
# maintained AGPL-3.0 community fork, pinned by index digest. INT-347 (#550)
# records the same reference in observability/registry.yaml, with the licence
# read from the raw LICENSE blob. This is the only copy in this tier:
# compose.yaml's minio service interpolates it, and deploy.sh refuses an
# empty or unpinned value before it touches the host. It is exported so every
# compose call (init, deploy, smoke) can interpolate it. It is not a secret.
OBJECT_STORE_IMAGE="pgsty/minio:RELEASE.2026-08-04T00-00-00Z@sha256:b6bfe7239bfc83fb90d31612d9704d86039dd714f7904b3f1ad68f211e602372"
export OBJECT_STORE_IMAGE
OBJECT_STORE_ISSUE="INT-347 (#550)"

# INT-352 (audit F18): /version's third stamp, sbom_digest. syft writes an
# SPDX SBOM of the built api image into this commit's release directory on
# the host. That directory is under STATE_DIR, outside the build context, so
# the SBOM never enters the image it describes. INTAKE_SBOM_DIGEST is the
# file's sha256, and compose requires it to start the api.
#
# syft v1.51.1 is the version CI's anchore/sbom-action v0.24.1 runs. It is
# pinned by the index digest resolved from Docker Hub's v2 API on 27 Sep 2026.
# Its licence is Apache-2.0, read from the raw LICENSE blob at the image's
# revision (docs/evidence/INT-352.md). It is not a secret.
SBOM_IMAGE="anchore/syft:v1.51.1@sha256:95fe0835e5bebc6f8b1f8acef68d47d63d594ef4c0f25c097ff853b23cbac74c"
SBOM_ISSUE="INT-352 (docs/evidence/INT-352.md)"
SBOM_FORMAT="spdx-json"
RELEASES_DIR="$STATE_DIR/releases"
# compose loads the whole file, so even `compose build` needs a value for the
# api's required INTAKE_SBOM_DIGEST, which names the SBOM of the image that
# build makes. build_api_image binds this value to that one call. It is not a
# digest, so /version could never pass smoke.sh with it.
SBOM_DIGEST_DURING_BUILD="none-while-the-image-builds"

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

# INT-352: the .env keys the operator sets by hand. init.sh generates none of
# them and writes each one empty, once, for the operator to fill. Each may stay
# empty: compose passes it to the API with no default, and the API reads empty
# as unset and fails closed (no Apple team id: every iOS attestation is
# refused). require_sms_with_app_attest refuses the one unsafe mix.
APP_ATTEST_KEYS=(INTAKE_APP_ATTEST_TEAM_ID INTAKE_APP_ATTEST_BUNDLE_ID INTAKE_APP_ATTEST_ENVIRONMENT)
SMS_KEYS=(TWILIO_ACCOUNT_SID TWILIO_AUTH_TOKEN TWILIO_FROM)
OPERATOR_KEYS=("${APP_ATTEST_KEYS[@]}" "${SMS_KEYS[@]}")

# INT-421: keys generated as 32 random bytes in base64url (43 characters, no
# padding), rather than gen_secret's 64 hex. oauth2-proxy accepts a cookie
# secret only as 16, 24 or 32 bytes, raw or base64-decoded, and 64 hex
# characters are neither.
COOKIE_SECRET_KEYS=(OAUTH2_PROXY_COOKIE_SECRET OAUTH2_PROXY_GRAFANA_COOKIE_SECRET)

# INT-421: the admin tier. Keycloak keeps its own database in the staging
# Postgres, under its own role. The API reads the realm's key set from a file
# that deploy.sh mirrors on every deploy, so no admin request depends on
# Keycloak answering (intake_platform.admin.oidc).
KEYCLOAK_DB=keycloak
KEYCLOAK_REALM=intake
# compose.yaml's KC_BOOTSTRAP_ADMIN_USERNAME, the master-realm admin the deploy uses
KEYCLOAK_BOOTSTRAP_ADMIN=intake-bootstrap
JWKS_FILE="$STATE_DIR/keycloak-jwks.json"
ATTEST_SMS_RUNBOOK='docs/runbooks/staging.md, section "App Attest and SMS"'

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
# INT-481: compose.obs.yaml (the telemetry tier) is part of the same project.
compose() {
  docker compose -p intake-staging --env-file "$ENV_FILE" -f "$STAGING_DIR/compose.yaml" \
    -f "$STAGING_DIR/compose.obs.yaml" "$@"
}

# --- pure helpers (tested without docker) ----------------------------------------------

gen_secret() {
  # 256 bits from the kernel CSPRNG, as hex: safe inside URLs, SQL and HCL
  od -An -tx1 -N32 /dev/urandom | tr -d ' \n'
  printf '\n'
}

gen_cookie_secret() {
  # INT-421: 256 bits from the kernel CSPRNG, as unpadded base64url (43
  # characters), the form oauth2-proxy decodes to a 32-byte key
  python3 -c 'import base64, sys; sys.stdout.write(base64.urlsafe_b64encode(open("/dev/urandom", "rb").read(32)).decode().rstrip("=") + "\n")'
}

is_cookie_secret_key() {
  local key=$1 cookie_key
  for cookie_key in "${COOKIE_SECRET_KEYS[@]}"; do
    [[ $key == "$cookie_key" ]] && return 0
  done
  return 1
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

env_has() {
  # the key is in the file, empty or not
  local file=$1 key=$2
  [[ -f $file ]] && grep -q "^${key}=" "$file"
}

template_keys() {
  sed -n 's/^\([A-Z_][A-Z0-9_]*\)=.*$/\1/p' "$ENV_TEMPLATE"
}

is_operator_key() {
  local key=$1 operator_key
  for operator_key in "${OPERATOR_KEYS[@]}"; do
    [[ $key == "$operator_key" ]] && return 0
  done
  return 1
}

generate_missing_secrets() {
  # Every template key but the owner-supplied hostname and the operator's keys
  # gets a generated value, once: a key that already has one keeps it, so a
  # re-run re-keys nothing. An operator key is only written empty, if absent.
  local key
  while IFS= read -r key; do
    [[ $key == STAGING_HOSTNAME ]] && continue
    if is_operator_key "$key"; then
      env_has "$ENV_FILE" "$key" || env_set "$ENV_FILE" "$key" ""
      continue
    fi
    if [[ -z $(env_get "$ENV_FILE" "$key") ]]; then
      if is_cookie_secret_key "$key"; then
        env_set "$ENV_FILE" "$key" "$(gen_cookie_secret)"
      else
        env_set "$ENV_FILE" "$key" "$(gen_secret)"
      fi
      log "generated $key"
    fi
  done < <(template_keys)
}

require_object_store_image() {
  # name:tag@sha256:<64 hex>, the same pin every other image here carries
  local image=${1:-}
  [[ -n $image ]] ||
    die "no object-store image is set: OBJECT_STORE_IMAGE in lib.sh must be the owner-approved, digest-pinned image that ${OBJECT_STORE_ISSUE} records (docs/runbooks/staging.md)"
  [[ $image =~ ^[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$ ]] ||
    die "the object-store image is not pinned by digest (name:tag@sha256:<64 hex>): see ${OBJECT_STORE_ISSUE}"
}

require_sbom_image() {
  # the same pin as the object store's: name:tag@sha256:<64 hex>
  local image=${1:-}
  [[ -n $image ]] ||
    die "no SBOM image is set: SBOM_IMAGE in lib.sh must be syft pinned by digest, as ${SBOM_ISSUE} records"
  [[ $image =~ ^[a-z0-9./_-]+:[A-Za-z0-9._-]+@sha256:[0-9a-f]{64}$ ]] ||
    die "the SBOM image is not pinned by digest (name:tag@sha256:<64 hex>): see ${SBOM_ISSUE}"
}

sha256_of() {
  # sha256:<hex> of a file, the form /version's sbom_digest takes
  python3 -c '
import hashlib, sys
digest = hashlib.sha256()
with open(sys.argv[1], "rb") as handle:
    for chunk in iter(lambda: handle.read(1 << 20), b""):
        digest.update(chunk)
print("sha256:" + digest.hexdigest())
' "$1"
}

sbom_is_spdx() {
  # an SPDX JSON document that lists at least one package; anything else,
  # empty output included, is no SBOM
  [[ -s ${1:-} ]] || return 1
  python3 -c '
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        doc = json.load(handle)
except (OSError, ValueError):
    sys.exit(1)
packages = doc.get("packages") if isinstance(doc, dict) else None
spdx = isinstance(doc, dict) and str(doc.get("spdxVersion", "")).startswith("SPDX-")
sys.exit(0 if spdx and isinstance(packages, list) and packages else 1)
' "$1"
}

release_sbom_path() {
  # <releases>/<commit>/api-<image id>.spdx.json: one SBOM per built image, in
  # its commit's release directory. Both parts are checked, so neither can
  # steer the path.
  local image_id=${1:-}
  [[ $INTAKE_GIT_SHA =~ ^[0-9a-f]{40}$ ]] || return 1
  [[ $image_id =~ ^sha256:[0-9a-f]{64}$ ]] || return 1
  printf '%s/%s/api-%s.spdx.json\n' "$RELEASES_DIR" "$INTAKE_GIT_SHA" "${image_id#sha256:}"
}

version_verdict() {
  # version_verdict <deployed sha> <sha256 of the SBOM on disk> < /version
  # body. Prints one line. Exits 1 unless every stamp is real and each names
  # what was deployed. "dev" is what VersionInfo reports for a missing stamp.
  python3 -c '
import json, sys
try:
    v = json.load(sys.stdin)
except ValueError:
    print("not JSON")
    sys.exit(1)
if not isinstance(v, dict):
    print("not a JSON object")
    sys.exit(1)
expected = {"git_sha": sys.argv[1], "sbom_digest": sys.argv[2]}
named = {"git_sha": "the deployed commit", "sbom_digest": "the sha256 of the SBOM on disk"}
problems = []
for field in ("git_sha", "built_at", "sbom_digest"):
    value = v.get(field)
    if value in (None, "", "dev"):
        problems.append("%s is not stamped (%r)" % (field, value))
    elif field in expected and value != expected[field]:
        problems.append("%s %r is not %s, %s" % (field, value, named[field], expected[field]))
if problems:
    print("; ".join(problems))
    sys.exit(1)
print("git_sha %s, built_at %s, sbom_digest %s" % (v["git_sha"], v["built_at"], v["sbom_digest"]))
' "$1" "$2"
}

require_sms_with_app_attest() {
  # With an Apple team id, a genuine iOS app passes attestation and the API
  # goes on to deliver the code. Without all three SMS keys it has no vendor
  # to deliver with, and would answer "sent" having sent nothing. Without a
  # team id no request passes attestation, so the SMS keys may be anything.
  # Names only: no value reaches the message.
  local key missing=()
  [[ -n $(env_get "$ENV_FILE" INTAKE_APP_ATTEST_TEAM_ID) ]] || return 0
  for key in "${SMS_KEYS[@]}"; do
    [[ -n $(env_get "$ENV_FILE" "$key") ]] || missing+=("$key")
  done
  if ((${#missing[@]} > 0)); then
    die "INTAKE_APP_ATTEST_TEAM_ID is set, but $ENV_FILE has no value for ${missing[*]}: a verified device would be told a code was sent that nobody sent. Set all three SMS keys, or empty the team id (${ATTEST_SMS_RUNBOOK})"
  fi
}

# --- host memory -------------------------------------------------------------------------

# OpenBao 2.6 dropped mlock, so an unsealed server's keys can be paged out.
# This tier runs only where active swap never reaches a disk in the clear: no
# swap, zram (compressed RAM), or a device with dm-crypt at or beneath it. A
# swap file is refused, because nothing here can prove its filesystem is
# encrypted. A check that cannot run refuses too.
SWAP_RUNBOOK='docs/runbooks/staging.md, section "Host memory: swap off or encrypted"'

swap_area_is_encrypted() {
  local device=$1 kind=$2
  [[ $kind == partition ]] || return 1
  [[ $device =~ ^/dev/zram[0-9]+$ ]] && return 0
  command -v lsblk >/dev/null 2>&1 ||
    die "missing tool: lsblk (util-linux): cannot tell whether swap on $device is encrypted (${SWAP_RUNBOOK})"
  # --inverse lists the device, then every device beneath it (LVM on dm-crypt)
  lsblk --list --noheadings --inverse --output TYPE "$device" 2>/dev/null |
    awk '$1 == "crypt" { found = 1 } END { exit !found }'
}

require_no_unencrypted_swap() {
  local listing device kind exposed=()
  command -v swapon >/dev/null 2>&1 ||
    die "missing tool: swapon (util-linux): cannot tell whether swap is active (${SWAP_RUNBOOK})"
  listing=$(swapon --show=NAME,TYPE --noheadings --raw) ||
    die "swapon --show failed: cannot tell whether swap is active (${SWAP_RUNBOOK})"
  while read -r device kind; do
    [[ -n $device ]] || continue
    swap_area_is_encrypted "$device" "$kind" || exposed+=("$device ($kind)")
  done <<<"$listing"
  if ((${#exposed[@]} > 0)); then
    die "active swap is not encrypted: ${exposed[*]}. OpenBao can no longer lock its memory, so its keys could be paged to disk in the clear. Turn swap off or encrypt it, then re-run (${SWAP_RUNBOOK})"
  fi
  log "swap: none active, or every active area is encrypted"
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
  # Validate that every template key but the operator's has a value. Shell
  # variables are set only for the values the scripts read; secrets are never
  # exported.
  [[ -f $ENV_FILE ]] || die "$ENV_FILE is missing: run ./init.sh first"
  local key
  while IFS= read -r key; do
    is_operator_key "$key" && continue
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

# --- the release SBOM (INT-352, audit F18) ------------------------------------------------

build_api_image() {
  # The only build in this tier. The value is bound to this one call and never
  # exported (see SBOM_DIGEST_DURING_BUILD). A build creates no container, and
  # every later compose call runs with stamp_sbom's digest or not at all.
  INTAKE_SBOM_DIGEST="$SBOM_DIGEST_DURING_BUILD" compose build api
}

api_image_id() {
  # the image compose built for this commit, by id
  local id
  id=$(docker image inspect --format '{{.Id}}' "$API_IMAGE_REPO:$INTAKE_GIT_SHA" 2>/dev/null) || return 1
  [[ $id =~ ^sha256:[0-9a-f]{64}$ ]] || return 1
  printf '%s\n' "$id"
}

run_syft() {
  # run_syft <image> <work dir>: syft reads a `docker image save` archive of
  # the image, mounted read-only, with no network and no capabilities. It
  # never gets the docker socket. The SBOM lands at <work dir>/sbom.spdx.json.
  # Called under `||`, so errexit is off here and every step returns its own
  # failure.
  local image=$1 work=$2
  docker image save --output "$work/image.tar" "$image" || return 1
  mkdir -m 700 "$work/scratch" || return 1
  docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges:true \
    --env SYFT_CHECK_FOR_APP_UPDATE=false --env HOME=/tmp \
    --volume "$work/image.tar:/in/image.tar:ro" --volume "$work/scratch:/tmp" \
    "$SBOM_IMAGE" scan docker-archive:/in/image.tar --output "$SBOM_FORMAT" \
    >"$work/sbom.spdx.json" || return 1
  sbom_is_spdx "$work/sbom.spdx.json"
}

generate_sbom() {
  # generate_sbom <image> <sbom file>: the whole SBOM lands at <sbom file>, or
  # nothing does and the script stops. The work dir sits beside the file, so
  # the final move is atomic, and it is removed either way.
  local image=$1 out=$2 work rc=0
  require_sbom_image "$SBOM_IMAGE"
  work="${out%/*}/.sbom.$$.${RANDOM}"
  mkdir -m 700 "$work" || die "could not create $work"
  run_syft "$image" "$work" || rc=$?
  if ((rc == 0)); then
    mv -f "$work/sbom.spdx.json" "$out" || rc=$?
  fi
  rm -rf "$work"
  ((rc == 0)) ||
    die "syft (${SBOM_IMAGE%%@*}) wrote no SPDX SBOM of $image: refusing to run an image /version cannot name (audit F18, ${SBOM_ISSUE})"
}

export_sbom_digest() {
  local digest
  digest=$(sha256_of "$SBOM_FILE") || die "could not hash $SBOM_FILE"
  [[ $digest =~ ^sha256:[0-9a-f]{64}$ ]] || die "the SBOM digest is malformed: $digest"
  INTAKE_SBOM_DIGEST=$digest
  export INTAKE_SBOM_DIGEST
}

stamp_sbom() {
  # init.sh and deploy.sh, after build_api_image: the SBOM of the image just
  # built, then INTAKE_SBOM_DIGEST = its sha256. An image that already has
  # its SBOM keeps it, so a re-run on the same commit changes nothing.
  local dir
  API_IMAGE_ID=$(api_image_id) || die "no api image for ${INTAKE_GIT_SHA}: build_api_image runs first"
  SBOM_FILE=$(release_sbom_path "$API_IMAGE_ID") || die "no release path for ${INTAKE_GIT_SHA}"
  dir=${SBOM_FILE%/*}
  (umask 077 && mkdir -p "$dir") || die "could not create $dir"
  if sbom_is_spdx "$SBOM_FILE"; then
    log "SBOM of ${API_IMAGE_ID} already written: ${SBOM_FILE}"
  else
    generate_sbom "$API_IMAGE_REPO:$INTAKE_GIT_SHA" "$SBOM_FILE"
    log "SBOM of ${API_IMAGE_ID} written: ${SBOM_FILE}"
  fi
  export_sbom_digest
}

stamp_sbom_from_disk() {
  # smoke.sh: the SBOM deploy.sh wrote for this commit's image. It never
  # writes one: with no SBOM on disk there is nothing to check against.
  API_IMAGE_ID=$(api_image_id) || die "no api image for ${INTAKE_GIT_SHA}: run ./deploy.sh"
  SBOM_FILE=$(release_sbom_path "$API_IMAGE_ID") || die "no release path for ${INTAKE_GIT_SHA}"
  sbom_is_spdx "$SBOM_FILE" || die "no SBOM on disk for ${API_IMAGE_ID} (${SBOM_FILE}): run ./deploy.sh"
  log "SBOM of ${API_IMAGE_ID}: ${SBOM_FILE}"
  export_sbom_digest
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

# --- the admin tier (INT-421) -----------------------------------------------------------

build_admin_web_image() {
  # The console image, built from the same commit as the api. compose
  # interpolates the whole file, so this call needs the build-time value too.
  INTAKE_SBOM_DIGEST="$SBOM_DIGEST_DURING_BUILD" compose build admin-web
}

build_keycloak_image() {
  # INT-378: INT-390's Keycloak plus the WebAuthn session-notes provider. The
  # build compiles and tests the provider and refuses a jar that is not
  # byte-identical to infra/keycloak/providers/webauthn-session-notes.sha256
  # (Dockerfile.keycloak). It runs before anything restarts, so a refused
  # build leaves the running tier as it was.
  INTAKE_SBOM_DIGEST="$SBOM_DIGEST_DURING_BUILD" compose build keycloak
}

ensure_keycloak_database() {
  # Keycloak's own role and database, both created only if absent. The role's
  # password is re-applied on every run. The SQL travels on stdin with
  # statement logging off, so the password never reaches argv or a log, as
  # with rotate_role_passwords.
  local value sql
  value=$(env_get "$ENV_FILE" KEYCLOAK_DB_PASSWORD)
  [[ $value =~ ^[0-9a-f]{64}$ ]] || die "KEYCLOAK_DB_PASSWORD is not a generated secret: run ./init.sh"
  sql="SET log_statement = 'none'; SET log_min_error_statement = 'panic';"$'\n'
  sql+="DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${KEYCLOAK_DB}') THEN"
  sql+=" CREATE ROLE ${KEYCLOAK_DB} LOGIN; END IF; END \$\$;"$'\n'
  sql+="ALTER ROLE ${KEYCLOAK_DB} PASSWORD '${value}';"$'\n'
  sql+="SELECT 'CREATE DATABASE ${KEYCLOAK_DB} OWNER ${KEYCLOAK_DB}'"
  sql+=" WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${KEYCLOAK_DB}') \\gexec"$'\n'
  printf '%s' "$sql" | compose exec -T postgres psql -v ON_ERROR_STOP=1 -q -U intake -d intake >/dev/null
  log "keycloak database and role present"
}

ensure_jwks_file() {
  # Every api container mounts $JWKS_FILE, migrations and the release gate
  # included, so it must exist before the first one is created. Absent, docker
  # would create a directory in its place. The empty key set is the console's
  # closed state: the API loads no key and answers 503 on every /admin route.
  if [[ ! -f $JWKS_FILE ]]; then
    printf '{"keys": []}\n' >"$JWKS_FILE"
    chmod 644 "$JWKS_FILE"
    log "no realm key set mirrored yet: the admin console stays closed (503) until mirror_keycloak_jwks"
  fi
}

jwks_is_usable() {
  # a JWKS document with at least one RSA signing key, the only kind the
  # API's verifier loads (RS256)
  python3 -c '
import json, sys
try:
    doc = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
keys = doc.get("keys") if isinstance(doc, dict) else None
ok = isinstance(keys, list) and any(
    isinstance(k, dict) and k.get("kty") == "RSA" and k.get("use") in (None, "sig")
    and k.get("alg") in (None, "RS256") and k.get("n") and k.get("e")
    for k in keys
)
sys.exit(0 if ok else 1)
'
}

# The live realm's WebAuthn step (INT-378). Keycloak imports a realm once, so
# the host's realm still runs the stock webauthn-authenticator, whose tokens
# carry no aaguid or credential_id and are refused by the API's admin gate.
# keycloak/staff_flow.py makes the live `staff second factor` subflow match the
# committed realm. It is idempotent, it fails unless the flow ends in the
# committed state, and it changes nothing else. The OTP alternative stays: that
# choice is the owner's (INT-389). It runs in a one-off api container (the
# Keycloak image has no HTTP client), and the bootstrap admin password travels on
# stdin, never in an argv, an environment or a log. `check` only reads.
staff_flow() {
  local mode=${1:-} value script
  case $mode in
  apply) set -- ;;
  check) set -- --check ;;
  *) die "usage: staff_flow apply|check" ;;
  esac
  value=$(env_get "$ENV_FILE" KEYCLOAK_ADMIN_PASSWORD)
  [[ $value =~ ^[0-9a-f]{64}$ ]] || die "KEYCLOAK_ADMIN_PASSWORD is not a generated secret: run ./init.sh"
  script=$(<"$STAGING_DIR/keycloak/staff_flow.py")
  printf '%s\n' "$value" | compose run --rm --no-deps -T api python -c "$script" \
    "$@" http://keycloak:8080 "$KEYCLOAK_REALM" "$KEYCLOAK_BOOTSTRAP_ADMIN"
}

ensure_staff_webauthn_notes() {
  staff_flow apply || die "the live realm's WebAuthn step is not the session-notes provider; staff sign-in stays refused"
}

# shellcheck disable=SC2034 # JWKS_CHANGED is read by deploy.sh after its final up
mirror_keycloak_jwks() {
  # The realm's public key set, read over the internal network by a one-off
  # api container (Keycloak's image carries no HTTP client) and written beside
  # the host's state. Public keys only. A key rotation is the next deploy. If
  # the fetch fails or returns no usable key, the previous file stays, and the
  # console stays as it was: closed on the first deploy.
  #
  # The file is rewritten in place, never moved over. An api container binds
  # the file's inode, so a moved-in replacement would never reach it. The API
  # reads the key set once, at start, so JWKS_CHANGED=1 tells deploy.sh to
  # restart the api after its final up.
  local doc
  JWKS_CHANGED=0
  # shellcheck disable=SC2016
  doc=$(compose run --rm --no-deps -T api python -c '
import sys, urllib.request
url = "http://keycloak:8080/realms/" + sys.argv[1] + "/protocol/openid-connect/certs"
with urllib.request.urlopen(url, timeout=10) as response:
    sys.stdout.write(response.read().decode("utf-8"))
' "$KEYCLOAK_REALM" 2>/dev/null) || doc=""
  if ! jwks_is_usable <<<"$doc"; then
    log "WARNING: realm ${KEYCLOAK_REALM} served no usable key set; the admin console keeps its previous state"
    return 0
  fi
  if [[ -f $JWKS_FILE ]] && [[ $(<"$JWKS_FILE") == "$doc" ]]; then
    log "realm ${KEYCLOAK_REALM} key set unchanged"
    return 0
  fi
  printf '%s\n' "$doc" >"$JWKS_FILE"
  chmod 644 "$JWKS_FILE"
  JWKS_CHANGED=1
  log "realm ${KEYCLOAK_REALM} key set mirrored to $JWKS_FILE"
}

# --- the telemetry tier (INT-481) --------------------------------------------------------

# Deploy markers. deploy.sh writes one node-exporter textfile per stage of a
# deploy; node-exporter reads the directory read-only and Prometheus keeps the
# one family, deploy_event_timestamp_seconds{head_sha,stage}, which the staff
# Grafana draws on every dashboard. A marker holds a commit sha and a time,
# nothing secret, so the directory is 0755 and each file 0644.
OBS_TEXTFILE_DIR="${INTAKE_OBS_TEXTFILE_DIR:-/var/lib/intake-obs/textfile}"
DEPLOY_STAGES=(started completed)
# Every service of compose.obs.yaml that reads a bind-mounted config file. Like
# caddy, each is recreated on every deploy, so it reads this release's files.
OBS_CONFIGURED_SERVICES=(prometheus alertmanager blackbox-exporter grafana oauth2-proxy-grafana)

ensure_obs_textfile_dir() {
  mkdir -p "$OBS_TEXTFILE_DIR"
  # root on the host (deploy.sh runs as root); a test runs this unprivileged
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    chown root:root "$OBS_TEXTFILE_DIR"
  fi
  chmod 755 "$OBS_TEXTFILE_DIR"
}

deploy_marker_line() {
  # The one exposition line of a marker. It refuses anything but a full commit
  # sha, a known stage and a unix time, so no other value reaches a label.
  local sha=$1 stage=$2 at=$3 known=0 candidate
  [[ $sha =~ ^[0-9a-f]{40}$ ]] || return 1
  for candidate in "${DEPLOY_STAGES[@]}"; do
    [[ $stage == "$candidate" ]] && known=1
  done
  ((known == 1)) || return 1
  [[ $at =~ ^[0-9]+$ ]] || return 1
  printf 'deploy_event_timestamp_seconds{head_sha="%s",stage="%s"} %s\n' "$sha" "$stage" "$at"
}

write_deploy_marker() {
  # write_deploy_marker <stage>: atomic, through a temporary name node-exporter
  # ignores and a rename. A new deploy's `started` removes the last deploy's
  # `completed`, so a started with no completed is a deploy that stopped.
  local stage=$1 line tmp
  line=$(deploy_marker_line "$INTAKE_GIT_SHA" "$stage" "$(date -u +%s)") ||
    die "refusing a deploy marker for '${stage}' at '${INTAKE_GIT_SHA}'"
  ensure_obs_textfile_dir
  if [[ $stage == started ]]; then
    rm -f "$OBS_TEXTFILE_DIR/deploy-completed.prom"
  fi
  tmp="$OBS_TEXTFILE_DIR/.deploy-${stage}.tmp"
  printf '%s\n' "$line" >"$tmp"
  chmod 644 "$tmp"
  mv -f "$tmp" "$OBS_TEXTFILE_DIR/deploy-${stage}.prom"
  log "deploy marker: ${stage} ${INTAKE_GIT_SHA}"
}

recreate_telemetry_tier() {
  # The telemetry tier reads its configuration from this release's files. Its
  # data volumes survive the recreate, and Prometheus misses at most a scrape.
  compose up -d --no-build --no-deps --force-recreate --wait "${OBS_CONFIGURED_SERVICES[@]}"
}

# The staff Grafana's Keycloak client (keycloak/grafana_client.py). Keycloak
# imports a realm once, so a host whose realm predates INT-481 has no `grafana`
# client. This creates it, or brings it back to the committed shape, and fails
# unless it ends there. Like staff_flow it runs in a one-off api container, and
# the bootstrap admin password and the client secret travel on stdin, never in
# an argv, an environment or a log. `check` only reads.
grafana_client() {
  local mode=${1:-} password secret script
  case $mode in
  apply) set -- ;;
  check) set -- --check ;;
  *) die "usage: grafana_client apply|check" ;;
  esac
  password=$(env_get "$ENV_FILE" KEYCLOAK_ADMIN_PASSWORD)
  [[ $password =~ ^[0-9a-f]{64}$ ]] || die "KEYCLOAK_ADMIN_PASSWORD is not a generated secret: run ./init.sh"
  secret=$(env_get "$ENV_FILE" INTAKE_GRAFANA_CLIENT_SECRET)
  [[ $secret =~ ^[0-9a-f]{64}$ ]] || die "INTAKE_GRAFANA_CLIENT_SECRET is not a generated secret: run ./init.sh"
  script=$(<"$STAGING_DIR/keycloak/grafana_client.py")
  printf '%s\n%s\n' "$password" "$secret" | compose run --rm --no-deps -T api python -c "$script" \
    "$@" http://keycloak:8080 "$KEYCLOAK_REALM" "$KEYCLOAK_BOOTSTRAP_ADMIN" "$STAGING_HOSTNAME"
}

ensure_grafana_client() {
  grafana_client apply || die "the live realm's grafana client is not in the committed shape; the staff Grafana stays closed"
}

prom_value() {
  # prom_value <PromQL>: the first sample's value of an instant query, asked
  # inside the prometheus container (Prometheus publishes no port), or nothing
  local url
  url="http://127.0.0.1:9090/api/v1/query?query=$(python3 -c '
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=""))
' "$1")"
  compose exec -T prometheus wget -qO- "$url" 2>/dev/null | python3 -c '
import json, sys
try:
    result = json.load(sys.stdin)["data"]["result"]
except (ValueError, KeyError, TypeError):
    sys.exit(1)
print(result[0]["value"][1] if result else "")
'
}

wait_prom_value() {
  # wait_prom_value <PromQL> <value>: two minutes for a fresh scrape to say so
  local _
  for _ in $(seq 1 24); do
    [[ $(prom_value "$1" || true) == "$2" ]] && return 0
    sleep 5
  done
  return 1
}

# --- the release gate (INT-187) ---------------------------------------------------------

# The console's deploy freeze and the SLO error budget, decided by one rule
# (intake_platform.release_freeze.release_verdict). The shell does not
# re-implement it: the gate runs in a one-off container of the image just
# built, on the project network, with the api's own environment, and reads the
# freeze from the deployment's Redis. Exit 0: allowed. Exit 3: refused, and its
# lines say why. Anything else: the gate did not run, which refuses too.
RELEASE_GATE_EXIT_REFUSED=3
FREEZE_RUNBOOK='docs/runbooks/staging.md, section "Deploy freeze", and docs/runbooks/deploy-freeze.md'

require_release_not_frozen() {
  local output rc=0 line
  output=$(compose run --rm --no-deps -T api python -m intake_api.admin.release_gate 2>&1) || rc=$?
  while IFS= read -r line; do
    if [[ -n $line ]]; then log "$line"; fi
  done <<<"$output"
  if ((rc == 0)); then
    return 0
  fi
  if ((rc == RELEASE_GATE_EXIT_REFUSED)); then
    die "deploys are frozen or the freeze cannot be read: nothing was restarted (${FREEZE_RUNBOOK})"
  fi
  die "the release gate did not run (exit ${rc}): refusing to deploy without it (${FREEZE_RUNBOOK})"
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
