"""INT-488 — what the security and legal reviews of 30 Oct 2026 added to the
App Store review sign-in (owner decision D39), each with a near miss:

- **the reviewer is a real person**: every window has its own reviewer patient,
  and opening and closing the window erase every reviewer subject through the
  DSAR erasure, so no reviewer sees another's input and nothing they enter
  outlives their review (legal review, finding 1);
- **sessions are bound to their window**: a token from one review is dead in
  every later one (security finding 5);
- **the live guards**: the deployment's bound data class (ADR-035) and hosted
  model lanes switched off for the reviewer tenant (security findings 2, 4);
- **the operator's rows do not fork the API's chain** (security finding 1):
  the API adopts rows another process appended, and refuses rows that do not
  chain from its head;
- **every label pair exists at zero**, so the first use of a kind alerts
  (security finding 3);
- **misses add up per generated code**: the cap closes the window (finding 9);
- **the reviewer answers as every number does under the spend kill switch**
  (finding 8), a limited request is audited, the CLI opens nothing it could
  not read or record, and the script's rotation and reveal are rows too.
"""

from __future__ import annotations

import io
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fakeredis
import pytest
import redis
from intake_platform.audit import AuditChain, AuditEntry, InMemoryAuditStore, verify_entries
from intake_platform.db.models import IntakeSession, SessionStatus
from intake_platform.model_lanes.model import ModelLanesControl, TenantDataClass
from intake_platform.model_lanes.store import InMemoryModelLanesStore, ModelLanesUnavailable
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import run  # noqa: E402
from intake_api.audit import AuditWriter  # noqa: E402
from intake_api.auth_store import OTP_LOCKOUT_S, OTP_MAX_ATTEMPTS, RESEND_COOLDOWN_S  # noqa: E402
from intake_api.dsar.grants import Privilege  # noqa: E402
from intake_api.sms_spend import SpendKillSwitch  # noqa: E402
from test_otp_abuse import PHONE, DpopClient, OtpHarness  # noqa: E402
from test_review_signin import (  # noqa: E402
    REPO,
    Voice,
    answer,
    ask,
    built,
    cli,
    cli_module,
    counted,
    draw,
    guards,
    harness,
    keyed,
    review,
    rows,
)

RUNBOOK = REPO / "docs" / "runbooks" / "review-signin.md"


def reset_now(otp: OtpHarness, **knobs: Any) -> Any:
    """The CLI's reset, run against the harness's own database and chain."""
    module = __import__("intake_api.review_reset", fromlist=["reset_review_tenant"])
    removed: list[str] = []

    def reset() -> str | None:
        try:
            run(
                module.reset_review_tenant(
                    otp.engine,
                    audit=AuditWriter(otp.audit_store),
                    remove_object=removed.append,
                    now=datetime.now(UTC),
                    **knobs,
                )
            )
        except module.ReviewResetBlocked as exc:
            return str(exc)
        return None

    return reset


def seed_session(otp: OtpHarness, tenant_id: uuid.UUID, patient_id: uuid.UUID) -> uuid.UUID:
    """A visit the reviewer (or a patient) left behind."""
    session_id = uuid.uuid4()

    async def seed() -> None:
        async with AsyncSession(otp.engine) as session, session.begin():
            session.add(
                IntakeSession(
                    id=session_id,
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    protocol_id="previsit.dev.visit",
                    protocol_version="int488-unit",
                    status=SessionStatus.CREATED,
                    started_at=datetime.now(UTC),
                )
            )

    run(seed())
    return session_id


def sessions_of(otp: OtpHarness, patient_id: str) -> list[tuple[Any, ...]]:
    return rows(otp, f"SELECT id FROM sessions WHERE patient_id = '{uuid.UUID(patient_id).hex}'")  # noqa: S608


# --- the reviewer's input is theirs: separated per window, erased after it -----------------------


