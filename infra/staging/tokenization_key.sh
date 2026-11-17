#!/usr/bin/env bash
# INT-584 (owner decision D38, 28 Oct 2026): the phone-tokenization key moves
# from this host's env file into OpenBao, carrying the SAME key material
# across, so that no pseudonym changes. The API reads it from
# secret/api/tokenization (field `key`) and from nowhere else
# (intake_api.tokenization_key; CLAUDE.md invariant 14).
#
# SYNTHETIC PATIENTS ONLY, like the rest of this tier.
#
# Run as root on the staging host, from infra/staging:
#   ./tokenization_key.sh           deploy.sh runs it on every deploy
#   ./tokenization_key.sh --init    init.sh runs it once OpenBao is configured
#   ./tokenization_key.sh --probe   the owner's check, any time after
#
# The default mode is idempotent, and it never moves anything it cannot prove:
#   - the env file has the key and OpenBao does not: write the env value to
#     OpenBao (check-and-set, so only where nothing is), read it back with the
#     API's own token, prove the two equal, prove the synthetic probe number's
#     pseudonym unchanged, and only then remove the env copy;
#   - both hold the same key (a run that stopped after the write): prove it
#     again, then remove the env copy;
#   - both hold a key and they differ: refuse loudly, keep both, exit
#     non-zero. Nothing is written or removed. So is a malformed copy on
#     either side, a read the API's token is refused, and a probe that says
#     differ;
#   - only OpenBao holds it (every deploy after the first): check that the
#     API's token reads it, and re-prove the pseudonym against the record;
#   - neither holds it: refuse. A deploy never makes a key, because a new key
#     changes every pseudonym. --init makes a new host's, in OpenBao only,
#     from the kernel CSPRNG; on a host that has one it does what a deploy does.
#
# Equality is proven, never shown:
#   - the key check value: HMAC-SHA-256 of a fixed label under each copy,
#     computed from stdin and compared in a shell variable. Neither the copies
#     nor the digests are printed;
#   - the pseudonym: intake_api.tokenization_probe, in a one-off api container
#     of this release, derives the probe number's pseudonym with the API's own
#     Tokenizer. `record` fingerprints it under the env copy before anything
#     moves, into $PROBE_RECORD (root, 0600, written once); `compare` resolves
#     the key exactly as the API does at boot and says equal or differ.
#
# No value reaches an argument list, a log line, the output or any file but
# OpenBao: the key goes from the env file to python, the bao CLI and the
# container on stdin only. Logs name states, never values. stdout is one word:
# `changed` or `unchanged` (deploy.sh restarts the API on `changed`), or, with
# --probe, `equal` or `differ` (exit 0 only for equal).
set -euo pipefail
# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

TOKENIZATION_KV_PATH="api/tokenization"
# The env-file key the API read before INT-584; this script is its last reader.
TOKENIZATION_ENV_KEY="INTAKE_TOKENIZATION_KEY"
PROBE_RECORD="$STATE_DIR/tokenization-probe.sha256"
TOKENIZATION_RUNBOOK='docs/runbooks/staging.md, section "Phone-tokenization key"'

tokenization_check_value() {
  # tokenization_check_value env|kv. stdin: the key bare (the env file's value)
  # or inside `bao kv get -format=json`. stdout: `absent`, `malformed`, or the
  # key check value (HMAC-SHA-256 of a fixed label under the key's UTF-8
  # bytes, as hex). The caller compares it in a variable and never prints it.
  python3 -c '
import hashlib, hmac, json, re, sys
raw = sys.stdin.read()
if sys.argv[1] == "kv":
    try:
        doc = json.loads(raw)["data"]["data"]
    except (ValueError, KeyError, TypeError):
        doc = None
    if not isinstance(doc, dict):
        print("absent")
        sys.exit()
    key = doc.get("key")
else:
    key = raw.strip()
    if not key:
        print("absent")
        sys.exit()
if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64,256}", key):
    print("malformed")
    sys.exit()
print(hmac.new(key.encode("utf-8"), b"intake.int584.key-check.v1", hashlib.sha256).hexdigest())
' "$1"
}

tokenization_document() {
  # tokenization_document <origin>. stdin: the key. stdout: the KV document,
  # {"key": ..., "origin": ...}, for `bao kv put -`.
  python3 -c '
import json, sys
sys.stdout.write(json.dumps({"key": sys.stdin.read().strip(), "origin": sys.argv[1]}))
' "$1"
}

