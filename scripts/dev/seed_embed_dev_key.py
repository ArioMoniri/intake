"""INT-320 (follow-up) — seed the dev embed tenant's launch-ticket signing key.

The embeddable partner handshake signs its launch tickets with a PER-TENANT key
read from OpenBao only (invariant 14): ``services/api`` resolves the key from the
tenant row's ``signing_key_ref`` and, when it is absent, the mint fails closed
(503 ``embed_signing_key_unavailable``). This script seeds that key into the
LOCAL dev OpenBao so the dev flow (mint → launch → consent) works end to end.

DEV ONLY. It refuses to run against ``INTAKE_ENV=prod`` and only ever seeds a
``dev``-tier tenant. The key is generated locally (32 random bytes), written to
OpenBao, and NEVER printed, logged or committed — only the ref path is shown. A
real partner's production key, its custody and its rotation are a human blocker
(HB, INT-320), not this script.

Prerequisites: the dev OpenBao must be reachable and its pointer in the
environment (``OPENBAO_ADDR`` + ``OPENBAO_TOKEN``, read from ``.env`` like the
rest of the dev stack). Run from the repository root::

    python scripts/dev/seed_embed_dev_key.py           # seed missing keys
    python scripts/dev/seed_embed_dev_key.py --force    # rotate existing keys

Idempotent: a tenant whose key is already a valid hex string is left untouched
unless ``--force`` is given.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
# Make this worktree's package srcs importable regardless of which worktree the
# editable install points at (the same shim the test conftests use).
for _src in ("packages/intake_platform/src",):
    _path = str(_REPO_ROOT / _src)
    if _path not in sys.path:
        sys.path.insert(0, _path)

from intake_platform.embed import TenantEmbedRegistry, shipped_registry_path  # noqa: E402
from intake_platform.secrets import SecretsProvider  # noqa: E402

#: 32 bytes = 256 bits of HMAC-SHA256 key material.
_KEY_BYTES = 32


def _has_valid_key(secrets_provider: SecretsProvider, ref: str) -> bool:
    """True when ``ref`` already holds a hex ``signing_key`` (so a re-run is a
    no-op). Any error — path absent, field missing, not hex — means "seed it"."""
    try:
        material = secrets_provider.get_kv(ref)["signing_key"]
        bytes.fromhex(material)
    except Exception:  # noqa: BLE001 — any failure means the key is not usable yet
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the dev embed signing key(s) into OpenBao.")
    parser.add_argument(
        "--force", action="store_true", help="rotate the key even if one is already present"
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=shipped_registry_path(),
        help="embed registry path (default: the committed dev registry)",
    )
    args = parser.parse_args()

    if os.environ.get("INTAKE_ENV", "dev").lower() == "prod":
        print("refusing to run against INTAKE_ENV=prod — dev only (invariant 17)", file=sys.stderr)
        return 2

    registry = TenantEmbedRegistry.from_yaml(args.registry)
    secrets_provider = SecretsProvider.from_env()

    seeded = 0
    for tenant_id in registry.tenant_ids():
        config = registry.resolve(tenant_id)
        if config.tier != "dev":
            # a prod row's key is production custody, never seeded by a script
            print(f"skip {config.signing_key_ref}: tenant is not dev-tier")
            continue
        ref = config.signing_key_ref
        if not args.force and _has_valid_key(secrets_provider, ref):
            print(f"ok   {ref}: already seeded (use --force to rotate)")
            continue
        secrets_provider.put_kv(ref, {"signing_key": secrets.token_bytes(_KEY_BYTES).hex()})
        seeded += 1
        print(f"seed {ref}: wrote a fresh dev signing key")

    print(f"done: {seeded} key(s) written; the material is in OpenBao, never here")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
