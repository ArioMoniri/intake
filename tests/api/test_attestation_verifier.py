"""INT-344 — the attestation verifiers: Apple App Attest, the platform router,
the Play Integrity verdict policy, and the fail-closed wiring.

Acceptance lines pinned here (GitHub #543): "the server verifier validates
attestation and assertion objects against recorded Apple and Google fixtures
(certificate chain, app id, counter, nonce binding) and refuses everything
else; FailClosedAttestationVerifier stays the default when keys are absent".

What this file proves:
- production trusts exactly one root: the committed Apple App Attestation Root
  CA, pinned by SHA-256 in code AND in this file, so neither pin moves alone;
- Apple's own published example attestation verifies against that pinned root
  (the "recorded Apple fixture"), and stops verifying once its leaf expires or
  against another App ID;
- every branch of Apple's attestation and assertion algorithms refuses on its
  own: chain, rpId, nonce, counter (zero on attestation, strictly increasing
  on assertions), aaguid environment, keyId, credentialId, signature;
- the develop aaguid is accepted only when the development environment is
  explicitly configured;
- Google has no recorded fixture: the Play Console account that would produce
  one is HB-A3, so the Play Integrity verdict POLICY is proven against decoded
  verdicts and the wired verifier stays fail-closed with a typed reason.

The replayed-challenge branch needs the service's single-use store and is
proven end to end in test_attestation_otp_flow.py.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import cbor2
import fakeredis
import pytest
from app_attest_testkit import (
    AAGUID_DEVELOPMENT,
    BUNDLE_ID,
    NOW,
    TEAM_ID,
    Device,
    Pki,
    authority,
    b64,
    cose_key,
    der,
    nonce_extension_value,
    sha256,
)
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from intake_api.app import _auth_from_settings
from intake_api.app_attest import (
    APPLE_APP_ATTEST_ROOT_PATH,
    APPLE_APP_ATTEST_ROOT_SHA256,
    AppAttestConfig,
    AppAttestConfigError,
    AppAttestEnvironment,
    AppAttestRefused,
    AppAttestVerifier,
    AttestedKey,
    load_apple_app_attest_root,
    verify_assertion_object,
    verify_attestation_object,
)
from intake_api.app_attest_store import RedisAppAttestKeyStore
from intake_api.attestation import (
    AttestationPayload,
    AttestationReason,
    DevStructuralAttestationVerifier,
    FailClosedAttestationVerifier,
    PlatformAttestationVerifier,
    attestation_client_data,
)
from intake_api.auth_store import CHALLENGE_TTL_S
from intake_api.play_integrity import (
    PlayIntegrityConfig,
    PlayIntegrityDecodeError,
    PlayIntegrityVerifier,
    play_integrity_request_hash,
)
from intake_api.settings import ApiSettings

REPO = Path(__file__).resolve().parents[2]
APPLE_EXAMPLE = REPO / "tests" / "fixtures" / "app_attest" / "apple_validation_guide_example.json"

# The SHA-256 of the DER bytes of the Apple App Attestation Root CA as
# retrieved from apple.com/certificateauthority on 2026-09-26. Written out here
# on purpose: the code's constant and the committed file each pin the other,
# and this literal pins both, so moving the trust anchor takes all three.
APPLE_ROOT_SHA256_AS_RETRIEVED = "1cb9823ba28ba6ad2d33a006941de2ae4f513ef1d4e831b9f7e0fa7b6242c932"

CONFIG = AppAttestConfig(
    team_id=TEAM_ID, bundle_id=BUNDLE_ID, environment=AppAttestEnvironment.PRODUCTION
)
REGISTER = attestation_client_data("attest.key", "challenge-register")
REQUEST = attestation_client_data("otp.request", "challenge-request")
VERIFY = attestation_client_data("otp.verify", "challenge-verify")


@pytest.fixture(scope="module")
def pki() -> Pki:
    return Pki.build()


@pytest.fixture()
def store() -> RedisAppAttestKeyStore:
    return RedisAppAttestKeyStore(fakeredis.FakeStrictRedis())


def _verifier(
    pki: Pki, store: RedisAppAttestKeyStore, config: AppAttestConfig = CONFIG
) -> AppAttestVerifier:
    return AppAttestVerifier(config, store, root=pki.root.cert, now_fn=NOW.timestamp)


@pytest.fixture()
def verifier(pki: Pki, store: RedisAppAttestKeyStore) -> AppAttestVerifier:
    return _verifier(pki, store)


@pytest.fixture()
def device(pki: Pki) -> Device:
    return Device(pki)


def _header(device: Device, token: str, *, platform: str = "ios") -> AttestationPayload:
    return AttestationPayload.model_validate(
        {
            "platform": platform,
            "mode": "app-attest",
            "token": token,
            "device_id": "device-a",
            "nonce": "challenge",
            "key_id": device.key_id,
        }
    )


def _registered(verifier: AppAttestVerifier, device: Device) -> None:
    result = verifier.register(device.key_id, device.attest(REGISTER), client_data=REGISTER)
    assert result.ok, result.reason


# --- the trust anchor ------------------------------------------------------------------


def test_production_pins_exactly_the_committed_apple_root(
    store: RedisAppAttestKeyStore,
) -> None:
    cert = x509.load_pem_x509_certificate(APPLE_APP_ATTEST_ROOT_PATH.read_bytes())
    der_sha256 = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    assert der_sha256 == APPLE_APP_ATTEST_ROOT_SHA256 == APPLE_ROOT_SHA256_AS_RETRIEVED
    assert cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value == (
        "Apple App Attestation Root CA"
    )
    assert load_apple_app_attest_root() == cert
    # a verifier built without an explicit root trusts the pinned Apple root and
    # nothing else — the test root below is reachable only through `root=`
    assert AppAttestVerifier(CONFIG, store).root_sha256 == APPLE_ROOT_SHA256_AS_RETRIEVED


def test_any_other_certificate_at_the_root_path_is_refused(pki: Pki, tmp_path: Path) -> None:
    impostor = tmp_path / "root.pem"
    impostor.write_bytes(pki.root.cert.public_bytes(serialization.Encoding.PEM))
    with pytest.raises(AppAttestConfigError):
        load_apple_app_attest_root(impostor)
    for unreadable in (tmp_path / "absent.pem", tmp_path):
        with pytest.raises(AppAttestConfigError):
            load_apple_app_attest_root(unreadable)
    garbled = tmp_path / "garbled.pem"
    garbled.write_text("-----BEGIN CERTIFICATE-----\nnot base64\n-----END CERTIFICATE-----\n")
    with pytest.raises(AppAttestConfigError):
        load_apple_app_attest_root(garbled)


# --- Apple's published example (the recorded Apple fixture) --------------------------


def _apple_example() -> dict[str, str]:
    loaded: dict[str, str] = json.loads(APPLE_EXAMPLE.read_text(encoding="utf-8"))
    return loaded


def _verify_apple_example(
    *, now: datetime, team_id: str | None = None, challenge: str | None = None
) -> Any:
    example = _apple_example()
    config = AppAttestConfig(
        team_id=team_id if team_id is not None else example["team_id"],
        bundle_id=example["bundle_id"],
        environment=AppAttestEnvironment.PRODUCTION,
    )
    # The guide's example app handed attestKey the raw challenge bytes as its
    # clientDataHash (the fixture's note records how that was established).
    client_data_hash = (challenge if challenge is not None else example["challenge"]).encode()
    return verify_attestation_object(
        base64.b64decode(example["attestation_object"]),
        key_id=base64.b64decode(example["key_id"]),
        client_data_hash=client_data_hash,
        config=config,
        root=load_apple_app_attest_root(),
        now=now,
    )


def test_apples_published_example_verifies_against_the_pinned_root() -> None:
    example = _apple_example()
    key = _verify_apple_example(now=datetime(2026, 4, 21, tzinfo=UTC))
    assert hashlib.sha256(key.public_key).digest() == base64.b64decode(example["key_id"])
    assert key.counter == 0
    assert key.environment is AppAttestEnvironment.PRODUCTION


@pytest.mark.parametrize(
    ("knobs", "reason"),
    [
        ({"now": datetime(2026, 4, 24, tzinfo=UTC)}, AttestationReason.APP_ATTEST_CHAIN),
        (
            {"now": datetime(2026, 4, 21, tzinfo=UTC), "team_id": "ABCDE12345"},
            AttestationReason.APP_ATTEST_RP_ID,
        ),
        (
            {"now": datetime(2026, 4, 21, tzinfo=UTC), "challenge": "another_challenge"},
            AttestationReason.APP_ATTEST_NONCE,
        ),
    ],
    ids=["leaf-expired", "other-app-id", "other-challenge"],
)
def test_apples_example_is_refused_outside_its_own_facts(
    knobs: dict[str, Any], reason: AttestationReason
) -> None:
    with pytest.raises(AppAttestRefused) as refused:
        _verify_apple_example(**knobs)
    assert refused.value.reason is reason


# --- synthetic attestation: accept, then every refusal ---------------------------------


def test_a_genuine_attestation_registers_the_key_at_counter_zero(
    verifier: AppAttestVerifier, store: RedisAppAttestKeyStore, device: Device
) -> None:
    result = verifier.register(device.key_id, device.attest(REGISTER), client_data=REGISTER)
    assert result.ok
    assert result.reason is AttestationReason.APP_ATTEST_KEY_REGISTERED
    stored = store.load(device.key_id)
    assert stored is not None
    assert stored.public_key == device.point
    assert stored.counter == 0
    assert stored.environment is AppAttestEnvironment.PRODUCTION


def test_attestation_extensions_are_read_strictly_when_present(
    verifier: AppAttestVerifier, device: Device
) -> None:
    # Apple's 2026 authenticator data carries a trailing CBOR extensions map;
    # a well-formed one is accepted, anything else after the COSE key is not
    extensions = {"apple_bundle_version_01": "1", "apple_validation_category_01": b"\x04\x00"}
    token = device.attest(REGISTER, extensions=extensions)
    assert verifier.register(device.key_id, token, client_data=REGISTER).ok

    # bytes after the COSE key that are not one CBOR map — signed over, so the
    # nonce holds and the parse is the only thing that can refuse them
    for trailing in (b"\xff", cbor2.dumps([1, 2]), cbor2.dumps({"a": 1}) + b"\x00"):
        other = Device(device.pki)
        result = verifier.register(
            other.key_id, other.attest(REGISTER, trailing=trailing), client_data=REGISTER
        )
        assert result.reason is AttestationReason.APP_ATTEST_MALFORMED, trailing


def _untrusted_chain(device: Device) -> dict[str, Any]:
    stranger = authority("Somebody Else's Root")
    return {"issuer": authority("Somebody Else's CA", stranger)}


REFUSED_ATTESTATIONS: list[tuple[str, Any, AttestationReason]] = [
    ("untrusted-chain", _untrusted_chain, AttestationReason.APP_ATTEST_CHAIN),
    (
        "leaf-only-chain",
        lambda d: {"chain": [d.leaf(b"\x00" * 32)]},
        AttestationReason.APP_ATTEST_CHAIN,
    ),
    (
        "expired-leaf",
        lambda d: {"leaf_not_after": NOW - timedelta(seconds=1)},
        AttestationReason.APP_ATTEST_CHAIN,
    ),
    (
        "signed-by-a-non-ca-under-the-root",
        lambda d: {"issuer": authority("Not A CA", d.pki.root, ca=False)},
        AttestationReason.APP_ATTEST_CHAIN,
    ),
    ("leaf-is-a-ca", lambda d: {"leaf_ca": True}, AttestationReason.APP_ATTEST_CHAIN),
    (
        "signer-without-basic-constraints",
        lambda d: {"issuer": authority("Silent CA", d.pki.root, ca=None)},
        AttestationReason.APP_ATTEST_CHAIN,
    ),
    (
        "x5c-is-not-certificates",
        lambda d: {"chain": [b"not a certificate", b"nor this"]},
        AttestationReason.APP_ATTEST_CHAIN,
    ),
    ("no-nonce-extension", lambda d: {"nonce_extension": b""}, AttestationReason.APP_ATTEST_NONCE),
    (
        "nonce-not-in-a-sequence",
        lambda d: {"nonce_extension": der(0x04, b"\x00" * 32)},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "nonce-not-tagged-one",
        lambda d: {"nonce_extension": der(0x30, der(0xA2, der(0x04, b"\x00" * 32)))},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "nonce-not-an-octet-string",
        lambda d: {"nonce_extension": der(0x30, der(0xA1, der(0x0C, b"\x00" * 32)))},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "nonce-with-trailing-bytes",
        lambda d: {"nonce_extension": nonce_extension_value(b"\x00" * 32) + b"\x00"},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "nonce-length-not-minimal",
        lambda d: {"nonce_extension": b"\x30\x81\x24" + der(0xA1, der(0x04, b"\x00" * 32))},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "nonce-truncated",
        lambda d: {"nonce_extension": b"\x30\x30\xa1"},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "nonce-a-lone-tag",
        lambda d: {"nonce_extension": b"\x30"},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "nonce-length-of-three-bytes",
        lambda d: {"nonce_extension": b"\x30\x83\x00\x00\x24" + b"\x00" * 36},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "nonce-long-form-one-byte-length",
        lambda d: {"nonce_extension": nonce_extension_value(b"\x00" * 200)},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "nonce-long-form-two-byte-length",
        lambda d: {"nonce_extension": nonce_extension_value(b"\x00" * 300)},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    (
        "wrong-rp-id",
        lambda d: {"rp_id_hash": sha256(f"ZZZZZ99999.{BUNDLE_ID}".encode())},
        AttestationReason.APP_ATTEST_RP_ID,
    ),
    (
        "wrong-nonce",
        lambda d: {"nonce_client_data": attestation_client_data("attest.key", "stale")},
        AttestationReason.APP_ATTEST_NONCE,
    ),
    ("counter-not-zero", lambda d: {"counter": 1}, AttestationReason.APP_ATTEST_COUNTER),
    (
        "develop-aaguid-in-production",
        lambda d: {"aaguid": AAGUID_DEVELOPMENT},
        AttestationReason.APP_ATTEST_ENVIRONMENT,
    ),
    (
        "credential-id-is-not-the-key",
        lambda d: {"credential_id": sha256(b"another key")},
        AttestationReason.APP_ATTEST_CREDENTIAL_ID,
    ),
    (
        "cose-key-is-not-the-leaf-key",
        lambda d: {"cose_point": Device(d.pki).point},
        AttestationReason.APP_ATTEST_KEY_ID,
    ),
    ("wrong-format", lambda d: {"fmt": "packed"}, AttestationReason.APP_ATTEST_FORMAT),
]


@pytest.mark.parametrize(
    ("knobs", "reason"),
    [(knobs, reason) for _, knobs, reason in REFUSED_ATTESTATIONS],
    ids=[name for name, _, _ in REFUSED_ATTESTATIONS],
)
def test_every_attestation_check_refuses_on_its_own(
    verifier: AppAttestVerifier,
    store: RedisAppAttestKeyStore,
    device: Device,
    knobs: Any,
    reason: AttestationReason,
) -> None:
    token = device.attest(REGISTER, **knobs(device))
    result = verifier.register(device.key_id, token, client_data=REGISTER)
    assert not result.ok
    assert result.reason is reason
    assert store.load(device.key_id) is None, "a refused attestation must store nothing"


def test_the_key_id_must_be_the_hash_of_the_attested_key(
    verifier: AppAttestVerifier, device: Device, pki: Pki
) -> None:
    impostor = Device(pki)
    result = verifier.register(impostor.key_id, device.attest(REGISTER), client_data=REGISTER)
    assert not result.ok
    assert result.reason is AttestationReason.APP_ATTEST_KEY_ID


def test_the_attestation_must_be_for_this_request(
    verifier: AppAttestVerifier, device: Device
) -> None:
    # attested over the otp.request client data, presented for key registration
    result = verifier.register(device.key_id, device.attest(REQUEST), client_data=REGISTER)
    assert not result.ok
    assert result.reason is AttestationReason.APP_ATTEST_NONCE


@pytest.mark.parametrize(
    "token",
    ["not base64 at all!", b64(b"\xff\xfe not cbor"), b64(b"\xa0"), ""],
    ids=["not-base64", "not-cbor", "empty-map", "empty"],
)
def test_malformed_attestations_are_refused(
    verifier: AppAttestVerifier, device: Device, token: str
) -> None:
    result = verifier.register(device.key_id, token, client_data=REGISTER)
    assert not result.ok
    assert result.reason is AttestationReason.APP_ATTEST_MALFORMED


def _attested_prefix(device: Device) -> bytes:
    """authData up to and including the credential id (Apple's layout)."""
    return device.auth_data()[: 32 + 1 + 4 + 16 + 2 + 32]


MALFORMED_AUTH_DATA: list[tuple[str, Any]] = [
    ("shorter-than-the-fixed-header", lambda d: b"\x00" * 36),
    ("no-attested-credential-data", lambda d: d.auth_data()[:37] + b"\x00" * 10),
    ("credential-id-overruns", lambda d: _attested_prefix(d)[:-34] + b"\x00\xff" + b"\x01"),
    ("cose-key-is-not-a-map", lambda d: _attested_prefix(d) + cbor2.dumps([1, 2])),
    (
        "cose-key-is-not-es256",
        lambda d: _attested_prefix(d) + cbor2.dumps({**cose_key(d.point), 3: -35}),
    ),
    (
        "cose-key-is-not-p256",
        lambda d: _attested_prefix(d) + cbor2.dumps({**cose_key(d.point), -1: 2}),
    ),
    (
        "extensions-with-a-non-text-key",
        lambda d: d.auth_data() + cbor2.dumps({1: "x"}),
    ),
]


@pytest.mark.parametrize(
    "auth_data",
    [build for _, build in MALFORMED_AUTH_DATA],
    ids=[name for name, _ in MALFORMED_AUTH_DATA],
)
def test_authenticator_data_is_parsed_strictly(
    verifier: AppAttestVerifier, device: Device, auth_data: Any
) -> None:
    token = device.attest(REGISTER, raw_auth_data=auth_data(device))
    result = verifier.register(device.key_id, token, client_data=REGISTER)
    assert result.reason is AttestationReason.APP_ATTEST_MALFORMED


def _object(**fields: Any) -> str:
    return b64(cbor2.dumps(fields))


@pytest.mark.parametrize(
    "fields",
    [
        {"fmt": 1, "attStmt": {}, "authData": b""},
        {"fmt": "apple-appattest", "attStmt": [], "authData": b""},
        {"fmt": "apple-appattest", "attStmt": {}, "authData": "text"},
        {"fmt": "apple-appattest", "attStmt": {"x5c": "no"}, "authData": b"\x00" * 37},
        {"fmt": "apple-appattest", "attStmt": {"x5c": ["no"]}, "authData": b"\x00" * 37},
    ],
    ids=[
        "fmt-not-text",
        "statement-not-a-map",
        "auth-data-not-bytes",
        "x5c-not-a-list",
        "x5c-not-bytes",
    ],
)
def test_the_attestation_object_is_schema_constrained(
    verifier: AppAttestVerifier, device: Device, fields: dict[str, Any]
) -> None:
    result = verifier.register(device.key_id, _object(**fields), client_data=REGISTER)
    assert result.reason is AttestationReason.APP_ATTEST_MALFORMED


def test_a_key_id_that_is_not_a_sha256_is_refused(
    verifier: AppAttestVerifier, device: Device
) -> None:
    result = verifier.register(b64(b"\x00" * 16), device.attest(REGISTER), client_data=REGISTER)
    assert result.reason is AttestationReason.APP_ATTEST_MALFORMED


def test_a_credential_key_off_p256_is_refused(verifier: AppAttestVerifier, pki: Pki) -> None:
    off_curve = Device(pki, key=ec.generate_private_key(ec.SECP384R1()))
    result = verifier.register(off_curve.key_id, off_curve.attest(REGISTER), client_data=REGISTER)
    assert result.reason is AttestationReason.APP_ATTEST_KEY_ID


def test_a_key_can_be_attested_once(verifier: AppAttestVerifier, device: Device) -> None:
    _registered(verifier, device)
    again = verifier.register(device.key_id, device.attest(REGISTER), client_data=REGISTER)
    assert not again.ok
    assert again.reason is AttestationReason.APP_ATTEST_KEY_EXISTS


def test_the_develop_aaguid_is_accepted_only_when_development_is_configured(
    pki: Pki, store: RedisAppAttestKeyStore, device: Device
) -> None:
    development = AppAttestConfig(
        team_id=TEAM_ID, bundle_id=BUNDLE_ID, environment=AppAttestEnvironment.DEVELOPMENT
    )
    dev_verifier = _verifier(pki, store, development)
    token = device.attest(REGISTER, aaguid=AAGUID_DEVELOPMENT)
    assert dev_verifier.register(device.key_id, token, client_data=REGISTER).ok
    stored = store.load(device.key_id)
    assert stored is not None
    assert stored.environment is AppAttestEnvironment.DEVELOPMENT

    # and a development verifier refuses production keys: Apple keeps the two apart
    other = Device(pki)
    refused = dev_verifier.register(other.key_id, other.attest(REGISTER), client_data=REGISTER)
    assert refused.reason is AttestationReason.APP_ATTEST_ENVIRONMENT


# --- synthetic assertions ----------------------------------------------------------------


def test_assertions_verify_and_the_counter_strictly_increases(
    verifier: AppAttestVerifier, store: RedisAppAttestKeyStore, device: Device
) -> None:
    _registered(verifier, device)
    first = verifier.verify(_header(device, device.assertion(REQUEST, 1)), client_data=REQUEST)
    assert first.ok
    assert first.reason is AttestationReason.APP_ATTEST_ASSERTION
    second = verifier.verify(_header(device, device.assertion(VERIFY, 2)), client_data=VERIFY)
    assert second.ok
    stored = store.load(device.key_id)
    assert stored is not None
    assert stored.counter == 2


@pytest.mark.parametrize(
    ("counters", "reason"),
    [((0,), "first-at-zero"), ((3, 3), "repeated"), ((3, 2), "decreasing")],
    ids=["first-assertion-at-zero", "counter-repeated", "counter-decreasing"],
)
def test_a_counter_that_does_not_increase_is_refused(
    verifier: AppAttestVerifier, device: Device, counters: tuple[int, ...], reason: str
) -> None:
    _registered(verifier, device)
    *accepted, last = counters
    for counter in accepted:
        assert verifier.verify(
            _header(device, device.assertion(REQUEST, counter)), client_data=REQUEST
        ).ok
    result = verifier.verify(_header(device, device.assertion(REQUEST, last)), client_data=REQUEST)
    assert not result.ok, reason
    assert result.reason is AttestationReason.APP_ATTEST_COUNTER


@pytest.mark.parametrize("presented", [3, 2], ids=["equal", "lower"])
def test_the_assertion_check_itself_demands_a_greater_counter(
    device: Device, presented: int
) -> None:
    """The object check holds on its own, not only through the store's atomic
    compare-and-set — two layers, each sufficient."""
    stored = AttestedKey(
        public_key=device.point, counter=3, environment=AppAttestEnvironment.PRODUCTION
    )
    with pytest.raises(AppAttestRefused) as refused:
        verify_assertion_object(
            device.assertion_object(REQUEST, presented),
            client_data_hash=sha256(REQUEST.encode()),
            config=CONFIG,
            key=stored,
        )
    assert refused.value.reason is AttestationReason.APP_ATTEST_COUNTER


def test_an_assertion_signed_by_another_key_is_refused(
    verifier: AppAttestVerifier, device: Device
) -> None:
    _registered(verifier, device)
    forged = device.assertion(REQUEST, 1, signer=ec.generate_private_key(ec.SECP256R1()))
    result = verifier.verify(_header(device, forged), client_data=REQUEST)
    assert result.reason is AttestationReason.APP_ATTEST_SIGNATURE


def test_an_assertion_for_another_request_is_refused(
    verifier: AppAttestVerifier, store: RedisAppAttestKeyStore, device: Device
) -> None:
    # signed for otp.request, presented where otp.verify is expected: the
    # nonce the server rebuilds differs, so the signature cannot hold
    _registered(verifier, device)
    result = verifier.verify(_header(device, device.assertion(REQUEST, 1)), client_data=VERIFY)
    assert result.reason is AttestationReason.APP_ATTEST_SIGNATURE
    stored = store.load(device.key_id)
    assert stored is not None
    assert stored.counter == 0, "a refused assertion must not move the counter"


def test_an_assertion_for_another_app_is_refused(
    verifier: AppAttestVerifier, device: Device
) -> None:
    _registered(verifier, device)
    other_app = sha256(f"{TEAM_ID}.com.example.other".encode())
    token = device.assertion(REQUEST, 1, rp_id_hash=other_app)
    result = verifier.verify(_header(device, token), client_data=REQUEST)
    assert result.reason is AttestationReason.APP_ATTEST_RP_ID


def test_a_development_key_is_refused_by_a_production_verifier(
    pki: Pki, store: RedisAppAttestKeyStore, device: Device
) -> None:
    development = AppAttestConfig(
        team_id=TEAM_ID, bundle_id=BUNDLE_ID, environment=AppAttestEnvironment.DEVELOPMENT
    )
    token = device.attest(REGISTER, aaguid=AAGUID_DEVELOPMENT)
    assert (
        _verifier(pki, store, development).register(device.key_id, token, client_data=REGISTER).ok
    )
    production = _verifier(pki, store)
    result = production.verify(_header(device, device.assertion(REQUEST, 1)), client_data=REQUEST)
    assert result.reason is AttestationReason.APP_ATTEST_ENVIRONMENT


def test_an_assertion_from_an_unregistered_key_is_refused(
    verifier: AppAttestVerifier, device: Device
) -> None:
    result = verifier.verify(_header(device, device.assertion(REQUEST, 1)), client_data=REQUEST)
    assert result.reason is AttestationReason.APP_ATTEST_UNKNOWN_KEY


@pytest.mark.parametrize(
    "token",
    [
        "%%%",
        b64(b"\x01"),
        b64(b'{"signature": 1}'),
        "",
        _object(signature="text", authenticatorData=b"\x00" * 37),
        _object(signature=b"\x00", authenticatorData=b"\x00" * 36),
        _object(signature=b"\x00", authenticatorData=b"\x00" * 37 + b"\xff"),
    ],
    ids=[
        "not-base64",
        "not-a-map",
        "not-cbor",
        "empty",
        "signature-not-bytes",
        "authenticator-data-too-short",
        "authenticator-data-trailing-garbage",
    ],
)
def test_malformed_assertions_are_refused(
    verifier: AppAttestVerifier, device: Device, token: str
) -> None:
    _registered(verifier, device)
    result = verifier.verify(_header(device, token), client_data=REQUEST)
    assert result.reason is AttestationReason.APP_ATTEST_MALFORMED


class RacingStore(RedisAppAttestKeyStore):
    """Another worker's assertion lands between this one's load and its write."""

    def advance_counter(self, key_id: str, counter: int) -> bool:
        super().advance_counter(key_id, counter)
        return super().advance_counter(key_id, counter)


def test_of_two_assertions_racing_on_one_counter_exactly_one_wins(pki: Pki, device: Device) -> None:
    racing = _verifier(pki, RacingStore(fakeredis.FakeStrictRedis()))
    _registered(racing, device)
    result = racing.verify(_header(device, device.assertion(REQUEST, 1)), client_data=REQUEST)
    assert result.reason is AttestationReason.APP_ATTEST_COUNTER


def test_the_app_attest_verifier_refuses_other_modes_and_platforms(
    verifier: AppAttestVerifier, device: Device
) -> None:
    _registered(verifier, device)
    token = device.assertion(REQUEST, 1)
    android = verifier.verify(_header(device, token, platform="android"), client_data=REQUEST)
    assert android.reason is AttestationReason.MODE_PLATFORM_MISMATCH
    keyless = _header(device, token).model_copy(update={"key_id": None})
    assert verifier.verify(keyless, client_data=REQUEST).reason is (
        AttestationReason.APP_ATTEST_MALFORMED
    )


# --- the counter store ---------------------------------------------------------------------


def test_the_store_advances_only_forward_and_only_for_known_keys(
    store: RedisAppAttestKeyStore, device: Device
) -> None:
    key = AttestedKey(
        public_key=device.point, counter=0, environment=AppAttestEnvironment.PRODUCTION
    )
    assert store.advance_counter(device.key_id, 1) is False  # unknown key
    assert store.register(device.key_id, key) is True
    assert store.register(device.key_id, key) is False  # once
    assert store.advance_counter(device.key_id, 5) is True
    assert store.advance_counter(device.key_id, 5) is False
    assert store.advance_counter(device.key_id, 4) is False
    loaded = store.load(device.key_id)
    assert loaded is not None
    assert loaded.counter == 5


@pytest.mark.parametrize(
    "record",
    [
        {"public_key": "%%%", "environment": "production", "counter": "0"},
        {"public_key": b64(b"\x04"), "environment": "staging", "counter": "0"},
        {"public_key": b64(b"\x04"), "environment": "production", "counter": "x"},
        {"public_key": b64(b"\x04"), "environment": "production"},
    ],
    ids=["key-not-base64", "unknown-environment", "counter-not-a-number", "field-missing"],
)
def test_a_record_this_code_did_not_write_is_not_a_key(
    record: dict[str, str], device: Device
) -> None:
    client = fakeredis.FakeStrictRedis()
    store = RedisAppAttestKeyStore(client)
    client.hset(f"auth:appattest:{device.key_id}", mapping=record)
    assert store.load(device.key_id) is None


# --- the router and the fail-closed defaults ------------------------------------------------


def _payload(mode: str, platform: str = "ios", **extra: Any) -> AttestationPayload:
    return AttestationPayload.model_validate(
        {
            "platform": platform,
            "mode": mode,
            "token": b64(b"intake-dev-attest"),
            "device_id": "device-a",
            "nonce": "challenge",
            **extra,
        }
    )


def test_the_fail_closed_verifier_keeps_its_default_and_carries_a_typed_reason() -> None:
    assert FailClosedAttestationVerifier().verify(
        _payload("app-attest"), client_data=REQUEST
    ).reason is (AttestationReason.BACKEND_NOT_WIRED)
    typed = FailClosedAttestationVerifier(AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED)
    result = typed.verify(_payload("play-integrity", "android"), client_data=REQUEST)
    assert not result.ok
    assert result.reason is AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED


def test_the_router_sends_each_mode_to_its_own_verifier() -> None:
    router = PlatformAttestationVerifier(
        app_attest=FailClosedAttestationVerifier(AttestationReason.APP_ATTEST_NOT_CONFIGURED),
        play_integrity=FailClosedAttestationVerifier(
            AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED
        ),
    )
    cases = {
        ("app-attest", "ios"): AttestationReason.APP_ATTEST_NOT_CONFIGURED,
        ("play-integrity", "android"): AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED,
        ("dev-unattested", "ios"): AttestationReason.DEV_UNATTESTED_REFUSED,
        ("app-attest", "android"): AttestationReason.MODE_PLATFORM_MISMATCH,
        ("play-integrity", "ios"): AttestationReason.MODE_PLATFORM_MISMATCH,
    }
    for (mode, platform), reason in cases.items():
        result = router.verify(_payload(mode, platform), client_data=REQUEST)
        assert not result.ok
        assert result.reason is reason, (mode, platform)


def test_the_router_reaches_the_dev_tier_only_when_it_is_wired() -> None:
    router = PlatformAttestationVerifier(
        app_attest=FailClosedAttestationVerifier(AttestationReason.APP_ATTEST_NOT_CONFIGURED),
        play_integrity=FailClosedAttestationVerifier(
            AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED
        ),
        dev=DevStructuralAttestationVerifier(),
    )
    assert router.verify(_payload("dev-unattested"), client_data=REQUEST).ok
    # the dev tier never waves a claimed real mode through
    assert not router.verify(_payload("app-attest"), client_data=REQUEST).ok


def _settings(**overrides: Any) -> ApiSettings:
    base: dict[str, Any] = {
        "token_patient": None,
        "token_admin": None,
        "app_db_url": "sqlite+aiosqlite:///unused.db",
        "audit_db_url": "sqlite+pysqlite:///unused-audit.db",
        "bootstrap_db_url": "sqlite+aiosqlite:///unused.db",
        "kek_mode": "file-dev",
        "tokenization_key": "unit-lane-tokenization-key",
    }
    base.update(overrides)
    return ApiSettings(**base)


def test_with_no_apple_config_every_real_mode_fails_closed_with_its_reason() -> None:
    wiring = _auth_from_settings(_settings())
    assert wiring is not None
    for (mode, platform), reason in {
        ("app-attest", "ios"): AttestationReason.APP_ATTEST_NOT_CONFIGURED,
        ("play-integrity", "android"): AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED,
        ("dev-unattested", "ios"): AttestationReason.DEV_UNATTESTED_REFUSED,
    }.items():
        result = wiring.attestation.verify(_payload(mode, platform), client_data=REQUEST)
        assert result.reason is reason, mode
    registration = wiring.key_attestation.register("a2V5", "dG9rZW4=", client_data=REGISTER)
    assert registration.reason is AttestationReason.APP_ATTEST_NOT_CONFIGURED


def test_a_configured_team_wires_app_attest_against_the_pinned_apple_root(
    device: Device,
) -> None:
    wiring = _auth_from_settings(_settings(app_attest_team_id=TEAM_ID))
    assert wiring is not None
    # a synthetic chain is refused on the CHAIN — the production verifier is
    # live and trusts Apple's root, not the test root this device chains to
    result = wiring.key_attestation.register(
        device.key_id, device.attest(REGISTER), client_data=REGISTER
    )
    assert result.reason is AttestationReason.APP_ATTEST_CHAIN
    # Play Integrity has no decoder until HB-A3 and stays closed, typed
    android = wiring.attestation.verify(_payload("play-integrity", "android"), client_data=REQUEST)
    assert android.reason is AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED


def test_a_malformed_team_id_fails_closed_rather_than_half_configuring() -> None:
    wiring = _auth_from_settings(_settings(app_attest_team_id="not-a-team"))
    assert wiring is not None
    result = wiring.attestation.verify(_payload("app-attest"), client_data=REQUEST)
    assert result.reason is AttestationReason.APP_ATTEST_CONFIG_INVALID


def test_the_apple_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "INTAKE_APP_ATTEST_TEAM_ID",
        "INTAKE_APP_ATTEST_BUNDLE_ID",
        "INTAKE_APP_ATTEST_ENVIRONMENT",
    ):
        monkeypatch.delenv(name, raising=False)
    unset = ApiSettings.from_env()
    assert unset.app_attest_team_id is None
    assert unset.app_attest_bundle_id == BUNDLE_ID
    assert unset.app_attest_environment is None

    monkeypatch.setenv("INTAKE_APP_ATTEST_TEAM_ID", TEAM_ID)
    monkeypatch.setenv("INTAKE_APP_ATTEST_BUNDLE_ID", "com.example.staging")
    monkeypatch.setenv("INTAKE_APP_ATTEST_ENVIRONMENT", "development")
    configured = ApiSettings.from_env()
    assert configured.app_attest_team_id == TEAM_ID
    assert configured.app_attest_bundle_id == "com.example.staging"
    assert configured.app_attest_environment == "development"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, AppAttestEnvironment.PRODUCTION),
        ("", AppAttestEnvironment.PRODUCTION),
        ("development", AppAttestEnvironment.DEVELOPMENT),
    ],
)
def test_production_is_the_environment_unless_development_is_explicit(
    raw: str | None, expected: AppAttestEnvironment
) -> None:
    assert AppAttestConfig.parse(TEAM_ID, BUNDLE_ID, raw).environment is expected


