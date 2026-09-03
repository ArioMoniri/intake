"""INT-139 — the share centre's first acceptance clause, as a test.

> revocation cascades to tokens within 1 min (test); patient sees access log

INT-150 proves that a revoked grant is *refused* (``test_revocation_is_immediate``
and its routing-hint sibling). What it does not state is the clause INT-139 is
accepted against: that the refusal arrives inside a **bounded interval** after
the revoking write returns, and that the bound is not a promise about a cache
somebody has to remember to keep short.

Three tests, and the second and third are what make the first mean something.

**The measured one** issues a grant, revokes it, and attempts the redemption as
the very next statement — no ``sleep``, no clock advance, no retry loop. That
ordering is the point: an implementation that revoked into a cache with a
sixty-second TTL satisfies a test that waits a minute and fails this one, which
is exactly the failure mode "within 1 min" is written to exclude.

**The clock one** proves the refusal is not waiting on time at all. The same
sequence runs with the injected clock untouched and again with it advanced by
the whole budget, and both refuse identically. A time-based store passes the
second and fails the first; a row check cannot tell them apart.

**The cascade one** is the plural in "cascades to **tokens**". Three live grants
over one share, one revocation of the share, and all three have to stop.

The wall-clock interval these measure is a **measurement, not a property of the
product** (CLAUDE.md invariant 20). It is asserted here only against the ceiling
the acceptance names; the distribution, with its date and its corpus, is in
docs/evidence/INT-139.md, and no patient-facing or regulatory text repeats it.

The harness is built here rather than imported from ``test_doctor_link``. Two
reasons, and the second is the real one: pytest's fixture-by-import pattern puts
the fixture's name in this module's namespace, where every test that requests it
shadows the import and earns ruff's F811 — and the honest answer to a lint that
is telling the truth about a module's shape is a different shape, not an ignore.
The wiring below is deliberately the smallest thing that serves these three
tests: one visit, one sent note, one injected clock.
"""

from __future__ import annotations

import sys
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import fakeredis
import pytest
from fastapi.testclient import TestClient
from intake_platform.db.models import DoctorLink
from intake_platform.tokenization import Tokenizer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run  # noqa: E402
from intake_api.attestation import FailClosedAttestationVerifier  # noqa: E402
from intake_api.auth_store import OTP_WINDOW_S, RESEND_COOLDOWN_S  # noqa: E402
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter  # noqa: E402

#: The acceptance's own bound, in seconds. It is a CEILING this asserts the
#: implementation stays under — never a figure any document or screen quotes as
#: a property of the service (invariant 20).
REVOCATION_BUDGET_S: Final = 60.0

VISIT_BODY: Final[dict[str, str]] = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-09-20",
}
NOTE_BODY: Final[dict[str, Any]] = {
    "sections": [
        {"id": "chief_complaint", "title": "Başvuru nedeni", "lines": ["Göğüs ağrısı"]},
    ],
    "scopes": {},
    "status": "sent",
}
RECIPIENT: Final = "Kardiyoloji"


class Clock:
    """The one clock this module uses, seeded at the start of an OTP rate-limit
    window so no budget assertion depends on the minute CI happened to start."""

    def __init__(self, at: datetime) -> None:
        self.now = float(int(at.timestamp()) // OTP_WINDOW_S * OTP_WINDOW_S) + 60.0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


@dataclass
class Centre:
    harness: ApiHarness
    clock: Clock
    visit_id: str

    @property
    def client(self) -> TestClient:
        return self.harness.client

    def patient(self) -> dict[str, str]:
        return self.harness.patient()

    def issue(self) -> dict[str, Any]:
        response = self.client.post(
            f"/v1/visits/{self.visit_id}/note/doctor-links",
            json={"recipient": RECIPIENT},
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
        self.clock.advance(RESEND_COOLDOWN_S + 1)
        return code

    def revoke(self, link_id: str) -> Any:
        return self.client.post(
            f"/v1/visits/{self.visit_id}/note/doctor-links/{link_id}/revoke",
            headers=self.patient(),
        )

    def view(self, token: str, code: str) -> Any:
        return self.client.post("/v1/doctor-link/view", json={"token": token, "code": code})

    def row(self, link_id: str) -> DoctorLink:
        async def _load() -> DoctorLink:
            async with AsyncSession(self.harness.engine) as session:
                found = await session.scalar(
                    select(DoctorLink).where(DoctorLink.id == uuid.UUID(link_id))
                )
                assert found is not None
                return found

        loaded: DoctorLink = run(_load())
        return loaded


@pytest.fixture()
def centre(tmp_path: Path) -> Iterator[Centre]:
    clock = Clock(datetime(2026, 9, 15, 9, 0, tzinfo=UTC))
    harnesses = build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        auth=AuthWiring(
            redis_client=fakeredis.FakeRedis(),
            tokenizer=Tokenizer(keys={"v1": b"int139-share-centre-test-key"}, active_key_id="v1"),
            delivery=DevLogDeliveryAdapter(),
            attestation=FailClosedAttestationVerifier(),
            dev_otp_peek=False,
            now_fn=clock,
        ),
    )
    harness = next(harnesses)
    visit = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert visit.status_code == 201, visit.text
    visit_id = str(visit.json()["id"])
    note = harness.client.put(
        f"/v1/visits/{visit_id}/note", json=NOTE_BODY, headers=harness.patient()
    )
    assert note.status_code == 200, note.text
    yield Centre(harness=harness, clock=clock, visit_id=visit_id)
    for _ in harnesses:  # drain the generator so the harness tears down
        pass


def _revoke_then_redeem(centre: Centre) -> tuple[float, int]:
    """Issue, revoke, and redeem as the next statement. Returns the elapsed
    seconds between the revoke returning and the refusal arriving, and the
    status the redemption was refused with."""
    issued = centre.issue()
    code = centre.mint(str(issued["link_id"]))
    revoked = centre.revoke(str(issued["link_id"]))
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] is True
    at_revoke = time.perf_counter()
    attempt = centre.view(str(issued["token"]), code)
    return time.perf_counter() - at_revoke, attempt.status_code


