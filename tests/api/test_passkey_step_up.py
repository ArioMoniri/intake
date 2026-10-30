"""INT-582 — the step-up gate on D36's sensitive actions, end to end.

D36 (owner, 28 Oct 2026): issuing a Doctor Link, changing the phone number,
data export and data delete step up to the patient's passkey. A patient with
a passkey asserts for each one; a patient without one is NOT locked out — the
OTP-session tier that guards these routes today still applies, and enrolment
is offered on the response. A refusal made on the step-up signal alone names
a manual path (KVKK m.11(1)(g)): a person reviews it.

Each attack has its near miss beside it — the closest call that must pass:
a replayed assertion / a fresh one; a challenge for another action / the
same action; a grant from another device session / that session's own grant;
a counter that stalls / one that moves; another account's credential / one's
own; a stale challenge / one inside its window.

Sec row: onboarding (files/10 §9).
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from intake_api.passkey.challenges import CHALLENGE_TTL_S  # noqa: E402
from intake_api.passkey.gate import (  # noqa: E402
    D36_ACTIONS,
    GRANT_HEADER,
    MANUAL_PATH,
    STEP_UP_ROUTES,
    StepUpAction,
    step_up_actions_of,
)
from passkey_harness import (  # noqa: E402
    PHONE_A,
    PHONE_B,
    PasskeyKit,
    Session,
    build_passkey_kit,
)
from passkey_testkit import Authenticator, b64url  # noqa: E402

DELETE = "/v1/me/dsar/delete"


@pytest.fixture()
def kit(tmp_path: Path) -> Iterator[PasskeyKit]:
    yield from build_passkey_kit(tmp_path)


def _enrolled(
    kit: PasskeyKit, phone: str = PHONE_A, **device_knobs: Any
) -> tuple[Session, Authenticator]:
    session = kit.sign_in(phone)
    device = Authenticator(**device_knobs)
    registered = kit.register(session, device)
    assert registered.status_code == 201, registered.text
    return session, device


def _delete(kit: PasskeyKit, session: Session | None, grant: str | None = None) -> Any:
    headers = {GRANT_HEADER: grant} if grant is not None else None
    return kit.call(session, "POST", DELETE, headers=headers)


def _export_read(kit: PasskeyKit, session: Session | None, grant: str | None = None) -> Any:
    headers = {GRANT_HEADER: grant} if grant is not None else None
    return kit.call(session, "GET", f"/v1/me/dsar/export/{uuid.uuid4()}", headers=headers)


# --- the D36 list and where it is enforced --------------------------------------------


def test_d36_names_exactly_four_actions() -> None:
    assert {action.value for action in D36_ACTIONS} == {
        "doctor_link_issue",
        "phone_change",
        "data_export",
        "data_delete",
    }


def test_every_served_d36_route_carries_the_gate_for_its_own_action(kit: PasskeyKit) -> None:
    served = step_up_actions_of(kit.client.app)  # type: ignore[arg-type]
    for action, routes in STEP_UP_ROUTES.items():
        for route in routes:
            assert served.get(route) == action, f"{route} does not step up to {action}"
    # and nothing else is gated by accident, under a D36 action or the
    # mechanism's own two (removing a passkey, cancelling a recovery)
    declared = {route: action for action, routes in STEP_UP_ROUTES.items() for route in routes}
    assert served == declared
    assert {action for action in served.values() if action in D36_ACTIONS} == D36_ACTIONS - {
        StepUpAction.PHONE_CHANGE
    }


def test_no_route_changes_the_phone_number_without_the_gate(kit: PasskeyKit) -> None:
    """No phone-change route is served today. The day one is, it must be in
    STEP_UP_ROUTES under phone_change or this fails — the near miss is the OTP
    request route, which names the phone and is pre-authentication."""
    assert STEP_UP_ROUTES[StepUpAction.PHONE_CHANGE] == ()
    served = step_up_actions_of(kit.client.app)  # type: ignore[arg-type]
    from intake_api.consent_guard import _iter_api_routes

    for path, route in _iter_api_routes(list(kit.client.app.routes)):  # type: ignore[attr-defined]
        if "phone" in path and not path.startswith("/v1/auth"):
            for method in route.methods or ():
                assert served.get(f"{method} {path}") == StepUpAction.PHONE_CHANGE, path


# --- no passkey: not locked out, enrolment offered ------------------------------------


def test_without_a_passkey_the_otp_tier_still_works_and_enrolment_is_offered(
    kit: PasskeyKit,
) -> None:
    session = kit.sign_in()
    response = _delete(kit, session)
    assert response.status_code == 201, response.text
    assert response.headers["X-Intake-Step-Up"] == "otp_session"
    assert response.headers["X-Intake-Passkey-Enrolment"] == "offered"
    options = kit.step_up_options(session, "data_delete")
    assert options.json() == {"enrolled": False, "tier": "otp_session", "enrolment": "offered"}
    assert ("step_up.otp_tier", "step-up:data_delete", f"patient:{session.patient_id}") in (
        kit.audit_actions()
    )


def test_the_dev_bearer_tier_is_offered_no_enrolment_but_keeps_working(kit: PasskeyKit) -> None:
    response = _delete(kit, None)
    assert response.status_code == 201, response.text
    assert response.headers["X-Intake-Passkey-Enrolment"] == "unavailable"


# --- a passkey: every action asserts ---------------------------------------------------


def test_a_patient_with_a_passkey_cannot_act_without_stepping_up(kit: PasskeyKit) -> None:
    session, _device = _enrolled(kit)
    refused = _delete(kit, session)
    assert refused.status_code == 403
    assert refused.json() == {
        "error": "step_up_required",
        "action": "data_delete",
        "manual_path": MANUAL_PATH,
    }


def test_a_passkey_assertion_opens_the_action_once(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    grant = kit.grant(session, device, "data_delete")
    allowed = _delete(kit, session, grant)
    assert allowed.status_code == 201, allowed.text
    assert allowed.headers["X-Intake-Step-Up"] == "passkey"
    again = _delete(kit, session, grant)
    assert again.status_code == 403
    assert again.json()["reason"] == "grant_missing"


def test_a_replayed_assertion_is_refused(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    options = kit.step_up_options(session, "data_delete").json()
    credential = device.assertion(options)
    assert kit.finish_step_up(session, "data_delete", credential).status_code == 200
    replay = kit.finish_step_up(session, "data_delete", credential)
    assert replay.status_code == 403
    assert replay.json()["reason"] == "challenge_missing"
    assert replay.json()["manual_path"] == MANUAL_PATH


def test_a_challenge_for_another_action_is_refused_and_burnt(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    options = kit.step_up_options(session, "data_export").json()
    credential = device.assertion(options)
    refused = kit.finish_step_up(session, "data_delete", credential)
    assert refused.status_code == 403
    assert refused.json()["reason"] == "challenge_mismatch"
    # burnt: the action it was issued for cannot use it either
    assert kit.finish_step_up(session, "data_export", credential).status_code == 403


def test_near_miss_a_challenge_for_the_same_action_passes(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    assert kit.step_up(session, device, "data_export").status_code == 200


def test_a_grant_for_another_action_does_not_open_this_one(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    grant = kit.grant(session, device, "data_export")
    refused = _delete(kit, session, grant)
    assert refused.status_code == 403
    assert refused.json()["reason"] == "grant_mismatch"


def test_near_miss_the_export_grant_opens_the_export(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    grant = kit.grant(session, device, "data_export")
    # past the gate: the body runs and finds no such request
    assert _export_read(kit, session, grant).status_code == 404
    assert _export_read(kit, session).status_code == 403


def test_a_grant_from_another_device_session_is_refused(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    grant = kit.grant(session, device, "data_delete")
    other_device = kit.sign_in(PHONE_A, device_id="device-b")
    assert other_device.patient_id == session.patient_id
    refused = _delete(kit, other_device, grant)
    assert refused.status_code == 403
    assert refused.json()["reason"] == "grant_mismatch"


def test_near_miss_the_other_device_session_steps_up_for_itself(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    other_device = kit.sign_in(PHONE_A, device_id="device-b")
    grant = kit.grant(other_device, device, "data_delete")
    assert _delete(kit, other_device, grant).status_code == 201


@pytest.mark.parametrize(
    ("knobs", "reason"),
    [
        ({"origin": "https://evil.example"}, "passkey_origin"),
        ({"rp_id": "evil.example"}, "passkey_rp_id"),
        ({"uv": False}, "passkey_user_verification"),
        ({"tamper": True}, "passkey_signature"),
    ],
)
def test_a_bad_assertion_is_refused_with_a_manual_path(
    kit: PasskeyKit, knobs: dict[str, Any], reason: str
) -> None:
    session, device = _enrolled(kit)
    refused = kit.step_up(session, device, "data_delete", **knobs)
    assert refused.status_code == 403
    assert refused.json() == {
        "error": "step_up_refused",
        "action": "data_delete",
        "reason": reason,
        "manual_path": MANUAL_PATH,
    }
    assert ("passkey.step_up.refused", "step-up:data_delete", f"patient:{session.patient_id}") in (
        kit.audit_actions()
    )


def test_a_counter_regression_is_refused_and_the_next_honest_count_passes(
    kit: PasskeyKit,
) -> None:
    session, device = _enrolled(kit, backed_up=False, counter=5)
    device.counter = 6
    assert kit.step_up(session, device, "data_delete").status_code == 200
    stalled = kit.step_up(session, device, "data_delete")  # 6 again: a second copy signed
    assert stalled.status_code == 403
    assert stalled.json()["reason"] == "passkey_sign_count"
    device.counter = 7
    assert kit.step_up(session, device, "data_delete").status_code == 200
    assert [row.sign_count for row in kit.passkey_rows()] == [7]


def test_another_accounts_credential_is_refused(kit: PasskeyKit) -> None:
    _alice, alice_device = _enrolled(kit, PHONE_A)
    bob, _bob_device = _enrolled(kit, PHONE_B)
    refused = kit.step_up(bob, alice_device, "data_delete")
    assert refused.status_code == 403
    assert refused.json()["reason"] == "credential_unknown"


def test_a_stale_challenge_is_refused(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    options = kit.step_up_options(session, "data_delete").json()
    kit.clock.advance(CHALLENGE_TTL_S + 1)
    refused = kit.finish_step_up(session, "data_delete", device.assertion(options))
    assert refused.status_code == 403
    assert refused.json()["reason"] == "challenge_expired"


def test_near_miss_a_challenge_inside_its_window_passes(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    options = kit.step_up_options(session, "data_delete").json()
    kit.clock.advance(CHALLENGE_TTL_S - 5)
    assert kit.finish_step_up(session, "data_delete", device.assertion(options)).status_code == 200


def test_step_up_options_name_only_the_patients_own_credentials(kit: PasskeyKit) -> None:
    session, device = _enrolled(kit)
    _enrolled(kit, PHONE_B)
    body = kit.step_up_options(session, "data_delete").json()
    public_key = body["publicKey"]
    assert [item["id"] for item in public_key["allowCredentials"]] == [b64url(device.credential_id)]
    assert public_key["rpId"] == "3-211-2-143.sslip.io"
    assert public_key["userVerification"] == "required"


def test_an_unknown_action_is_refused_before_any_challenge(kit: PasskeyKit) -> None:
    session, _device = _enrolled(kit)
    assert kit.step_up_options(session, "read_everything").status_code == 422


# --- the doctor link, on the dev-bearer patient with a seeded passkey -----------------


def test_issuing_a_doctor_link_steps_up(kit: PasskeyKit) -> None:
    from api_harness import run
    from intake_api.db import tenant_session
    from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID
    from intake_api.passkey.store import insert_credential
    from intake_api.passkey.webauthn import RegisteredCredential

    device = Authenticator()
    numbers = device.key.public_key().public_numbers()
    point = b"\x04" + numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
    device.user_handle = b"\x01" * 32

    async def _seed() -> None:
        async with tenant_session(kit.harness.engine, DEV_TENANT_ID) as db:
            await insert_credential(
                db,
                tenant_id=DEV_TENANT_ID,
                patient_id=DEV_PATIENT_ID,
                credential=RegisteredCredential(
                    credential_id=device.credential_id,
                    public_key=point,
                    sign_count=0,
                    backup_eligible=True,
                    backup_state=True,
                ),
                user_handle=device.user_handle,
                created_at=kit.clock.utc,
            )

    run(_seed())
    visit = kit.call(
        None,
        "POST",
        "/v1/visits",
        json_body={
            "hospital": "Ankara Şehir Hastanesi",
            "department": "İç Hastalıkları",
            "date": "2026-12-01",
        },
    )
    assert visit.status_code == 201, visit.text
    visit_id = visit.json()["id"]
    note = kit.call(
        None,
        "PUT",
        f"/v1/visits/{visit_id}/note",
        json_body={
            "sections": [{"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["x"]}],
            "scopes": {},
            "status": "sent",
        },
    )
    assert note.status_code == 200, note.text
    path = f"/v1/visits/{visit_id}/note/doctor-links"
    body = {"recipient": "Dr. Test · Kardiyoloji"}
    refused = kit.call(None, "POST", path, json_body=body)
    assert refused.status_code == 403
    assert refused.json()["error"] == "step_up_required"
    grant = kit.grant(None, device, "doctor_link_issue")
    issued = kit.call(None, "POST", path, json_body=body, headers={GRANT_HEADER: grant})
    assert issued.status_code == 201, issued.text
