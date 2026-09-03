"""INT-150 — Doctor Link: 128-bit token + OTP + expiry + view limit + revoke +
watermark + access log + no-index.

Acceptance line under test, verbatim:
  "entropy/expiry tests; watermark carries recipient+timestamp; robots/noindex;
   every open audited and visible to patient"

files/10 §2 (clinicians) is the source of the controls: *"OTP to the phone/
e-mail the patient chose + 128-bit random token + expiry (default 72 h) + view
limit + instant revoke; PDF downloads watermarked with recipient and
timestamp"*, and files/10 §9's `doctor-link` row adds *"no indexing, access
log"*. files/02 §2b supplies the clock: expiry is anchored on the VISIT, never
on issue time.

The near-miss negative controls a naive implementation passes are the point of
this file, and each is named where it lives:

- a token that has expired by exactly one second (``test_expiry_is_exact``);
- the (limit + 1)th view (``test_the_view_after_the_last_one_is_refused``);
- a token used immediately after revocation, both with the routing hint gone
  and with it forcibly restored (``test_revocation_is_immediate*``);
- a token differing from a valid one in exactly one character
  (``test_a_token_one_character_off_opens_nothing``);
- an OTP that is one digit off, and the sixth attempt after five wrong ones.

Everything time-dependent runs on ONE injected clock (docs/TDD.md rule 6):
``DoctorLinkService.utcnow`` is the clock the routes read for expiry, the view
budget and the watermark instant, and it is the same clock ``AuthStore`` counts
OTP windows on. Nothing here sleeps and nothing reads the wall clock.
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from intake_platform.audit import verify_entries
from intake_platform.db.models import DoctorLink
from intake_platform.doctor_link import (
    DEFAULT_VIEW_LIMIT,
    DOCTOR_LINK_TTL,
    TOKEN_ENTROPY_BITS,
    RecipientInvalidError,
    Watermark,
    link_expires_at,
    new_token,
    normalise_recipient,
    token_fingerprint,
    token_matches,
)
from intake_platform.pdf import render_document_pdf
from intake_platform.tokenization import Tokenizer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import (  # noqa: E402
    ADMIN_TOKEN,
    PATIENT_TOKEN,
    ApiHarness,
    build_harness,
    run,
)
from intake_api.attestation import FailClosedAttestationVerifier  # noqa: E402
from intake_api.auth_store import (  # noqa: E402
    OTP_MAX_ATTEMPTS,
    OTP_TTL_S,
    OTP_WINDOW_S,
    RESEND_COOLDOWN_S,
)
from intake_api.consent_guard import (  # noqa: E402
    DOCTOR_LINK_PREFIX,
    doctor_link_redemption,
    doctor_link_redemption_routes,
    unguarded_data_routes,
)
from intake_api.doctor_link.service import (  # noqa: E402
    FailClosedDoctorLinkDelivery,
    RecipientChannelUnconfiguredError,
)
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter  # noqa: E402

VISIT_DATE = "2026-09-20"
VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": VISIT_DATE,
}
NOTE_BODY: dict[str, Any] = {
    "sections": [
        {"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Göğüs ağrısı"]},
        {"id": "hpi", "title": "Şikâyet öyküsü", "lines": ["Birkaç gündür"]},
        {"id": "medications", "title": "Kullandığı ilaçlar", "lines": ["Metoprolol"]},
    ],
    "scopes": {"medications": False},
    "status": "sent",
}
RECIPIENT = "Dr. Ayşe Yılmaz · Kardiyoloji"


class Clock:
    """The suite's only clock. Seeded from the START of an OTP rate-limit
    window (the INT-285 rule): ``auth_store`` counts in fixed windows keyed on
    ``floor(now / OTP_WINDOW_S)``, so a wall-clock seed would make every budget
    assertion depend on the minute CI happened to start."""

    def __init__(self, at: datetime) -> None:
        raw = at.timestamp()
        self.now = float(int(raw) // OTP_WINDOW_S * OTP_WINDOW_S) + 60.0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now

    @property
    def utc(self) -> datetime:
        return datetime.fromtimestamp(self.now, UTC)


def _auth_wiring(clock: Clock, *, dev_peek: bool = False) -> AuthWiring:
    """The OTP/Doctor Link tier over fakeredis. Nothing dials a network."""
    return AuthWiring(
        redis_client=fakeredis.FakeRedis(),
        tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
        delivery=DevLogDeliveryAdapter(),
        attestation=FailClosedAttestationVerifier(),
        dev_otp_peek=dev_peek,
        now_fn=clock,
    )


@dataclass
class Fixture:
    harness: ApiHarness
    clock: Clock
    visit_id: str

    @property
    def client(self) -> TestClient:
        return self.harness.client

    def patient(self) -> dict[str, str]:
        return self.harness.patient()

    # --- the patient's side ---------------------------------------------------

    def issue(self, **overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {"recipient": RECIPIENT, **overrides}
        response = self.client.post(
            f"/v1/visits/{self.visit_id}/note/doctor-links",
            json=payload,
            headers=self.patient(),
        )
        assert response.status_code == 201, response.text
        body: dict[str, Any] = response.json()
        return body

    def mint(self, link_id: str) -> str:
        response = self.client.post(
            f"/v1/visits/{self.visit_id}/note/doctor-links/{link_id}/otp",
            headers=self.patient(),
        )
        assert response.status_code == 200, response.text
        code: str = response.json()["code"]
        # every mint spends the resend cooldown, so the next one needs the clock
        self.clock.advance(RESEND_COOLDOWN_S + 1)
        return code

    def revoke(self, link_id: str) -> Any:
        return self.client.post(
            f"/v1/visits/{self.visit_id}/note/doctor-links/{link_id}/revoke",
            headers=self.patient(),
        )

    def links(self) -> list[dict[str, Any]]:
        response = self.client.get(
            f"/v1/visits/{self.visit_id}/note/doctor-links", headers=self.patient()
        )
        assert response.status_code == 200, response.text
        rows: list[dict[str, Any]] = response.json()
        return rows

    def access_log(self) -> list[dict[str, Any]]:
        response = self.client.get(
            f"/v1/visits/{self.visit_id}/note/doctor-links/access-log", headers=self.patient()
        )
        assert response.status_code == 200, response.text
        rows: list[dict[str, Any]] = response.json()
        return rows

    # --- the clinician's side --------------------------------------------------

    def view(self, token: str, code: str) -> Any:
        return self.client.post("/v1/doctor-link/view", json={"token": token, "code": code})

    def open_once(self, issued: dict[str, Any]) -> Any:
        code = self.mint(str(issued["link_id"]))
        return self.view(str(issued["token"]), code)

    # --- direct row access (state a test constructs rather than waits for) -----

    def row(self, link_id: str) -> DoctorLink:
        async def _load() -> DoctorLink:
            async with AsyncSession(self.harness.engine) as session:
                row = await session.scalar(
                    select(DoctorLink).where(DoctorLink.id == uuid.UUID(link_id))
                )
                assert row is not None
                return row

        loaded: DoctorLink = run(_load())
        return loaded


@pytest.fixture()
def fixture(tmp_path: Path) -> Iterator[Fixture]:
    clock = Clock(datetime(2026, 9, 15, 9, 0, tzinfo=UTC))
    harnesses = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        auth=_auth_wiring(clock),
    )
    harness = next(harnesses)
    visit = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert visit.status_code == 201, visit.text
    visit_id = str(visit.json()["id"])
    note = harness.client.put(
        f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=harness.patient()
    )
    assert note.status_code == 200, note.text
    yield Fixture(harness=harness, clock=clock, visit_id=visit_id)
    for _ in harnesses:  # drain the generator so the harness tears down
        pass


# --- entropy (acceptance: "entropy ... tests") --------------------------------------


def test_the_token_is_128_bits_from_the_csprng() -> None:
    token = new_token()
    padding = "=" * (-len(token) % 4)
    assert len(base64.urlsafe_b64decode(token + padding)) * 8 == TOKEN_ENTROPY_BITS
    assert TOKEN_ENTROPY_BITS == 128, "files/10 §2: 128-bit random token"


def test_tokens_do_not_repeat() -> None:
    draws = {new_token() for _ in range(2048)}
    assert len(draws) == 2048


def test_the_token_source_is_secrets_and_never_random() -> None:
    """Near-miss negative control on the generator itself.

    A ``random.choice`` implementation passes every statistical check above —
    2048 distinct 22-character strings — and is still predictable from a few
    observations. The only checkable difference is which module is imported.
    """
    source = Path(
        str(Path(__file__).resolve().parents[2])
        + "/packages/intake_platform/src/intake_platform/doctor_link.py"
    ).read_text(encoding="utf-8")
    assert "import secrets" in source
    assert "import random" not in source
    assert "secrets.token_urlsafe" in source


def test_only_the_fingerprint_is_stored_and_the_compare_is_constant_time(
    fixture: Fixture,
) -> None:
    issued = fixture.issue()
    row = fixture.row(str(issued["link_id"]))
    token = str(issued["token"])
    assert row.token_fingerprint != token
    assert row.token_fingerprint == token_fingerprint(token)
    assert token_matches(token, row.token_fingerprint)
    assert not token_matches(token + "x", row.token_fingerprint)
    # nothing in the persisted row carries the token in any form
    serialised = json.dumps(
        {
            "fingerprint": row.token_fingerprint,
            "recipient": row.recipient,
            "id": str(row.id),
        }
    )
    assert token not in serialised


def test_the_token_never_appears_in_a_log_line(
    fixture: Fixture, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        issued = fixture.issue()
        code = fixture.mint(str(issued["link_id"]))
        assert fixture.view(str(issued["token"]), code).status_code == 200
    text = caplog.text
    assert str(issued["token"]) not in text
    assert code not in text
    assert RECIPIENT not in text


# --- expiry (acceptance: "... expiry tests"; files/02 §2b) --------------------------


def test_expiry_is_anchored_on_the_visit_and_not_on_issue_time(fixture: Fixture) -> None:
    issued = fixture.issue()
    expires = datetime.fromisoformat(str(issued["expires_at"]))
    assert expires == link_expires_at(datetime.fromisoformat(VISIT_DATE).date())
    # the whole point of 02 §2b: a note prepared days early must NOT expire on
    # an issue-time clock, which here would be five days too early
    assert expires > fixture.clock.utc + DOCTOR_LINK_TTL


def test_the_anchor_is_the_start_of_the_visit_day_in_turkiye() -> None:
    """The start of the day is never later than the appointment, so the
    computed expiry is never later than files/02 §2b's ``visit_datetime + 72 h``
    — the schema records no time of day and none is invented."""
    expires = link_expires_at(datetime.fromisoformat("2026-09-20").date())
    # 2026-09-20 00:00 +03:00 is 2026-09-19 21:00 UTC; + 72 h
    assert expires == datetime(2026, 9, 22, 21, 0, tzinfo=UTC)
    assert expires - datetime(2026, 9, 20, 21, 0, tzinfo=UTC) == timedelta(hours=48)


def test_a_visit_with_no_date_gets_no_link(fixture: Fixture) -> None:
    undated = fixture.client.post(
        "/v1/visits",
        json={"hospital": "H", "department": "D"},
        headers=fixture.patient(),
    )
    assert undated.status_code == 201, undated.text
    visit_id = str(undated.json()["id"])
    assert (
        fixture.client.put(
            f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=fixture.patient()
        ).status_code
        == 200
    )
    refused = fixture.client.post(
        f"/v1/visits/{visit_id}/note/doctor-links",
        json={"recipient": RECIPIENT},
        headers=fixture.patient(),
    )
    assert refused.status_code == 422
    assert refused.json() == {"error": "visit_date_unknown"}


def test_expiry_is_exact(fixture: Fixture) -> None:
    """NEAR-MISS: expired by exactly one second is expired.

    An implementation using ``>=`` where the spec means ``>``, or comparing
    dates rather than instants, passes every other test in this file.
    """
    issued = fixture.issue()
    expires = datetime.fromisoformat(str(issued["expires_at"]))

    # a code minted two minutes before the deadline is still inside its own
    # 5-minute TTL on both sides of it, so the ONLY thing that changes between
    # the two calls below is which side of the deadline the clock is on
    fixture.clock.now = (expires - timedelta(seconds=120)).timestamp()
    code = fixture.mint(str(issued["link_id"]))
    fixture.clock.now = (expires - timedelta(seconds=1)).timestamp()
    alive = fixture.view(str(issued["token"]), code)
    assert alive.status_code == 200, alive.text

    code = fixture.mint(str(issued["link_id"]))
    fixture.clock.now = (expires + timedelta(seconds=1)).timestamp()
    dead = fixture.view(str(issued["token"]), code)
    assert dead.status_code == 410
    assert dead.json() == {"error": "doctor_link_expired"}


# --- view limit ----------------------------------------------------------------------


def test_the_default_view_limit_is_applied_and_can_only_be_tightened(
    fixture: Fixture,
) -> None:
    assert fixture.issue()["view_limit"] == DEFAULT_VIEW_LIMIT
    assert fixture.issue(view_limit=2)["view_limit"] == 2
    too_wide = fixture.client.post(
        f"/v1/visits/{fixture.visit_id}/note/doctor-links",
        json={"recipient": RECIPIENT, "view_limit": DEFAULT_VIEW_LIMIT + 1},
        headers=fixture.patient(),
    )
    assert too_wide.status_code == 422


def test_the_view_after_the_last_one_is_refused(fixture: Fixture) -> None:
    """NEAR-MISS: the (limit + 1)th view. An off-by-one that admits it passes
    a test that only opens the link once."""
    issued = fixture.issue(view_limit=2)
    first = fixture.open_once(issued)
    assert first.status_code == 200, first.text
    assert first.json()["view_index"] == 1
    assert first.json()["views_remaining"] == 1

    second = fixture.open_once(issued)
    assert second.status_code == 200, second.text
    assert second.json()["view_index"] == 2
    assert second.json()["views_remaining"] == 0

    # the patient cannot even mint a code for a spent link
    refused_mint = fixture.client.post(
        f"/v1/visits/{fixture.visit_id}/note/doctor-links/{issued['link_id']}/otp",
        headers=fixture.patient(),
    )
    assert refused_mint.status_code == 403
    assert refused_mint.json() == {"error": "doctor_link_view_limit"}

    # and a caller who already HOLDS a valid code — the concurrent-tab case —
    # is refused by the budget itself rather than by the missing code. The
    # code is re-armed directly because the route that mints one now refuses.
    service = fixture.harness.client.app.state.api.doctor_link
    run(service.remember(uuid.UUID(str(issued["link_id"])), "424242"))
    third = fixture.view(str(issued["token"]), "424242")
    assert third.status_code == 403
    assert third.json() == {"error": "doctor_link_view_limit"}
    assert fixture.row(str(issued["link_id"])).views_used == 2


def test_a_refused_consent_costs_the_patient_no_view(fixture: Fixture) -> None:
    issued = fixture.issue(view_limit=1)
    code = fixture.mint(str(issued["link_id"]))
    fixture.harness.revoke_consent("share:previsit_note")
    refused = fixture.view(str(issued["token"]), code)
    assert refused.status_code == 403
    assert refused.json() == {"error": "consent_required", "scope": "share:previsit_note"}
    assert fixture.row(str(issued["link_id"])).views_used == 0


# --- revocation ----------------------------------------------------------------------


def test_revocation_is_immediate(fixture: Fixture) -> None:
    """NEAR-MISS: the token used immediately after revocation, with no clock
    movement at all."""
    issued = fixture.issue()
    code = fixture.mint(str(issued["link_id"]))
    revoked = fixture.revoke(str(issued["link_id"]))
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] is True
    assert fixture.view(str(issued["token"]), code).status_code == 404


def test_revocation_holds_even_if_the_routing_hint_comes_back(fixture: Fixture) -> None:
    """The database is the authority, not the Redis routing hint.

    Revoking drops the fingerprint→(tenant, link) index, so an ordinary
    redemption 404s. This forces the index back — the state an attacker with
    Redis write access would create — and proves the row's own ``revoked_at``
    still refuses.
    """
    issued = fixture.issue()
    code = fixture.mint(str(issued["link_id"]))
    row = fixture.row(str(issued["link_id"]))
    assert fixture.revoke(str(issued["link_id"])).status_code == 200

    service = fixture.harness.client.app.state.api.doctor_link
    run(
        service.register(
            fingerprint=row.token_fingerprint,
            link_id=row.id,
            tenant_id=row.tenant_id,
            ttl_s=3600,
        )
    )
    denied = fixture.view(str(issued["token"]), code)
    assert denied.status_code == 410
    assert denied.json() == {"error": "doctor_link_revoked"}


def test_a_withdrawn_share_consent_cannot_lock_the_revoke_button(fixture: Fixture) -> None:
    """files/06 §2.1: a patient who withdrew consent to share must still be
    able to stop the sharing they already started. Issuing and minting refuse;
    revoking and the access log do not."""
    issued = fixture.issue()
    fixture.harness.revoke_consent("share:previsit_note")

    blocked = fixture.client.post(
        f"/v1/visits/{fixture.visit_id}/note/doctor-links",
        json={"recipient": RECIPIENT},
        headers=fixture.patient(),
    )
    assert blocked.status_code == 403
    assert blocked.json() == {"error": "consent_required", "scope": "share:previsit_note"}
    assert (
        fixture.client.post(
            f"/v1/visits/{fixture.visit_id}/note/doctor-links/{issued['link_id']}/otp",
            headers=fixture.patient(),
        ).status_code
        == 403
    )

    assert fixture.revoke(str(issued["link_id"])).status_code == 200
    assert fixture.access_log()


def test_revoking_the_share_revokes_every_link_on_it(fixture: Fixture) -> None:
    """Taking the note back to draft must not leave an open link behind."""
    issued = fixture.issue()
    code = fixture.mint(str(issued["link_id"]))
    draft = fixture.client.put(
        f"/v1/visits/{fixture.visit_id}/note",
        json={**NOTE_BODY, "status": "draft"},
        headers=fixture.patient(),
    )
    assert draft.status_code == 200, draft.text
    assert fixture.row(str(issued["link_id"])).revoked_at is not None
    assert fixture.view(str(issued["token"]), code).status_code == 410


def test_revoking_twice_writes_one_audit_entry(fixture: Fixture) -> None:
    issued = fixture.issue()
    assert fixture.revoke(str(issued["link_id"])).status_code == 200
    assert fixture.revoke(str(issued["link_id"])).status_code == 200
    revocations = [row for row in fixture.access_log() if row["category"] == "share_revoked"]
    assert len(revocations) == 1


def test_a_link_over_a_note_that_was_never_sent_is_refused(fixture: Fixture) -> None:
    draft = fixture.client.put(
        f"/v1/visits/{fixture.visit_id}/note",
        json={**NOTE_BODY, "status": "draft"},
        headers=fixture.patient(),
    )
    assert draft.status_code == 200
    refused = fixture.client.post(
        f"/v1/visits/{fixture.visit_id}/note/doctor-links",
        json={"recipient": RECIPIENT},
        headers=fixture.patient(),
    )
    assert refused.status_code == 409
    assert refused.json() == {"error": "note_not_shared"}


# --- the token itself ------------------------------------------------------------------


def test_a_token_one_character_off_opens_nothing(fixture: Fixture) -> None:
    """NEAR-MISS: one character different from a valid token."""
    issued = fixture.issue()
    code = fixture.mint(str(issued["link_id"]))
    token = str(issued["token"])
    swapped = ("A" if token[0] != "A" else "B") + token[1:]
    assert swapped != token and len(swapped) == len(token)
    assert fixture.view(swapped, code).status_code == 404
    # and the real one still works, so the refusal was about the token
    assert fixture.view(token, code).status_code == 200


def test_no_route_carries_the_token_in_a_url(fixture: Fixture) -> None:
    """A token in a path or a query string reaches access logs, Referer
    headers, browser history and proxy traces (invariant 6)."""
    openapi = fixture.client.get("/openapi.json").json()
    for path, operations in openapi["paths"].items():
        if "doctor-link" not in path:
            continue
        assert "token" not in path, path
        for method, operation in operations.items():
            names = {p["name"] for p in operation.get("parameters", [])}
            assert not any("token" in name or "code" in name for name in names), (
                f"{method.upper()} {path} carries a credential in the URL: {names}"
            )


def test_the_token_is_returned_exactly_once(fixture: Fixture) -> None:
    issued = fixture.issue()
    listed = fixture.links()
    assert listed and all("token" not in row for row in listed)
    code = fixture.mint(str(issued["link_id"]))
    view = fixture.view(str(issued["token"]), code)
    assert view.status_code == 200
    assert "token" not in view.json()


# --- the OTP, on the INT-131 gate ------------------------------------------------------


def test_a_code_one_digit_off_is_refused_generically(fixture: Fixture) -> None:
    issued = fixture.issue()
    code = fixture.mint(str(issued["link_id"]))
    wrong = f"{(int(code) + 1) % 10**6:06d}"
    refused = fixture.view(str(issued["token"]), wrong)
    assert refused.status_code == 401
    assert refused.json() == {"error": "otp_invalid"}
    # the right code still works: the refusal was about the code
    assert fixture.view(str(issued["token"]), code).status_code == 200


def test_the_attempt_budget_kills_the_code(fixture: Fixture) -> None:
    issued = fixture.issue()
    code = fixture.mint(str(issued["link_id"]))
    wrong = f"{(int(code) + 1) % 10**6:06d}"
    for _ in range(OTP_MAX_ATTEMPTS):
        assert fixture.view(str(issued["token"]), wrong).status_code == 401
    # NEAR-MISS: the RIGHT code on the attempt after the budget is spent
    dead = fixture.view(str(issued["token"]), code)
    assert dead.status_code == 401
    assert dead.json() == {"error": "otp_invalid"}


def test_a_code_expires_with_the_shared_otp_ttl(fixture: Fixture) -> None:
    issued = fixture.issue()
    code = fixture.mint(str(issued["link_id"]))
    fixture.clock.advance(OTP_TTL_S + 1)
    assert fixture.view(str(issued["token"]), code).status_code == 401


def test_the_mint_path_runs_the_shared_resend_cooldown(fixture: Fixture) -> None:
    issued = fixture.issue()
    link_id = str(issued["link_id"])
    first = fixture.client.post(
        f"/v1/visits/{fixture.visit_id}/note/doctor-links/{link_id}/otp",
        headers=fixture.patient(),
    )
    assert first.status_code == 200
    burst = fixture.client.post(
        f"/v1/visits/{fixture.visit_id}/note/doctor-links/{link_id}/otp",
        headers=fixture.patient(),
    )
    assert burst.status_code == 429
    assert burst.json()["error"] == "otp_limited"
    assert "Retry-After" in burst.headers


def test_two_links_do_not_share_one_attempt_budget(fixture: Fixture) -> None:
    """A brute-forcer working on one link must not lock out another."""
    first = fixture.issue()
    second = fixture.issue()
    first_code = fixture.mint(str(first["link_id"]))
    second_code = fixture.mint(str(second["link_id"]))
    for _ in range(OTP_MAX_ATTEMPTS):
        assert fixture.view(str(first["token"]), "000000").status_code == 401
    assert fixture.view(str(second["token"]), second_code).status_code == 200
    assert first_code  # the first link's own code is dead, which is the point


def test_the_public_delivery_route_gates_first_then_fails_closed(fixture: Fixture) -> None:
    """files/10 §2's channel does not exist, and the refusal is honest.

    The abuse gate runs BEFORE the delivery attempt, so the second call inside
    the resend cooldown is refused by the gate rather than by the missing
    channel — which is what proves the control is real the day a channel lands.
    """
    issued = fixture.issue()
    first = fixture.client.post("/v1/doctor-link/otp", json={"token": str(issued["token"])})
    assert first.status_code == 503
    assert first.json() == {"error": "doctor_link_delivery_unconfigured"}
    second = fixture.client.post("/v1/doctor-link/otp", json={"token": str(issued["token"])})
    assert second.status_code == 429


def test_a_failed_delivery_does_not_kill_a_code_the_patient_already_minted(
    fixture: Fixture,
) -> None:
    issued = fixture.issue()
    code = fixture.mint(str(issued["link_id"]))
    assert (
        fixture.client.post("/v1/doctor-link/otp", json={"token": str(issued["token"])}).status_code
        == 503
    )
    assert fixture.view(str(issued["token"]), code).status_code == 200


def test_the_only_wired_delivery_adapter_refuses() -> None:
    with pytest.raises(RecipientChannelUnconfiguredError):
        FailClosedDoctorLinkDelivery().send(link_ref="doctor_link:x", code="000000")


# --- watermark (acceptance: "watermark carries recipient+timestamp") -------------------


def test_the_watermark_carries_the_recipient_and_the_timestamp(fixture: Fixture) -> None:
    issued = fixture.issue()
    view = fixture.open_once(issued).json()
    assert view["watermark_recipient"] == RECIPIENT
    assert view["watermark_viewed_at_utc"] == fixture.clock.utc.replace(microsecond=0).isoformat()
    assert view["watermark_link_ref"] == f"doctor_link:{issued['link_id']}"
    assert RECIPIENT in view["watermark_line"]
    assert view["watermark_viewed_at_utc"] in view["watermark_line"]


def test_the_watermark_survives_into_the_committed_pdf_renderer() -> None:
    """The stamp is data until something draws it. ``render_document_pdf``
    (INT-084) takes the watermark line verbatim, so this asserts the bytes."""
    watermark = Watermark.compose(
        recipient=RECIPIENT,
        viewed_at=datetime(2026, 9, 20, 8, 30, tzinfo=UTC),
        link_id="8b1d",
    )
    pdf = render_document_pdf(
        title="Ön görüşme notu",
        lines=["Göğüs ağrısı"],
        footer="footer fixture — the real one renders from docs/legal (INT-210)",
        watermark=watermark.render(),
        escape_unencodable=True,
    )
    assert b"Kardiyoloji" in pdf
    assert b"2026-09-20T08:30:00+00:00" in pdf


def test_the_watermark_says_nothing_about_the_viewer(fixture: Fixture) -> None:
    """It must not become a way to identify the reader beyond the consent."""
    issued = fixture.issue()
    view = fixture.open_once(issued).json()
    assert set(view) >= {"watermark_recipient", "watermark_viewed_at_utc", "watermark_link_ref"}
    blob = json.dumps(view)
    for leak in ("testclient", "user_agent", "User-Agent", "127.0.0.1", "python-httpx"):
        assert leak not in blob
    # and the field set is closed: no viewer-derived key can have crept in
    assert {key for key in view if key.startswith("watermark_")} == {
        "watermark_recipient",
        "watermark_viewed_at_utc",
        "watermark_link_ref",
        "watermark_line",
    }


def test_a_recipient_label_is_bounded_and_single_line() -> None:
    assert normalise_recipient("  Dr. X  ") == "Dr. X"
    for bad in ("", "   ", "Dr.\nX", "Dr.\x00X", "x" * 121):
        with pytest.raises(RecipientInvalidError):
            normalise_recipient(bad)


def test_the_recipient_is_encrypted_at_rest(fixture: Fixture) -> None:
    issued = fixture.issue()
    row = fixture.row(str(issued["link_id"]))
    assert set(row.recipient) == {"key_version", "wrapped_dek", "nonce", "ciphertext"}
    assert RECIPIENT not in json.dumps(row.recipient)


# --- audit + the patient's access log ---------------------------------------------------


def test_every_open_is_audited_and_visible_to_the_patient(fixture: Fixture) -> None:
    """The acceptance's last clause, end to end."""
    issued = fixture.issue()
    assert fixture.open_once(issued).status_code == 200
    rows = fixture.access_log()
    opens = [row for row in rows if row["category"] == "record_viewed"]
    assert len(opens) == 1
    (opened,) = opens
    assert opened["resource_ref"] == f"doctor_link:{issued['link_id']}"
    assert opened["accessor_role"] == "clinician"
    assert {row["category"] for row in rows} >= {"record_shared", "record_viewed"}


