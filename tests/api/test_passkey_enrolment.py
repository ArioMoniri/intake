"""INT-582 — enrolling, listing, removing and recovering a patient passkey.

- Registration only from an already authenticated OTP session; the dev-bearer
  tier cannot enrol. The challenge is single-use and bound to that session.
- What is stored is the PUBLIC half (credential id, public key, counter, the
  backup flags) and an opaque user handle — never the phone, never a name.
- Removing a passkey is itself a step-up (else an OTP-only attacker removes
  it and walks through). Losing the phone is the recovery path: the OTP tier
  plus a cool-off, cancellable by the passkey's holder, after which the
  passkey stops counting and enrolment is offered again.
- Unconfigured passkey tier: nobody can enrol; a patient who has a passkey is
  refused with a manual path rather than silently downgraded.
- Ids only in the audit chain and in logs (invariant 6).

Sec row: onboarding (files/10 §9).
"""

from __future__ import annotations

import logging
import re
import sys
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from prometheus_client import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parent))

from intake_api.passkey.gate import GRANT_HEADER, MANUAL_PATH  # noqa: E402
from intake_api.passkey.service import PASSKEY_BASIS_REF, RECOVERY_COOLOFF_S  # noqa: E402
from passkey_harness import (  # noqa: E402
    PHONE_A,
    PasskeyKit,
    Session,
    build_passkey_kit,
)
from passkey_testkit import RP_ID, Authenticator, b64url, unb64url  # noqa: E402

DELETE = "/v1/me/dsar/delete"


@pytest.fixture()
def kit(tmp_path: Path) -> Iterator[PasskeyKit]:
    yield from build_passkey_kit(tmp_path)


@pytest.fixture()
def unwired(tmp_path: Path) -> Iterator[PasskeyKit]:
    yield from build_passkey_kit(tmp_path, passkey_wired=False)


def _enrol(kit: PasskeyKit, session: Session, device: Authenticator | None = None) -> Authenticator:
    device = device if device is not None else Authenticator()
    response = kit.register(session, device)
    assert response.status_code == 201, response.text
    return device


# --- registration ----------------------------------------------------------------------


def test_registration_needs_an_otp_session(kit: PasskeyKit) -> None:
    refused = kit.call(None, "POST", "/v1/me/passkeys/registration/options")
    assert refused.status_code == 403
    assert refused.json() == {"error": "passkey_otp_session_required"}
    session = kit.sign_in()
    assert kit.register(session, Authenticator()).status_code == 201


def test_the_creation_options_ask_for_a_verified_platform_passkey_with_no_attestation(
    kit: PasskeyKit,
) -> None:
    session = kit.sign_in()
    first = kit.call(session, "POST", "/v1/me/passkeys/registration/options").json()["publicKey"]
    assert first["rp"]["id"] == RP_ID
    assert first["attestation"] == "none"
    assert first["pubKeyCredParams"] == [{"type": "public-key", "alg": -7}]
    assert first["authenticatorSelection"] == {
        "authenticatorAttachment": "platform",
        "residentKey": "required",
        "userVerification": "required",
    }
    assert len(unb64url(first["challenge"])) == 32
    handle = unb64url(first["user"]["id"])
    assert len(handle) == 32
    # no phone, no patient id: the platform shows these strings in its UI
    for text in (first["user"]["name"], first["user"]["displayName"]):
        assert not re.search(r"\d{4}", text)
        assert session.patient_id not in text
    device = _enrol(kit, session)
    stored_handle = unb64url(kit.passkey_rows()[0].user_handle)
    assert device.user_handle == stored_handle  # the one the phone was offered
    second = kit.call(session, "POST", "/v1/me/passkeys/registration/options").json()["publicKey"]
    third = kit.call(session, "POST", "/v1/me/passkeys/registration/options").json()["publicKey"]
    # one handle per patient once enrolled, so a second passkey is the same account
    assert unb64url(second["user"]["id"]) == unb64url(third["user"]["id"]) == stored_handle
    assert second["excludeCredentials"] == [
        {"type": "public-key", "id": b64url(device.credential_id)}
    ]


