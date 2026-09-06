#!/usr/bin/env bash
# INT-203 — fetch and verify the Coraza WAF plugin named in the edge policy.
#
#   make edge-plugin
#
# The OWASP CRS the acceptance names ships *inside* this artefact, so "which
# ruleset is deployed" is answered by a hash rather than by a directory
# listing. The URL and both sha256 values come from
# infra/security/edge/edge-policy.yaml and are never arguments: a downloader
# that takes a URL is a downloader that can be pointed somewhere else.
#
# The shape is `make deid-model`'s: verify before unpacking, never after, and
# leave the artefact under .cache/ rather than in git. Nothing is fetched when
# the module is already present and hashes correctly, so the target is cheap to
# re-run and safe to depend on.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
POLICY="${REPO}/infra/security/edge/edge-policy.yaml"
DEST="${REPO}/.cache/edge/plugins-local/src/github.com/corazawaf/coraza-http-wasm"

read_policy() {
  uv run --project "${REPO}" python -c "
import sys, yaml
policy = yaml.safe_load(open('${POLICY}', encoding='utf-8'))
sys.stdout.write(str(policy['waf'][sys.argv[1]]))
" "$1"
}

sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

URL="$(read_policy plugin_url)"
ZIP_SHA="$(read_policy plugin_sha256)"
WASM_SHA="$(read_policy wasm_sha256)"

if [[ -f "${DEST}/coraza-http-wasm.wasm" ]] &&
  [[ "$(sha256_of "${DEST}/coraza-http-wasm.wasm")" == "${WASM_SHA}" ]]; then
  echo "coraza plugin present and verified (${WASM_SHA:0:16}...)"
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -r "${TMP}"' EXIT

echo "fetching ${URL}"
curl -fsSL -o "${TMP}/plugin.zip" "${URL}"

GOT="$(sha256_of "${TMP}/plugin.zip")"
if [[ "${GOT}" != "${ZIP_SHA}" ]]; then
  echo "sha256 mismatch for the plugin archive" >&2
  echo "  expected ${ZIP_SHA}" >&2
  echo "  got      ${GOT}" >&2
  echo "Nothing was unpacked. Either the release was re-cut or the download was" >&2
  echo "tampered with; both are decisions for a human, not a retry." >&2
  exit 1
fi

mkdir -p "${DEST}"
unzip -oq "${TMP}/plugin.zip" -d "${DEST}"

GOT_WASM="$(sha256_of "${DEST}/coraza-http-wasm.wasm")"
if [[ "${GOT_WASM}" != "${WASM_SHA}" ]]; then
  echo "the archive verified but the module inside it did not: ${GOT_WASM}" >&2
  rm -r "${DEST}"
  exit 1
fi

# The licence blob travels inside the artefact; hashing it here is what makes
# the registry row re-checkable rather than a claim (files/03 §4.9.0 rule 3).
echo "coraza plugin verified and unpacked to ${DEST#"${REPO}/"}"
echo "  archive ${ZIP_SHA}"
echo "  module  ${WASM_SHA}"
echo "  licence $(sha256_of "${DEST}/LICENSE")"
