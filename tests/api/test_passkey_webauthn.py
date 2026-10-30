"""INT-582 — the WebAuthn verifier for patient passkeys, one check at a time.

Every refusal is proven on its own with the bytes a real authenticator would
produce and ONE knob turned (passkey_testkit), and every refusal has its near
miss beside it: the nearest input that must still pass. A verifier that refused
everything would pass the first half of this file and fail the second.

Sec row: onboarding (files/10 §9 — "passkeys").
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import cbor2
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).resolve().parent))

from intake_api.passkey.webauthn import (  # noqa: E402
    PasskeyConfig,
    PasskeyConfigError,
    PasskeyReason,
    PasskeyRefused,
    StoredCredential,
    b64url_decode,
    client_data_challenge,
    sign_count_advances,
    verify_assertion,
    verify_registration,
)
from passkey_testkit import (  # noqa: E402
    FLAG_AT,
    FLAG_BS,
    FLAG_ED,
    FLAG_UP,
    FLAG_UV,
    ORIGIN,
    RP_ID,
    Authenticator,
    b64url,
)

CONFIG = PasskeyConfig(rp_id=RP_ID, origins=frozenset({ORIGIN}))
CHALLENGE = os.urandom(32)
HANDLE = os.urandom(32)


def _creation_options(challenge: bytes = CHALLENGE) -> dict[str, object]:
    return {
        "challenge": b64url(challenge),
        "rp": {"id": RP_ID, "name": "Önvizit"},
        "user": {"id": b64url(HANDLE), "name": "Önvizit", "displayName": "Önvizit"},
    }


def _register(device: Authenticator, response: dict[str, object] | None = None):  # type: ignore[no-untyped-def]
    body = response if response is not None else device.register(_creation_options())
    inner = body["response"]
    assert isinstance(inner, dict)
    return verify_registration(
        config=CONFIG,
        expected_challenge=CHALLENGE,
        credential_id=str(body["rawId"]),
        client_data_json=b64url_decode(inner["clientDataJSON"]),
        attestation_object=b64url_decode(inner["attestationObject"]),
    )


def _refused(reason: PasskeyReason, call) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PasskeyRefused) as caught:
        call()
    assert caught.value.reason is reason


# --- registration ------------------------------------------------------------------------


def test_a_platform_passkey_registers_and_leaves_only_its_public_half() -> None:
    device = Authenticator()
    registered = _register(device)
    numbers = device.key.public_key().public_numbers()
    assert registered.credential_id == device.credential_id
    assert registered.public_key == (
        b"\x04" + numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    )
    assert registered.sign_count == 0
    assert registered.backup_eligible and registered.backup_state


def test_a_device_bound_passkey_registers_with_its_backup_flags_clear() -> None:
    registered = _register(Authenticator(backed_up=False, counter=7))
    assert (registered.backup_eligible, registered.backup_state) == (False, False)
    assert registered.sign_count == 7


def test_registration_refuses_the_get_ceremony() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), ceremony="webauthn.get")
    _refused(PasskeyReason.CEREMONY, lambda: _register(device, response))


def test_registration_refuses_another_challenge() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), challenge=b64url(os.urandom(32)))
    _refused(PasskeyReason.CHALLENGE, lambda: _register(device, response))


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        f"http://{RP_ID}",  # the scheme
        f"https://{RP_ID}:8443",  # the port
        f"https://{RP_ID}/",  # a path
        "https://sslip.io",  # the parent domain
        f"https://x{RP_ID}",  # a lookalike, not a subdomain
    ],
)
def test_registration_refuses_an_origin_that_is_not_configured(origin: str) -> None:
    device = Authenticator()
    response = device.register(_creation_options(), origin=origin)
    _refused(PasskeyReason.ORIGIN, lambda: _register(device, response))


def test_registration_refuses_a_cross_origin_ceremony() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), cross_origin=True)
    _refused(PasskeyReason.CROSS_ORIGIN, lambda: _register(device, response))


def test_a_cross_origin_member_that_is_not_the_boolean_false_is_refused() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), cross_origin="false")
    _refused(PasskeyReason.CROSS_ORIGIN, lambda: _register(device, response))


def test_near_miss_an_explicit_cross_origin_false_registers() -> None:
    device = Authenticator()
    assert _register(device, device.register(_creation_options(), cross_origin=False))


@pytest.mark.parametrize("rp_id", ["sslip.io", "evil.example", "3-211-2-143.sslip.io.evil"])
def test_registration_refuses_another_rp_id(rp_id: str) -> None:
    device = Authenticator(rp_id=rp_id)
    _refused(PasskeyReason.RP_ID, lambda: _register(device))


def test_registration_refuses_without_user_presence() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), up=False)
    _refused(PasskeyReason.USER_PRESENCE, lambda: _register(device, response))


def test_registration_refuses_without_user_verification() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), uv=False)
    _refused(PasskeyReason.USER_VERIFICATION, lambda: _register(device, response))


def test_backed_up_without_backup_eligible_is_refused() -> None:
    device = Authenticator(backed_up=False)
    response = device.register(_creation_options(), flags=FLAG_UP | FLAG_UV | FLAG_AT | FLAG_BS)
    _refused(PasskeyReason.BACKUP_FLAGS, lambda: _register(device, response))


@pytest.mark.parametrize("fmt", ["packed", "apple", "android-key", "tpm", "fido-u2f"])
def test_registration_refuses_any_attestation_format_but_none(fmt: str) -> None:
    device = Authenticator()
    response = device.register(_creation_options(), fmt=fmt)
    _refused(PasskeyReason.ATTESTATION_FORMAT, lambda: _register(device, response))


def test_format_none_with_a_statement_is_refused() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), att_stmt={"alg": -7})
    _refused(PasskeyReason.ATTESTATION_FORMAT, lambda: _register(device, response))


@pytest.mark.parametrize("alg", [-257, -8, -35])
def test_registration_refuses_every_algorithm_but_es256(alg: int) -> None:
    device = Authenticator()
    response = device.register(_creation_options(), cose=device.cose_key(alg=alg))
    _refused(PasskeyReason.ALGORITHM, lambda: _register(device, response))


def test_a_cose_key_with_an_extra_parameter_is_refused() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), cose=device.cose_key(extra={2: b"kid"}))
    _refused(PasskeyReason.ALGORITHM, lambda: _register(device, response))


def test_a_point_off_the_curve_is_refused() -> None:
    device = Authenticator()
    off_curve = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: b"\x01" * 32, -3: b"\x02" * 32})
    response = device.register(_creation_options(), cose=off_curve)
    _refused(PasskeyReason.MALFORMED, lambda: _register(device, response))


def test_the_credential_id_must_be_the_one_the_response_names() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), raw_id=os.urandom(20))
    _refused(PasskeyReason.CREDENTIAL_ID, lambda: _register(device, response))


@pytest.mark.parametrize("length", [0, 1024])
def test_a_credential_id_outside_one_to_1023_bytes_is_refused(length: int) -> None:
    device = Authenticator(credential_id=os.urandom(length))
    _refused(PasskeyReason.CREDENTIAL_ID, lambda: _register(device))


def test_bytes_after_the_key_without_the_extension_flag_are_refused() -> None:
    device = Authenticator()
    response = device.register(_creation_options(), trailing=b"\x00")
    _refused(PasskeyReason.MALFORMED, lambda: _register(device, response))


def test_near_miss_an_extensions_map_under_the_extension_flag_registers() -> None:
    device = Authenticator()
    flags = device.flags(up=True, uv=True, attested=True) | FLAG_ED
    response = device.register(
        _creation_options(), flags=flags, trailing=cbor2.dumps({"credProtect": 2})
    )
    assert _register(device, response).credential_id == device.credential_id


def test_an_attestation_object_with_another_member_is_refused() -> None:
    device = Authenticator()
    response = device.register(_creation_options())
    inner = response["response"]
    decoded = cbor2.loads(b64url_decode(inner["attestationObject"]))
    decoded["extra"] = 1
    inner["attestationObject"] = b64url(cbor2.dumps(decoded))
    _refused(PasskeyReason.MALFORMED, lambda: _register(device, response))


def test_client_data_with_a_duplicate_member_is_refused() -> None:
    device = Authenticator()
    response = device.register(_creation_options())
    raw = b64url_decode(response["response"]["clientDataJSON"]).decode("utf-8")
    duplicated = raw[:-1] + ',"origin":"https://evil.example"}'
    response["response"]["clientDataJSON"] = b64url(duplicated.encode("utf-8"))
    _refused(PasskeyReason.MALFORMED, lambda: _register(device, response))


def test_client_data_that_is_not_an_object_is_refused() -> None:
    device = Authenticator()
    response = device.register(_creation_options())
    response["response"]["clientDataJSON"] = b64url(json.dumps(["webauthn.create"]).encode())
    _refused(PasskeyReason.MALFORMED, lambda: _register(device, response))


def test_the_challenge_is_read_from_client_data_strictly() -> None:
    device = Authenticator()
    raw = device.client_data("webauthn.create", b64url(CHALLENGE))
    assert client_data_challenge(raw) == CHALLENGE
    padded = device.client_data("webauthn.create", b64url(CHALLENGE) + "=")
    _refused(PasskeyReason.MALFORMED, lambda: client_data_challenge(padded))


# --- assertion -----------------------------------------------------------------------------


def _stored(device: Authenticator, sign_count: int = 0) -> StoredCredential:
    registered = _register(device)
    return StoredCredential(
        credential_id=registered.credential_id,
        public_key=registered.public_key,
        sign_count=sign_count,
        user_handle=HANDLE,
        backup_eligible=registered.backup_eligible,
    )


def _assert(device: Authenticator, credential: StoredCredential, **knobs):  # type: ignore[no-untyped-def]
    body = device.assertion({"challenge": b64url(CHALLENGE)}, **knobs)
    inner = body["response"]
    handle = inner.get("userHandle")
    return verify_assertion(
        config=CONFIG,
        expected_challenge=CHALLENGE,
        credential=credential,
        client_data_json=b64url_decode(inner["clientDataJSON"]),
        authenticator_data=b64url_decode(inner["authenticatorData"]),
        signature=b64url_decode(inner["signature"]),
        user_handle=None if handle is None else b64url_decode(handle),
    )


def test_a_synced_passkey_asserts_with_a_zero_counter() -> None:
    device = Authenticator()
    credential = _stored(device)
    assert _assert(device, credential).sign_count == 0


def test_an_assertion_signed_by_another_key_is_refused() -> None:
    # another account's credential presented under this one's id
    device = Authenticator()
    credential = _stored(device)
    other = ec.generate_private_key(ec.SECP256R1())
    _refused(PasskeyReason.SIGNATURE, lambda: _assert(device, credential, signing_key=other))


def test_a_tampered_signature_is_refused() -> None:
    device = Authenticator()
    credential = _stored(device)
    _refused(PasskeyReason.SIGNATURE, lambda: _assert(device, credential, tamper=True))


def test_assertion_refuses_the_create_ceremony() -> None:
    device = Authenticator()
    credential = _stored(device)
    _refused(
        PasskeyReason.CEREMONY, lambda: _assert(device, credential, ceremony="webauthn.create")
    )


def test_assertion_refuses_another_origin() -> None:
    device = Authenticator()
    credential = _stored(device)
    _refused(
        PasskeyReason.ORIGIN, lambda: _assert(device, credential, origin="https://evil.example")
    )


def test_assertion_refuses_another_rp_id() -> None:
    device = Authenticator()
    credential = _stored(device)
    _refused(PasskeyReason.RP_ID, lambda: _assert(device, credential, rp_id="evil.example"))


def test_assertion_refuses_without_user_verification() -> None:
    device = Authenticator()
    credential = _stored(device)
    _refused(PasskeyReason.USER_VERIFICATION, lambda: _assert(device, credential, uv=False))


def test_assertion_refuses_attested_credential_data() -> None:
    device = Authenticator()
    credential = _stored(device)
    flags = device.flags(up=True, uv=True, attested=False) | FLAG_AT
    _refused(PasskeyReason.MALFORMED, lambda: _assert(device, credential, flags=flags))


def test_assertion_refuses_another_user_handle() -> None:
    device = Authenticator()
    credential = _stored(device)
    _refused(
        PasskeyReason.USER_HANDLE,
        lambda: _assert(device, credential, user_handle=os.urandom(32)),
    )


def test_near_miss_an_assertion_without_a_user_handle_passes() -> None:
    device = Authenticator()
    credential = _stored(device)
    assert _assert(device, credential, user_handle=None).sign_count == 0


@pytest.mark.parametrize(("stored", "presented"), [(5, 5), (5, 4), (3, 0)])
def test_a_counter_that_does_not_move_forward_is_refused(stored: int, presented: int) -> None:
    device = Authenticator(backed_up=False, counter=presented)
    credential = _stored(Authenticator(key=device.key, credential_id=device.credential_id))
    credential = StoredCredential(
        credential_id=credential.credential_id,
        public_key=credential.public_key,
        sign_count=stored,
        user_handle=HANDLE,
        backup_eligible=False,
    )
    _refused(PasskeyReason.SIGN_COUNT, lambda: _assert(device, credential))


@pytest.mark.parametrize(("stored", "presented"), [(5, 6), (0, 1), (0, 0)])
def test_near_miss_a_counter_that_moves_forward_or_stays_at_zero_passes(
    stored: int, presented: int
) -> None:
    device = Authenticator(backed_up=False, counter=presented)
    base = _stored(Authenticator(key=device.key, credential_id=device.credential_id))
    credential = StoredCredential(
        credential_id=base.credential_id,
        public_key=base.public_key,
        sign_count=stored,
        user_handle=HANDLE,
        backup_eligible=False,
    )
    assert _assert(device, credential).sign_count == presented


def test_the_counter_rule_is_webauthn_6_1_1() -> None:
    assert sign_count_advances(0, 0)
    assert sign_count_advances(0, 9)
    assert sign_count_advances(9, 10)
    assert not sign_count_advances(9, 9)
    assert not sign_count_advances(9, 0)


# --- configuration ------------------------------------------------------------------------


def test_configuration_requires_both_values() -> None:
    for rp_id, origins in ((None, ORIGIN), (RP_ID, None), ("", ""), (RP_ID, " , ")):
        with pytest.raises(PasskeyConfigError):
            PasskeyConfig.parse(rp_id, origins)


def test_a_subdomain_origin_is_accepted_and_parsed_from_a_list() -> None:
    config = PasskeyConfig.parse(RP_ID, f"{ORIGIN}, https://app.{RP_ID}")
    assert config.origins == {ORIGIN, f"https://app.{RP_ID}"}


@pytest.mark.parametrize(
    "origin",
    [f"http://{RP_ID}", f"https://{RP_ID}:443", f"https://{RP_ID}/path", "https://sslip.io"],
)
def test_configuration_refuses_an_origin_off_the_rp_id(origin: str) -> None:
    with pytest.raises(PasskeyConfigError):
        PasskeyConfig.parse(RP_ID, origin)


@pytest.mark.parametrize("rp_id", ["3-211-2-143.SSLIP.IO", "localhost", "https://x.example"])
def test_configuration_refuses_an_rp_id_that_is_not_a_dns_name(rp_id: str) -> None:
    with pytest.raises(PasskeyConfigError):
        PasskeyConfig.parse(rp_id, f"https://{rp_id}")


@pytest.mark.parametrize("value", ["YQ==", "a+b/", "a b", "a"])
def test_base64url_is_strict(value: str) -> None:
    _refused(PasskeyReason.MALFORMED, lambda: b64url_decode(value))


# --- review fixes: CBOR semantic tags, and BE against the stored value ---------------


@pytest.mark.parametrize(
    "where",
    ["attestation object", "attestation member", "COSE key value", "extensions value"],
)
def test_every_cbor_semantic_tag_is_refused(where: str) -> None:
    """cbor2 decodes the tags it knows (an epoch date, a bignum, a URI)
    silently, so a refusal by type after decoding would miss them; the shape
    walker refuses major type 6 wherever it sits."""
    device = Authenticator()
    if where == "attestation object":
        response = device.register(_creation_options())
        inner = response["response"]
        decoded = cbor2.loads(b64url_decode(inner["attestationObject"]))
        inner["attestationObject"] = b64url(cbor2.dumps(cbor2.CBORTag(55799, decoded)))
    elif where == "attestation member":
        response = device.register(_creation_options())
        inner = response["response"]
        decoded = cbor2.loads(b64url_decode(inner["attestationObject"]))
        decoded["fmt"] = cbor2.CBORTag(32, "none")
        inner["attestationObject"] = b64url(cbor2.dumps(decoded))
    elif where == "COSE key value":
        numbers = device.key.public_key().public_numbers()
        cose = cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: cbor2.CBORTag(24, numbers.x.to_bytes(32, "big")),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )
        response = device.register(_creation_options(), cose=cose)
    else:
        flags = device.flags(up=True, uv=True, attested=True) | FLAG_ED
        response = device.register(
            _creation_options(),
            flags=flags,
            trailing=cbor2.dumps({"credProtect": cbor2.CBORTag(1, 2)}),
        )
    _refused(PasskeyReason.MALFORMED, lambda: _register(device, response))


def test_near_miss_the_same_shapes_untagged_register() -> None:
    device = Authenticator()
    flags = device.flags(up=True, uv=True, attested=True) | FLAG_ED
    response = device.register(
        _creation_options(), flags=flags, trailing=cbor2.dumps({"credProtect": 2})
    )
    assert _register(device, response).credential_id == device.credential_id


def test_backup_eligibility_must_match_the_stored_value_at_assertion() -> None:
    """BE is fixed for a credential's life (WebAuthn §6.1.3); a flip is a
    different authenticator answering under this credential id."""
    device = Authenticator(backed_up=False)
    registered = _register(device)
    flipped = StoredCredential(
        credential_id=registered.credential_id,
        public_key=registered.public_key,
        sign_count=0,
        user_handle=HANDLE,
        backup_eligible=True,
    )
    _refused(PasskeyReason.BACKUP_FLAGS, lambda: _assert(device, flipped))
    same = StoredCredential(
        credential_id=registered.credential_id,
        public_key=registered.public_key,
        sign_count=0,
        user_handle=HANDLE,
        backup_eligible=False,
    )
    assert _assert(device, same).sign_count == 0
