"""INT-587 — the note reaches the clinician: the API contract the app's
note-sync client, share-consent step and Doctor Link screens rely on.

The app (apps/mobile/src/lib/intake/delivery, lib/consent, lib/shares) now
drives this exact sequence on the synthetic host:

1. ``GET /v1/consents`` → the share text under the bare purpose ``share``;
2. ``POST /v1/consents/grant`` with ``share:previsit_note`` and that text's
   {version, text_hash};
3. ``PUT /v1/visits/{id}/note`` with ``status: "sent"`` — retried as is after
   a lost answer;
4. ``POST …/note/doctor-links`` then ``…/{link_id}/otp``;
5. ``POST /v1/consents/withdraw`` with ``share:previsit_note`` when the patient
   takes the consent back.

No server code changes in INT-587. These tests pin the behaviour the client
classifies — which refusal means "ask for consent", which is "not shared",
that a retried PUT leaves one live share — on the synthetic legal tree, so a
server change that broke the client's reading fails here, beside the server.
They are characterisation tests over unchanged code, so their first run is
green by design (docs/evidence/INT-587.md says so).
"""

from __future__ import annotations

import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from intake_platform.db.models import Consent, Share
from intake_platform.legal.synthetic import SYNTHETIC_CONSENTS_ROOT
from intake_platform.tokenization import Tokenizer
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run  # noqa: E402
from intake_api.attestation import FailClosedAttestationVerifier  # noqa: E402
from intake_api.auth_store import OTP_WINDOW_S, RESEND_COOLDOWN_S  # noqa: E402
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID  # noqa: E402
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC_CONSENTS = REPO / SYNTHETIC_CONSENTS_ROOT

#: What the app grants and the server checks (apps/mobile consent/ledger.ts
#: SHARE_SCOPE, services/api notes.SHARE_SCOPE).
SHARE_SCOPE = "share:previsit_note"

VISIT_BODY = {"hospital": "Deneme Hastanesi", "department": "Kardiyoloji", "date": "2026-11-20"}

#: The body shape apps/mobile delivery/payload.ts builds: every section with a
#: rendered title, an explicit scope for each, status sent. Synthetic content.
NOTE_BODY: dict[str, Any] = {
    "sections": [
        {"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Ağrı"]},
        {"id": "hpi", "title": "Şikâyet öyküsü", "lines": ["Süre: Birkaç gündür"]},
    ],
    "scopes": {"chief_complaint": True, "hpi": False},
    "status": "sent",
}


class Clock:
    """Seeded at the start of an OTP window so rate-limit budgets are stable."""

    def __init__(self) -> None:
        raw = datetime(2026, 11, 15, 9, 0, tzinfo=UTC).timestamp()
        self.now = float(int(raw) // OTP_WINDOW_S * OTP_WINDOW_S) + 60.0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


@dataclass
class Host:
    harness: ApiHarness
    clock: Clock
    visit_id: str

    def get(self, path: str) -> Any:
        return self.harness.client.get(path, headers=self.harness.patient())

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.harness.client.post(path, json=body, headers=self.harness.patient())

    def put_note(self) -> Any:
        return self.harness.client.put(
            f"/v1/visits/{self.visit_id}/note", json=NOTE_BODY, headers=self.harness.patient()
        )

    def text(self, purpose: str) -> dict[str, Any]:
        snapshot = self.get("/v1/consents").json()
        (row,) = [r for r in snapshot["texts"] if r["purpose"] == purpose]
        found: dict[str, Any] = row
        return found

    def grant(self, scope: str) -> Any:
        purpose = "share" if scope.startswith("share:") else scope
        text = self.text(purpose)
        return self.post(
            "/v1/consents/grant",
            {"scope": scope, "version": text["version"], "text_hash": text["text_hash"]},
        )

    def live_shares(self) -> list[Share]:
        async def _read() -> list[Share]:
            async with AsyncSession(self.harness.engine) as session:
                rows = await session.scalars(
                    select(Share).where(
                        Share.tenant_id == DEV_TENANT_ID, Share.revoked_at.is_(None)
                    )
                )
                return list(rows.all())

        shares: list[Share] = run(_read())
        return shares

    def issue(self) -> Any:
        return self.post(
            f"/v1/visits/{self.visit_id}/note/doctor-links", {"recipient": "Dr Deneme"}
        )

    def mint(self, link_id: str) -> Any:
        response = self.post(f"/v1/visits/{self.visit_id}/note/doctor-links/{link_id}/otp")
        self.clock.advance(RESEND_COOLDOWN_S + 1)
        return response


def _wipe_consents(harness: ApiHarness) -> None:
    """Start from no consent at all: the dev seeds are unbound rows that a
    loaded text makes stale, and this test wants the patient's own grants."""

    async def _wipe() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            await session.execute(
                delete(Consent).where(
                    Consent.tenant_id == DEV_TENANT_ID, Consent.patient_id == DEV_PATIENT_ID
                )
            )

    run(_wipe())


@pytest.fixture()
def host(tmp_path: Path) -> Iterator[Host]:
    clock = Clock()
    harnesses = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        legal_root=SYNTHETIC_CONSENTS,
        deployment_data_class="synthetic",
        auth=AuthWiring(
            redis_client=fakeredis.FakeRedis(),
            tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
            delivery=DevLogDeliveryAdapter(),
            attestation=FailClosedAttestationVerifier(),
            dev_otp_peek=False,
            now_fn=clock,
        ),
    )
    harness = next(harnesses)
    _wipe_consents(harness)
    probe = Host(harness=harness, clock=clock, visit_id="")
    assert probe.grant("core").status_code == 201
    visit = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert visit.status_code == 201, visit.text
    yield Host(harness=harness, clock=clock, visit_id=str(visit.json()["id"]))
    for _ in harnesses:
        pass