def test_closing_the_window_erases_what_the_reviewer_left(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        consumer = otp.sign_up(DpopClient())
        bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        seed_session(otp, review().REVIEW_TENANT_ID, uuid.UUID(bundle["patient_id"]))
        seed_session(otp, uuid.UUID(consumer["tenant_id"]), uuid.UUID(consumer["patient_id"]))
        assert sessions_of(otp, bundle["patient_id"]) != []
        code, said, _ = cli("off", otp.redis_client, reset=reset_now(otp))
        assert code == 0, said
        assert sessions_of(otp, bundle["patient_id"]) == [], (
            "the reviewer's visit outlived the review"
        )
        # near miss: a consumer patient's record is untouched
        assert sessions_of(otp, consumer["patient_id"]) != []
        done = rows(otp, "SELECT status FROM dsar_requests")
        assert done == [("completed",)]
        acts = [entry.action for entry in otp.audit_store.entries()]
        assert "auth.review.reset" in acts and "dsar.delete.shred" in acts
        assert verify_entries(list(otp.audit_store.entries())).ok


def test_the_next_window_lands_a_different_reviewer_patient(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        first = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        assert cli("off", otp.redis_client, reset=reset_now(otp))[0] == 0
        assert cli("on", otp.redis_client, reset=reset_now(otp), now_fn=otp.clock)[0] == 0
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        second = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        assert second["patient_id"] != first["patient_id"]
        assert second["tenant_id"] == first["tenant_id"] == str(review().REVIEW_TENANT_ID)


def test_a_reset_the_erasure_refuses_keeps_the_window_shut(tmp_path: Path) -> None:
    reviewer = draw()
    missing = (Privilege("patient_overlays", "DELETE"),)
    with harness(tmp_path, reviewer) as otp:
        answer(otp, DpopClient(), reviewer, ask(otp, reviewer))
        blocked = reset_now(otp, privileges=lambda session: _missing(missing))
        code, said, _ = cli("off", otp.redis_client, reset=blocked)
        assert code == 1 and "patient_overlays" in said
        assert review().ReviewWindow(otp.redis_client, otp.clock).is_open() is False, (
            "closed regardless"
        )
        code, said, audited = cli("on", otp.redis_client, reset=blocked, now_fn=otp.clock)
        assert code == 1 and audited == [], "a window over a reviewer's data never opens"
        assert review().ReviewWindow(otp.redis_client, otp.clock).is_open() is False
        # near miss: once the erasure may run, the same tenant is emptied and opens
        assert cli("on", otp.redis_client, reset=reset_now(otp), now_fn=otp.clock)[0] == 0
        assert review().ReviewWindow(otp.redis_client, otp.clock).is_open() is True


async def _missing(missing: tuple[Privilege, ...]) -> tuple[Privilege, ...]:
    return missing


# --- sessions are bound to their window ------------------------------------------------------


def test_a_token_from_one_review_is_dead_in_the_next(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        dpop = DpopClient()
        bundle = answer(otp, dpop, reviewer, ask(otp, reviewer)).json()
        # near miss: inside its own window the token works
        assert otp.get_visits(dpop, bundle["access_token"]).status_code == 403
        window = review().ReviewWindow(otp.redis_client, otp.clock)
        window.close()
        window.open()
        assert otp.get_visits(dpop, bundle["access_token"]).status_code == 401
        assert otp.refresh(dpop, bundle["refresh_token"]).status_code == 401


# --- the live guards --------------------------------------------------------------------------


def _lanes(data_class: TenantDataClass | None) -> InMemoryModelLanesStore:
    control = ModelLanesControl.unconfigured().model_copy(update={"data_class": data_class})
    return InMemoryModelLanesStore(control)


class UnreadableLanes:
    def read(self) -> ModelLanesControl:
        raise ModelLanesUnavailable("model_lanes_unreachable")


LIVE_REFUSALS: dict[str, tuple[dict[str, Any], str]] = {
    "bound-real-phi": ({"lanes": _lanes(TenantDataClass.REAL_PHI)}, "not_synthetic"),
    "lanes-unreadable": ({"lanes": UnreadableLanes()}, "not_synthetic"),
    "no-voice-store": ({"voice": None}, "hosted_lanes_open"),
    "kill-switch-off": ({"voice": Voice(engaged=False)}, "hosted_lanes_open"),
    "kill-switch-unreadable": ({"voice": Voice(unreadable=True)}, "hosted_lanes_open"),
}


@pytest.mark.parametrize("case", sorted(LIVE_REFUSALS))
def test_a_live_guard_refuses_the_reviewer_with_nothing_minted(tmp_path: Path, case: str) -> None:
    knobs, outcome = LIVE_REFUSALS[case]
    reviewer = draw()
    signin = built(reviewer, keyed(), live=guards(**knobs))
    with harness(tmp_path, reviewer, signin=signin) as otp:
        before = counted("request", outcome)
        asked = ask(otp, reviewer)
        assert asked.status_code == 202
        assert list(otp.redis_client.scan_iter("auth:otp:code:*")) == []
        assert answer(otp, DpopClient(), reviewer, asked).status_code == 401
        assert counted("request", outcome) == before + 1
        assert otp.sends == 0


@pytest.mark.parametrize(
    "lanes",
    [None, _lanes(None), _lanes(TenantDataClass.SYNTHETIC)],
    ids=["no-lane-control", "unbound", "bound-synthetic"],
)
def test_near_miss_the_guards_admit_a_synthetic_host_with_hosted_lanes_off(
    tmp_path: Path, lanes: Any
) -> None:
    reviewer = draw()
    signin = built(reviewer, keyed(), live=guards(lanes=lanes))
    with harness(tmp_path, reviewer, signin=signin) as otp:
        assert answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).status_code == 200


def test_the_runbook_names_the_reviewer_tenant_the_kill_switch_is_for() -> None:
    assert str(review().REVIEW_TENANT_ID) in RUNBOOK.read_text(encoding="utf-8")


# --- the operator's rows and the API's chain ---------------------------------------------------


def test_the_api_adopts_rows_an_operator_appended_beside_it() -> None:
    store = InMemoryAuditStore()
    writer = AuditWriter(store)
    record = {"resource_ref": "review_signin:window", "consent_scope": "scope:auth"}
    run(writer.record(actor="system:api", action="auth.otp.requested", **record))
    # the owner's command, another process, another chain object
    AuditChain(store).append(
        actor="operator:host",
        action="auth.review.window.opened",
        resource_ref="review_signin:window",
        consent_scope_ref="scope:auth",
    )
    run(writer.record(actor="system:api", action="auth.review.requested", **record))
    entries = list(store.entries())
    assert [entry.seq for entry in entries] == [1, 2, 3]
    assert verify_entries(entries).ok


def test_near_miss_a_row_that_does_not_chain_is_refused() -> None:
    store = InMemoryAuditStore()
    writer = AuditWriter(store)
    record = {"resource_ref": "review_signin:window", "consent_scope": "scope:auth"}
    run(writer.record(actor="system:api", action="auth.otp.requested", **record))
    store.append(
        AuditEntry(
            seq=2,
            timestamp_utc=datetime.now(UTC).isoformat(),
            actor="operator:host",
            action="auth.review.window.opened",
            resource_ref="review_signin:window",
            consent_scope_ref="scope:auth",
            prev_hash="0" * 64,
            entry_hash="f" * 64,
        )
    )
    from intake_platform.audit import AuditChainForked

    with pytest.raises(AuditChainForked):
        run(writer.record(actor="system:api", action="auth.review.requested", **record))


# --- every label pair at zero -------------------------------------------------------------------


def test_every_label_pair_is_exported_before_its_first_use() -> None:
    for step, outcomes in review().REVIEW_LABELS.items():
        for outcome in outcomes:
            labels = {"step": step, "outcome": outcome}
            assert REGISTRY.get_sample_value("sec_review_signin_total", labels) is not None, labels


# --- misses add up per generated code -----------------------------------------------------------


def _miss_rounds(otp: OtpHarness, reviewer: Any, misses: int) -> None:
    done = 0
    while done < misses:
        otp.clock.advance(OTP_LOCKOUT_S + RESEND_COOLDOWN_S * 8)
        asked = ask(otp, reviewer)
        for _ in range(min(OTP_MAX_ATTEMPTS, misses - done)):
            answer(otp, DpopClient(), reviewer, asked, code=reviewer.wrong)
            done += 1


def test_the_miss_cap_closes_the_window(tmp_path: Path) -> None:
    reviewer = draw()
    cap = review().REVIEW_MISS_CAP
    with harness(tmp_path, reviewer) as otp:
        _miss_rounds(otp, reviewer, cap - 1)
        assert review().ReviewWindow(otp.redis_client, otp.clock).is_open(), (
            "near miss: one short of the cap"
        )
        _miss_rounds(otp, reviewer, 1)
        assert review().ReviewWindow(otp.redis_client, otp.clock).is_open() is False
        closing = [e for e in otp.audit_store.entries() if e.action == "auth.review.window.closed"]
        assert [entry.actor for entry in closing] == ["system:review-guard"]
        # the code is retired: reopening the window buys no more guesses, and
        # not even the right code signs in until a new one is generated
        assert cli("on", otp.redis_client, reset=reset_now(otp), now_fn=otp.clock)[0] == 0
        before = counted("verify", "code_retired")
        otp.clock.advance(OTP_LOCKOUT_S + RESEND_COOLDOWN_S * 8)
        assert answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).status_code == 401
        assert counted("verify", "code_retired") == before + 1
        # near miss: the latch is the retired code's own; another code has none
        latched = list(otp.redis_client.scan_iter("auth:review:misses:*"))
        assert len(latched) == 1 and otp.redis_client.ttl(latched[0]) == -1


def test_off_on_a_closed_window_still_erases_the_reviewer_tenant(tmp_path: Path) -> None:
    """The miss cap closes the window without erasing; the owner's --off on the
    closed window does it (legal review)."""
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        seed_session(otp, review().REVIEW_TENANT_ID, uuid.UUID(bundle["patient_id"]))
        review().ReviewWindow(otp.redis_client, otp.clock).close()
        code, said, audited = cli("off", otp.redis_client, reset=reset_now(otp))
        assert code == 0, said
        assert audited == [], "no flip, so no window row"
        assert sessions_of(otp, bundle["patient_id"]) == []


# --- the spend kill switch, a limited request, the CLI's own refusals -----------------------------


def test_under_the_spend_kill_switch_the_reviewer_answers_as_every_number(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        SpendKillSwitch(otp.redis_client).engage("manual")
        refused = ask(otp, reviewer)
        assert refused.status_code == 503
        assert refused.json() == otp.request_otp(PHONE).json()
        SpendKillSwitch(otp.redis_client).release()
        assert ask(otp, reviewer).status_code == 202


def test_a_limited_request_is_on_the_chain(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        for _ in range(4):  # the device budget is three an hour
            otp.clock.advance(RESEND_COOLDOWN_S * 4)
            last = ask(otp, reviewer)
        assert last.status_code == 429
        refs = [
            e.resource_ref for e in otp.audit_store.entries() if e.action == "auth.review.refused"
        ]
        assert "review:limited" in refs


class Down:
    def get(self, name: str) -> bytes:
        raise redis.ConnectionError("down")


def test_an_unreadable_window_is_not_opened_and_writes_no_row() -> None:
    code, said, audited = cli("on", Down())
    assert code == 1 and audited == [] and "unreadable" in said


class FailingOpen(fakeredis.FakeStrictRedis):
    def set(self, *args: Any, **kwargs: Any) -> Any:
        raise redis.ConnectionError("down")


def test_an_opening_that_fails_after_its_row_is_compensated() -> None:
    code, said, audited = cli("on", FailingOpen())
    assert code == 1
    assert audited == ["auth.review.window.opened", "auth.review.window.open_failed"]
    assert "stays closed" in said


@pytest.mark.parametrize(
    ("verb", "action"),
    [("rotated", "auth.review.code.rotated"), ("revealed", "auth.review.code.revealed")],
)
def test_the_scripts_rotation_and_reveal_are_rows(verb: str, action: str) -> None:
    fake = fakeredis.FakeStrictRedis()
    code, said, audited = cli(verb, fake)
    assert code == 0 and audited == [action] and said == ""

    def failing(action: str) -> None:
        raise RuntimeError("audit store down")

    assert cli(verb, fake, audit=failing)[0] == 1


def test_a_reset_that_fails_on_close_still_closes_and_says_so() -> None:
    fake = fakeredis.FakeStrictRedis()
    review().ReviewWindow(fake).open()
    out = io.StringIO()
    code = cli_module().main(
        ["off"],
        out=out,
        redis_factory=lambda: fake,
        audit=lambda action: None,
        readiness=lambda: None,
        reset=lambda: "the reviewer erasure is refused: missing patient_overlays",
    )
    assert code == 1 and review().ReviewWindow(fake).is_open() is False
    assert "not emptied" in out.getvalue()
