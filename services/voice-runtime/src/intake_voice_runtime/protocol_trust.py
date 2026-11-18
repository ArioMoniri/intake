"""Which signature a session's protocol bundle must carry, by tenant (INT-058).

The voice runtime is where a session starts, so it is where the bundle trust is
chosen. There are two paths and the tenant kind alone picks one:

- **synthetic** (files/00_STATE.md D23): the ed25519 OpenBao Transit test key
  ``redset-synthetic-test`` on the synthetic AWS host. Its public half is the
  committed ``packages/protocols/signing/trusted_keys.yaml``; only the keys whose
  scope ``intake_platform.red_signature.admitted_scopes`` admits for this tenant
  enter the :class:`~protocols.serving.trust.SyntheticTrust`, and it is bound to
  the host the tenant names. A synthetic tenant that names no host trusts nothing.
- **every other kind**: the cosign trust root (``make sign``), from
  ``INTAKE_PROTOCOL_TRUST_ROOT``. With none configured nothing loads (INT-019).
  A real tenant never receives the test key, whatever the registry holds.

There is no fallback between the two and no development bypass.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping

from intake_platform.red_signature import (
    COMMITTED_TRUST_REGISTRY,
    TrustRegistry,
    admitted_scopes,
    load_trust_registry,
)
from intake_platform.red_tenant import TenantKind, TenantRedConfig
from protocols.serving.trust import BundleTrust, SyntheticTrust, TrustRootMissing, load_trust_root

__all__ = ["bundle_trust_for"]


def bundle_trust_for(
    tenant: TenantRedConfig,
    *,
    env: Mapping[str, str] | None = None,
    registry: TrustRegistry | None = None,
) -> BundleTrust:
    """The one trust path this tenant's bundles are verified under, or a refusal."""
    if tenant.kind is not TenantKind.SYNTHETIC:
        return load_trust_root(env)
    if tenant.deployment is None:
        raise TrustRootMissing(
            "a synthetic tenant names no deployment host; the test key is bound to one "
            "host, so no synthetic bundle loads"
        )
    trusted = load_trust_registry(COMMITTED_TRUST_REGISTRY) if registry is None else registry
    admitted = admitted_scopes(tenant)
    keys = {
        key.key_id: (key.scope.value, base64.b64decode(key.public_key))
        for key in trusted.keys
        if key.scope in admitted
    }
    return SyntheticTrust(keys=keys, deployment=tenant.deployment)
