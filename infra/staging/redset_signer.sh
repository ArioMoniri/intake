#!/usr/bin/env bash
# INT-465: the synthetic-only test key that signs the red rule set.
#
# SYNTHETIC PATIENTS ONLY. Owner decision, 3 Oct 2026, read with D18: a test
# key signs the red rule set for the synthetic AWS test server only
# (i-0e489e48739f5de98). A licensed physician's review is still required
# before any real patient, and every non-synthetic tenant rejects this key
# (intake_platform.red_signature). The production signing path is cosign (INT-058)
# and nothing here touches it.
#
# Run as root on the staging host:
#   ./redset_signer.sh setup        once: key, policy, scoped token
#   ./redset_signer.sh sign <b64>   sign one canonical payload
#
# setup reads the OpenBao root token exactly once, inside this shell. With it,
# it creates:
#   - the Transit key: ed25519, exportable=false, allow_plaintext_backup=false;
#   - the policy redset-synthetic-signer: sign on that key and nothing else
#     (openbao/redset-synthetic-signer-policy.hcl);
#   - an orphan periodic token with only that policy. Its id is generated here
#     and written to a root-only file, then handed to OpenBao on stdin.
# It prints only the key's public half, which is not a secret.
#
# sign uses only that scoped token, and prints only the signature and the key
# version. No token ever reaches argv, stdout or a log. A token reaches the bao
# CLI only through the docker CLI's environment (lib.sh bao_as).
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The deployed tier's helpers. When this script is copied to the host on its
# own, INTAKE_STAGING_LIB points at the deployed lib.sh.
# shellcheck source=SCRIPTDIR/lib.sh
source "${INTAKE_STAGING_LIB:-$SELF_DIR/lib.sh}"

REDSET_KEY="redset-synthetic-test"
REDSET_POLICY="redset-synthetic-signer"
REDSET_POLICY_FILE="$SELF_DIR/openbao/redset-synthetic-signer-policy.hcl"
REDSET_TOKEN_FILE="$STATE_DIR/redset-signer.token"

prepare_tier() {
  # As smoke.sh does: compose interpolates the deployed release's stamps, so
  # every compose call needs them (bao_as finds the openbao container through
  # one). load_env reads the root-only env file and exports no secret.
  require_root
  load_env
  stamp_revision
  stamp_sbom_from_disk
}

public_half() {
  # Prints the public half, and stops on a key that is not what setup creates:
  # an existing key is never trusted on its name alone.
  python3 -c '
import json, sys
key = json.load(sys.stdin)["data"]
if key["type"] != "ed25519" or key["exportable"] or key["allow_plaintext_backup"]:
    sys.exit("the existing key is not ed25519, non-exportable, without plaintext backup")
latest = str(key["latest_version"])
print(json.dumps({
    "name": key["name"],
    "type": key["type"],
    "exportable": key["exportable"],
    "allow_plaintext_backup": key["allow_plaintext_backup"],
    "latest_version": key["latest_version"],
    "public_key": key["keys"][latest]["public_key"],
}, indent=2))'
}

setup_signer() {
  prepare_tier
  [[ -f $REDSET_POLICY_FILE ]] || die "missing $REDSET_POLICY_FILE"
  local root token_id
  root=$(init_field root_token)
  if ! bao_as "$root" read -format=json "transit/keys/${REDSET_KEY}" >/dev/null 2>&1; then
    bao_as "$root" write "transit/keys/${REDSET_KEY}" \
      type=ed25519 exportable=false allow_plaintext_backup=false >/dev/null
    log "test key ${REDSET_KEY} created (ed25519, non-exportable)"
  fi
  bao_as "$root" policy write "$REDSET_POLICY" - <"$REDSET_POLICY_FILE" >/dev/null
  if [[ ! -s $REDSET_TOKEN_FILE ]]; then
    (
      umask 077
      gen_secret >"$REDSET_TOKEN_FILE"
    )
    chmod 600 "$REDSET_TOKEN_FILE"
    token_id=$(cat "$REDSET_TOKEN_FILE")
    # The token carries the signer policy plus OpenBao's built-in `default`,
    # exactly like the API token (openbao/intake-api-policy.hcl): `default`
    # is what lets a token look itself up and renew itself, which sign does.
    printf '%s' "$token_id" | bao_as "$root" write -format=json \
      auth/token/create-orphan id=- policies="$REDSET_POLICY" period=768h \
      display_name=redset-synthetic-signer >/dev/null
    log "scoped signing token minted (policy ${REDSET_POLICY}, periodic 768h, orphan)"
  fi
  bao_as "$root" read -format=json "transit/keys/${REDSET_KEY}" | public_half
}

sign_payload() {
  prepare_tier
  local input=$1 scoped
  [[ $input =~ ^[A-Za-z0-9+/]+=*$ ]] || die "the payload must be base64"
  [[ -s $REDSET_TOKEN_FILE ]] || die "no scoped signing token: run setup first"
  scoped=$(cat "$REDSET_TOKEN_FILE")
  # A periodic token lapses after 768h unused: renew it first, and stop with a
  # clear message rather than a bare permission error if it has lapsed.
  bao_as "$scoped" token renew >/dev/null 2>&1 ||
    die "the scoped signing token has lapsed: an operator re-runs setup (docs/runbooks/red-rule-set-signing.md)"
  bao_as "$scoped" write -format=json "transit/sign/${REDSET_KEY}" input="$input" |
    python3 -c '
import json, sys
data = json.load(sys.stdin)["data"]
print(json.dumps({"signature": data["signature"], "key_version": data["key_version"]}))'
}

case "${1:-}" in
  setup) setup_signer ;;
  sign) sign_payload "${2:?usage: redset_signer.sh sign <base64 payload>}" ;;
  *) die "usage: redset_signer.sh setup | sign <base64 payload>" ;;
esac
