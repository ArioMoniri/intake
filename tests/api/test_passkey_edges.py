"""INT-582 — the passkey tier's edges: malformed bytes, shapes off the
documented one, the tier boundaries, and the counter race.

Every malformed input below is refused as ``passkey_malformed`` and never
raises past the verifier; each sits next to the well-formed input it was
derived from (which the other files prove passes).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import cbor2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from intake_api.passkey.gate import GRANT_HEADER  # noqa: E402
from intake_api.passkey.webauthn import (  # noqa: E402
    PasskeyConfig,
    PasskeyReason,
    PasskeyRefused,
    verify_registration,
)
from passkey_harness import PasskeyKit, build_passkey_kit  # noqa: E402
from passkey_testkit import (  # noqa: E402
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
RP_HASH = hashlib.sha256(RP_ID.encode("ascii")).digest()


def _client_data() -> bytes:
    return Authenticator().client_data("webauthn.create", b64url(CHALLENGE))


def _attestation(auth_data: Any, fmt: Any = "none", statement: Any = None) -> bytes:
    return cbor2.dumps(
        {"fmt": fmt, "attStmt": {} if statement is None else statement, "authData": auth_data}
    )


def _verify(attestation: bytes, client_data: bytes | None = None, raw_id: str = "AA") -> None:
    verify_registration(
        config=CONFIG,
        expected_challenge=CHALLENGE,
        credential_id=raw_id,
        client_data_json=_client_data() if client_data is None else client_data,
        attestation_object=attestation,
    )


def _with_cred(rest: bytes, flags: int = FLAG_UP | FLAG_UV | 0x40) -> bytes:
    return RP_HASH + bytes([flags]) + b"\x00\x00\x00\x00" + rest


MALFORMED: dict[str, Callable[[], None]] = {
    "client data not utf-8": lambda: _verify(b"", client_data=b"\xff\xfe"),
    "client data missing origin": lambda: _verify(
        b"", client_data=json.dumps({"type": "webauthn.create", "challenge": "AA"}).encode()
    ),
    "attestation not cbor": lambda: _verify(b"\xff"),
    "attestation trailing bytes": lambda: _verify(
        _attestation(Authenticator().auth_data(attested=True)) + b"\x00"
    ),
    "attestation a list": lambda: _verify(cbor2.dumps(["none", {}, b""])),
    "fmt not text": lambda: _verify(_attestation(b"\x00" * 37, fmt=1)),
    "statement not a map": lambda: _verify(_attestation(b"\x00" * 37, statement=[])),
    "auth data not bytes": lambda: _verify(_attestation("auth")),
    "auth data short": lambda: _verify(_attestation(b"\x00" * 36)),
    "registration without attested data": lambda: _verify(
        _attestation(_with_cred(b"", flags=FLAG_UP | FLAG_UV))
    ),
    "attested data truncated": lambda: _verify(_attestation(_with_cred(b"\x00" * 17))),
    "credential id truncated": lambda: _verify(
        _attestation(_with_cred(b"\x00" * 16 + (20).to_bytes(2, "big") + b"\x01" * 5))
    ),
    "cose key a list": lambda: _verify(
        _attestation(
            _with_cred(b"\x00" * 16 + (1).to_bytes(2, "big") + b"\x01" + cbor2.dumps([2, -7]))
        )
    ),
    "cose coordinate short": lambda: _verify(
        _attestation(
            _with_cred(
                b"\x00" * 16
                + (1).to_bytes(2, "big")
                + b"\x01"
                + cbor2.dumps({1: 2, 3: -7, -1: 1, -2: b"\x01" * 31, -3: b"\x02" * 32})
            )
        )
    ),
    "extension flag with nothing after": lambda: _verify(
        _attestation(
            Authenticator().auth_data(attested=True, flags=FLAG_UP | FLAG_UV | 0x40 | FLAG_ED)
        )
    ),
    "extensions with a non-text key": lambda: _verify(
        _attestation(
            Authenticator().auth_data(
                attested=True,
                flags=FLAG_UP | FLAG_UV | 0x40 | FLAG_ED,
                trailing=cbor2.dumps({1: True}),
            )
        )
    ),
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_malformed_bytes_are_refused_as_malformed(case: str) -> None:
    with pytest.raises(PasskeyRefused) as caught:
        MALFORMED[case]()
    assert caught.value.reason in (PasskeyReason.MALFORMED, PasskeyReason.ALGORITHM)


# --- the HTTP edges ----------------------------------------------------------------------


@pytest.fixture()
def kit(tmp_path: Path) -> Iterator[PasskeyKit]:
    yield from build_passkey_kit(tmp_path)


@pytest.fixture()
def unwired(tmp_path: Path) -> Iterator[PasskeyKit]:
    yield from build_passkey_kit(tmp_path, passkey_wired=False)


def test_the_dev_bearer_tier_can_neither_finish_an_enrolment_nor_start_a_recovery(
    kit: PasskeyKit,
) -> None:
    session = kit.sign_in()
    options = kit.call(session, "POST", "/v1/me/passkeys/registration/options").json()
    credential = Authenticator().register(options)
    refused = kit.call(
        None, "POST", "/v1/me/passkeys/registration", json_body={"credential": credential}
    )
    assert refused.json() == {"error": "passkey_otp_session_required"}
    assert kit.call(None, "POST", "/v1/me/passkeys/recovery").status_code == 403


def test_an_id_that_is_not_the_raw_id_is_refused(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    device = Authenticator()
    options = kit.call(session, "POST", "/v1/me/passkeys/registration/options").json()
    credential = device.register(options)
    credential["id"] = b64url(os.urandom(20))
    refused = kit.call(
        session, "POST", "/v1/me/passkeys/registration", json_body={"credential": credential}
    )
    assert refused.status_code == 400
    assert refused.json()["reason"] == "passkey_malformed"
    assert kit.register(session, device).status_code == 201
    step = kit.step_up_options(session, "data_delete").json()
    assertion = device.assertion(step)
    assertion["id"] = b64url(os.urandom(20))
    refused_step = kit.finish_step_up(session, "data_delete", assertion)
    assert refused_step.status_code == 403
    assert refused_step.json()["reason"] == "passkey_malformed"
    # both refusals are on the chain, and the step-up's challenge was not spent
    actions = [action for action, _, _ in kit.audit_actions()]
    assert "passkey.register.refused" in actions and "passkey.step_up.refused" in actions
    assertion["id"] = assertion["rawId"]
    assert kit.finish_step_up(session, "data_delete", assertion).status_code == 200


def test_client_data_that_is_not_base64url_is_refused_at_both_ceremonies(
    kit: PasskeyKit,
) -> None:
    session = kit.sign_in()
    device = Authenticator()
    options = kit.call(session, "POST", "/v1/me/passkeys/registration/options").json()
    credential = device.register(options)
    credential["response"]["clientDataJSON"] = "not base64url!"
    refused = kit.call(
        session, "POST", "/v1/me/passkeys/registration", json_body={"credential": credential}
    )
    assert refused.json()["reason"] == "passkey_malformed"
    assert kit.register(session, device).status_code == 201
    step = kit.step_up_options(session, "data_delete").json()
    assertion = device.assertion(step)
    assertion["response"]["signature"] = "+/="
    refused = kit.finish_step_up(session, "data_delete", assertion)
    assert refused.json()["reason"] == "passkey_malformed"


def test_a_counter_race_lost_to_another_step_up_is_refused(
    kit: PasskeyKit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two step-ups verified against one stored counter: the compare-and-set
    lets exactly one move it. The loser is refused as a counter failure."""
    session = kit.sign_in()
    device = Authenticator()
    assert kit.register(session, device).status_code == 201
    from intake_api.passkey import store

    async def lost(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(store, "advance_sign_count", lost)
    refused = kit.step_up(session, device, "data_delete")
    assert refused.status_code == 403
    assert refused.json()["reason"] == "passkey_sign_count"


def test_removing_or_cancelling_nothing_is_not_found(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    device = Authenticator()
    assert kit.register(session, device).status_code == 201
    grant = kit.grant(session, device, "passkey_remove")
    gone = kit.call(
        session,
        "DELETE",
        "/v1/me/passkeys/00000000-0000-4000-8000-000000000000",
        headers={GRANT_HEADER: grant},
    )
    assert gone.status_code == 404
    grant = kit.grant(session, device, "recovery_cancel")
    nothing = kit.call(session, "DELETE", "/v1/me/passkeys/recovery", headers={GRANT_HEADER: grant})
    assert nothing.status_code == 404


def test_unwired_step_up_options_keep_a_patient_without_a_passkey_on_the_otp_tier(
    unwired: PasskeyKit,
) -> None:
    session = unwired.sign_in()
    options = unwired.step_up_options(session, "data_delete")
    assert options.json() == {"enrolled": False, "tier": "otp_session", "enrolment": "unavailable"}
    for method, path in (
        ("GET", "/v1/me/passkeys"),
        ("POST", "/v1/me/passkeys/recovery"),
        ("POST", "/v1/me/passkeys/registration/options"),
    ):
        assert unwired.call(session, method, path).status_code == 503, path


def test_a_registration_challenge_without_its_handle_is_a_refusal_not_a_500(
    kit: PasskeyKit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spend that admits but carries no offered handle (a registration
    challenge registration_options did not issue) has its own branch: a
    typed challenge_missing refusal, never MetricReason("challenge_ok")."""
    from intake_api.passkey.challenges import Spent

    session = kit.sign_in()
    options = kit.call(session, "POST", "/v1/me/passkeys/registration/options").json()
    credential = Authenticator().register(options)
    service = kit.client.app.state.api.passkey  # type: ignore[attr-defined]
    monkeypatch.setattr(service._challenges, "consume_noted", lambda *_args: (Spent.OK, None))
    refused = kit.call(
        session, "POST", "/v1/me/passkeys/registration", json_body={"credential": credential}
    )
    assert refused.status_code == 400
    assert refused.json() == {
        "error": "passkey_registration_refused",
        "reason": "challenge_missing",
    }
    assert kit.passkey_rows() == []
