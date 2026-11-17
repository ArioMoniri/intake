"""INT-058: sign a compiled protocol bundle for the synthetic host with the D23 key.

The key is the existing ed25519 OpenBao Transit test key ``redset-synthetic-test``
on the synthetic AWS host (files/00_STATE.md D23; INT-465). Its private half never
leaves OpenBao, so signing has the same three steps as the red rule set
(``scripts/protocols/red_rule_set_signature.py``):

1. ``payload`` (here) writes the canonical ``intake.protocol_bundle.v1`` payload for
   one ``bundle.tar.gz``: its sha256, the scope and the host. It prints it as base64.
2. ``infra/staging/redset_signer.sh sign <base64>`` runs on the host with the scoped
   token, and prints the Transit signature and the key version. Nothing changes there.
3. ``assemble`` (here) turns that signature into ``bundle.tar.gz.synthetic.json``
   beside the archive, after verifying it under a synthetic tenant on that host
   against the committed public key.

Production bundles take the cosign path (``make sign``); this script never touches it.

Usage:
    uv run python scripts/protocols/bundle_signature.py payload --archive <bundle.tar.gz>
    uv run python scripts/protocols/bundle_signature.py assemble --archive <bundle.tar.gz> \
        --key-id redset-synthetic-test@1 --transit '<signature from the host>'
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path

from intake_platform.red_tenant import TenantKind, TenantRedConfig
from intake_voice_runtime.protocol_trust import bundle_trust_for
from protocols.compile.archive import SYNTHETIC_SIGNATURE_SUFFIX, archive_sha256
from protocols.serving.trust import (
    BUNDLE_PAYLOAD_KIND,
    BundleSignatureEnvelope,
    BundleSignaturePayload,
    canonical_bundle_payload,
    load_verified_bundle,
)

#: The synthetic AWS host the signature is bound to (D23), as for the red rule set.
DEPLOYMENT = "i-0e489e48739f5de98"
SCOPE = "synthetic_test"
_TRANSIT = re.compile(r"^[a-z]+:v([1-9][0-9]*):([A-Za-z0-9+/]+=*)$")


def build_payload(archive: Path, *, deployment: str = DEPLOYMENT) -> BundleSignaturePayload:
    return BundleSignaturePayload(
        kind=BUNDLE_PAYLOAD_KIND,
        scope=SCOPE,
        archive_sha256=archive_sha256(archive.read_bytes()),
        deployment=deployment,
    )


def envelope_from_transit(
    payload: BundleSignaturePayload, *, key_id: str, transit: str
) -> BundleSignatureEnvelope:
    """``<prefix>:v<N>:<base64>`` from Transit, checked against ``key_id``'s version."""
    match = _TRANSIT.match(transit.strip())
    if match is None:
        raise ValueError("not a Transit signature")
    version, signature = match.groups()
    if not key_id.endswith(f"@{version}"):
        raise ValueError(f"the signature is key version {version}, not {key_id}")
    return BundleSignatureEnvelope(payload=payload, key_id=key_id, signature=signature)


def write_envelope(envelope: BundleSignatureEnvelope, archive: Path) -> Path:
    out = archive.with_name(archive.name + SYNTHETIC_SIGNATURE_SUFFIX)
    out.write_text(envelope.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    payload_cmd = commands.add_parser("payload")
    payload_cmd.add_argument("--archive", type=Path, required=True)
    assemble = commands.add_parser("assemble")
    assemble.add_argument("--archive", type=Path, required=True)
    assemble.add_argument("--key-id", required=True)
    assemble.add_argument("--transit", required=True)
    args = parser.parse_args(argv)

    payload = build_payload(args.archive)
    if args.command == "payload":
        print(base64.b64encode(canonical_bundle_payload(payload)).decode("ascii"))
        return 0
    envelope = envelope_from_transit(payload, key_id=args.key_id, transit=args.transit)
    out = write_envelope(envelope, args.archive)
    trust = bundle_trust_for(TenantRedConfig(kind=TenantKind.SYNTHETIC, deployment=DEPLOYMENT))
    try:
        verified = load_verified_bundle(args.archive, trust)
    except Exception:
        out.unlink()
        raise
    print(f"verified and written: {out} (resolved_protocol_hash {verified.resolved_protocol_hash})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
