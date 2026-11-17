"""INT-465: the red rule set is signed with a synthetic-only test key.

Owner decision, 3 Oct 2026 (with D18): the rule set the synthetic AWS host serves to
simulated patients is signed with a test key. The key is ed25519. It is held
non-exportable in OpenBao Transit on that host (i-0e489e48739f5de98), so its private
half is never in this repository or in any log. Only the public half is committed, in
``packages/protocols/signing/trusted_keys.yaml``, with scope ``synthetic_test``.

Properties pinned here:
- The load-bearing one: **any non-synthetic tenant config rejects the test-key
  signature.** The check runs before any cryptography, so a real tenant never even
  evaluates a test signature.
- The signature covers the exact bytes of both documents and the exact list of rules
  served. A changed byte or a changed rule list is refused.
- This trust registry can never hold a production key. Production signing is the
  cosign path (INT-058) and is untouched here.

Unit cases use keys minted in-process. The committed envelope is checked as well:
it verifies under a synthetic tenant and is rejected under every other one.
"""

from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from intake_platform.red_signature import (
    COMMITTED_SIGNATURE,
    COMMITTED_TRUST_REGISTRY,
    KeyScope,
    RedRuleSetPayload,
    RedRuleSetSignature,
    RedSignatureRefused,
    TrustedKey,
    TrustRegistry,
    admitted_scopes,
    canonical_payload_bytes,
    load_signature,
    load_trust_registry,
    verify_red_rule_set,
)
from intake_platform.red_tenant import TenantKind, TenantRedConfig

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
GENERIC = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"

#: The synthetic AWS host the committed signature is bound to (review round 2).
DEPLOYMENT = "i-0e489e48739f5de98"
SYNTHETIC = TenantRedConfig(kind=TenantKind.SYNTHETIC, deployment=DEPLOYMENT)
NON_SYNTHETIC_KINDS = [kind for kind in TenantKind if kind is not TenantKind.SYNTHETIC]
NON_SYNTHETIC_CONFIGS = [
    TenantRedConfig(kind=kind, acil_location_tr=location, deployment=DEPLOYMENT)
    for kind in NON_SYNTHETIC_KINDS
    for location in (None, "zemin kat")
]

LT_BYTES = b"kind: life_threat_set\n# sentetik\n"
GR_BYTES = b"kind: generic_red\n# sentetik\n"
SERVED = ("rf.sentetik_a", "rf.sentetik_b")


def _public_b64(key: Ed25519PrivateKey) -> str:
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def _registry(key: Ed25519PrivateKey, key_id: str = "redset-sentetik@1") -> TrustRegistry:
    return TrustRegistry(
        kind="red_rule_set_trusted_keys",
        keys=(
            TrustedKey(
                key_id=key_id,
                algorithm="ed25519",
                public_key=_public_b64(key),
                scope=KeyScope.SYNTHETIC_TEST,
                custody="minted in-process by this test; never written anywhere",
                created_on=date(2026, 10, 3),
            ),
        ),
    )


def _payload(**update: Any) -> RedRuleSetPayload:
    payload = RedRuleSetPayload.build(
        scope=KeyScope.SYNTHETIC_TEST,
        life_threat_path="files/protocols/base.life_threat.yaml",
        life_threat_bytes=LT_BYTES,
        generic_red_path="packages/protocols/generic/generic_red.yaml",
        generic_red_bytes=GR_BYTES,
        served_rule_ids=SERVED,
        deployment=DEPLOYMENT,
    )
    return payload.model_copy(update=update)


def _signed(
    key: Ed25519PrivateKey, payload: RedRuleSetPayload | None = None
) -> RedRuleSetSignature:
    body = payload if payload is not None else _payload()
    signature = key.sign(canonical_payload_bytes(body))
    return RedRuleSetSignature(
        payload=body,
        key_id="redset-sentetik@1",
        signature=base64.b64encode(signature).decode("ascii"),
    )


def _verify(
    signature: RedRuleSetSignature,
    registry: TrustRegistry,
    tenant: TenantRedConfig = SYNTHETIC,
    *,
    life_threat: bytes = LT_BYTES,
    generic: bytes = GR_BYTES,
    served: tuple[str, ...] = SERVED,
) -> TrustedKey:
    return verify_red_rule_set(
        signature,
        registry=registry,
        tenant=tenant,
        life_threat_bytes=life_threat,
        generic_red_bytes=generic,
        served_rule_ids=served,
    )


# --- the property the owner's decision rests on ---------------------------------------------


def test_a_synthetic_tenant_accepts_the_test_key() -> None:
    key = Ed25519PrivateKey.generate()
    registry = _registry(key)
    assert _verify(_signed(key), registry).scope is KeyScope.SYNTHETIC_TEST


