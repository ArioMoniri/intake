"""INT-058: the voice runtime picks a bundle's trust path by tenant kind alone.

The verification itself is tests/protocols/test_bundle_synthetic_signature.py and
test_bundle_signature.py. This file holds the selection rule in the runtime's own lane:
a real tenant gets the cosign trust root or nothing, never the D23 test key; a synthetic
tenant gets only the admitted test keys, bound to the host it names.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from intake_platform.red_signature import COMMITTED_TRUST_REGISTRY, load_trust_registry
from intake_platform.red_tenant import TenantKind, TenantRedConfig
from intake_voice_runtime.protocol_trust import bundle_trust_for
from protocols.serving.trust import TRUST_ROOT_ENV, SyntheticTrust, TrustRoot, TrustRootMissing

HOST = "i-0e489e48739f5de98"


def test_a_synthetic_tenant_gets_the_committed_test_keys_for_its_host() -> None:
    trust = bundle_trust_for(TenantRedConfig(kind=TenantKind.SYNTHETIC, deployment=HOST), env={})
    assert isinstance(trust, SyntheticTrust)
    assert trust.deployment == HOST
    committed = load_trust_registry(COMMITTED_TRUST_REGISTRY)
    assert trust.key_ids == frozenset(key.key_id for key in committed.keys)


def test_a_synthetic_tenant_naming_no_host_gets_nothing() -> None:
    with pytest.raises(TrustRootMissing):
        bundle_trust_for(TenantRedConfig(kind=TenantKind.SYNTHETIC), env={})


def test_a_real_tenant_with_no_trust_root_gets_nothing() -> None:
    # Near-miss: the same host, the same committed registry, a real tenant.
    with pytest.raises(TrustRootMissing):
        bundle_trust_for(TenantRedConfig(kind=TenantKind.REAL, deployment=HOST), env={})


def test_a_real_tenant_gets_the_cosign_trust_root(tmp_path: Path) -> None:
    root = tmp_path / "root.pem"
    root.write_bytes(
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    trust = bundle_trust_for(TenantRedConfig(), env={TRUST_ROOT_ENV: str(root)})
    assert isinstance(trust, TrustRoot)
