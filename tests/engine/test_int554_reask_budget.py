"""INT-554 D6 — CD-04's "once" never takes the council's red-flag re-ask.

GitHub #938, CD-04 round 4 (author revision after the verifier's D6 finding).
CD-04 decides that an UNCLEAR answer to a scripted red-flag question takes its
``follow_up_tr`` once. The engine shares each slot's clarification bound with
ADR-036's council appends (:meth:`IntakeEngine.append_verification`), and
ADR-036 keeps "each slot ... its two attempts": a red-flag slot answered absent
while any council draw reads it present is re-asked (``REASK_POSITIVE``).

So the once counts ``follow_up_tr`` asks only, and the slot's shared bound
stays files/13 §11.1's two attempts. This suite pins, against the decision and
the engine as it is today:

1. the decision says so, machine-readably, and its arithmetic leaves the
   council at least one attempt once the follow-up is spent;
2. **the near miss the decision protects:** a slot whose one follow-up was
   spent and then answered "hayır" is still re-asked under the shared bound;
3. the wiring the decision rejects: the once handed to the engine as the
   slot's whole bound leaves that "hayır" with no re-ask (``EXHAUSTED``) —
   the verifier's probe, kept so the near miss is shown to discriminate.

The protocol is ``test_fsm``'s synthetic one; every id and string is
synthetic (files/04 §7).
"""

from __future__ import annotations

from clinical_schemas.session import AnswerState
from intake_voice_runtime.clinical_agent import IntakeEngine
from intake_voice_runtime.clinical_agent.fsm import (
    MAX_CLARIFICATION_ATTEMPTS,
    AppendOutcome,
    VerificationKind,
)
from protocols.clinical_decisions import load_register
from test_fsm import NOW, _protocol

#: A boolean step of the synthetic protocol, standing in for a red-flag slot.
SYMPTOM = "oyku.belirti_var"


def _cd04() -> dict[str, object]:
    return dict(load_register()["CD-04"].value)


def _hayir_after_the_spent_follow_up(bounds: dict[str, int] | None) -> IntakeEngine:
    """An unclear answer, its one follow-up, then a plain negative to it."""
    engine = IntakeEngine(protocol=_protocol(), reference_time=NOW, clarification_bounds=bounds)
    engine.mark_asked(SYMPTOM)
    engine.apply_extraction(SYMPTOM, {}, clarification_needed=True)
    follow_up = f"{SYMPTOM}/clarify/1"
    assert engine.follow_ups == (follow_up,)
    engine.mark_asked(follow_up)
    engine.apply_extraction(follow_up, {SYMPTOM: False})
    assert engine.state_of(SYMPTOM) is AnswerState.ASKED_ABSENT
    return engine


def _reask(engine: IntakeEngine) -> AppendOutcome:
    return engine.append_verification(
        SYMPTOM, VerificationKind.REASK, engine.slot_revision(SYMPTOM)
    )


def test_d6_the_once_counts_follow_up_asks_only() -> None:
    value = _cd04()
    scope = value["follow_up_bound_scope"]
    assert isinstance(scope, dict)
    once = value["unclear_follow_up_tr_asks"]
    assert isinstance(once, int) and once == 1
    assert scope["once_counts"] == "follow_up_tr_after_unclear"
    assert "council_reask_positive" in scope["once_never_counts"]
    assert scope["shared_reentry_bound_unchanged"] is True
    assert scope["council_reask_after_spent_follow_up"] == "available"
    # the shared bound is files/13 §11.1's two; the once leaves the council at least one
    assert MAX_CLARIFICATION_ATTEMPTS - once >= 1


def test_d6_near_miss_a_hayir_after_the_spent_follow_up_is_still_reasked() -> None:
    """The budget D6 keeps: the slot's shared bound is files/13 §11.1's two."""
    engine = _hayir_after_the_spent_follow_up(None)
    assert engine.clarification_bound(SYMPTOM) == MAX_CLARIFICATION_ATTEMPTS
    assert _reask(engine) is AppendOutcome.APPENDED
    assert f"{SYMPTOM}/verify/2" in [step.step_id for step in engine.frontier()]


def test_d6_the_rejected_wiring_would_leave_that_hayir_without_its_reask() -> None:
    """The once handed to the engine as the slot's whole bound exhausts the re-ask."""
    once = _cd04()["unclear_follow_up_tr_asks"]
    assert isinstance(once, int)
    engine = _hayir_after_the_spent_follow_up({SYMPTOM: once})
    assert _reask(engine) is AppendOutcome.EXHAUSTED
