"""INT-058, synthetic half: a bundle signed with the D23 OpenBao Transit test key.

files/00_STATE.md D23: the synthetic AWS host's ed25519 key ``redset-synthetic-test``
is non-exportable in OpenBao Transit, signs through a sign-only token, and its public
half is the one key in ``packages/protocols/signing/trusted_keys.yaml`` (scope
``synthetic_test``). Every non-synthetic tenant rejects it
(``intake_platform.red_signature.admitted_scopes``). This file proves the same key,
through the same ``infra/staging/redset_signer.sh sign`` step, signs a protocol
bundle for that host, and that the runtime refuses an unsigned or tampered one.

The production path (cosign, ``make sign``) is ``test_bundle_signature.py``. No key
scheme is new here: the payload is a second, domain-separated payload kind for the
existing key, and its signature is Transit's pure ed25519 over canonical JSON, as
for the red rule set.

Every private key below is generated in memory for one test.
"""

from __future__ import annotations

import base64
import datetime
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from clinical_schemas.note import NoteMeta
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from intake_platform.red_signature import (
    COMMITTED_TRUST_REGISTRY,
    KeyScope,
    TrustedKey,
    TrustRegistry,
    load_trust_registry,
)
from intake_platform.red_tenant import TenantKind, TenantRedConfig
from intake_voice_runtime.protocol_trust import bundle_trust_for
from protocols.bindings import OperationalTemplate
from protocols.compile import CompiledBundle, LifeThreatSet, compile_bundle, write_bundle
from protocols.compile.archive import (
    BUNDLE_ARCHIVE,
    SIGNATURE_SUFFIX,
    SYNTHETIC_SIGNATURE_SUFFIX,
    archive_sha256,
    bundle_archive,
)
from protocols.loader import PackRegistry
from protocols.serving.pins import BundleKey, ServedBundles
from protocols.serving.trust import (
    BUNDLE_PAYLOAD_KIND,
    TRUST_ROOT_ENV,
    BundleHashMismatch,
    BundleRefused,
    BundleSignatureEnvelope,
    BundleSignatureInvalid,
    BundleSignaturePayload,
    BundleUnsigned,
    BundleUntrustedSigner,
    SyntheticTrust,
    TrustRoot,
    TrustRootInvalid,
    TrustRootMissing,
    canonical_bundle_payload,
    load_verified_bundle,
    verify_bundle,
)

PACK_ID = "base.derlenebilir"
VOICE = "sentetik-ses"
KEY = BundleKey(pack_id=PACK_ID, locale="tr", voice=VOICE)
REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "protocols" / "bundle_signature.py"
RED_SCRIPT = REPO / "scripts" / "protocols" / "red_rule_set_signature.py"
HOST = "i-0e489e48739f5de98"
KEY_ID = "redset-synthetic-test@1"


# ------------------------------------------------------------------ helpers