def test_the_access_log_rows_are_chain_verified(fixture: Fixture) -> None:
    issued = fixture.issue()
    assert fixture.open_once(issued).status_code == 200
    entries = fixture.harness.audit_store.entries()
    assert verify_entries(entries).ok
    hashes = {entry.entry_hash for entry in entries}
    assert {row["entry_hash"] for row in fixture.access_log()} <= hashes


def test_the_access_log_carries_a_role_and_never_an_identity(fixture: Fixture) -> None:
    issued = fixture.issue()
    assert fixture.open_once(issued).status_code == 200
    blob = json.dumps(fixture.access_log())
    assert "dev-patient" not in blob
    assert RECIPIENT not in blob
    assert str(issued["token"]) not in blob


def test_the_access_log_shows_only_this_patients_refs(fixture: Fixture) -> None:
    issued = fixture.issue()
    assert fixture.open_once(issued).status_code == 200
    refs = {row["resource_ref"] for row in fixture.access_log()}
    assert refs
    assert all(ref.startswith(("note:", "share:", "doctor_link:")) for ref in refs), refs


# --- no-index (acceptance: "robots/noindex") --------------------------------------------


def test_every_doctor_link_response_is_unindexable(fixture: Fixture) -> None:
    issued = fixture.issue()
    code = fixture.mint(str(issued["link_id"]))
    responses = [
        fixture.client.post(
            f"/v1/visits/{fixture.visit_id}/note/doctor-links",
            json={"recipient": RECIPIENT},
            headers=fixture.patient(),
        ),
        fixture.client.get(
            f"/v1/visits/{fixture.visit_id}/note/doctor-links", headers=fixture.patient()
        ),
        fixture.client.get(
            f"/v1/visits/{fixture.visit_id}/note/doctor-links/access-log",
            headers=fixture.patient(),
        ),
        fixture.view(str(issued["token"]), code),
        fixture.client.post("/v1/doctor-link/view", json={"token": "x" * 22, "code": "000000"}),
        fixture.client.post("/v1/doctor-link/otp", json={"token": str(issued["token"])}),
    ]
    for response in responses:
        tag = response.headers.get("x-robots-tag", "")
        assert "noindex" in tag and "nofollow" in tag, (response.request.url, tag)