def test_the_revocation_reaches_the_redemption_path_inside_the_budget(centre: Centre) -> None:
    elapsed, status = _revoke_then_redeem(centre)
    assert status != 200, "a revoked grant opened"
    assert elapsed <= REVOCATION_BUDGET_S, (
        f"the redemption path still admitted the revoked grant {elapsed:.3f} s after "
        f"the revoke returned, against a budget of {REVOCATION_BUDGET_S} s"
    )
    # The measurement has to be a measurement: a harness that recorded zero
    # would satisfy any ceiling, and would be asserting nothing at all.
    assert elapsed > 0.0


def test_the_refusal_does_not_wait_for_any_clock(centre: Centre) -> None:
    """NEAR-MISS: a revocation held in a store that expires on a timer.

    Such an implementation refuses once the timer lapses and admits before it
    does. Running the same sequence at two points on the injected clock — no
    movement at all, and a full budget's worth — separates it from a row check,
    which cannot tell the two apart because it never reads a clock.
    """
    # no movement on the clock at all: the case a TTL-backed revocation fails
    immediate_elapsed, immediate_status = _revoke_then_redeem(centre)
    assert immediate_status != 200

    centre.clock.advance(REVOCATION_BUDGET_S)
    later_elapsed, later_status = _revoke_then_redeem(centre)
    assert later_status == immediate_status, (
        "the refusal changed with the clock, so something on this path is "
        "time-based rather than reading the row"
    )
    assert immediate_elapsed <= REVOCATION_BUDGET_S
    assert later_elapsed <= REVOCATION_BUDGET_S


def test_revoking_the_share_reaches_every_token_on_it_inside_the_budget(centre: Centre) -> None:
    """The acceptance says revocation cascades to TOKENS, plural.

    INT-150 proves the cascade with ONE link
    (``test_revoking_the_share_revokes_every_link_on_it``), and with one link a
    loop that stops after the first row is indistinguishable from one that does
    not. Three live grants over one share separate them.

    Both halves are asserted, and the reason is a finding rather than caution.
    Mutating ``_revoke_links_of_share`` to revoke only ``links[:1]`` leaves
    every redemption still refused — ``redeem`` checks the SHARE's own
    ``revoked_at`` before it looks at the link — so a test that only tried the
    tokens passes against a broken cascade and reports it as working. That
    row-level cascade is a real control, not a redundancy: it is what stops a
    link outliving its share if the share check ever moves. So this asserts the
    behaviour the acceptance names (every token stops) AND the state INT-150
    wrote to guarantee it (every row carries ``revoked_at``), and the mutation
    reddens the second.
    """
    grants = []
    for _ in range(3):
        # each mint spends a resend cooldown and a slice of the request budget;
        # the budget is the abuse control, not the subject of this test
        centre.clock.advance(OTP_WINDOW_S + 1)
        issued = centre.issue()
        grants.append((issued, centre.mint(str(issued["link_id"]))))
    assert len({str(g["link_id"]) for g, _ in grants}) == 3

    # Taking the note back to draft revokes the live share, which is the
    # cascade the acceptance names.
    draft = centre.client.put(
        f"/v1/visits/{centre.visit_id}/note",
        json={**NOTE_BODY, "status": "draft"},
        headers=centre.patient(),
    )
    assert draft.status_code == 200, draft.text
    at_revoke = time.perf_counter()

    for issued, code in grants:
        attempt = centre.view(str(issued["token"]), code)
        assert attempt.status_code != 200, f"{issued['link_id']} survived the cascade"
    elapsed = time.perf_counter() - at_revoke

    for issued, _ in grants:
        assert centre.row(str(issued["link_id"])).revoked_at is not None, (
            f"{issued['link_id']} still has no revoked_at: the row-level cascade "
            "stopped early, and only the share check is refusing the redemption"
        )
    assert elapsed <= REVOCATION_BUDGET_S, (
        f"the last of three grants was still reachable {elapsed:.3f} s after the "
        f"share was revoked, against a budget of {REVOCATION_BUDGET_S} s"
    )