env_copy() {
  # the env file's copy, on stdout, for a pipe and nothing else
  env_get "$ENV_FILE" "$TOKENIZATION_ENV_KEY"
}

env_unset() {
  # env_unset <file> <key>: every KEY= line removed, atomically, with env_set's
  # temp-file discipline (0600 from birth, beside the target, then mv)
  local file=$1 key=$2 tmp
  tmp="$(dirname "$file")/.env.tmp.$$.${RANDOM}"
  (
    umask 077
    set -o noclobber
    : >"$tmp"
  ) || die "could not create $tmp"
  grep -v "^${key}=" "$file" >"$tmp" || true
  chmod 600 "$tmp"
  mv -f "$tmp" "$file"
}

openbao_check_value() {
  # openbao_check_value <token>: the document as that token reads it, as a
  # check value; `absent` when the read is refused or finds nothing
  (bao_as "$1" kv get -mount=secret -format=json "$TOKENIZATION_KV_PATH" 2>/dev/null || printf '{}') |
    tokenization_check_value kv
}

ensure_release_stamps() {
  # compose interpolates the deployed release's stamps, so every compose call
  # needs them. deploy.sh and init.sh export them; run on its own (--probe, or
  # by hand) this reads them as smoke.sh does. load_env exports no secret.
  if [[ -z ${INTAKE_GIT_SHA:-} || -z ${INTAKE_SBOM_DIGEST:-} ]]; then
    load_env
    stamp_revision
    stamp_sbom_from_disk
  fi
}

probe_in_api() {
  # probe_in_api record|compare: the probe in a one-off container of this
  # release's api image, with the api's own environment, on stdin
  compose run --rm --no-deps -T api python -m intake_api.tokenization_probe "$1"
}

probe_verdict() {
  # stdout: `equal` or `differ`. Anything else the container says is differ.
  local verdict
  verdict=$(probe_in_api compare <"$PROBE_RECORD") || true
  if [[ $verdict == equal ]]; then
    printf 'equal\n'
  else
    printf 'differ\n'
  fi
}

record_before() {
  # The probe number's pseudonym under the env copy, fingerprinted before
  # anything moves. Written once: it is "before the migration", so a later
  # run never replaces it.
  [[ -s $PROBE_RECORD ]] && return 0
  local fingerprint tmp="$PROBE_RECORD.tmp.$$"
  fingerprint=$(env_copy | probe_in_api record) ||
    die "the probe could not fingerprint the env copy: nothing was written or removed (${TOKENIZATION_RUNBOOK})"
  [[ $fingerprint =~ ^[0-9a-f]{64}$ ]] ||
    die "the probe returned no fingerprint: nothing was written or removed (${TOKENIZATION_RUNBOOK})"
  (
    umask 077
    printf '%s\n' "$fingerprint" >"$tmp"
  )
  chmod 600 "$tmp"
  mv -f "$tmp" "$PROBE_RECORD"
  log "tokenization key: the probe number's pseudonym recorded before the move ($PROBE_RECORD, a fingerprint)"
}

require_api_reads() {
  # require_api_reads <check value>: the read the API makes at boot, with the
  # API's own token, yields exactly this key, or the script stops
  local expected=$1 seen
  [[ $expected =~ ^[0-9a-f]{64}$ ]] || die "internal: no key check value to verify against"
  seen=$(openbao_check_value "$(env_get "$ENV_FILE" OPENBAO_TOKEN)")
  [[ $seen == "$expected" ]] ||
    die "the API's own token does not read the same key from OpenBao secret/${TOKENIZATION_KV_PATH} (no read grant in openbao/intake-api-policy.hcl, or another value): the env copy, if any, is kept (${TOKENIZATION_RUNBOOK})"
}

require_probe_equal() {
  [[ $(probe_verdict) == equal ]] ||
    die "the probe number's pseudonym under the key the API reads from OpenBao is not the one recorded before the move ($PROBE_RECORD): the env copy, if any, is kept (${TOKENIZATION_RUNBOOK})"
}