def _load_script(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _raw_public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def _registry(key: Ed25519PrivateKey, *, key_id: str = KEY_ID) -> TrustRegistry:
    return TrustRegistry(
        kind="red_rule_set_trusted_keys",
        keys=(
            TrustedKey(
                key_id=key_id,
                algorithm="ed25519",
                public_key=base64.b64encode(_raw_public(key)).decode("ascii"),
                scope=KeyScope.SYNTHETIC_TEST,
                custody="an in-memory key minted for one test",
                created_on=datetime.date(2026, 11, 17),
            ),
        ),
    )


def _synthetic(deployment: str | None = HOST) -> TenantRedConfig:
    return TenantRedConfig(kind=TenantKind.SYNTHETIC, deployment=deployment)


def _payload(archive: bytes, *, deployment: str = HOST) -> BundleSignaturePayload:
    return BundleSignaturePayload(
        kind=BUNDLE_PAYLOAD_KIND,
        scope="synthetic_test",
        archive_sha256=archive_sha256(archive),
        deployment=deployment,
    )


def _envelope(
    payload: BundleSignaturePayload, key: Ed25519PrivateKey, *, key_id: str = KEY_ID
) -> bytes:
    """What ``bundle_signature.py assemble`` writes from the Transit signature."""
    signature = key.sign(canonical_bundle_payload(payload))
    return (
        BundleSignatureEnvelope(
            payload=payload, key_id=key_id, signature=base64.b64encode(signature).decode("ascii")
        )
        .model_dump_json()
        .encode("utf-8")
    )


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def bundle(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> CompiledBundle:
    return compile_bundle(
        pack_id=PACK_ID,
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )


@pytest.fixture
def archive(bundle: CompiledBundle) -> bytes:
    return bundle_archive(bundle)


@pytest.fixture
def transit_key() -> Ed25519PrivateKey:
    """Stands in for the non-exportable Transit key; its public half is registered."""
    return Ed25519PrivateKey.generate()


@pytest.fixture
def trust(transit_key: Ed25519PrivateKey) -> SyntheticTrust:
    trust = bundle_trust_for(_synthetic(), env={}, registry=_registry(transit_key))
    assert isinstance(trust, SyntheticTrust)
    return trust


# =================================================================== the tenant picks the path


class TestTheTenantPicksTheTrustPath:
    def test_a_synthetic_tenant_trusts_only_its_admitted_test_keys(
        self, transit_key: Ed25519PrivateKey
    ) -> None:
        trust = bundle_trust_for(_synthetic(), env={}, registry=_registry(transit_key))
        assert isinstance(trust, SyntheticTrust)
        assert trust.key_ids == frozenset({KEY_ID})
        assert trust.signature_suffix == SYNTHETIC_SIGNATURE_SUFFIX

    def test_the_committed_registry_is_the_default(self) -> None:
        trust = bundle_trust_for(_synthetic(), env={})
        assert isinstance(trust, SyntheticTrust)
        committed = load_trust_registry(COMMITTED_TRUST_REGISTRY)
        assert trust.key_ids == frozenset(k.key_id for k in committed.keys)

    def test_a_real_tenant_never_gets_the_test_key(self, transit_key: Ed25519PrivateKey) -> None:
        # Near-miss: the very registry that admits the key for a synthetic tenant.
        with pytest.raises(TrustRootMissing):
            bundle_trust_for(TenantRedConfig(), env={}, registry=_registry(transit_key))

    def test_a_real_tenant_takes_the_cosign_trust_root(self, tmp_path: Path) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        pem = (
            ec.generate_private_key(ec.SECP256R1())
            .public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )
        root = tmp_path / "root.pem"
        root.write_bytes(pem)
        trust = bundle_trust_for(TenantRedConfig(), env={TRUST_ROOT_ENV: str(root)})
        assert isinstance(trust, TrustRoot)
        assert trust.signature_suffix == SIGNATURE_SUFFIX

    def test_a_synthetic_tenant_naming_no_host_trusts_nothing(
        self, transit_key: Ed25519PrivateKey
    ) -> None:
        with pytest.raises(TrustRootMissing, match="deployment"):
            bundle_trust_for(_synthetic(None), env={}, registry=_registry(transit_key))

    def test_an_empty_key_set_is_no_trust_root(self) -> None:
        with pytest.raises(TrustRootMissing):
            SyntheticTrust(keys={}, deployment=HOST)

    def test_a_key_that_is_not_a_raw_ed25519_public_key_is_refused(self) -> None:
        with pytest.raises(TrustRootInvalid):
            SyntheticTrust(keys={KEY_ID: ("synthetic_test", b"\x00" * 31)}, deployment=HOST)

    def test_the_trust_names_its_keys_and_host_and_no_key_material(
        self, transit_key: Ed25519PrivateKey, trust: SyntheticTrust
    ) -> None:
        assert trust.deployment == HOST
        shown = repr(trust)
        assert KEY_ID in shown and HOST in shown
        assert base64.b64encode(_raw_public(transit_key)).decode("ascii") not in shown


# =================================================================== verify, then load


class TestTheRuntimeRefusesUnsignedOrTampered:
    def test_a_transit_signed_bundle_verifies(
        self, archive: bytes, transit_key: Ed25519PrivateKey, trust: SyntheticTrust
    ) -> None:
        verified = verify_bundle(archive, _envelope(_payload(archive), transit_key), trust)
        assert verified.signer_key_id == KEY_ID
        assert verified.archive_sha256 == archive_sha256(archive)
        assert verified.pack_id == PACK_ID

    def test_an_unsigned_bundle_is_refused(self, archive: bytes, trust: SyntheticTrust) -> None:
        with pytest.raises(BundleUnsigned):
            verify_bundle(archive, None, trust)

    def test_a_tampered_archive_is_refused(
        self, archive: bytes, transit_key: Ed25519PrivateKey, trust: SyntheticTrust
    ) -> None:
        envelope = _envelope(_payload(archive), transit_key)
        tampered = archive[:-1] + bytes([archive[-1] ^ 0x01])
        with pytest.raises(BundleHashMismatch):
            verify_bundle(tampered, envelope, trust)

    def test_an_edited_payload_is_refused(
        self, archive: bytes, transit_key: Ed25519PrivateKey, trust: SyntheticTrust
    ) -> None:
        # A signer of bundle A; the envelope edited to claim bundle B's digest.
        other = archive + b"\x00"
        envelope = json.loads(_envelope(_payload(archive), transit_key))
        envelope["payload"]["archive_sha256"] = archive_sha256(other)
        with pytest.raises(BundleSignatureInvalid):
            verify_bundle(other, json.dumps(envelope).encode(), trust)

    def test_another_keys_signature_under_the_registered_id_is_refused(
        self, archive: bytes, trust: SyntheticTrust
    ) -> None:
        forged = _envelope(_payload(archive), Ed25519PrivateKey.generate())
        with pytest.raises(BundleSignatureInvalid):
            verify_bundle(archive, forged, trust)

    def test_an_unknown_key_id_is_not_trusted(
        self, archive: bytes, transit_key: Ed25519PrivateKey, trust: SyntheticTrust
    ) -> None:
        envelope = _envelope(_payload(archive), transit_key, key_id="redset-synthetic-test@2")
        with pytest.raises(BundleUntrustedSigner):
            verify_bundle(archive, envelope, trust)

    def test_a_signature_for_another_host_is_refused(
        self, archive: bytes, transit_key: Ed25519PrivateKey, trust: SyntheticTrust
    ) -> None:
        envelope = _envelope(_payload(archive, deployment="i-0aaaaaaaaaaaaaaaa"), transit_key)
        with pytest.raises(BundleUntrustedSigner, match="host"):
            verify_bundle(archive, envelope, trust)

    def test_a_red_rule_set_signature_is_not_a_bundle_signature(
        self, archive: bytes, trust: SyntheticTrust
    ) -> None:
        # Domain separation: the committed red-set envelope, by the same key id.
        red = (REPO / "packages/protocols/signing/red_rule_set.synthetic.json").read_bytes()
        with pytest.raises(BundleSignatureInvalid):
            verify_bundle(archive, red, trust)

    def test_a_cosign_bundle_is_not_a_synthetic_signature(
        self, archive: bytes, trust: SyntheticTrust
    ) -> None:
        sigstore = json.dumps(
            {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"}
        ).encode()
        with pytest.raises(BundleSignatureInvalid):
            verify_bundle(archive, sigstore, trust)

    def test_a_payload_of_another_scope_is_refused(
        self, archive: bytes, transit_key: Ed25519PrivateKey, trust: SyntheticTrust
    ) -> None:
        payload = _payload(archive).model_copy(update={"scope": "production"})
        with pytest.raises(BundleUntrustedSigner, match="scope"):
            verify_bundle(archive, _envelope(payload, transit_key), trust)

    def test_the_committed_public_key_is_not_bypassed(self, archive: bytes) -> None:
        # The real D23 public half: an in-memory key claiming its id is refused.
        trust = bundle_trust_for(_synthetic(), env={})
        forged = _envelope(_payload(archive), Ed25519PrivateKey.generate())
        with pytest.raises(BundleSignatureInvalid):
            verify_bundle(archive, forged, trust)

    def test_load_reads_the_synthetic_envelope_and_never_the_sigstore_one(
        self,
        tmp_path: Path,
        bundle: CompiledBundle,
        transit_key: Ed25519PrivateKey,
        trust: SyntheticTrust,
    ) -> None:
        write_bundle(bundle, tmp_path)
        archive_path = tmp_path / PACK_ID / BUNDLE_ARCHIVE
        archive = archive_path.read_bytes()
        # Only a sigstore file beside it: the synthetic path sees no signature.
        archive_path.with_name(BUNDLE_ARCHIVE + SIGNATURE_SUFFIX).write_bytes(b"{}")
        with pytest.raises(BundleUnsigned):
            load_verified_bundle(archive_path, trust)
        archive_path.with_name(BUNDLE_ARCHIVE + SYNTHETIC_SIGNATURE_SUFFIX).write_bytes(
            _envelope(_payload(archive), transit_key)
        )
        assert load_verified_bundle(archive_path, trust).signer_key_id == KEY_ID

    @pytest.mark.parametrize("signature", ["not*base64", base64.b64encode(b"\x01" * 63).decode()])
    def test_a_malformed_envelope_signature_is_refused(
        self,
        archive: bytes,
        transit_key: Ed25519PrivateKey,
        trust: SyntheticTrust,
        signature: str,
    ) -> None:
        envelope = json.loads(_envelope(_payload(archive), transit_key))
        envelope["signature"] = signature
        with pytest.raises(BundleSignatureInvalid):
            verify_bundle(archive, json.dumps(envelope).encode(), trust)

    def test_every_refusal_is_a_bundle_refusal(self) -> None:
        for refusal in (BundleUnsigned, BundleSignatureInvalid, BundleUntrustedSigner):
            assert issubclass(refusal, BundleRefused)


# =================================================================== pin + note meta


class TestTheSessionPinsTheSyntheticBundle:
    def test_the_pinned_hash_is_the_note_meta_hash(
        self, archive: bytes, transit_key: Ed25519PrivateKey, trust: SyntheticTrust
    ) -> None:
        verified = verify_bundle(archive, _envelope(_payload(archive), transit_key), trust)
        shelf = ServedBundles()
        shelf.deploy(verified)
        pin = shelf.pin("ses-sentetik", KEY)
        meta = NoteMeta(
            visit_id="visit-ses-sentetik",
            protocol_hash=pin.protocol_hash,
            mode="fast",
            generated_at=datetime.datetime(2026, 11, 17, 9, 0, tzinfo=datetime.UTC),
            model="synthetic-note-model@rev0",
            prompt_version="note-v0",
        )
        assert meta.protocol_hash == verified.resolved_protocol_hash
        assert pin.archive_sha256 == archive_sha256(archive)


# =================================================================== the signing script


class TestTheSigningScript:
    def test_payload_then_transit_then_assemble_round_trips(
        self, tmp_path: Path, bundle: CompiledBundle, transit_key: Ed25519PrivateKey
    ) -> None:
        script = _load_script(SCRIPT, "bundle_signature")
        write_bundle(bundle, tmp_path)
        archive_path = tmp_path / PACK_ID / BUNDLE_ARCHIVE
        payload = script.build_payload(archive_path)
        raw = canonical_bundle_payload(payload)
        # infra/staging/redset_signer.sh sign <base64> prints Transit's "vault:v1:<b64>".
        transit = "vault:v1:" + base64.b64encode(transit_key.sign(raw)).decode("ascii")
        envelope = script.envelope_from_transit(payload, key_id=KEY_ID, transit=transit)
        out = script.write_envelope(envelope, archive_path)
        assert out.name == BUNDLE_ARCHIVE + SYNTHETIC_SIGNATURE_SUFFIX
        trust = bundle_trust_for(_synthetic(), env={}, registry=_registry(transit_key))
        assert load_verified_bundle(archive_path, trust).signer_key_id == KEY_ID

    def test_a_transit_signature_of_another_key_version_is_refused(
        self, tmp_path: Path, bundle: CompiledBundle
    ) -> None:
        script = _load_script(SCRIPT, "bundle_signature")
        write_bundle(bundle, tmp_path)
        payload = script.build_payload(tmp_path / PACK_ID / BUNDLE_ARCHIVE)
        with pytest.raises(ValueError, match="version"):
            script.envelope_from_transit(
                payload, key_id=KEY_ID, transit="vault:v2:" + "A" * 86 + "=="
            )

    def test_the_script_signs_for_the_d23_host(self) -> None:
        script = _load_script(SCRIPT, "bundle_signature")
        red = _load_script(RED_SCRIPT, "red_rule_set_signature")
        assert script.DEPLOYMENT == red.DEPLOYMENT == HOST
