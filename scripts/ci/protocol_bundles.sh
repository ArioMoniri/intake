#!/usr/bin/env bash
# INT-019 — enumerate the protocol-bundle artefacts a tag build signs.
#
# The acceptance asks for "cosign keyless signing + SLSA provenance for images
# and protocol bundles on tags". Keyless signing itself needs the OIDC token
# GitHub Actions mints, so it cannot run on a developer machine; what CAN run
# anywhere, and what this script is, is the half that decides WHAT gets signed
# — and refuses to let a tag be signed over nothing.
#
# `protocols compile` writes one directory of artefacts per pack under
# packages/protocols/dist/<pack_id>/ (packages/protocols/src/protocols/compile
# /bundle.py::write_bundle). Every regular file under the emit root is a
# signing subject; the caller signs each one with `cosign sign-blob` and
# attests it.
#
# FAILS CLOSED ON AN EMPTY EMIT ROOT, which is today's state: no pack compiles
# (every pack is L0 and the life-threat sign-off is empty — HB-C1), so a tag
# cut today would produce a release with no protocol content in it. "Signed
# nothing" and "signed everything" print the same green tick, which is the
# failure mode this exists to prevent.
#
# usage: protocol_bundles.sh [emit-root]   (default packages/protocols/dist)
set -euo pipefail
cd "$(dirname "$0")/../.."

root="${1:-packages/protocols/dist}"

if [[ ! -d "$root" ]]; then
  echo "protocol_bundles: emit root $root does not exist — run" >&2
  echo "  make protocols-compile PACK=<pack_id> VOICE=<voice_id>" >&2
  exit 1
fi

# Dot-files are not artefacts. packages/protocols/dist/ is kept in git by a
# .gitkeep, and counting it as a signing subject is precisely the failure this
# script exists to prevent: a tag would sign one empty marker file and
# report a signed release.
files=$(find "$root" -type f ! -name '.*' | LC_ALL=C sort)

if [[ -z "$files" ]]; then
  echo "protocol_bundles: no protocol bundle under $root — nothing to sign." >&2
  echo "A tag signs the packs it ships; an empty emit root means the compiler" >&2
  echo "refused every pack (HB-C1: no pack has clinical sign-off yet), and a" >&2
  echo "release with no protocol content is not a release worth signing." >&2
  exit 1
fi

printf '%s\n' "$files"