migrate() {
  local mode=$1 root env_cv bao_cv wrote=0
  root=$(init_field root_token)
  # the KV engine and the committed policy, with its read grant on the
  # document, before the API's token is asked to read it
  ensure_secret_kv "$root"
  bao_as "$root" policy write intake-api - <"$STAGING_DIR/openbao/intake-api-policy.hcl" >/dev/null
  env_cv=$(env_copy | tokenization_check_value env)
  bao_cv=$(openbao_check_value "$root")

  [[ $env_cv != malformed ]] ||
    die "${TOKENIZATION_ENV_KEY} in $ENV_FILE is not a well-formed key (64 to 256 lower-case hex characters): nothing was written or removed (${TOKENIZATION_RUNBOOK})"
  [[ $bao_cv != malformed ]] ||
    die "OpenBao secret/${TOKENIZATION_KV_PATH} holds a document that is not a well-formed key: refusing to overwrite it; nothing was written or removed (${TOKENIZATION_RUNBOOK})"

  if [[ $env_cv == absent && $bao_cv == absent ]]; then
    [[ $mode == init ]] ||
      die "no phone-tokenization key in OpenBao secret/${TOKENIZATION_KV_PATH} or in $ENV_FILE. A deploy never makes one, because a new key changes every pseudonym; a new host gets its key from ./init.sh (${TOKENIZATION_RUNBOOK})"
    gen_secret | tokenization_document generated |
      bao_as "$root" kv put -mount=secret -cas=0 "$TOKENIZATION_KV_PATH" - >/dev/null ||
      die "could not write OpenBao secret/${TOKENIZATION_KV_PATH} (check-and-set refused it)"
    require_api_reads "$(openbao_check_value "$root")"
    log "tokenization key: made in OpenBao secret/${TOKENIZATION_KV_PATH} for this new host (origin generated); the API's token reads it (value not shown)"
    printf 'changed\n'
    return 0
  fi

  if [[ $env_cv == absent ]]; then
    local proven=""
    require_api_reads "$bao_cv"
    if [[ -s $PROBE_RECORD ]]; then
      require_probe_equal
      proven=", and the probe number's pseudonym is the one recorded before the move"
    fi
    log "tokenization key: in OpenBao secret/${TOKENIZATION_KV_PATH} only, read by the API's token${proven}; nothing to do"
    printf 'unchanged\n'
    return 0
  fi

  if [[ $bao_cv != absent && $bao_cv != "$env_cv" ]]; then
    die "CONFLICT: OpenBao secret/${TOKENIZATION_KV_PATH} and ${TOKENIZATION_ENV_KEY} in $ENV_FILE hold DIFFERENT keys, and the API would derive different pseudonyms under each. Nothing was written or removed, and both copies are kept. Find which key this host's pseudonyms were made under before anything else (${TOKENIZATION_RUNBOOK})"
  fi

  record_before
  if [[ $bao_cv == absent ]]; then
    env_copy | tokenization_document env_file |
      bao_as "$root" kv put -mount=secret -cas=0 "$TOKENIZATION_KV_PATH" - >/dev/null ||
      die "could not write OpenBao secret/${TOKENIZATION_KV_PATH} (check-and-set refused it: something is already there); the env copy is kept (${TOKENIZATION_RUNBOOK})"
    wrote=1
  fi
  require_api_reads "$env_cv"
  require_probe_equal
  env_unset "$ENV_FILE" "$TOKENIZATION_ENV_KEY"
  log "tokenization key: moved from $ENV_FILE into OpenBao secret/${TOKENIZATION_KV_PATH} (origin env_file); the same key (check value) and the same pseudonym (probe) proven; env copy removed (values not shown)"
  if ((wrote == 1)); then
    printf 'changed\n'
  else
    printf 'unchanged\n'
  fi
}

probe() {
  # The owner's check: equal or differ, and the exit code to match.
  if [[ ! -s $PROBE_RECORD ]]; then
    log "no before-record at $PROBE_RECORD: this host's key was never moved from the env file here, so there is nothing to compare against"
    printf 'differ\n'
    return 2
  fi
  local verdict
  verdict=$(probe_verdict)
  printf '%s\n' "$verdict"
  [[ $verdict == equal ]]
}

main() {
  local mode=deploy
  case ${1:-} in
  --init) mode=init && shift ;;
  --probe) mode=probe && shift ;;
  esac
  [[ $# -eq 0 ]] || die "usage: tokenization_key.sh [--init | --probe]"
  require_root
  ensure_release_stamps
  if [[ $mode == probe ]]; then
    probe
    return
  fi
  migrate "$mode"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
