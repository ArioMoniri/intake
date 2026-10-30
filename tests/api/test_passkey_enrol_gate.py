"""INT-582 review fix (security B1) — enrolment is itself a step-up once a
passkey exists, and cancelling a scheduled erasure is a data_delete step-up.

The bypass the review found: a SIM-swapper with an OTP session enrolled their
own passkey beside the patient's (201), used it to remove the patient's
(204), then scheduled the erasure (201). Enrolment now requires a
``passkey_add`` grant from an ACTIVE passkey — including during a recovery's
cool-off — on both registration routes, and an un-stepped caller is told
nothing about the existing passkeys (no user handle, no credential id).

Near misses: a patient with no passkey enrols on the OTP tier as before; after
a completed recovery the new phone enrols on the OTP tier; the holder adds a
second passkey with one step-up; a patient without a passkey cancels a
scheduled erasure as before.

Sec row: onboarding (files/10 §9).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from intake_api.passkey.gate import GRANT_HEADER, STEP_UP_ROUTES, StepUpAction  # noqa: E402
from intake_api.passkey.service import RECOVERY_COOLOFF_S  # noqa: E402
from passkey_harness import PHONE_A, PasskeyKit, Session, build_passkey_kit  # noqa: E402
from passkey_testkit import Authenticator, b64url  # noqa: E402

OPTIONS = "/v1/me/passkeys/registration/options"
FINISH = "/v1/me/passkeys/registration"


@pytest.fixture()
def kit(tmp_path: Path) -> Iterator[PasskeyKit]:
    yield from build_passkey_kit(tmp_path)


def _enrolled(kit: PasskeyKit) -> tuple[Session, Authenticator]:
    session = kit.sign_in()
    device = Authenticator()
    assert kit.register(session, device).status_code == 201
    return session, device


def _a_credential() -> dict[str, Any]:
    """A well-formed registration body under a challenge nobody issued."""
    return Authenticator().register(
        {"challenge": b64url(b"\x00" * 32), "user": {"id": b64url(b"\x01" * 32)}}
    )


def test_both_registration_routes_step_up_to_passkey_add() -> None:
    assert STEP_UP_ROUTES[StepUpAction.PASSKEY_ADD] == (
        f"POST {OPTIONS}",
        f"POST {FINISH}",
    )


def test_a_second_otp_device_cannot_enrol_while_a_passkey_is_active(kit: PasskeyKit) -> None:
    _victim, victim_device = _enrolled(kit)
    attacker = kit.sign_in(PHONE_A, device_id="device-swapped-sim")
    options = kit.call(attacker, "POST", OPTIONS)
    assert options.status_code == 403
    assert options.json() == {
        "error": "step_up_required",
        "action": "passkey_add",
        "manual_path": "kvkk_m13_application",
    }
    # nothing about the existing passkey reaches an un-stepped caller
    stored = kit.passkey_rows()[0]
    assert stored.user_handle not in options.text
    assert b64url(victim_device.credential_id) not in options.text
    finish = kit.call(attacker, "POST", FINISH, json_body={"credential": _a_credential()})
    assert finish.status_code == 403
    assert finish.json()["action"] == "passkey_add"
    assert len(kit.passkey_rows()) == 1


def test_the_review_path_stops_at_its_first_step(kit: PasskeyKit) -> None:
    """The reproduction from the security review, end to end."""
    _enrolled(kit)
    attacker = kit.sign_in(PHONE_A, device_id="device-swapped-sim")
    attacker_device = Authenticator()
    options = kit.call(attacker, "POST", OPTIONS)
    assert options.status_code == 403
    erasure = kit.call(attacker, "POST", "/v1/me/dsar/delete")
    assert erasure.status_code == 403
    assert kit.step_up(attacker, attacker_device, "passkey_remove").status_code == 403


def test_during_the_recovery_cool_off_enrolment_still_needs_the_passkey(kit: PasskeyKit) -> None:
    _enrolled(kit)
    new_phone = kit.sign_in(PHONE_A, device_id="device-new")
    assert kit.call(new_phone, "POST", "/v1/me/passkeys/recovery").status_code == 202
    kit.clock.advance(RECOVERY_COOLOFF_S - 600)
    new_phone = kit.sign_in(PHONE_A, device_id="device-new")
    assert kit.call(new_phone, "POST", OPTIONS).status_code == 403


def test_near_miss_after_the_cool_off_the_new_phone_enrols_on_the_otp_tier(
    kit: PasskeyKit,
) -> None:
    _enrolled(kit)
    new_phone = kit.sign_in(PHONE_A, device_id="device-new")
    assert kit.call(new_phone, "POST", "/v1/me/passkeys/recovery").status_code == 202
    kit.clock.advance(RECOVERY_COOLOFF_S + 1)
    new_phone = kit.sign_in(PHONE_A, device_id="device-new")
    assert kit.register(new_phone, Authenticator()).status_code == 201
    assert len(kit.passkey_rows()) == 1


def test_near_miss_a_patient_with_no_passkey_enrols_on_the_otp_tier(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    assert kit.register(session, Authenticator()).status_code == 201


def test_the_holder_adds_a_second_passkey_with_one_step_up(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    grant = kit.grant(session, device, "passkey_add")
    second = Authenticator()
    assert kit.register(session, second, grant=grant).status_code == 201
    assert len(kit.passkey_rows()) == 2
    # the grant was spent by the registration it opened
    third = kit.call(session, "POST", OPTIONS, headers={GRANT_HEADER: grant})
    assert third.status_code == 403
    assert third.json()["reason"] == "grant_missing"


def test_a_grant_for_another_action_does_not_open_enrolment(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    grant = kit.grant(session, device, "data_delete")
    refused = kit.call(session, "POST", OPTIONS, headers={GRANT_HEADER: grant})
    assert refused.status_code == 403
    assert refused.json()["reason"] == "grant_mismatch"


def test_a_passkey_add_grant_from_another_device_session_does_not_open_enrolment(
    kit: PasskeyKit,
) -> None:
    session, device = _enrolled(kit)
    grant = kit.grant(session, device, "passkey_add")
    other = kit.sign_in(PHONE_A, device_id="device-b")
    refused = kit.call(other, "POST", OPTIONS, headers={GRANT_HEADER: grant})
    assert refused.json()["reason"] == "grant_mismatch"


def test_step_up_options_carry_no_credential_id(kit: PasskeyKit) -> None:
    """A passkey is discoverable (residentKey required), so the step-up asks
    the phone with an empty allowCredentials and no id ever reaches an OTP-only
    caller; the server matches the returned rawId against the patient's own."""
    session, device = _enrolled(kit)
    body = kit.step_up_options(session, "data_delete")
    assert body.json()["publicKey"]["allowCredentials"] == []
    assert b64url(device.credential_id) not in body.text
    assert kit.passkey_rows()[0].user_handle not in body.text


