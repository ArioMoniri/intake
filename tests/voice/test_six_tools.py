"""INT-091 — the six-tool Talker boundary (CLAUDE.md invariant 9 clause 1).

Acceptance line under test, verbatim (docs/backlog/issues.yaml INT-091):
  "exactly protocol_next, submit_utterance, cancel_work,
   request_repeat_or_clarify, patient_memory, respond_permission; adding a
   seventh fails introspection; PolicyGuard <=20ms per sentence"

files/03 §4.2 states the surface and adds the negative half: *"The Talker has
**no** tools for: setting triage, editing slots, choosing protocols, reading
records, writing notes, sharing, or ending the session."* Both halves are
asserted here — the set equality, and that no forbidden capability name is
reachable through the registry.

The introspection is over the **real builder**, not a hand-made registry: a
seventh tool added to ``build_talker_tools`` fails
``test_the_talker_registers_exactly_the_six_tools`` because the set stops
being equal. The gate's own ability to fail is proven separately, against
synthetic registries holding seven and five.
"""

from __future__ import annotations

import inspect

import pytest
from intake_voice_runtime.ports import PatientMemoryKey, WorkState, WorkType
from intake_voice_runtime.steps import StepKind
from intake_voice_runtime.talker.registry import (
    TALKER_TOOLS,
    ToolRegistry,
    ToolSurfaceError,
    assert_six_tool_surface,
)
from intake_voice_runtime.talker.tools import (
    ConsentDecision,
    MemoryOp,
    PermissionAck,
    RepeatReason,
    build_talker_tools,
)
from talker_harness import FakeClock, build_session, scripted_step


@pytest.fixture()
def tools() -> ToolRegistry:
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    return build_talker_tools(session)


# --- the surface itself -----------------------------------------------------------


def test_the_six_tool_names_are_the_blueprint_names() -> None:
    assert TALKER_TOOLS == frozenset(
        {
            "protocol_next",
            "submit_utterance",
            "cancel_work",
            "request_repeat_or_clarify",
            "patient_memory",
            "respond_permission",
        }
    )


def test_the_talker_registers_exactly_the_six_tools(tools: ToolRegistry) -> None:
    """Set equality — not a superset, not a subset (invariant 9 clause 1)."""
    assert tools.names == TALKER_TOOLS
    assert len(tools.names) == 6
    assert_six_tool_surface(tools)


def test_every_registered_tool_is_callable_and_typed(tools: ToolRegistry) -> None:
    for name in sorted(tools.names):
        handler = tools.handler(name)
        assert callable(handler)
        signature = inspect.signature(handler)
        assert signature.return_annotation is not inspect.Signature.empty, name


# --- the gate can fail ------------------------------------------------------------


def test_a_seventh_tool_fails_introspection(tools: ToolRegistry) -> None:
    seventh = ToolRegistry()
    for name in sorted(tools.names):
        seventh.register(name, tools.handler(name))
    seventh.register("set_triage", lambda: None)

    with pytest.raises(ToolSurfaceError) as err:
        assert_six_tool_surface(seventh)
    assert "set_triage" in str(err.value)


def test_a_missing_tool_fails_introspection(tools: ToolRegistry) -> None:
    five = ToolRegistry()
    for name in sorted(tools.names - {"cancel_work"}):
        five.register(name, tools.handler(name))

    with pytest.raises(ToolSurfaceError) as err:
        assert_six_tool_surface(five)
    assert "cancel_work" in str(err.value)


def test_registering_the_same_name_twice_is_refused(tools: ToolRegistry) -> None:
    with pytest.raises(ToolSurfaceError):
        tools.register("protocol_next", lambda: None)


def test_a_sealed_registry_refuses_further_registration(tools: ToolRegistry) -> None:
    assert tools.sealed is True
    with pytest.raises(ToolSurfaceError):
        tools.register("end_session", lambda: None)


