"""INT-510 — the patient's send reaches the clinic (GitHub #872).

The phone used to mark a note ``sent`` without telling anyone. INT-510 makes
the send a ``PUT /v1/visits/{server id}/note`` with ``status: "sent"``, carrying
only the sections the patient left on. This file is the SERVER's half of that
contract, driven with the very body the app builds — the JSON fixture
``tests/fixtures/note_send/app_note_put.json`` is asserted equal to the app's
``notePutBody`` output in ``apps/mobile/src/lib/intake/noteSend.test.ts``:

- a send with the share consent creates exactly ONE share, scoped to exactly
  the sections the body carries, and audits it (invariant 4);
- the section the patient withheld never reached the server, yet the share
  still records it as withheld — the INT-304 fact survives the client sending
  less (``NoteBody.withheld_section_ids`` reads ``scopes``, not ``sections``);
- a send without the consent creates NO share and leaves nothing behind, and
  the answer is a 403 the phone words rather than a 200 it would show as sent;
- a Doctor Link issued after the send succeeds against the server id;
- the near miss: the same calls made with the phone's LOCAL id are refused and
  create nothing.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run
from intake_api.attestation import FailClosedAttestationVerifier
from intake_api.auth_store import OTP_WINDOW_S
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter
from intake_api.schemas import NoteBody
from intake_platform.db.models import DoctorLink, Note, Share
from intake_platform.tokenization import Tokenizer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "note_send" / "app_note_put.json"

#: The id the phone mints for a visit it created (``buildLocalVisit``):
#: meaningful on the device, unknown to the server by construction.
LOCAL_ID = "v-local-1"

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-20",
}
SHARE_SCOPE = "share:previsit_note"


def _app_body() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return body


class _Clock:
    """One injected clock for the OTP/Doctor Link tier (docs/TDD.md rule 6),
    seeded at the start of a rate-limit window so no budget depends on the
    minute the suite runs."""

    def __init__(self, at: datetime) -> None:
        self.now = float(int(at.timestamp()) // OTP_WINDOW_S * OTP_WINDOW_S) + 60.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def linked(tmp_path: Path) -> Iterator[ApiHarness]:
    """The harness with the Doctor Link tier wired over fakeredis."""
    clock = _Clock(datetime(2026, 9, 15, 9, 0, tzinfo=UTC))
    yield from build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        auth=AuthWiring(
            redis_client=fakeredis.FakeRedis(),
            tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
            delivery=DevLogDeliveryAdapter(),
            attestation=FailClosedAttestationVerifier(),
            dev_otp_peek=False,
            now_fn=clock,
        ),
    )


def _server_visit(harness: ApiHarness) -> str:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _send(harness: ApiHarness, visit_id: str) -> Any:
    return harness.client.put(
        f"/v1/visits/{visit_id}/note", json=_app_body(), headers=harness.patient()
    )


def _shares(harness: ApiHarness) -> list[Share]:
    async def _load() -> list[Share]:
        async with AsyncSession(harness.engine) as session:
            return list((await session.scalars(select(Share))).all())

    loaded: list[Share] = run(_load())
    return loaded


def _count(harness: ApiHarness, model: type[Any]) -> int:
    async def _load() -> int:
        async with AsyncSession(harness.engine) as session:
            return int(await session.scalar(select(func.count()).select_from(model)) or 0)

    counted: int = run(_load())
    return counted


def _share_audits(harness: ApiHarness) -> list[Any]:
    return [e for e in harness.audit_store.entries() if e.action == "api.note.share"]


# --- the contract itself ---------------------------------------------------------------


def test_the_app_body_is_a_valid_note_carrying_only_the_shared_sections() -> None:
    body = NoteBody.model_validate({k: v for k, v in _app_body().items() if k != "status"})
    assert body.shared_section_ids() == ["chief_complaint", "hpi"]
    # the withheld section is a scope, not a section: its content never travelled
    assert "pmh" not in {s.id for s in body.sections}
    assert body.withheld_section_ids() == ["pmh"]


def test_withheld_is_read_from_the_scopes_in_note_order() -> None:
    # Near miss for the change above: a withheld section that DID travel (the
    # INT-304 body shape) is still withheld, and ids come out in note order.
    body = NoteBody.model_validate(
        {
            "sections": [
                {"id": "chief_complaint", "title": "t", "lines": ["x"]},
                {"id": "medications", "title": "t", "lines": ["x"]},
            ],
            "scopes": {"family_social": False, "medications": False, "chief_complaint": True},
        }
    )
    assert body.shared_section_ids() == ["chief_complaint"]
    assert body.withheld_section_ids() == ["medications", "family_social"]


# --- a send with consent ---------------------------------------------------------------


def test_a_send_with_consent_creates_exactly_one_share(harness: ApiHarness) -> None:
    visit_id = _server_visit(harness)
    response = _send(harness, visit_id)
    assert response.status_code == 200, response.text
    # the phone shows "sent" on exactly this: a 200 that says sent
    assert response.json()["status"] == "sent"

    shares = _shares(harness)
    assert len(shares) == 1
    assert shares[0].revoked_at is None
    assert shares[0].scope_sections == {
        "section_ids": ["chief_complaint", "hpi"],
        "withheld_section_ids": ["pmh"],
    }
    audits = _share_audits(harness)
    assert [a.resource_ref for a in audits] == [f"share:{shares[0].id}"]
    assert audits[0].consent_scope_ref == f"scope:{SHARE_SCOPE}"


def test_a_resend_leaves_exactly_one_live_share(harness: ApiHarness) -> None:
    # A queued send that is retried after the first one did land (the response
    # was lost on the way back) must not leave two live grants.
    visit_id = _server_visit(harness)
    assert _send(harness, visit_id).status_code == 200
    assert _send(harness, visit_id).status_code == 200
    live = [s for s in _shares(harness) if s.revoked_at is None]
    assert len(live) == 1


def test_the_clinic_reads_only_what_the_body_carried(harness: ApiHarness) -> None:
    visit_id = _server_visit(harness)
    assert _send(harness, visit_id).status_code == 200
    read = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.admin())
    assert read.status_code == 200, read.text
    assert [s["id"] for s in read.json()["sections"]] == ["chief_complaint", "hpi"]


# --- a send without consent ------------------------------------------------------------


def test_a_send_without_consent_creates_no_share_and_is_not_sent(harness: ApiHarness) -> None:
    visit_id = _server_visit(harness)
    harness.revoke_consent(SHARE_SCOPE)

    response = _send(harness, visit_id)
    # not a 200: the phone keeps the note a draft and words the refusal
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": SHARE_SCOPE}

    assert _shares(harness) == []
    assert _share_audits(harness) == []
    # the whole write rolled back — no note row was left half-sent either
    assert _count(harness, Note) == 0
    own = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.patient())
    assert own.status_code == 404


# --- the Doctor Link after a send ------------------------------------------------------


def test_a_doctor_link_issued_after_a_send_succeeds_against_the_server_id(
    linked: ApiHarness,
) -> None:
    visit_id = _server_visit(linked)
    assert _send(linked, visit_id).status_code == 200
    issued = linked.client.post(
        f"/v1/visits/{visit_id}/note/doctor-links",
        json={"recipient": "Kardiyoloji polikliniği"},
        headers=linked.patient(),
    )
    assert issued.status_code == 201, issued.text
    assert _count(linked, DoctorLink) == 1


def test_a_doctor_link_before_any_send_is_refused_as_not_shared(linked: ApiHarness) -> None:
    # What the old phone produced: a visit with no sent note behind it.
    visit_id = _server_visit(linked)
    issued = linked.client.post(
        f"/v1/visits/{visit_id}/note/doctor-links",
        json={"recipient": "Kardiyoloji polikliniği"},
        headers=linked.patient(),
    )
    assert issued.status_code == 404
    assert _count(linked, DoctorLink) == 0


# --- the near miss: the phone's local id ------------------------------------------------


def test_a_send_to_the_local_id_is_refused_and_creates_nothing(harness: ApiHarness) -> None:
    _server_visit(harness)  # the real visit exists; the local id still names nothing
    response = harness.client.put(
        f"/v1/visits/{LOCAL_ID}/note", json=_app_body(), headers=harness.patient()
    )
    assert response.status_code == 422
    assert _shares(harness) == []
    assert _count(harness, Note) == 0


def test_a_doctor_link_on_the_local_id_is_refused(linked: ApiHarness) -> None:
    visit_id = _server_visit(linked)
    assert _send(linked, visit_id).status_code == 200
    issued = linked.client.post(
        f"/v1/visits/{LOCAL_ID}/note/doctor-links",
        json={"recipient": "Kardiyoloji polikliniği"},
        headers=linked.patient(),
    )
    assert issued.status_code == 422
    listed = linked.client.get(f"/v1/visits/{LOCAL_ID}/note/doctor-links", headers=linked.patient())
    assert listed.status_code == 422
    assert _count(linked, DoctorLink) == 0


def test_a_well_formed_id_the_server_never_issued_is_not_found(linked: ApiHarness) -> None:
    visit_id = _server_visit(linked)
    assert _send(linked, visit_id).status_code == 200
    stranger = str(uuid.uuid4())
    sent = linked.client.put(
        f"/v1/visits/{stranger}/note", json=_app_body(), headers=linked.patient()
    )
    assert sent.status_code == 404
    issued = linked.client.post(
        f"/v1/visits/{stranger}/note/doctor-links",
        json={"recipient": "Kardiyoloji polikliniği"},
        headers=linked.patient(),
    )
    assert issued.status_code == 404
    assert len(_shares(linked)) == 1
    assert _count(linked, DoctorLink) == 0
