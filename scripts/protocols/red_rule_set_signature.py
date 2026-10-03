"""INT-465: build, assemble and check the synthetic-only test-key signature.

The private key never leaves OpenBao on the synthetic host, so signing has three steps:

1. ``payload`` (here) writes the canonical payload bytes for the committed rule set and
   prints them as base64. Those bytes are the life-threat set's digest, the generic
   RED's digest and the served rule ids (``active`` only).
2. ``infra/staging/redset_signer.sh sign <base64>`` runs on the host with the scoped
   token, and prints the Transit signature and the key version.
3. ``assemble`` (here) turns that signature into the committed envelope. It verifies
   the envelope under a synthetic tenant against the committed public key before
   writing anything.

``verify`` checks the committed envelope for one tenant kind. It exits non-zero for
every kind but ``synthetic``, which is the point.

Usage:
    uv run python scripts/protocols/red_rule_set_signature.py payload --out <file>
    uv run python scripts/protocols/red_rule_set_signature.py assemble --payload <file> \
        --key-id redset-synthetic-test@1 --transit '<signature from the host>'
    uv run python scripts/protocols/red_rule_set_signature.py verify --tenant-kind synthetic
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

from intake_platform.red_signature import (
    COMMITTED_SIGNATURE,
    COMMITTED_TRUST_REGISTRY,
    KeyScope,
    RedRuleSetPayload,
    RedRuleSetSignature,
    RedSignatureRefused,
    canonical_payload_bytes,
    load_signature,
    load_trust_registry,
    verify_red_rule_set,
)
from intake_platform.red_tenant import TenantKind, TenantRedConfig
from protocols.compile.life_threat import load_life_threat_set
from protocols.types import RuleStatus

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = "files/protocols/base.life_threat.yaml"
GENERIC = "packages/protocols/generic/generic_red.yaml"
_TRANSIT = re.compile(r"^[a-z]+:v([1-9][0-9]*):([A-Za-z0-9+/]+=*)$")


def served_rule_ids(life_threat: Path) -> tuple[str, ...]:
    """The rules a signed set serves: the ``active`` ones. A draft is never served."""
    rules = load_life_threat_set(life_threat).rules
    return tuple(sorted(e.rule.id for e in rules if e.rule.status is RuleStatus.ACTIVE))


def build_payload(life_threat: str = LIFE_THREAT, generic: str = GENERIC) -> RedRuleSetPayload:
    return RedRuleSetPayload.build(
        scope=KeyScope.SYNTHETIC_TEST,
        life_threat_path=life_threat,
        life_threat_bytes=(REPO / life_threat).read_bytes(),
        generic_red_path=generic,
        generic_red_bytes=(REPO / generic).read_bytes(),
        served_rule_ids=served_rule_ids(REPO / life_threat),
    )


def envelope_from_transit(
    payload: RedRuleSetPayload, *, key_id: str, transit: str
) -> RedRuleSetSignature:
    """``<prefix>:v<N>:<base64>`` from Transit, checked against ``key_id``'s version."""
    match = _TRANSIT.match(transit.strip())
    if match is None:
        raise ValueError("not a Transit signature")
    version, signature = match.groups()
    if not key_id.endswith(f"@{version}"):
        raise ValueError(f"the signature is key version {version}, not {key_id}")
    return RedRuleSetSignature(payload=payload, key_id=key_id, signature=signature)


def verify_committed(
    kind: TenantKind, signature_path: Path = COMMITTED_SIGNATURE
) -> RedSignatureRefused | None:
    signature = load_signature(signature_path)
    try:
        verify_red_rule_set(
            signature,
            registry=load_trust_registry(COMMITTED_TRUST_REGISTRY),
            tenant=TenantRedConfig(kind=kind),
            life_threat_bytes=(REPO / signature.payload.life_threat.path).read_bytes(),
            generic_red_bytes=(REPO / signature.payload.generic_red.path).read_bytes(),
            served_rule_ids=served_rule_ids(REPO / signature.payload.life_threat.path),
        )
    except RedSignatureRefused as refused:
        return refused
    return None


def _write_envelope(envelope: RedRuleSetSignature, out: Path) -> None:
    body = json.dumps(envelope.model_dump(mode="json"), indent=2, ensure_ascii=False)
    out.write_text(body + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    payload_cmd = commands.add_parser("payload")
    payload_cmd.add_argument("--out", type=Path, required=True)
    assemble = commands.add_parser("assemble")
    assemble.add_argument("--payload", type=Path, required=True)
    assemble.add_argument("--key-id", required=True)
    assemble.add_argument("--transit", required=True)
    assemble.add_argument("--out", type=Path, default=COMMITTED_SIGNATURE)
    verify = commands.add_parser("verify")
    verify.add_argument("--tenant-kind", choices=[k.value for k in TenantKind], required=True)
    args = parser.parse_args(argv)

    if args.command == "payload":
        payload = build_payload()
        raw = canonical_payload_bytes(payload)
        args.out.write_bytes(raw)
        print(base64.b64encode(raw).decode("ascii"))
        return 0
    if args.command == "assemble":
        payload = RedRuleSetPayload.model_validate_json(args.payload.read_bytes())
        envelope = envelope_from_transit(payload, key_id=args.key_id, transit=args.transit)
        verify_red_rule_set(
            envelope,
            registry=load_trust_registry(COMMITTED_TRUST_REGISTRY),
            tenant=TenantRedConfig(kind=TenantKind.SYNTHETIC),
            life_threat_bytes=(REPO / payload.life_threat.path).read_bytes(),
            generic_red_bytes=(REPO / payload.generic_red.path).read_bytes(),
            served_rule_ids=served_rule_ids(REPO / payload.life_threat.path),
        )
        _write_envelope(envelope, args.out)
        print(f"verified and written: {args.out}")
        return 0
    refused = verify_committed(TenantKind(args.tenant_kind))
    print("verified" if refused is None else f"refused: {refused.code}")
    return 0 if refused is None else 1


if __name__ == "__main__":
    sys.exit(main())