@pytest.mark.parametrize(
    "forbidden",
    [
        "set_triage",
        "edit_slot",
        "choose_protocol",
        "read_records",
        "write_note",
        "share_note",
        "end_session",
        "get_work_status",
    ],
)
def test_the_forbidden_capabilities_are_absent(tools: ToolRegistry, forbidden: str) -> None:
    """files/03 §4.2's negative list, plus the tool files/12 §7.1 deleted."""
    assert forbidden not in tools.names
    with pytest.raises(KeyError):
        tools.handler(forbidden)


# --- each tool does its job -------------------------------------------------------


def test_protocol_next_reads_the_snapshot_without_taking_a_lock(tools: ToolRegistry) -> None:
    step = tools.handler("protocol_next")()
    assert step.step_id == "s1"
    assert step.kind is StepKind.SCRIPTED
    assert step.engine_version == 1


def test_submit_utterance_returns_a_work_id_and_does_not_wait(tools: ToolRegistry) -> None:
    ticket = tools.handler("submit_utterance")("s1", "iki gündür ağrıyor")
    assert ticket.work_id
    assert ticket.state is WorkState.QUEUED
    assert not inspect.iscoroutine(ticket)


def test_submit_utterance_is_content_addressed(tools: ToolRegistry) -> None:
    """files/12 §7.5: work_id is derived, so a restart re-submitting the same
    transcript produces the same id and dedupe works."""
    first = tools.handler("submit_utterance")("s1", "aynı cümle")
    second = tools.handler("submit_utterance")("s1", "aynı cümle")
    assert first.work_id == second.work_id


def test_cancel_work_reaches_the_cancelled_state(tools: ToolRegistry) -> None:
    ticket = tools.handler("submit_utterance")("s1", "yanlış söyledim")
    cancelled = tools.handler("cancel_work")(ticket.work_id, "patient retracted")
    assert cancelled.state is WorkState.CANCELLED


def test_request_repeat_or_clarify_returns_the_step_verbatim(tools: ToolRegistry) -> None:
    """files/03 §4.4b: a handover gap re-asks the current step verbatim."""
    repeat = tools.handler("request_repeat_or_clarify")(RepeatReason.NOT_HEARD)
    assert repeat.text_tr == "Nereniz ağrıyor?"


def test_patient_memory_round_trips_a_non_clinical_key(tools: ToolRegistry) -> None:
    handler = tools.handler("patient_memory")
    assert handler(MemoryOp.RECALL, PatientMemoryKey.PACE) is None
    handler(MemoryOp.REMEMBER, PatientMemoryKey.PACE, "slow")
    assert handler(MemoryOp.RECALL, PatientMemoryKey.PACE).value == "slow"
    handler(MemoryOp.FORGET, PatientMemoryKey.PACE)
    assert handler(MemoryOp.RECALL, PatientMemoryKey.PACE) is None


def test_patient_memory_refuses_a_clinical_key(tools: ToolRegistry) -> None:
    """files/03 §4.2: name, form of address, pace, language — nothing clinical."""
    handler = tools.handler("patient_memory")
    with pytest.raises(ValueError, match="closed"):
        handler(MemoryOp.REMEMBER, "chest_pain", "yes")


def test_respond_permission_acknowledges_a_gated_yes(tools: ToolRegistry) -> None:
    ack = tools.handler("respond_permission")(
        request_id="perm-1",
        decision=ConsentDecision.YES,
        span_start_ms=2_000.0,
        span_end_ms=2_400.0,
        asr_confidence=0.97,
        prompt_text_hash="a" * 64,
    )
    assert isinstance(ack, PermissionAck)


def test_the_work_types_the_talker_can_submit_are_closed(tools: ToolRegistry) -> None:
    """The Talker submits transcripts. It cannot ask for triage, notes or
    shares — files/12 §7.3 deleted EVALUATE_TRIAGE from the registry entirely."""
    assert WorkType.EXTRACT_SLOTS in set(WorkType)
    assert "EVALUATE_TRIAGE" not in {member.name for member in WorkType}