@pytest.mark.parametrize("tenant", NON_SYNTHETIC_CONFIGS, ids=repr)
def test_any_non_synthetic_tenant_config_rejects_the_test_key_signature(
    tenant: TenantRedConfig,
) -> None:
    """The same valid signature that a synthetic tenant accepts (near miss above)."""
    key = Ed25519PrivateKey.generate()
    with pytest.raises(RedSignatureRefused) as caught:
        _verify(_signed(key), _registry(key), tenant)
    assert caught.value.code == "key_scope_not_admitted_for_tenant"


@pytest.mark.parametrize("kind", NON_SYNTHETIC_KINDS)
def test_a_non_synthetic_tenant_admits_no_key_scope_at_all(kind: TenantKind) -> None:
    """Admission is an allow-list keyed on SYNTHETIC alone, so a tenant kind added
    later is rejected without anyone remembering to list it."""
    assert admitted_scopes(TenantRedConfig(kind=kind)) == frozenset()
    assert admitted_scopes(SYNTHETIC) == frozenset({KeyScope.SYNTHETIC_TEST})


def test_the_tenant_is_checked_before_any_cryptography() -> None:
    """A real tenant refuses on scope even when the signature bytes are garbage:
    a test signature is never evaluated on a real tenant."""
    key = Ed25519PrivateKey.generate()
    garbage = _signed(key).model_copy(update={"signature": base64.b64encode(b"\0" * 64).decode()})
    with pytest.raises(RedSignatureRefused) as caught:
        _verify(garbage, _registry(key), NON_SYNTHETIC_CONFIGS[0])
    assert caught.value.code == "key_scope_not_admitted_for_tenant"


# --- the signature binds the exact bytes and the exact rule list ----------------------------


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"life_threat": LT_BYTES + b" "}, "life_threat_digest_mismatch"),
        ({"generic": GR_BYTES.replace(b"generic", b"generik")}, "generic_red_digest_mismatch"),
        ({"served": ("rf.sentetik_a",)}, "served_rules_mismatch"),
        ({"served": (*SERVED, "rf.crisis_disclosure_signposting")}, "served_rules_mismatch"),
    ],
    ids=["life-threat-byte", "generic-byte", "rule-dropped", "draft-rule-added"],
)
def test_a_changed_byte_or_rule_list_is_refused(override: dict[str, Any], code: str) -> None:
    key = Ed25519PrivateKey.generate()
    with pytest.raises(RedSignatureRefused) as caught:
        _verify(_signed(key), _registry(key), **override)
    assert caught.value.code == code


def test_a_forged_or_resigned_payload_is_refused() -> None:
    key = Ed25519PrivateKey.generate()
    registry = _registry(key)
    honest = _signed(key)
    # The payload is edited after signing: the signature no longer covers it.
    edited = honest.model_copy(update={"payload": _payload(served_rule_ids=("rf.sentetik_a",))})
    with pytest.raises(RedSignatureRefused) as caught:
        _verify(edited, registry, served=("rf.sentetik_a",))
    assert caught.value.code == "bad_signature"
    # A key nobody registered signs the same payload.
    stranger = _signed(Ed25519PrivateKey.generate())
    with pytest.raises(RedSignatureRefused) as caught:
        _verify(stranger, registry)
    assert caught.value.code == "bad_signature"