# --- cancelling a scheduled erasure is a data_delete step-up --------------------------


def test_a_sim_swapper_cannot_cancel_the_holders_scheduled_erasure(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    grant = kit.grant(session, device, "data_delete")
    scheduled = kit.call(session, "POST", "/v1/me/dsar/delete", headers={GRANT_HEADER: grant})
    assert scheduled.status_code == 201, scheduled.text
    request_id = scheduled.json()["request_id"]
    attacker = kit.sign_in(PHONE_A, device_id="device-swapped-sim")
    refused = kit.call(attacker, "DELETE", f"/v1/me/dsar/delete/{request_id}")
    assert refused.status_code == 403
    assert refused.json()["action"] == "data_delete"
    # near miss: the holder withdraws it with the passkey
    grant = kit.grant(session, device, "data_delete")
    withdrawn = kit.call(
        session, "DELETE", f"/v1/me/dsar/delete/{request_id}", headers={GRANT_HEADER: grant}
    )
    assert withdrawn.status_code == 200, withdrawn.text


def test_near_miss_a_patient_without_a_passkey_cancels_as_before(kit: PasskeyKit) -> None:
    session = kit.sign_in()
    scheduled = kit.call(session, "POST", "/v1/me/dsar/delete")
    assert scheduled.status_code == 201
    request_id = scheduled.json()["request_id"]
    withdrawn = kit.call(session, "DELETE", f"/v1/me/dsar/delete/{request_id}")
    assert withdrawn.status_code == 200
    assert withdrawn.headers["X-Intake-Step-Up"] == "otp_session"