@pytest.mark.parametrize(
    ("team_id", "bundle_id", "environment"),
    [
        ("abcde12345", BUNDLE_ID, None),  # team ids are upper-case
        ("ABCDE1234", BUNDLE_ID, None),  # and ten characters
        (TEAM_ID, "intakemobile", None),  # a bundle id is reverse-DNS
        (TEAM_ID, BUNDLE_ID, "Development"),  # the environment word is exact
        (TEAM_ID, BUNDLE_ID, "staging"),
    ],
)
def test_malformed_apple_config_is_refused(
    team_id: str, bundle_id: str, environment: str | None
) -> None:
    with pytest.raises(AppAttestConfigError):
        AppAttestConfig.parse(team_id, bundle_id, environment)


def test_client_data_binds_purpose_and_challenge() -> None:
    assert attestation_client_data("otp.request", "abc") == "intake.attest.v1|otp.request|abc"
    assert attestation_client_data("otp.request", "abc") != attestation_client_data(
        "otp.verify", "abc"
    )


# --- Play Integrity: the verdict policy (no Google fixture exists until HB-A3) --------------

PACKAGE = "com.ariomoniri.intakemobile"


class DecodedVerdicts:
    """Test decoder: Google's decode call needs the HB-A3 service account, so
    the policy is exercised against decoded verdict payloads directly."""

    def __init__(self, verdicts: Mapping[str, Mapping[str, Any]]) -> None:
        self._verdicts = verdicts

    def decode(self, token: str) -> Mapping[str, Any]:
        if token not in self._verdicts:
            raise PlayIntegrityDecodeError("unknown token")
        return self._verdicts[token]