# --- scope: what a link may show ---------------------------------------------------------


def test_a_link_shows_only_the_sections_the_share_scoped_on(fixture: Fixture) -> None:
    """``medications`` is scope-off in NOTE_BODY, so the share never carried
    it. The section list is read off the share and is never hard-coded here."""
    issued = fixture.issue()
    view = fixture.open_once(issued).json()
    ids = [section["id"] for section in view["sections"]]
    assert ids == ["chief_complaint", "hpi"]
    assert "medications" not in ids


def test_the_view_carries_the_attribution_flags(fixture: Fixture) -> None:
    issued = fixture.issue()
    view = fixture.open_once(issued).json()
    assert view["proxy_reported"] is False
    assert view["third_party_present"] is False


# --- route declarations and the fail-closed tier -------------------------------------------


def test_no_route_is_undeclared_and_the_marker_is_caged(fixture: Fixture) -> None:
    app = fixture.client.app
    assert unguarded_data_routes(app) == []
    assert doctor_link_redemption_routes(app) == [
        "POST /v1/doctor-link/otp",
        "POST /v1/doctor-link/view",
    ]

    borrowed = FastAPI()

    @borrowed.get("/v1/doctor-linkish", dependencies=[doctor_link_redemption()])
    async def _lookalike() -> dict[str, str]:  # pragma: no cover — never called
        return {}

    @borrowed.get("/v1/sneaky", dependencies=[doctor_link_redemption()])
    async def _elsewhere() -> dict[str, str]:  # pragma: no cover — never called
        return {}

    assert sorted(unguarded_data_routes(borrowed)) == [
        "GET /v1/doctor-linkish",
        "GET /v1/sneaky",
    ]
    assert DOCTOR_LINK_PREFIX == "/v1/doctor-link"


def test_the_tier_fails_closed_without_redis(tmp_path: Path) -> None:
    harnesses = build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN)
    harness = next(harnesses)
    try:
        visit = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
        visit_id = str(visit.json()["id"])
        harness.client.put(f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=harness.patient())
        refused = harness.client.post(
            f"/v1/visits/{visit_id}/note/doctor-links",
            json={"recipient": RECIPIENT},
            headers=harness.patient(),
        )
        assert refused.status_code == 503
        assert refused.json() == {"error": "doctor_link_unconfigured"}
        assert (
            harness.client.post(
                "/v1/doctor-link/view", json={"token": "x" * 22, "code": "000000"}
            ).status_code
            == 503
        )
    finally:
        for _ in harnesses:
            pass


def test_a_clinic_admin_cannot_mint_a_link_for_someone(fixture: Fixture) -> None:
    refused = fixture.client.post(
        f"/v1/visits/{fixture.visit_id}/note/doctor-links",
        json={"recipient": RECIPIENT},
        headers=fixture.harness.admin(),
    )
    assert refused.status_code in {403, 404}