# --- the share text the app renders --------------------------------------------------


def test_the_share_text_is_served_under_the_bare_family_id(host: Host) -> None:
    text = host.text("share")
    assert text["body"].startswith("Sentetik test metni")
    assert len(text["text_hash"]) == 64


# --- no share without the grant ------------------------------------------------------


def test_a_send_without_the_share_grant_is_refused_on_the_share_scope(host: Host) -> None:
    response = host.put_note()
    assert response.status_code == 403
    # the exact body the client maps to "ask for consent", ids only
    assert response.json() == {"error": "consent_required", "scope": SHARE_SCOPE}
    # and the refusal wrote nothing: no share, no note
    assert host.live_shares() == []
    assert host.get(f"/v1/visits/{host.visit_id}/note").status_code == 404


def test_a_grant_against_the_served_text_then_a_send_is_confirmed(host: Host) -> None:
    assert host.grant(SHARE_SCOPE).status_code == 201
    response = host.put_note()
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "sent"
    (share,) = host.live_shares()
    assert share.scope_sections["section_ids"] == ["chief_complaint"]
    assert share.scope_sections["withheld_section_ids"] == ["hpi"]


def test_a_grant_against_a_moved_text_is_refused_and_nothing_is_sent(host: Host) -> None:
    text = host.text("share")
    response = host.post(
        "/v1/consents/grant",
        {"scope": SHARE_SCOPE, "version": text["version"], "text_hash": "0" * 64},
    )
    assert response.status_code == 409
    assert response.json() == {"error": "consent_text_changed", "scope": SHARE_SCOPE}
    assert host.put_note().status_code == 403


def test_a_core_refusal_names_core_not_the_share(host: Host) -> None:
    """The near miss of the share refusal: the client must tell them apart,
    because a missing core consent is a different switch for the patient."""
    assert host.grant(SHARE_SCOPE).status_code == 201
    assert host.post("/v1/consents/withdraw", {"scope": "core"}).status_code == 200
    response = host.put_note()
    assert response.status_code == 403
    assert response.json() == {"error": "consent_required", "scope": "core"}


# --- the retried PUT ---------------------------------------------------------------------


def test_a_retried_send_leaves_exactly_one_live_share(host: Host) -> None:
    """The client retries an unconfirmed PUT as is. The server's contract is a
    replace: the earlier share is revoked and one live share remains, scoped
    to the same sections — so a lost answer cannot fork the disclosure."""
    assert host.grant(SHARE_SCOPE).status_code == 201
    assert host.put_note().status_code == 200
    assert host.put_note().status_code == 200
    (share,) = host.live_shares()
    assert share.scope_sections["section_ids"] == ["chief_complaint"]


# --- Doctor Link, and a revoked grant stops it ---------------------------------------


def test_a_delivered_note_can_be_linked_and_a_withdrawn_grant_stops_the_link(host: Host) -> None:
    assert host.grant(SHARE_SCOPE).status_code == 201
    assert host.put_note().status_code == 200
    issued = host.issue()
    assert issued.status_code == 201, issued.text
    link_id = str(issued.json()["link_id"])
    code = host.mint(link_id)
    assert code.status_code == 200, code.text

    withdrawn = host.post("/v1/consents/withdraw", {"scope": SHARE_SCOPE})
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["revoked_share_ids"], "the withdrawal must revoke the live share"
    assert host.live_shares() == []

    # the code minted before the withdrawal opens nothing
    view = host.harness.client.post(
        "/v1/doctor-link/view",
        json={"token": issued.json()["token"], "code": code.json()["code"]},
    )
    assert view.status_code in (403, 404, 410), view.text
    # no new code, and no new link
    assert host.mint(link_id).status_code == 403
    assert host.issue().status_code == 409
    assert host.issue().json() == {"error": "note_not_shared"}


def test_a_link_is_refused_before_the_note_is_delivered(host: Host) -> None:
    """What the issue screen meets for a note still on the phone."""
    assert host.grant(SHARE_SCOPE).status_code == 201
    response = host.issue()
    assert response.status_code == 404  # no note row exists until a PUT lands


def test_every_share_and_link_is_audited_with_the_share_scope(host: Host) -> None:
    assert host.grant(SHARE_SCOPE).status_code == 201
    assert host.put_note().status_code == 200
    assert host.issue().status_code == 201

    actions = {
        (entry.action, entry.consent_scope_ref) for entry in host.harness.audit_store.entries()
    }
    assert ("consent.grant", f"scope:{SHARE_SCOPE}") in actions
    assert ("api.note.share", f"scope:{SHARE_SCOPE}") in actions
    assert ("api.doctor_link.issued", f"scope:{SHARE_SCOPE}") in actions


def test_no_note_content_reaches_a_refusal_body(host: Host) -> None:
    """Invariant 6 on the wire the client reads: a refusal carries ids only."""
    response = host.put_note()
    assert "Ağrı" not in response.text
    assert "Kardiyoloji" not in response.text
    assert uuid.UUID(host.visit_id)  # the id the client addresses is a server id
