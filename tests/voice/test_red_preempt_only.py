"""INT-091 — only a rules-engine RED may preempt (invariant 9 clause 4).

files/03 §4.3: *"``priority:"preempt"`` is accepted by the result validator
**only** when ``triage_update.level == "RED"`` and the rule ids come from
``packages/protocols/triage``. … LLM ``candidate_flags`` can never carry
``preempt``."* CLAUDE.md invariant 1 is the reason it holds at type level:
``LlmCandidateTriage`` can express exactly one level, ``YELLOW_REVIEW``, so an
LLM-derived flag cannot even *spell* RED.

Two gates, tested separately because they fail for different reasons:

1. **Shape** — a ``model_validator`` on ``BackendResult``. RED, and only RED,
   from ``RulesTriageResult``.
2. **Provenance** — :func:`authorise_preempt` against the rule-id set of the
   session's pinned protocol. A well-formed RED naming a rule the pack does
   not contain is refused, which kills the copy-a-RED-shape attack.

The HMAC attestation files/12 §5 adds on top of this — signing key from
OpenBao, nonce, ``inputs_hash``, the seven-way forgery mutation test — is
INT-093's scope and is recorded as such in docs/evidence/INT-091.md. What is
here is the part that can be built and proven today, and it fails closed.
"""

from __future__ import annotations

import pytest
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.talker.insertion import DeliveryClass
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    PreemptRefused,
    Presentation,
    Priority,
    authorise_preempt,
)
from pydantic import ValidationError

PACK_RULES = frozenset({"rf.gogus_agrisi_akut", "rf.kanama"})

RULES_RED = RulesTriageResult(
    level=TriageLevel.RED,
    rules=(RuleFire(id="rf.gogus_agrisi_akut", evidence="gogus_agrisi=evet"),),
    register=RedRegister.ALERT,
    location=RedLocation.REMOTE,
)
RULES_YELLOW = RulesTriageResult(
    level=TriageLevel.YELLOW,
    rules=(RuleFire(id="rf.kanama", evidence="kanama=evet"),),
)
RULES_GREEN = RulesTriageResult(level=TriageLevel.GREEN)
LLM_CANDIDATE = LlmCandidateTriage(
    candidate_flags=(CandidateFlag(text="olası kanama", evidence="hastanın ifadesi"),)
)


def _result(triage: object, priority: Priority) -> BackendResult:
    return BackendResult(
        work_id="w1",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=Presentation(speech_tr="Hemen yüz on ikiyi arayın.", triage_update=triage),
        priority=priority,
    )


# --- gate 1: shape --------------------------------------------------------------------


def test_a_rules_engine_red_may_preempt() -> None:
    result = _result(RULES_RED, Priority.PREEMPT)
    assert result.priority is Priority.PREEMPT


def test_a_rules_engine_yellow_may_not_preempt() -> None:
    """RT-07: YELLOW waits for the insertion window, always."""
    with pytest.raises(ValidationError, match="RED"):
        _result(RULES_YELLOW, Priority.PREEMPT)


def test_a_green_result_may_not_preempt() -> None:
    with pytest.raises(ValidationError, match="RED"):
        _result(RULES_GREEN, Priority.PREEMPT)


def test_a_result_with_no_triage_update_may_not_preempt() -> None:
    with pytest.raises(ValidationError, match="RED"):
        BackendResult(
            work_id="w1",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.ROUTINE,
            presentation=Presentation(speech_tr="Belgeniz okundu."),
            priority=Priority.PREEMPT,
        )


def test_an_llm_candidate_may_not_preempt() -> None:
    """Invariant 1 at type level: the candidate type has no RED to offer."""
    with pytest.raises(ValidationError, match="RED"):
        _result(LLM_CANDIDATE, Priority.PREEMPT)


def test_the_llm_candidate_type_cannot_express_red_at_all() -> None:
    assert LLM_CANDIDATE.level == "YELLOW_REVIEW"
    with pytest.raises(ValidationError):
        LlmCandidateTriage(
            level="RED",  # type: ignore[arg-type]
            candidate_flags=(CandidateFlag(text="x", evidence="y"),),
        )