@pytest.mark.parametrize(
    "content",
    [b"", b"{}", b"not json", b"\xff\xfe", b'{"payload": 1, "key_id": "k", "signature": "x"}'],
)
def test_a_malformed_signature_file_is_refused(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "envelope.json"
    path.write_bytes(content)
    with pytest.raises(RedSignatureRefused) as caught:
        load_signature(path)
    assert caught.value.code == "malformed_signature"
    with pytest.raises(RedSignatureRefused) as caught:
        load_signature(tmp_path / "absent.json")
    assert caught.value.code == "malformed_signature"


def test_an_unknown_key_id_is_refused() -> None:
    key = Ed25519PrivateKey.generate()
    signature = _signed(key).model_copy(update={"key_id": "redset-nobody@1"})
    with pytest.raises(RedSignatureRefused) as caught:
        _verify(signature, _registry(key))
    assert caught.value.code == "unknown_key"


def test_the_payload_must_declare_the_keys_own_scope() -> None:
    """The payload says what it was signed for; it cannot claim more than its key."""
    doc = _payload().model_dump(mode="json")
    doc["scope"] = "production"
    with pytest.raises(ValueError):
        RedRuleSetPayload.model_validate(doc)


@pytest.mark.parametrize(
    "tenant",
    [
        TenantRedConfig(kind=TenantKind.SYNTHETIC, deployment="i-0123456789abcdef0"),
        TenantRedConfig(kind=TenantKind.SYNTHETIC, deployment=None),
    ],
    ids=["another-host", "no-host-declared"],
)
def test_a_synthetic_tenant_on_another_deployment_is_refused(tenant: TenantRedConfig) -> None:
    """The signature names the one host it is for. A synthetic tenant elsewhere, or
    one that declares no host, refuses it. Near miss: the bound host accepts it."""
    key = Ed25519PrivateKey.generate()
    with pytest.raises(RedSignatureRefused) as caught:
        _verify(_signed(key), _registry(key), tenant)
    assert caught.value.code == "deployment_mismatch"
    assert _verify(_signed(key), _registry(key), SYNTHETIC).scope is KeyScope.SYNTHETIC_TEST


def test_the_committed_signature_is_bound_to_the_synthetic_host() -> None:
    assert load_signature(COMMITTED_SIGNATURE).payload.deployment == DEPLOYMENT


def test_canonical_bytes_are_stable_and_ordered() -> None:
    payload = _payload()
    once = canonical_payload_bytes(payload)
    assert once == canonical_payload_bytes(RedRuleSetPayload.model_validate(payload.model_dump()))
    decoded = json.loads(once)
    assert list(decoded) == sorted(decoded)
    assert decoded["served_rule_ids"] == sorted(SERVED)


# --- the registry: public halves of test keys only ------------------------------------------


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d["keys"][0].update(scope="production"),
        lambda d: d["keys"][0].update(algorithm="rsa"),
        lambda d: d["keys"][0].update(public_key=base64.b64encode(b"x" * 31).decode()),
        lambda d: d["keys"].append(dict(d["keys"][0])),
        lambda d: d["keys"][0].update(private_key="anything"),
    ],
    ids=["production-scope", "wrong-algorithm", "short-key", "duplicate-id", "private-field"],
)
def test_the_registry_holds_only_synthetic_test_public_keys(tmp_path: Path, edit: Any) -> None:
    key = Ed25519PrivateKey.generate()
    doc = json.loads(_registry(key).model_dump_json())
    edit(doc)
    path = tmp_path / "trusted_keys.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    with pytest.raises(RedSignatureRefused) as caught:
        load_trust_registry(path)
    assert caught.value.code == "malformed_trust_registry"


def test_the_committed_registry_names_the_openbao_custody_and_holds_no_private_key() -> None:
    registry = load_trust_registry(COMMITTED_TRUST_REGISTRY)
    [key] = registry.keys
    assert key.scope is KeyScope.SYNTHETIC_TEST
    assert len(base64.b64decode(key.public_key)) == 32
    assert "OpenBao Transit" in key.custody and "i-0e489e48739f5de98" in key.custody
    text = COMMITTED_TRUST_REGISTRY.read_text(encoding="utf-8")
    assert "-----BEGIN" not in text and "private_key" not in text


# --- the committed signature over the committed rule set ------------------------------------


def _committed_served_ids() -> tuple[str, ...]:
    from protocols.compile.life_threat import load_life_threat_set
    from protocols.types import RuleStatus

    life_threat = load_life_threat_set(LIFE_THREAT)
    return tuple(sorted(e.rule.id for e in life_threat.rules if e.rule.status is RuleStatus.ACTIVE))


def _verify_committed(tenant: TenantRedConfig) -> TrustedKey:
    return verify_red_rule_set(
        load_signature(COMMITTED_SIGNATURE),
        registry=load_trust_registry(COMMITTED_TRUST_REGISTRY),
        tenant=tenant,
        life_threat_bytes=LIFE_THREAT.read_bytes(),
        generic_red_bytes=GENERIC.read_bytes(),
        served_rule_ids=_committed_served_ids(),
    )


def test_the_committed_signature_verifies_for_a_synthetic_tenant() -> None:
    key = _verify_committed(SYNTHETIC)
    assert key.scope is KeyScope.SYNTHETIC_TEST
    payload = load_signature(COMMITTED_SIGNATURE).payload
    # Draft rules are never in a served list.
    assert "rf.crisis_disclosure_signposting" not in payload.served_rule_ids
    assert "rf.paediatric_airway_obstruction" not in payload.served_rule_ids


@pytest.mark.parametrize("tenant", NON_SYNTHETIC_CONFIGS, ids=repr)
def test_the_committed_signature_is_rejected_by_every_non_synthetic_tenant(
    tenant: TenantRedConfig,
) -> None:
    with pytest.raises(RedSignatureRefused) as caught:
        _verify_committed(tenant)
    assert caught.value.code == "key_scope_not_admitted_for_tenant"


def test_the_committed_signature_leaves_d17_untouched() -> None:
    """The test signature stands in for a physician on the synthetic host only.
    It fills no clinical_signoff field, and the file still says served: false."""
    doc = yaml.safe_load(LIFE_THREAT.read_text(encoding="utf-8"))
    assert doc["served"] is False
    assert all(value is None for value in doc["clinical_signoff"].values())