def _verdict(**changes: Any) -> dict[str, Any]:
    verdict: dict[str, Any] = {
        "requestDetails": {
            "requestPackageName": PACKAGE,
            "requestHash": play_integrity_request_hash(REQUEST),
            "timestampMillis": str(int(NOW.timestamp() * 1000) - 5_000),
        },
        "appIntegrity": {"appRecognitionVerdict": "PLAY_RECOGNIZED", "packageName": PACKAGE},
        "deviceIntegrity": {"deviceRecognitionVerdict": ["MEETS_DEVICE_INTEGRITY"]},
    }
    for path, value in changes.items():
        section, name = path.split("__")
        if value is None:
            verdict[section].pop(name, None)
        else:
            verdict[section][name] = value
    return verdict


@pytest.fixture()
def play() -> Iterator[PlayIntegrityVerifier]:
    yield PlayIntegrityVerifier(
        PlayIntegrityConfig(package_name=PACKAGE),
        DecodedVerdicts(
            {
                "good": _verdict(),
                "other-package": _verdict(requestDetails__requestPackageName="com.evil"),
                "other-request": _verdict(
                    requestDetails__requestHash=play_integrity_request_hash(VERIFY)
                ),
                "stale": _verdict(
                    requestDetails__timestampMillis=str(
                        int(NOW.timestamp() * 1000) - (CHALLENGE_TTL_S + 1) * 1000
                    )
                ),
                "unrecognized-app": _verdict(
                    appIntegrity__appRecognitionVerdict="UNRECOGNIZED_VERSION"
                ),
                "no-device-integrity": _verdict(deviceIntegrity__deviceRecognitionVerdict=None),
                "blank-device-verdict": _verdict(deviceIntegrity__deviceRecognitionVerdict=[]),
                "basic-integrity-only": _verdict(
                    deviceIntegrity__deviceRecognitionVerdict=["MEETS_BASIC_INTEGRITY"]
                ),
                "other-app-package": _verdict(appIntegrity__packageName="com.evil"),
                "future-timestamp": _verdict(
                    requestDetails__timestampMillis=str(
                        int(NOW.timestamp() * 1000) + (CHALLENGE_TTL_S + 1) * 1000
                    )
                ),
                "no-timestamp": _verdict(requestDetails__timestampMillis=None),
            }
        ),
        now_fn=NOW.timestamp,
    )