def test_candidate_flags_riding_alongside_a_yellow_do_not_unlock_preempt() -> None:
    with pytest.raises(ValidationError, match="RED"):
        BackendResult(
            work_id="w1",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.TRIAGE_YELLOW,
            presentation=Presentation(
                speech_tr="Bunu hekiminiz görecek.",
                triage_update=RULES_YELLOW,
                candidate_flags=(CandidateFlag(text="RED", evidence="hastanın ifadesi"),),
            ),
            priority=Priority.PREEMPT,
        )


def test_normal_priority_is_the_default_and_needs_no_triage_update() -> None:
    result = BackendResult(
        work_id="w1",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.ROUTINE,
        presentation=Presentation(speech_tr="Belgeniz okundu."),
    )
    assert result.priority is Priority.NORMAL


def test_a_red_still_carries_both_axes() -> None:
    """CLAUDE.md invariant 21: register and location have no permitted default."""
    with pytest.raises(ValidationError):
        RulesTriageResult(
            level=TriageLevel.RED,
            rules=(RuleFire(id="rf.gogus_agrisi_akut", evidence="e"),),
            register=RedRegister.ALERT,
        )


# --- gate 2: provenance ------------------------------------------------------------------


def test_a_red_naming_only_pack_rules_is_authorised() -> None:
    authorise_preempt(_result(RULES_RED, Priority.PREEMPT), rule_ids=PACK_RULES)


def test_a_red_naming_a_rule_the_pack_does_not_contain_is_refused() -> None:
    forged = RulesTriageResult(
        level=TriageLevel.RED,
        rules=(RuleFire(id="rf.uydurma_kural", evidence="whatever"),),
        register=RedRegister.ALERT,
        location=RedLocation.REMOTE,
    )
    with pytest.raises(PreemptRefused, match="rf.uydurma_kural"):
        authorise_preempt(_result(forged, Priority.PREEMPT), rule_ids=PACK_RULES)


def test_authorisation_against_an_empty_rule_set_fails_closed() -> None:
    """An unpinned session cannot authorise anything — no rule set, no RED."""
    with pytest.raises(PreemptRefused, match="no rule ids"):
        authorise_preempt(_result(RULES_RED, Priority.PREEMPT), rule_ids=frozenset())


def test_a_normal_priority_result_needs_no_authorisation() -> None:
    routine = BackendResult(
        work_id="w1",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.ROUTINE,
        presentation=Presentation(speech_tr="Belgeniz okundu."),
    )
    authorise_preempt(routine, rule_ids=frozenset())


# --- the runtime honours both -------------------------------------------------------------


def test_the_session_refuses_an_unauthorised_preempt_and_speaks_nothing() -> None:
    from talker_harness import FakeClock, StalledBackend, build_session, scripted_step

    clock = FakeClock()
    forged = RulesTriageResult(
        level=TriageLevel.RED,
        rules=(RuleFire(id="rf.uydurma_kural", evidence="whatever"),),
        register=RedRegister.ALERT,
        location=RedLocation.REMOTE,
    )
    backend = StalledBackend(clock=clock, stall_s=0.0)
    session = build_session(clock, steps=[scripted_step()], backend=backend, rule_ids=PACK_RULES)
    with pytest.raises(PreemptRefused):
        session.accept_result(_result(forged, Priority.PREEMPT))
    assert session.preempts == ()


def test_the_session_accepts_a_pack_authorised_preempt() -> None:
    from talker_harness import FakeClock, build_session, scripted_step

    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()], rule_ids=PACK_RULES)
    session.accept_result(_result(RULES_RED, Priority.PREEMPT))
    assert [result.work_id for result in session.preempts] == ["w1"]


def test_a_yellow_result_goes_to_the_insertion_scheduler_not_the_preempt_path() -> None:
    from talker_harness import FakeClock, build_session, scripted_step

    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()], rule_ids=PACK_RULES)
    session.accept_result(
        BackendResult(
            work_id="w2",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.TRIAGE_YELLOW,
            presentation=Presentation(
                speech_tr="Bunu hekiminiz görecek.", triage_update=RULES_YELLOW
            ),
        )
    )
    assert session.preempts == ()
    assert session.scheduler.pending_work_ids == ("w2",)