def test_only_the_public_half_is_stored(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    device = _enrol(kit, session)
    (row,) = kit.passkey_rows()
    numbers = device.key.public_key().public_numbers()
    point = b"\x04" + numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    assert row.credential_id == b64url(device.credential_id)
    assert row.public_key == b64url(point)
    assert str(row.patient_id) == session.patient_id
    assert row.sign_count == 0 and row.backup_eligible and row.backup_state
    stored = " ".join(str(getattr(row, column)) for column in row.__table__.columns.keys())
    assert PHONE_A not in stored and PHONE_A[3:] not in stored


@pytest.mark.parametrize(
    ("knobs", "reason"),
    [
        ({"origin": "https://evil.example"}, "passkey_origin"),
        ({"rp_id": "evil.example"}, "passkey_rp_id"),
        ({"fmt": "packed"}, "passkey_attestation_format"),
        ({"uv": False}, "passkey_user_verification"),
    ],
)
def test_a_bad_registration_is_refused_and_audited(
    kit: PasskeyKit, knobs: dict[str, Any], reason: str
) -> None:
    session = kit.sign_in()
    device = Authenticator(rp_id=knobs.pop("rp_id", RP_ID))
    refused = kit.register(session, device, **knobs)
    assert refused.status_code == 400
    assert refused.json() == {"error": "passkey_registration_refused", "reason": reason}
    assert kit.passkey_rows() == []
    assert any(action == "passkey.register.refused" for action, _, _ in kit.audit_actions())


def test_a_registration_challenge_is_single_use_and_bound_to_its_session(
    kit: PasskeyKit,
) -> None:
    session = kit.sign_in()
    other_device = kit.sign_in(PHONE_A, device_id="device-b")
    options = kit.call(session, "POST", "/v1/me/passkeys/registration/options").json()
    credential = Authenticator().register(options)
    refused = kit.call(
        other_device,
        "POST",
        "/v1/me/passkeys/registration",
        json_body={"credential": credential},
    )
    assert refused.json()["reason"] == "challenge_mismatch"
    replay = kit.call(
        session, "POST", "/v1/me/passkeys/registration", json_body={"credential": credential}
    )
    assert replay.json()["reason"] == "challenge_missing"


def test_the_same_credential_cannot_be_registered_twice(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    device = _enrol(kit, session)
    again = kit.register(session, device)
    assert again.status_code == 409
    assert again.json() == {"error": "passkey_exists"}


def test_the_list_shows_ids_and_dates_and_no_key_material(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    device = _enrol(kit, session)
    listed = kit.call(session, "GET", "/v1/me/passkeys").json()
    assert listed["enrolment"] == "enrolled"
    (item,) = listed["passkeys"]
    assert set(item) == {
        "passkey_id",
        "created_at",
        "last_used_at",
        "backup_eligible",
        "recovery_ends_at",
    }
    assert b64url(device.credential_id) not in str(listed)


# --- removal is a step-up of its own --------------------------------------------------


def test_removing_a_passkey_needs_its_own_step_up(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    device = _enrol(kit, session)
    passkey_id = kit.call(session, "GET", "/v1/me/passkeys").json()["passkeys"][0]["passkey_id"]
    path = f"/v1/me/passkeys/{passkey_id}"
    refused = kit.call(session, "DELETE", path)
    assert refused.status_code == 403
    assert refused.json()["action"] == "passkey_remove"
    wrong = kit.grant(session, device, "data_delete")
    assert kit.call(session, "DELETE", path, headers={GRANT_HEADER: wrong}).status_code == 403
    grant = kit.grant(session, device, "passkey_remove")
    assert kit.call(session, "DELETE", path, headers={GRANT_HEADER: grant}).status_code == 204
    assert kit.passkey_rows() == []
    after = kit.call(session, "POST", DELETE)
    assert after.status_code == 201
    assert after.headers["X-Intake-Passkey-Enrolment"] == "offered"


# --- recovery: the OTP tier plus a cool-off ------------------------------------------


def test_recovery_from_the_otp_tier_takes_effect_only_after_the_cool_off(
    kit: PasskeyKit,
) -> None:
    session = kit.sign_in()
    _enrol(kit, session)
    lost_phone = kit.sign_in(PHONE_A, device_id="device-new")
    started = kit.call(lost_phone, "POST", "/v1/me/passkeys/recovery")
    assert started.status_code == 202, started.text
    ends = started.json()["recovery_ends_at"]
    assert ends == (kit.clock.utc + timedelta(seconds=RECOVERY_COOLOFF_S)).isoformat()
    # inside the cool-off the passkey still guards everything (the 15-minute
    # access token is long gone by then, so the new phone signs in again)
    kit.clock.advance(RECOVERY_COOLOFF_S - 600)
    lost_phone = kit.sign_in(PHONE_A, device_id="device-new")
    assert kit.call(lost_phone, "POST", DELETE).status_code == 403
    kit.clock.advance(600)
    lost_phone = kit.sign_in(PHONE_A, device_id="device-new")
    after = kit.call(lost_phone, "POST", DELETE)
    assert after.status_code == 201, after.text
    assert after.headers["X-Intake-Step-Up"] == "otp_session"
    assert after.headers["X-Intake-Passkey-Enrolment"] == "offered"
    assert kit.passkey_rows() == []
    actions = [action for action, _, _ in kit.audit_actions()]
    assert "passkey.recovery.request" in actions
    assert "passkey.recovery.complete" in actions


def test_the_passkey_holder_cancels_a_recovery_they_did_not_start(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    device = _enrol(kit, session)
    attacker = kit.sign_in(PHONE_A, device_id="device-swapped-sim")
    assert kit.call(attacker, "POST", "/v1/me/passkeys/recovery").status_code == 202
    # the attacker cannot cancel or complete it early, and cannot act meanwhile
    assert kit.call(attacker, "DELETE", "/v1/me/passkeys/recovery").status_code == 403
    grant = kit.grant(session, device, "recovery_cancel")
    cancelled = kit.call(
        session, "DELETE", "/v1/me/passkeys/recovery", headers={GRANT_HEADER: grant}
    )
    assert cancelled.status_code == 200, cancelled.text
    kit.clock.advance(RECOVERY_COOLOFF_S + 1)
    attacker = kit.sign_in(PHONE_A, device_id="device-swapped-sim")
    assert kit.call(attacker, "POST", DELETE).status_code == 403  # still guarded
    assert len(kit.passkey_rows()) == 1


def test_recovery_with_no_passkey_has_nothing_to_recover(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    assert kit.call(session, "POST", "/v1/me/passkeys/recovery").status_code == 404


# --- an unconfigured passkey tier -------------------------------------------------------


def test_unconfigured_nobody_enrols_and_the_otp_tier_carries_on(unwired: PasskeyKit) -> None:
    session = unwired.sign_in()
    refused = unwired.call(session, "POST", "/v1/me/passkeys/registration/options")
    assert refused.status_code == 503
    assert refused.json() == {"error": "passkey_not_configured"}
    allowed = unwired.call(session, "POST", DELETE)
    assert allowed.status_code == 201
    assert allowed.headers["X-Intake-Passkey-Enrolment"] == "unavailable"


def test_unconfigured_a_patient_who_has_a_passkey_is_refused_with_a_manual_path(
    unwired: PasskeyKit,
) -> None:
    """Not a silent downgrade to the OTP tier: the tier that would check the
    passkey is missing, so the action waits for a person (KVKK m.11(1)(g))."""
    from api_harness import run
    from intake_api.db import tenant_session
    from intake_api.otp import CONSUMER_TENANT_ID
    from intake_api.passkey.store import insert_credential
    from intake_api.passkey.webauthn import RegisteredCredential

    session = unwired.sign_in()

    async def _seed() -> None:
        async with tenant_session(unwired.harness.engine, CONSUMER_TENANT_ID) as db:
            await insert_credential(
                db,
                tenant_id=CONSUMER_TENANT_ID,
                patient_id=uuid.UUID(session.patient_id),
                credential=RegisteredCredential(
                    credential_id=b"\x07" * 20,
                    public_key=b"\x04" + b"\x01" * 64,
                    sign_count=0,
                    backup_eligible=True,
                    backup_state=True,
                ),
                user_handle=b"\x02" * 32,
                created_at=unwired.clock.utc,
            )

    run(_seed())
    refused = unwired.call(session, "POST", DELETE)
    assert refused.status_code == 503
    assert refused.json() == {
        "error": "passkey_not_configured",
        "manual_path": MANUAL_PATH,
    }
    options = unwired.step_up_options(session, "data_delete")
    assert options.status_code == 503


# --- ids only: the audit chain, the logs, the metrics ---------------------------------


def test_the_audit_chain_carries_ids_only(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    device = _enrol(kit, session)
    kit.grant(session, device, "data_delete")
    kit.step_up(session, device, "data_delete", origin="https://evil.example")
    entries = [
        entry
        for entry in kit.harness.audit_store.entries()
        if entry.action.startswith(("passkey.", "step_up."))
    ]
    assert {entry.action for entry in entries} >= {
        "passkey.register",
        "passkey.step_up",
        "passkey.step_up.refused",
    }
    for entry in entries:
        assert re.fullmatch(r"patient:[0-9a-f-]{36}", entry.actor), entry
        assert re.fullmatch(
            r"(passkey:[0-9a-f-]{36}|step-up:[a-z_]+|ceremony:register)", entry.resource_ref
        ), entry
        assert entry.consent_scope_ref == PASSKEY_BASIS_REF


def test_no_key_material_challenge_grant_or_phone_reaches_a_log(
    kit: PasskeyKit, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    session = kit.sign_in()
    device = Authenticator()
    options = kit.call(session, "POST", "/v1/me/passkeys/registration/options").json()
    credential = device.register(options)
    kit.call(session, "POST", "/v1/me/passkeys/registration", json_body={"credential": credential})
    step = kit.step_up_options(session, "data_delete").json()
    assertion = device.assertion(step)
    grant = kit.finish_step_up(session, "data_delete", assertion).json()["grant"]
    kit.call(session, "POST", DELETE, headers={GRANT_HEADER: grant})
    kit.step_up(session, device, "data_delete", origin="https://evil.example")
    # the product's own loggers (intake_api, intake_platform). The test
    # client's request line and the SQLite driver's DEBUG parameter echo are
    # this harness's, not the service's: the dev peek URL is the test reading
    # its own code, and no deployed tier logs driver DEBUG.
    records = [record for record in caplog.records if record.name.startswith("intake")]
    assert records, "the flow logged nothing at all — the scan would prove nothing"
    text = "\n".join(record.getMessage() for record in records)
    secrets = [
        PHONE_A,
        PHONE_A[3:],
        options["publicKey"]["challenge"],
        step["publicKey"]["challenge"],
        grant,
        credential["rawId"],
        credential["response"]["attestationObject"][:40],
        assertion["response"]["clientDataJSON"][:40],
        assertion["response"]["signature"][:40],
    ]
    assert not [secret for secret in secrets if secret in text]


def test_the_events_are_counted_with_closed_labels(kit: PasskeyKit) -> None:
    def count(event: str, reason: str = "none") -> float:
        value = REGISTRY.get_sample_value(
            "passkey_events_total", {"event": event, "reason": reason}
        )
        return value or 0.0

    before = (
        count("registered"),
        count("step_up_passed"),
        count("step_up_refused", "passkey_origin"),
    )
    session = kit.sign_in()
    device = _enrol(kit, session)
    kit.grant(session, device, "data_delete")
    kit.step_up(session, device, "data_delete", origin="https://evil.example")
    after = (
        count("registered"),
        count("step_up_passed"),
        count("step_up_refused", "passkey_origin"),
    )
    assert [b - a for a, b in zip(before, after, strict=True)] == [1.0, 1.0, 1.0]


# --- the consent scan: declared, and caged to its prefix ------------------------------


def test_the_passkey_routes_declare_themselves_to_the_consent_scan(kit: PasskeyKit) -> None:
    from fastapi import FastAPI
    from intake_api.consent_guard import (
        SIGN_IN_FACTOR_PREFIX,
        sign_in_factor_routes,
        unguarded_data_routes,
    )

    app = kit.client.app
    assert isinstance(app, FastAPI)
    assert unguarded_data_routes(app) == []
    assert sign_in_factor_routes(app) == [
        "DELETE /v1/me/passkeys/recovery",
        "DELETE /v1/me/passkeys/{passkey_id}",
        "GET /v1/me/passkeys",
        "POST /v1/me/passkeys/recovery",
        "POST /v1/me/passkeys/registration",
        "POST /v1/me/passkeys/registration/options",
        "POST /v1/me/passkeys/step-up",
        "POST /v1/me/passkeys/step-up/options",
    ]
    for route in sign_in_factor_routes(app):
        assert route.split(" ", 1)[1].startswith(SIGN_IN_FACTOR_PREFIX)


def test_near_miss_the_marker_cannot_be_borrowed_outside_its_prefix() -> None:
    from fastapi import FastAPI
    from intake_api.consent_guard import sign_in_factor, unguarded_data_routes

    borrowed = FastAPI()

    @borrowed.get("/v1/me/passkeysish", dependencies=[sign_in_factor()])
    async def lookalike() -> dict[str, str]:
        return {}

    @borrowed.get("/v1/visits/elsewhere", dependencies=[sign_in_factor()])
    async def elsewhere() -> dict[str, str]:
        return {}

    assert sorted(unguarded_data_routes(borrowed)) == [
        "GET /v1/me/passkeysish",
        "GET /v1/visits/elsewhere",
    ]