def _android(token: str) -> AttestationPayload:
    return _payload("play-integrity", "android").model_copy(update={"token": token})


def test_a_recognized_app_on_an_integral_device_passes_the_policy(
    play: PlayIntegrityVerifier,
) -> None:
    result = play.verify(_android("good"), client_data=REQUEST)
    assert result.ok
    assert result.reason is AttestationReason.PLAY_INTEGRITY_VERDICT


@pytest.mark.parametrize(
    ("token", "reason"),
    [
        ("other-package", AttestationReason.PLAY_INTEGRITY_REQUEST),
        ("other-request", AttestationReason.PLAY_INTEGRITY_REQUEST),
        ("stale", AttestationReason.PLAY_INTEGRITY_STALE),
        ("unrecognized-app", AttestationReason.PLAY_INTEGRITY_APP),
        ("no-device-integrity", AttestationReason.PLAY_INTEGRITY_DEVICE),
        ("blank-device-verdict", AttestationReason.PLAY_INTEGRITY_DEVICE),
        ("basic-integrity-only", AttestationReason.PLAY_INTEGRITY_DEVICE),
        ("other-app-package", AttestationReason.PLAY_INTEGRITY_APP),
        ("future-timestamp", AttestationReason.PLAY_INTEGRITY_STALE),
        ("no-timestamp", AttestationReason.PLAY_INTEGRITY_STALE),
        ("undecodable", AttestationReason.PLAY_INTEGRITY_MALFORMED),
    ],
)
def test_every_play_integrity_check_refuses_on_its_own(
    play: PlayIntegrityVerifier, token: str, reason: AttestationReason
) -> None:
    result = play.verify(_android(token), client_data=REQUEST)
    assert not result.ok
    assert result.reason is reason


def test_the_play_verifier_refuses_ios_payloads(play: PlayIntegrityVerifier) -> None:
    ios = _payload("play-integrity", "ios").model_copy(update={"token": "good"})
    assert play.verify(ios, client_data=REQUEST).reason is (
        AttestationReason.MODE_PLATFORM_MISMATCH
    )
