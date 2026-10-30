"""INT-488 — the App Review window closes itself 14 days after ``--on``.

The orchestrator's instruction of 30 Oct 2026, replacing the owner ask the
security re-review raised: a fail-closed engineering default, not a value for
the owner to supply. On a fake clock:

- at 13 days 23 hours the window is still open and the reviewer signs in
  (the near miss);
- at 14 days it reads closed at once, to every reviewer step and session, and
  the API closes it the way ``--off`` does: the document first, the audit row
  (``auth.review.window.closed`` by ``system:review-expiry``) second, the
  reviewer tenant's erasure last — on the next reviewer step or its own sweep;
- nothing reopens it but a fresh ``--on``;
- ``--status`` shows when it closes itself and how long is left.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import fakeredis

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from intake_api.auth_store import RESEND_COOLDOWN_S  # noqa: E402
from test_otp_abuse import DpopClient, OtpHarness  # noqa: E402
from test_review_signin import (  # noqa: E402
    REPO,
    answer,
    ask,
    cli,
    draw,
    harness,
    review,
    window_module,
)
from test_review_signin_reset import reset_now, seed_session, sessions_of  # noqa: E402

RUNBOOK = REPO / "docs" / "runbooks" / "review-signin.md"
HOUR = 3600
DAY = 24 * HOUR


def window(otp: OtpHarness) -> Any:
    """The window as the API reads it: on the harness clock."""
    return review().ReviewWindow(otp.redis_client, otp.clock)


def reopen_on_the_harness_clock(otp: OtpHarness) -> Any:
    """The harness opened its window on the wall clock; this test needs the
    opening on the fake clock it advances."""
    w = window(otp)
    w.close()
    w.open()
    return w.state()


def rows_of(otp: OtpHarness, action: str) -> list[Any]:
    return [entry for entry in otp.audit_store.entries() if entry.action == action]


def expire(otp: OtpHarness) -> bool:
    """The API's own sweep, once, on the app's event loop."""
    result: bool = otp.client.portal.call(otp.client.app.state.api.auth.expire_review_window)
    return result


def test_the_window_lasts_fourteen_days() -> None:
    assert window_module().REVIEW_WINDOW_S == 14 * DAY


def test_near_miss_at_13_days_23_hours_the_window_is_open(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        opened = reopen_on_the_harness_clock(otp)
        otp.clock.advance(13 * DAY + 23 * HOUR)
        assert window(otp).is_open()
        assert expire(otp) is False, "nothing is due yet"
        bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer))
        assert bundle.status_code == 200, bundle.text
        assert window(otp).state().id == opened.id
        assert rows_of(otp, "auth.review.window.closed") == []


def test_at_14_days_the_window_closes_itself_audited_then_erased(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        reopen_on_the_harness_clock(otp)
        dpop = DpopClient()
        bundle = answer(otp, dpop, reviewer, ask(otp, reviewer)).json()
        seed_session(otp, review().REVIEW_TENANT_ID, uuid.UUID(bundle["patient_id"]))
        otp.clock.advance(14 * DAY)
        # closed at once, to every reader, before anything records it
        assert window(otp).is_open() is False
        # the next reviewer step is refused, and it closes the window as --off would
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        refused = ask(otp, reviewer)
        assert refused.status_code == 202
        assert answer(otp, DpopClient(), reviewer, refused).status_code == 401
        assert otp.redis_client.get("auth:review:window") is None, "the document is gone"
        [closed] = rows_of(otp, "auth.review.window.closed")
        assert closed.actor == "system:review-expiry"
        assert closed.resource_ref == "review_signin:window"
        actions = [entry.action for entry in otp.audit_store.entries()]
        assert actions.index("auth.review.window.closed") < actions.index("auth.review.reset")
        assert sessions_of(otp, bundle["patient_id"]) == [], "the reviewer's visit outlived it"
        # the reviewer's session ended with it
        assert otp.get_visits(dpop, bundle["access_token"]).status_code == 401


def test_the_sweep_closes_an_expired_window_nobody_touches_once(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        reopen_on_the_harness_clock(otp)
        otp.clock.advance(14 * DAY)
        assert expire(otp) is True
        assert expire(otp) is False, "a second pass finds nothing to close"
        assert [entry.actor for entry in rows_of(otp, "auth.review.window.closed")] == [
            "system:review-expiry"
        ]


def test_an_expiry_never_closes_a_fresh_window() -> None:
    """The close is by id: a window the owner opened a moment before survives
    the expiry of the one before it."""
    fake = fakeredis.FakeStrictRedis()
    w = review().ReviewWindow(fake)
    w.open()
    old = w.state()
    w.close()
    w.open()
    assert w.close(expect_id=old.id) is False
    assert w.is_open()
    assert w.close(expect_id=w.state().id) is True


def test_nothing_but_a_fresh_on_reopens_it(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        first = reopen_on_the_harness_clock(otp)
        otp.clock.advance(14 * DAY)
        expire(otp)
        otp.clock.advance(30 * DAY)
        assert window(otp).is_open() is False
        code, said, audited = cli("on", otp.redis_client, reset=reset_now(otp), now_fn=otp.clock)
        assert code == 0, said
        assert audited == ["auth.review.window.opened"]
        assert window(otp).state().id != first.id
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        assert answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).status_code == 200


def test_on_over_an_expired_window_closes_it_as_off_would_first() -> None:
    fake = fakeredis.FakeStrictRedis()
    now = [1_000_000.0]
    review().ReviewWindow(fake, lambda: now[0]).open()
    now[0] += 14 * DAY
    erased: list[str] = []

    def reset() -> None:
        erased.append("reset")

    code, said, audited = cli("on", fake, reset=reset, now_fn=lambda: now[0])
    assert code == 0, said
    assert audited == ["auth.review.window.closed", "auth.review.window.opened"]
    assert erased == ["reset", "reset"], "erased on the close and again before the opening"
    assert review().ReviewWindow(fake, lambda: now[0]).is_open()


def test_status_shows_when_it_closes_itself_and_how_long_is_left() -> None:
    fake = fakeredis.FakeStrictRedis()
    now = [1_000_000.0]
    review().ReviewWindow(fake, lambda: now[0]).open()
    said = cli("status", fake, now_fn=lambda: now[0])[1]
    assert "closes itself at" in said and "in 14d 0h 0m" in said
    now[0] += 13 * DAY + 23 * HOUR
    said = cli("status", fake, now_fn=lambda: now[0])[1]
    assert "in 0d 1h 0m" in said and "can sign in" in said
    now[0] += HOUR
    said = cli("status", fake, now_fn=lambda: now[0])[1]
    assert "expired at" in said and "no reviewer can sign in" in said


def test_the_runbook_states_the_default_and_who_may_change_it() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "14 days" in runbook and "engineering default" in runbook
    assert "system:review-expiry" in runbook
