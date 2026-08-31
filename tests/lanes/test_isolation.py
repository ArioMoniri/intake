"""INT-110 — the lane framework: read-only at compile time, off the speech path.

Acceptance line under test, verbatim (docs/backlog/issues.yaml INT-110):
  "lanes cannot write slots/triage (compile-time); stalled lanes never delay
   speech (fake clock); frames dropped under load with metric"

``legal: KVKK-6`` · ``sec_row: observer-lanes`` · ``depends_on: [INT-092,
INT-038]``.

CLAUDE.md invariant 11 is this issue, and it has four clauses. Each is proved
here in the strongest form the clause admits, and each gate carries a negative
control, because a gate that has never been shown to fail is a gate nobody has
tested:

- **read-only, at compile time.** Three independent layers. (a) *Type-level*:
  ``LaneContext`` hands a lane no writer and ``LaneObservation`` has no carrier
  for a slot or a triage result, so the forbidden write has no expression —
  proved by running ``mypy --strict`` over a conforming lane and over a lane
  that tries all four ways to write, and asserting the checker separates them.
  (b) *Reachability*: an AST walk over the package, in the posture INT-172 took
  for invariant 12 — no writer, no engine, no network, no process. (c)
  *Routing*: ``ObserverStateBuilder`` is the only writer, it refuses M3
  entirely and refuses an ``InteractionState`` field from a lane outside M1
  (invariant 22).
- **never on the speech critical path.** Structural — the scheduler surface the
  speech path holds has no awaitable member — and measured, on INT-091's
  virtual clock: a turn with lanes stalled 30 s costs exactly what the same
  turn costs with no lanes at all.
- **frames dropped under load.** A stalled lane fills its bounded buffer and
  every further frame is dropped and counted by ``(lane, reason)``.
- **`acoustic` unreachable unless four fields assert, fails closed on
  amendment.** Each of the four is tested missing on its own.

Per-lane consent (KVKK-6, files/06 §2) is the fifth thing this file pins: a
lane whose consent scope is not in the closed files/06 §2 registry cannot be
registered at all, ``lane:acoustic`` is refused *by name* because §2.4 turned
it into an investigational-device ICF, and a withdrawal zeroizes the buffer.
"""

from __future__ import annotations

import ast
import asyncio
import enum
import inspect
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from clinical_schemas.observers import Lane, ObserverState
from harness import (
    FakeClock,
    GrantingConsentProbe,
    RecordingObserver,
    SlowObserver,
    build_session,
    frames,
    lane_spec,
    scripted_step,
)
from intake_platform.consent.registry import REMOVED_PURPOSES, purpose_ids
from intake_voice_runtime.observers import (
    LANE_CONSENT_SCOPES,
    LANE_DROPPED_FRAMES_ID,
    LANE_DROPPED_FRAMES_LABELS,
    LANE_DROPPED_FRAMES_NAME,
    LANE_MODULE,
    MAX_WINDOW_MS,
    MODULE_INTENDED_PURPOSE,
    UNDECLARED_CONSENT_LANES,
    ConsentReading,
    DropLedger,
    DropReason,
    Frame,
    InteractionDelta,
    LaneAdmission,
    LaneBudget,
    LaneConsentScopeRefusedError,
    LaneConsentUndeclaredError,
    LaneContext,
    LaneModule,
    LaneObservation,
    LaneSpec,
    Observer,
    ObserverScheduler,
    ObserverStateBuilder,
    ObserverStateRefusedError,
    StudyAssertion,
    StudyGate,
    StudyGateState,
    WindowBuffer,
    ZeroizeTrigger,
    consent_scope_for,
    zeroize_frames,
)
from intake_voice_runtime.talker.registry import TALKER_TOOLS, assert_six_tool_surface
from intake_voice_runtime.talker.tools import build_talker_tools
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
LANE_PACKAGE = REPO / "services" / "voice-runtime" / "src" / "intake_voice_runtime" / "observers"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

SESSION_REF = "11111111-2222-4333-8444-555555555555"


# --- the AST gates' vocabulary -------------------------------------------------------

#: Modules that hold a writer for clinical state, or a route to one. A lane
#: that cannot *import* the engine cannot write a slot through it, whatever it
#: intends — the same posture INT-172 took for invariant 12.
FORBIDDEN_MODULES: dict[str, str] = {
    "intake_voice_runtime.work_queue": (
        "the Work queue — the one thing that writes SessionState (files/03 §4.3)"
    ),
    "intake_voice_runtime.clinical_agent": "the deterministic engine FSM (invariant 11)",
    "intake_voice_runtime.talker": (
        "the Talker: its six tools, PolicyGuard and the speech path (invariants 9, 11)"
    ),
    "protocols": "the triage rules and the protocol compiler (invariant 1)",
    "intake_api": "the persistence surface for every one of the above",
    "intake_platform.db": "the database session and models",
    "intake_platform.store": "the object store",
    "sqlalchemy": "any statement a lane could issue",
}

#: Invariant 13 (``lane_shared_stream_guard``): *"Lanes have no network
#: capability at type level; they receive frames from the runtime and return
#: signals."* Process and filesystem modules ride along, because invariant 3
#: says raw audio is never *reachable*, not merely never written.
NETWORK_OR_PROCESS_MODULES = frozenset(
    {
        "aiohttp",
        "ftplib",
        "http",
        "httpx",
        "livekit",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "smtplib",
        "socket",
        "subprocess",
        "tempfile",
        "urllib",
    }
)

#: Attribute calls that write something outside the lane's own value.
WRITE_CAPABLE_ATTRS = frozenset(
    {
        "apply_extraction",
        "chmod",
        "commit",
        "execute",
        "makedirs",
        "mkdir",
        "remove",
        "rename",
        "rmdir",
        "rmtree",
        "submit",
        "system",
        "unlink",
        "write",
        "write_bytes",
        "write_text",
        "writelines",
    }
)

#: Prometheus family constructors. The lane package builds none: every emitted
#: series must exist in observability/metrics_catalog.yaml (invariant 13) and
#: no lane row is catalogued, so the framework counts in process and names the
#: series it *would* emit rather than emitting one the catalogue does not know.
PROMETHEUS_FAMILIES = frozenset({"Counter", "Gauge", "Histogram", "Summary", "Info", "Enum"})


def _sources() -> list[Path]:
    return sorted(LANE_PACKAGE.rglob("*.py"))


def _imports_in(source: str, *, label: str) -> set[str]:
    """Every dotted module name imported anywhere in ``source``.

    The whole tree is walked, not only module level: a function-local import is
    still a reachable edge, and one under ``if TYPE_CHECKING`` is still a design
    that names the module.
    """
    tree = ast.parse(source, filename=label)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _forbidden_hits(names: set[str]) -> list[str]:
    return sorted(
        f"{dotted} -> {subject}"
        for dotted in names
        for forbidden, subject in FORBIDDEN_MODULES.items()
        if dotted == forbidden or dotted.startswith(f"{forbidden}.")
    )


def _roots(names: set[str]) -> set[str]:
    return {dotted.split(".")[0] for dotted in names}


def _write_calls(source: str, *, label: str) -> list[str]:
    offences: list[str] = []
    for node in ast.walk(ast.parse(source, filename=label)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in WRITE_CAPABLE_ATTRS:
            offences.append(f"{label}:{node.lineno} .{func.attr}(")
        if isinstance(func, ast.Name) and func.id in {"open", "exec", "eval", "compile"}:
            offences.append(f"{label}:{node.lineno} {func.id}(")
    return offences


def _prometheus_calls(source: str, *, label: str) -> list[str]:
    offences: list[str] = []
    for node in ast.walk(ast.parse(source, filename=label)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in PROMETHEUS_FAMILIES:
                offences.append(f"{label}:{node.lineno} {name}(")
    return offences


# --- scheduler assembly --------------------------------------------------------------


@dataclass
class Rig:
    """One wired scheduler and the doubles behind it."""

    clock: FakeClock
    probe: GrantingConsentProbe
    scheduler: ObserverScheduler


def build_rig(
    *,
    clock: FakeClock | None = None,
    granted: dict[str, str] | None = None,
    study_gate: StudyGate | None = None,
) -> Rig:
    clock = clock or FakeClock()
    probe = GrantingConsentProbe(
        granted_scopes=dict(granted if granted is not None else {"lane:affect": "v1"})
    )
    scheduler = ObserverScheduler(
        session_ref=SESSION_REF,
        clock=clock,
        consent=probe,
        study_gate=study_gate,
    )
    return Rig(clock=clock, probe=probe, scheduler=scheduler)


@pytest.fixture()
def rig() -> Rig:
    return build_rig()


# =====================================================================================
# 1 · lanes cannot write slots or triage — compile time
# =====================================================================================


@pytest.fixture(scope="module")
def mypy_report() -> str:
    """One ``mypy --strict`` run over both fixture lanes, cold cache.

    Both files in one invocation: the checker is the thing under test, so the
    conforming lane and the writing lane must be judged by the same run.
    """
    from mypy import api

    stdout, stderr, _status = api.run(
        [
            "--strict",
            "--no-error-summary",
            "--no-incremental",
            "--hide-error-context",
            str(FIXTURES / "read_only_lane.py"),
            str(FIXTURES / "writing_lane.py"),
        ]
    )
    return stdout + stderr


def test_mypy_accepts_a_lane_that_only_reads(mypy_report: str) -> None:
    """The positive control: the checker is not simply rejecting everything."""
    report = mypy_report
    assert "read_only_lane.py" not in report, (
        "the conforming lane must type-check clean, or the negative control below "
        f"proves nothing:\n{report}"
    )


def test_mypy_rejects_every_way_a_lane_could_try_to_write(mypy_report: str) -> None:
    """Invariant 11's *"(compile-time)"*, as the acceptance words it.

    Four attempts, four findings. The assertion is per-attempt rather than
    "some error happened", because one loud failure could otherwise mask three
    silent successes.
    """
    lines = [line for line in mypy_report.splitlines() if "writing_lane.py" in line]
    assert lines, f"mypy found nothing wrong with a lane that writes:\n{mypy_report}"
    joined = "\n".join(lines)

    assert 'has no attribute "engine"' in joined, (
        f"a lane reached the engine through its context:\n{joined}"
    )
    assert any(marker in joined for marker in ('"window"', "read-only", "frozen")), (
        f"a lane mutated the read-only window it was handed:\n{joined}"
    )
    assert 'has no attribute "slot_updates"' in joined, (
        f"an observation carried a slot-update field:\n{joined}"
    )
    assert "TriageWritingLane" in joined or "incompatible type" in joined, (
        f"a lane returning a triage result satisfied the Observer protocol:\n{joined}"
    )


def test_the_lane_observation_has_no_carrier_for_a_slot_or_a_triage_result() -> None:
    """The INT-091 / INT-172 posture: refused by type, not validated at the edge.

    ``LaneObservation`` is everything a lane may return. No field in it, and no
    field type reachable from it, can hold a slot value, a triage level or a
    rule id — so "a lane that writes triage" is not a case to reject, it is a
    thing that cannot be written down.
    """
    fields = set(LaneObservation.model_fields)
    assert fields == {"interaction", "markers", "confidence", "dropped_frames_in_window"}

    banned = ("Triage", "CandidateFlag", "Slot", "WorkOutcome", "Presentation", "Path")
    rendered = {name: str(field.annotation) for name, field in LaneObservation.model_fields.items()}
    offences = [
        f"{name}: {shape}"
        for name, shape in rendered.items()
        if any(token in shape for token in banned)
    ]
    assert offences == [], f"a lane observation names a forbidden carrier: {offences}"

    with pytest.raises(ValidationError):
        LaneObservation(confidence=1.0, slot_updates={"chest_pain": True})  # type: ignore[call-arg]


def test_the_interaction_delta_is_exactly_the_closed_six_field_record() -> None:
    """files/03 §4.7.1: ``InteractionState`` is M1's whole egress, six fields.

    No emotion label, no confidence score, no numeric affect value and no free
    text crosses it (invariant 22).
    """
    assert set(InteractionDelta.model_fields) == {
        "pace",
        "modality",
        "break_offer",
        "confirm_by_card",
        "repeat_request",
        "third_party_present",
    }
    with pytest.raises(ValidationError):
        InteractionDelta(emotion="sad")  # type: ignore[call-arg]


def test_the_lane_context_hands_a_lane_no_writer(rig: Rig) -> None:
    """What a lane is given: a window, some ids, and nothing to call."""
    observer = RecordingObserver(lane_id=Lane.AFFECT)
    rig.scheduler.register(lane_spec(Lane.AFFECT), observer)
    for frame in frames(2):
        rig.scheduler.offer(frame)
    rig.clock.run(rig.scheduler.pump())

    assert observer.contexts, "the lane never ran, so nothing was proved about it"
    context = observer.contexts[0]
    for name in ("engine", "backend", "queue", "sink", "store", "session", "submit"):
        assert not hasattr(context, name), f"LaneContext exposes {name!r} — a lane could write"
    callables = [
        name
        for name in dir(context)
        if not name.startswith("_") and callable(getattr(context, name))
    ]
    assert callables == [], f"LaneContext exposes callable members: {callables}"
    with pytest.raises((AttributeError, TypeError)):
        context.window_id = "other"  # type: ignore[misc]


def test_the_observer_protocol_admits_only_a_lane_observation() -> None:
    signature = inspect.signature(Observer.observe)
    assert list(signature.parameters) == ["self", "context"]
    hints = inspect.get_annotations(Observer.observe, eval_str=True)
    assert hints["context"] is LaneContext
    assert hints["return"] is LaneObservation


# --- reachability: the AST gates and their negative controls -------------------------


def test_the_scan_walks_a_real_corpus() -> None:
    """The gate is hollow if the walker finds nothing to scan."""
    assert LANE_PACKAGE.is_dir()
    names = {path.name for path in _sources()}
    for expected in ("__init__.py", "scheduler.py", "consent.py", "study.py", "state.py"):
        assert expected in names, f"{expected} must be inside the scan"


def test_no_lane_module_reaches_a_writer() -> None:
    offences: list[str] = []
    for path in _sources():
        label = str(path.relative_to(REPO))
        offences += [
            f"{label}: {hit}"
            for hit in _forbidden_hits(_imports_in(path.read_text(encoding="utf-8"), label=label))
        ]
    assert offences == [], (
        "a lane module reached something that writes clinical state. Invariant 11 "
        f"is a reachability claim, not an intention: {offences}"
    )


def test_the_writer_gate_would_report_a_breach(tmp_path: Path) -> None:
    """Negative control: silence must not be the only possible answer."""
    sneaky = "from intake_voice_runtime.work_queue import WorkQueue\nimport protocols.triage\n"
    hits = _forbidden_hits(_imports_in(sneaky, label="sneaky.py"))
    assert {hit.split(" -> ", 1)[0] for hit in hits} == {
        "intake_voice_runtime.work_queue",
        "intake_voice_runtime.work_queue.WorkQueue",
        "protocols.triage",
    }


def test_no_lane_module_has_a_network_or_process_capability() -> None:
    """Invariant 13: lanes receive frames from the runtime and return signals."""
    offences: list[str] = []
    for path in _sources():
        label = str(path.relative_to(REPO))
        roots = _roots(_imports_in(path.read_text(encoding="utf-8"), label=label))
        offences += [f"{label}: {name}" for name in sorted(roots & NETWORK_OR_PROCESS_MODULES)]
    assert offences == [], f"a lane module can open a socket, a process or a file: {offences}"


def test_the_capability_gate_would_report_a_breach() -> None:
    sneaky = "import socket\nfrom urllib import request\n"
    roots = _roots(_imports_in(sneaky, label="sneaky.py"))
    assert roots & NETWORK_OR_PROCESS_MODULES == {"socket", "urllib"}


def test_no_lane_module_contains_a_write_capable_call() -> None:
    offences: list[str] = []
    for path in _sources():
        label = str(path.relative_to(REPO))
        offences += _write_calls(path.read_text(encoding="utf-8"), label=label)
    assert offences == [], (
        "a lane module holds a write-capable call. The framework returns values "
        f"and owns no sink, which is what makes 'writes ObserverState only' true: {offences}"
    )


def test_the_write_call_gate_would_report_a_breach() -> None:
    sneaky = "def go(engine, path):\n    engine.apply_extraction('s', {})\n    open(path).read()\n"
    offences = _write_calls(sneaky, label="sneaky.py")
    assert len(offences) == 2
    assert any("apply_extraction" in offence for offence in offences)
    assert any("open(" in offence for offence in offences)


# --- routing: the state builder is the only writer -----------------------------------


def test_the_state_builder_routes_each_lane_to_its_own_aggregate() -> None:
    """files/03 §4.7.5's output column, as a routing table.

    ``asr_quality{}``, ``engagement{}`` and ``linguistic_markers{}`` each take
    their own lane's markers and nobody else's.
    """
    builder = ObserverStateBuilder(session_ref=SESSION_REF)
    builder.apply(Lane.ASR_QUALITY, LaneObservation(confidence=0.9, markers={"conf_mean": 0.8}))
    builder.apply(Lane.ENGAGEMENT, LaneObservation(confidence=0.9, markers={"silence_ratio": 0.2}))
    builder.apply(Lane.LINGUISTIC, LaneObservation(confidence=0.9, markers={"pause_ratio": 0.3}))

    state = builder.state()
    assert isinstance(state, ObserverState)
    assert state.asr_quality == {"conf_mean": 0.8}
    assert state.engagement == {"silence_ratio": 0.2}
    assert state.linguistic_markers == {"pause_ratio": 0.3}


def test_the_state_builder_refuses_the_acoustic_module_entirely() -> None:
    """files/03 §4.7.4: M3's output goes to a sealed research store, never here.

    There is no acoustic aggregate on ``ObserverState`` at all, so this is a
    refusal rather than a filter — the destination does not exist.
    """
    builder = ObserverStateBuilder(session_ref=SESSION_REF)
    with pytest.raises(ObserverStateRefusedError, match="M3"):
        builder.apply(Lane.ACOUSTIC, LaneObservation(confidence=0.9, markers={"band": "none"}))
    assert not hasattr(builder.state(), "acoustic")


def test_only_an_m1_lane_may_set_an_interaction_field() -> None:
    """Invariant 22 (``interaction_state_closed_domain``) at the write side."""
    builder = ObserverStateBuilder(session_ref=SESSION_REF)
    builder.apply(
        Lane.ENGAGEMENT,
        LaneObservation(confidence=0.9, interaction=InteractionDelta(pace="slow")),
    )
    assert builder.state().interaction.pace == "slow"

    with pytest.raises(ObserverStateRefusedError, match="M1"):
        builder.apply(
            Lane.LINGUISTIC,
            LaneObservation(confidence=0.9, interaction=InteractionDelta(break_offer=True)),
        )


def test_the_affect_lane_has_no_marker_egress_at_all() -> None:
    """files/03 §4.7.5: ``affect``'s output is *"closed InteractionState only —
    no label, no score, no text"*. The emotion inference dies inside M1."""
    builder = ObserverStateBuilder(session_ref=SESSION_REF)
    builder.apply(
        Lane.AFFECT, LaneObservation(confidence=0.9, interaction=InteractionDelta(pace="slow"))
    )
    with pytest.raises(ObserverStateRefusedError, match="affect"):
        builder.apply(Lane.AFFECT, LaneObservation(confidence=0.9, markers={"emotion": "sad"}))


def test_the_lane_module_map_is_the_blueprint_four_module_boundary() -> None:
    """files/03 §4.7.1's table, as data."""
    assert LANE_MODULE == {
        Lane.AFFECT: LaneModule.INTERACTION_SIGNALS,
        Lane.ENGAGEMENT: LaneModule.INTERACTION_SIGNALS,
        Lane.ASR_QUALITY: LaneModule.INTERACTION_SIGNALS,
        Lane.LINGUISTIC: LaneModule.CLINICAL_SIGNALS,
        Lane.ACOUSTIC: LaneModule.ACOUSTIC,
    }
    assert set(MODULE_INTENDED_PURPOSE) == set(LaneModule)


def test_a_lane_manifest_without_an_intended_purpose_cannot_be_built() -> None:
    """Invariant 29 (``lane_intended_purpose_manifest``): the string is
    regulatory text in the technical file, so its absence is a build failure."""
    with pytest.raises(ValidationError):
        LaneSpec(  # type: ignore[call-arg]
            lane=Lane.AFFECT,
            budget=LaneBudget(
                window_ms=20.0, max_queued_frames=4, deadline_ms=100.0, sampling_rate_hz=50.0
            ),
        )
    with pytest.raises(ValidationError):
        LaneSpec(
            lane=Lane.AFFECT,
            intended_purpose="",
            budget=LaneBudget(
                window_ms=20.0, max_queued_frames=4, deadline_ms=100.0, sampling_rate_hz=50.0
            ),
        )


def test_registering_a_lane_costs_the_talker_no_seventh_tool(rig: Rig) -> None:
    """Invariant 9: the six-tool surface is unchanged by the whole framework."""
    rig.scheduler.register(lane_spec(Lane.AFFECT), RecordingObserver(lane_id=Lane.AFFECT))
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    tools = build_talker_tools(session)
    assert_six_tool_surface(tools)
    assert tools.names == TALKER_TOOLS


# =====================================================================================
# 2 · stalled lanes never delay speech — fake clock
# =====================================================================================


def test_the_scheduler_surface_the_speech_path_holds_has_no_awaitable_member() -> None:
    """Structural half. ``offer`` is what the speech path calls, every frame.

    ``pump`` is the lane tasks' own entry point and is the only coroutine on
    the class — the same split the Work queue uses for ``run_pending``.
    """
    public = {
        name: value
        for name, value in vars(ObserverScheduler).items()
        if callable(value) and not name.startswith("_")
    }
    coroutines = {name for name, value in public.items() if inspect.iscoroutinefunction(value)}
    assert coroutines == {"pump"}, (
        "the speech path holds this object; every member but the lane pump must "
        f"be an ordinary function (invariant 11): {sorted(coroutines)}"
    )


def test_the_consent_probe_port_has_no_awaitable_member() -> None:
    """The consent check runs on the offer path, so it may not be awaited."""
    assert not inspect.iscoroutinefunction(GrantingConsentProbe.granted)


def _turn_latency(*, lane_stall_s: float | None) -> float:
    """One real Talker turn, with and without lanes, on the same virtual clock."""
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])

    if lane_stall_s is None:
        return float(clock.run(session.take_turn("iki gündür ağrıyor")).elapsed_ms)

    rig = build_rig(clock=clock)
    observer = SlowObserver(lane_id=Lane.AFFECT, clock=clock, stall_s=lane_stall_s)
    rig.scheduler.register(lane_spec(Lane.AFFECT, deadline_ms=1_000_000.0), observer)

    async def scenario() -> float:
        async def pump_forever() -> None:
            while True:
                await rig.scheduler.pump()
                await clock.sleep(0.005)

        pump = asyncio.ensure_future(pump_forever())
        for frame in frames(4):
            rig.scheduler.offer(frame)
        await asyncio.sleep(0)
        outcome = await session.take_turn("iki gündür ağrıyor")
        pump.cancel()
        return float(outcome.elapsed_ms)

    return float(clock.run(scenario()))


def test_turn_latency_is_unchanged_by_lanes_stalled_thirty_seconds() -> None:
    """Invariant 11's named test, verbatim: *"lanes stalled 30 s → turn latency
    unchanged"*.

    Taken past 30 s as well, because a number that survives absurdity is a
    property and a number that survives only the stated case is a coincidence.
    """
    no_lanes = _turn_latency(lane_stall_s=None)
    stalled_30s = _turn_latency(lane_stall_s=30.0)
    stalled_an_hour = _turn_latency(lane_stall_s=3_600.0)

    assert no_lanes > 0.0, "the turn must actually have spoken something"
    assert stalled_30s == no_lanes == stalled_an_hour


def test_offering_a_frame_consumes_no_time_at_all(rig: Rig) -> None:
    rig.scheduler.register(lane_spec(Lane.AFFECT), RecordingObserver(lane_id=Lane.AFFECT))
    for frame in frames(8):
        rig.scheduler.offer(frame)
    assert rig.clock.now_ms() == 0.0


def test_a_lane_that_overruns_its_budget_is_cancelled_and_never_awaited() -> None:
    """files/03 §4.7.6: lanes run with per-lane budgets. Overrun is a drop."""
    clock = FakeClock()
    rig = build_rig(clock=clock)
    observer = SlowObserver(lane_id=Lane.AFFECT, clock=clock, stall_s=30.0)
    rig.scheduler.register(lane_spec(Lane.AFFECT, deadline_ms=50.0), observer)
    for frame in frames(4):
        rig.scheduler.offer(frame)

    outcomes = clock.run(rig.scheduler.pump())

    assert observer.started == 1
    assert observer.finished == 0, "the pump waited for a lane past its budget"
    assert clock.now_ms() == pytest.approx(50.0)
    assert [outcome.dropped for outcome in outcomes] == [DropReason.LANE_OVERRAN]
    assert rig.scheduler.drops.count(lane=Lane.AFFECT, reason=DropReason.LANE_OVERRAN) > 0


# =====================================================================================
# 3 · frames dropped under load, with a metric
# =====================================================================================


def test_a_stalled_lane_drops_frames_instead_of_holding_them(rig: Rig) -> None:
    """Backpressure: the buffer is bounded, so load is shed at the offer."""
    rig.scheduler.register(
        lane_spec(Lane.AFFECT, max_queued_frames=3), RecordingObserver(lane_id=Lane.AFFECT)
    )
    offers = [rig.scheduler.offer(frame) for frame in frames(10)]

    accepted = [offer for offer in offers if Lane.AFFECT in offer.accepted]
    dropped = [offer for offer in offers if offer.dropped]
    assert len(accepted) == 3
    assert len(dropped) == 7
    assert {reason for offer in dropped for _lane, reason in offer.dropped} == {
        DropReason.BACKPRESSURE
    }


def test_the_drop_counter_is_keyed_by_lane_and_reason_only(rig: Rig) -> None:
    """Invariant 6: labels are ids and closed enumerations, never free text."""
    rig.scheduler.register(
        lane_spec(Lane.AFFECT, max_queued_frames=2), RecordingObserver(lane_id=Lane.AFFECT)
    )
    for frame in frames(6):
        rig.scheduler.offer(frame)

    series = rig.scheduler.drops.series()
    assert series == {(Lane.AFFECT.value, DropReason.BACKPRESSURE.value): 4}
    for lane_label, reason_label in series:
        assert lane_label in {member.value for member in Lane}
        assert reason_label in {member.value for member in DropReason}


def test_the_dropped_frame_count_reaches_the_lane_and_its_observation(rig: Rig) -> None:
    """files/03 §4.8 property 3: non-determinism is recorded, not eliminated.

    ``dropped_frames_in_window`` is a field on the recorded signal precisely so
    that replaying a degraded session reproduces the *degraded* decision.
    """
    observer = RecordingObserver(lane_id=Lane.AFFECT)
    rig.scheduler.register(lane_spec(Lane.AFFECT, max_queued_frames=2), observer)
    for frame in frames(6):
        rig.scheduler.offer(frame)

    outcomes = rig.clock.run(rig.scheduler.pump())

    assert observer.contexts[0].dropped_frames_in_window == 4
    assert outcomes[0].observation is not None
    assert outcomes[0].observation.dropped_frames_in_window == 4


def test_the_lane_package_constructs_no_prometheus_family() -> None:
    """Invariant 13, honestly: no lane row exists in the catalogue yet, so the
    framework counts in process and emits nothing."""
    offences: list[str] = []
    for path in _sources():
        label = str(path.relative_to(REPO))
        offences += _prometheus_calls(path.read_text(encoding="utf-8"), label=label)
    assert offences == [], (
        "the lane package constructs a Prometheus family. Every emitted series "
        "must exist in observability/metrics_catalog.yaml; the row this framework "
        f"needs is named in docs/evidence/INT-110.md: {offences}"
    )


def test_the_metric_this_framework_needs_is_named_exactly_once() -> None:
    """The series the threat model already lists as an ``observer-lanes`` signal.

    ``lane.dropped_frames`` is the OTel dotted id; ``lane_dropped_frames_total``
    is its Prometheus form (dots become underscores, counters end ``_total``).
    """
    assert LANE_DROPPED_FRAMES_ID == "lane.dropped_frames"
    assert LANE_DROPPED_FRAMES_NAME == "lane_dropped_frames_total"
    assert LANE_DROPPED_FRAMES_LABELS == ("lane", "reason")


# =====================================================================================
# 4 · per-lane consent — KVKK-6, files/06 §2
# =====================================================================================


def test_every_declared_lane_scope_is_in_the_closed_files_06_registry() -> None:
    """INT-038 holds the closed purpose list; this framework may not widen it."""
    assert set(LANE_CONSENT_SCOPES.values()) <= set(purpose_ids())
    assert LANE_CONSENT_SCOPES == {
        Lane.AFFECT: "lane:affect",
        Lane.LINGUISTIC: "lane:linguistic",
    }


def test_lane_acoustic_is_refused_as_a_consent_scope_by_name() -> None:
    """files/06 §2.4: an ICF under TCKAY, not a toggle.

    *"A device you may not place on the market is not made lawful by a
    toggle."* The registry already refuses the id; the framework refuses it a
    second time, at the point a lane would ask for it.
    """
    assert "lane:acoustic" in REMOVED_PURPOSES
    with pytest.raises(LaneConsentScopeRefusedError, match="lane:acoustic"):
        consent_scope_for(Lane.ACOUSTIC)


@pytest.mark.parametrize("lane", sorted(UNDECLARED_CONSENT_LANES))
def test_a_lane_with_no_declared_consent_scope_cannot_be_registered(rig: Rig, lane: Lane) -> None:
    """KVKK-6: every lane read checks a consent scope, so a lane without one
    does not run.

    files/03 §4.7 says *"each lane is a separate consent purpose"*; files/06 §2
    lists two lane purposes. ``asr_quality`` and ``engagement`` therefore have
    no scope any human has decided, and the framework fails closed on them
    rather than inventing one (docs/evidence/INT-110.md records the ask).
    """
    with pytest.raises(LaneConsentUndeclaredError, match=lane.value):
        consent_scope_for(lane)

    admission = rig.scheduler.register(lane_spec(lane), RecordingObserver(lane_id=lane))
    assert admission is LaneAdmission.REFUSED_NO_CONSENT_SCOPE
    assert lane not in rig.scheduler.lanes
    assert rig.scheduler.offer(frames(1)[0]).accepted == ()


def test_a_lane_whose_scope_is_not_granted_does_not_run() -> None:
    rig = build_rig(granted={})
    observer = RecordingObserver(lane_id=Lane.AFFECT)
    admission = rig.scheduler.register(lane_spec(Lane.AFFECT), observer)

    assert admission is LaneAdmission.REFUSED_CONSENT_NOT_GRANTED
    assert rig.scheduler.lanes == frozenset()
    for frame in frames(4):
        rig.scheduler.offer(frame)
    assert rig.clock.run(rig.scheduler.pump()) == ()
    assert observer.contexts == []


def test_the_granted_consent_version_travels_with_every_lane_read(rig: Rig) -> None:
    """files/03 §4.8: ``consent_version`` is a recorded field on the signal."""
    observer = RecordingObserver(lane_id=Lane.AFFECT)
    rig.scheduler.register(lane_spec(Lane.AFFECT), observer)
    for frame in frames(4):
        rig.scheduler.offer(frame)
    rig.clock.run(rig.scheduler.pump())

    assert observer.contexts[0].consent_version == "v1"
    # Checked once at registration and again at every window: KVKK-6 is
    # "every lane *read* checks a consent scope", not "the lane was admitted
    # once at the start of the session".
    assert set(rig.probe.reads) == {"lane:affect"}
    assert len(rig.probe.reads) >= 2


def test_a_consent_that_disappears_between_windows_stops_the_lane(rig: Rig) -> None:
    """The re-check has teeth: the lane stops at the next window, not at the
    next session (files/06 §2.2, ≤ 1 s at the lane boundary)."""
    observer = RecordingObserver(lane_id=Lane.AFFECT)
    rig.scheduler.register(lane_spec(Lane.AFFECT, max_queued_frames=8), observer)
    for frame in frames(2):
        rig.scheduler.offer(frame)
    rig.clock.run(rig.scheduler.pump())
    assert len(observer.contexts) == 1

    rig.probe.granted_scopes.clear()
    for frame in frames(2, start_seq=10):
        rig.scheduler.offer(frame)
    assert rig.clock.run(rig.scheduler.pump()) == ()

    assert len(observer.contexts) == 1, "the lane read after its consent was gone"
    assert rig.scheduler.lanes == frozenset()
    assert rig.scheduler.retained_bytes() == 0


def test_withdrawing_consent_stops_the_lane_and_zeroizes_its_buffer(rig: Rig) -> None:
    """files/06 §2.2: effective ≤ 1 s at the lane boundary — the task stops,
    the buffer is zeroized, and the zeroization is asserted."""
    observer = RecordingObserver(lane_id=Lane.AFFECT)
    rig.scheduler.register(lane_spec(Lane.AFFECT, max_queued_frames=8), observer)
    for frame in frames(4):
        rig.scheduler.offer(frame)

    stopped = rig.scheduler.withdraw("lane:affect")

    assert stopped == (Lane.AFFECT,)
    assert rig.scheduler.lanes == frozenset()
    assert rig.scheduler.retained_bytes() == 0
    assert rig.scheduler.drops.count(lane=Lane.AFFECT, reason=DropReason.CONSENT_WITHDRAWN) == 4
    assert rig.clock.run(rig.scheduler.pump()) == ()
    assert observer.contexts == []


# =====================================================================================
# 5 · acoustic — the study assertion, and failing closed on amendment
# =====================================================================================


def _assertion_fields() -> dict[str, object]:
    return {
        "study_id": "STUDY-0001",
        "protocol_version": "1.0",
        "icf_version": "1.0",
        "approval_date": date(2026, 8, 30),
    }


@pytest.mark.parametrize("missing", sorted(_assertion_fields()))
def test_the_acoustic_lane_is_unreachable_without_each_of_the_four_fields(
    missing: str,
) -> None:
    """Invariant 23: *"M3 is unreachable unless {study_id, protocol_version,
    ICF_version, approval_date} **all** assert"*.

    Each field is removed on its own, because a conjunction tested only in the
    all-present and all-absent cases is three untested conjuncts.
    """
    fields = _assertion_fields()
    del fields[missing]
    with pytest.raises(ValidationError, match=missing):
        StudyAssertion(**fields)  # type: ignore[arg-type]


def test_the_acoustic_lane_is_unreachable_with_no_assertion_at_all() -> None:
    gate = StudyGate(assertion=None, live_protocol_version="1.0")
    assert gate.state is StudyGateState.NO_ASSERTION
    assert not gate.admits

    rig = build_rig(study_gate=gate)
    admission = rig.scheduler.register(
        lane_spec(Lane.ACOUSTIC), RecordingObserver(lane_id=Lane.ACOUSTIC)
    )
    assert admission is LaneAdmission.REFUSED_STUDY_ASSERTION
    assert rig.scheduler.lanes == frozenset()


def test_the_acoustic_lane_fails_closed_on_a_protocol_amendment() -> None:
    """TCKAY m.11 makes an amendment a fresh submission, so the gate shuts.

    The assertion is still complete and still signed — it is simply no longer
    the protocol being run, and *"fails closed"* means the difference alone is
    enough.
    """
    assertion = StudyAssertion(**_assertion_fields())  # type: ignore[arg-type]
    assert StudyGate(assertion=assertion, live_protocol_version="1.0").admits

    amended = StudyGate(assertion=assertion, live_protocol_version="1.1")
    assert amended.state is StudyGateState.AMENDED
    assert not amended.admits

    rig = build_rig(study_gate=amended)
    admission = rig.scheduler.register(
        lane_spec(Lane.ACOUSTIC), RecordingObserver(lane_id=Lane.ACOUSTIC)
    )
    assert admission is LaneAdmission.REFUSED_STUDY_ASSERTION


def test_a_fully_asserted_acoustic_lane_still_never_reaches_observer_state() -> None:
    """files/03 §4.7.4: the output goes to the sealed research store, and
    ``ObserverState`` is not it. Reachable is not the same as visible."""
    gate = StudyGate(
        assertion=StudyAssertion(**_assertion_fields()),  # type: ignore[arg-type]
        live_protocol_version="1.0",
    )
    rig = build_rig(study_gate=gate)
    observer = RecordingObserver(lane_id=Lane.ACOUSTIC)
    assert rig.scheduler.register(lane_spec(Lane.ACOUSTIC), observer) is LaneAdmission.ADMITTED

    for frame in frames(4):
        rig.scheduler.offer(frame)
    outcomes = rig.clock.run(rig.scheduler.pump())

    assert observer.contexts, "the lane was admitted, so it must have run"
    assert len(outcomes) == 2, "two windows of two frames each"
    assert not any(outcome.recorded_in_state for outcome in outcomes)
    assert all(outcome.observation is not None for outcome in outcomes)
    state = rig.scheduler.observer_state()
    assert state.linguistic_markers == {}
    assert state.asr_quality == {}
    assert state.engagement == {}


def test_the_acoustic_lane_needs_no_consent_scope_because_it_has_none(rig: Rig) -> None:
    """The gate is the ICF, not a toggle — so the consent probe is never asked."""
    gate = StudyGate(
        assertion=StudyAssertion(**_assertion_fields()),  # type: ignore[arg-type]
        live_protocol_version="1.0",
    )
    acoustic = build_rig(granted={}, study_gate=gate)
    assert (
        acoustic.scheduler.register(
            lane_spec(Lane.ACOUSTIC), RecordingObserver(lane_id=Lane.ACOUSTIC)
        )
        is LaneAdmission.ADMITTED
    )
    assert acoustic.probe.reads == []


# =====================================================================================
# 6 · invariant 3 — bounded buffers, zeroized on every trigger
# =====================================================================================


def test_a_lane_window_cannot_be_configured_beyond_sixty_seconds() -> None:
    """Invariant 3: *"Memory buffers ≤ 60 s"*, as a type refusal."""
    assert MAX_WINDOW_MS == 60_000.0
    LaneBudget(
        window_ms=MAX_WINDOW_MS, max_queued_frames=2, deadline_ms=10.0, sampling_rate_hz=50.0
    )
    with pytest.raises(ValidationError):
        LaneBudget(
            window_ms=MAX_WINDOW_MS + 1.0,
            max_queued_frames=2,
            deadline_ms=10.0,
            sampling_rate_hz=50.0,
        )


def test_a_window_buffer_never_holds_more_than_its_budget() -> None:
    buffer = WindowBuffer(
        budget=LaneBudget(
            window_ms=1_000.0, max_queued_frames=3, deadline_ms=10.0, sampling_rate_hz=50.0
        )
    )
    accepted = [buffer.append(frame) for frame in frames(10)]
    assert accepted.count(True) == 3
    assert buffer.frame_count == 3


@pytest.mark.parametrize("trigger", sorted(ZeroizeTrigger))
def test_every_zeroize_trigger_leaves_the_buffer_all_zero(trigger: ZeroizeTrigger) -> None:
    """Invariant 3 / invariant 18: the buffer reads all-zero after **every**
    trigger in files/10 §3 — window consumed, gate rejection, lane disabled,
    consent withdrawn, session end, shutdown."""
    buffer = WindowBuffer(
        budget=LaneBudget(
            window_ms=1_000.0, max_queued_frames=8, deadline_ms=10.0, sampling_rate_hz=50.0
        )
    )
    held = frames(4)
    for frame in held:
        buffer.append(frame)
    assert any(any(frame.samples) for frame in held)

    zeroed = buffer.zeroize(trigger)

    assert zeroed == 4
    assert buffer.frame_count == 0
    assert buffer.retained_bytes() == 0
    for frame in held:
        assert not any(frame.samples), f"{trigger.value} left readable audio behind"


def test_the_zeroize_trigger_set_is_the_files_10_list() -> None:
    assert {trigger.value for trigger in ZeroizeTrigger} == {
        "window_consumed",
        "gate_rejected",
        "lane_disabled",
        "consent_withdrawn",
        "session_end",
        "shutdown",
    }


def test_a_consumed_window_is_zeroized_before_the_next_one_opens(rig: Rig) -> None:
    observer = RecordingObserver(lane_id=Lane.AFFECT)
    rig.scheduler.register(lane_spec(Lane.AFFECT, max_queued_frames=8), observer)
    offered = frames(4)
    for frame in offered:
        rig.scheduler.offer(frame)

    rig.clock.run(rig.scheduler.pump())

    assert observer.contexts, "the lane must have run for a window to be consumed"
    assert rig.scheduler.retained_bytes() == 0
    for frame in offered:
        assert not any(frame.samples)


def test_ending_the_session_zeroizes_every_lane(rig: Rig) -> None:
    rig.scheduler.register(
        lane_spec(Lane.AFFECT, max_queued_frames=8), RecordingObserver(lane_id=Lane.AFFECT)
    )
    offered = frames(4)
    for frame in offered:
        rig.scheduler.offer(frame)

    zeroed = rig.scheduler.end_session()

    assert zeroed == 4
    assert rig.scheduler.lanes == frozenset()
    assert rig.scheduler.retained_bytes() == 0
    for frame in offered:
        assert not any(frame.samples)


def test_the_window_a_lane_reads_is_a_read_only_view(rig: Rig) -> None:
    """A lane may read the frames it is scoring and may not alter them."""
    observer = RecordingObserver(lane_id=Lane.AFFECT)
    rig.scheduler.register(lane_spec(Lane.AFFECT), observer)
    for frame in frames(4):
        rig.scheduler.offer(frame)
    rig.clock.run(rig.scheduler.pump())

    window = observer.contexts[0].window
    assert window.frame_count == 2
    samples = window.samples()
    assert all(view.readonly for view in samples)
    with pytest.raises(TypeError):
        samples[0][0] = 0


# --- the enum surfaces, pinned -------------------------------------------------------


def _values(members: Iterator[enum.StrEnum]) -> set[str]:
    return {member.value for member in members}


def test_the_drop_reason_vocabulary_is_closed() -> None:
    assert _values(iter(DropReason)) == {
        "backpressure",
        "lane_overran",
        "consent_withdrawn",
        "lane_disabled",
    }


def test_the_admission_vocabulary_is_closed() -> None:
    assert _values(iter(LaneAdmission)) == {
        "admitted",
        "refused_no_consent_scope",
        "refused_consent_not_granted",
        "refused_study_assertion",
    }


def test_a_consent_reading_carries_a_scope_and_a_version_and_nothing_else() -> None:
    assert set(ConsentReading.model_fields) == {"scope", "version"}


# =====================================================================================
# 7 · containment — a lane that misbehaves is stopped, not obeyed
# =====================================================================================


@dataclass
class RaisingObserver:
    """A lane whose implementation is broken. It must not take the pump down."""

    lane_id: Lane

    @property
    def lane(self) -> Lane:
        return self.lane_id

    async def observe(self, context: LaneContext) -> LaneObservation:
        raise RuntimeError(f"broken lane at window {context.window_id}")


@dataclass
class BoundaryBreachingObserver:
    """An M1 lane that returns markers it has no egress for (files/03 §4.7.5)."""

    lane_id: Lane

    @property
    def lane(self) -> Lane:
        return self.lane_id

    async def observe(self, context: LaneContext) -> LaneObservation:
        del context
        return LaneObservation(confidence=1.0, markers={"emotion": "sad"})


def test_a_lane_that_raises_is_disabled_and_its_window_zeroized(rig: Rig) -> None:
    rig.scheduler.register(lane_spec(Lane.AFFECT), RaisingObserver(lane_id=Lane.AFFECT))
    offered = frames(4)
    for frame in offered:
        rig.scheduler.offer(frame)

    outcomes = rig.clock.run(rig.scheduler.pump())

    assert [outcome.dropped for outcome in outcomes] == [DropReason.LANE_DISABLED]
    assert rig.scheduler.lanes == frozenset()
    assert rig.scheduler.retained_bytes() == 0
    for frame in offered:
        assert not any(frame.samples)


def test_a_lane_that_breaches_its_module_boundary_is_disabled_not_obeyed(rig: Rig) -> None:
    """The type gates make this near-impossible; the runtime still fails closed.

    ``affect`` has no marker egress at all, so an observation carrying one is
    a breach of M1's boundary — and the lane that produced it does not get a
    second window.
    """
    rig.scheduler.register(lane_spec(Lane.AFFECT), BoundaryBreachingObserver(lane_id=Lane.AFFECT))
    for frame in frames(4):
        rig.scheduler.offer(frame)

    outcomes = rig.clock.run(rig.scheduler.pump())

    assert [outcome.dropped for outcome in outcomes] == [DropReason.LANE_DISABLED]
    assert outcomes[0].recorded_in_state is False
    assert rig.scheduler.lanes == frozenset()
    assert rig.scheduler.observer_state().asr_quality == {}


def test_an_amendment_mid_session_closes_the_acoustic_gate_at_the_next_window() -> None:
    """TCKAY m.11 again, this time arriving *during* a session.

    The lane was admitted under version 1.0. The protocol is amended, the gate
    is re-read at the next window, and the lane stops with its buffer zeroized
    — files/03 §4.7.4's *"genuinely unreachable, not merely unrendered"*.
    """
    assertion = StudyAssertion(**_assertion_fields())  # type: ignore[arg-type]
    rig = build_rig(study_gate=StudyGate(assertion=assertion, live_protocol_version="1.0"))
    observer = RecordingObserver(lane_id=Lane.ACOUSTIC)
    assert rig.scheduler.register(lane_spec(Lane.ACOUSTIC), observer) is LaneAdmission.ADMITTED

    rig.scheduler.study_gate = StudyGate(assertion=assertion, live_protocol_version="1.1")
    offered = frames(4)
    for frame in offered:
        rig.scheduler.offer(frame)

    assert rig.clock.run(rig.scheduler.pump()) == ()
    assert observer.contexts == []
    assert rig.scheduler.lanes == frozenset()
    assert rig.scheduler.retained_bytes() == 0
    for frame in offered:
        assert not any(frame.samples)


def test_disabling_a_lane_that_is_not_running_is_a_no_op(rig: Rig) -> None:
    assert (
        rig.scheduler.disable(Lane.LINGUISTIC, ZeroizeTrigger.SESSION_END, DropReason.LANE_DISABLED)
        == 0
    )


# =====================================================================================
# 8 · one frame, several lanes — zeroized once the last holder is done
# =====================================================================================


def test_a_frame_shared_by_two_lanes_is_zeroized_only_when_both_are_done() -> None:
    """Invariant 3 has to mean the bytes, once.

    The runtime decodes each frame once and offers it to every admitted lane,
    so a lane that zeroized on its own would blank another lane's window
    mid-read — a correctness bug wearing a safety argument. The scheduler
    reference-counts instead.
    """
    rig = build_rig(granted={"lane:affect": "v1", "lane:linguistic": "v1"})
    affect = RecordingObserver(lane_id=Lane.AFFECT)
    linguistic = RecordingObserver(lane_id=Lane.LINGUISTIC)
    rig.scheduler.register(lane_spec(Lane.AFFECT, window_ms=20.0), affect)
    rig.scheduler.register(lane_spec(Lane.LINGUISTIC, window_ms=40.0), linguistic)

    offered = frames(4)
    for frame in offered:
        rig.scheduler.offer(frame)
    assert rig.scheduler.lanes == {Lane.AFFECT, Lane.LINGUISTIC}

    rig.clock.run(rig.scheduler.pump())

    assert len(affect.contexts) == 2, "20 ms windows over four 10 ms frames"
    assert len(linguistic.contexts) == 1, "one 40 ms window"
    assert rig.scheduler.retained_bytes() == 0
    for frame in offered:
        assert not any(frame.samples), "a shared frame outlived its last holder"


# =====================================================================================
# 9 · the bounds themselves
# =====================================================================================


def test_a_buffer_refuses_a_frame_that_would_push_it_past_sixty_seconds() -> None:
    """The frame-depth bound and the 60-second bound are independent.

    A budget generous enough to allow thousands of frames still cannot hold
    more than a minute of a patient's voice — invariant 3 does not depend on
    somebody having sized ``max_queued_frames`` correctly.
    """
    buffer = WindowBuffer(
        budget=LaneBudget(
            window_ms=MAX_WINDOW_MS,
            max_queued_frames=10_000,
            deadline_ms=10.0,
            sampling_rate_hz=50.0,
        )
    )
    one_second = 1_000.0
    accepted = [buffer.append(frame) for frame in frames(61, duration_ms=one_second)]

    assert accepted.count(True) == 60
    assert accepted[-1] is False
    assert buffer.duration_ms == MAX_WINDOW_MS
    assert buffer.take_dropped() == 1


def test_the_drop_ledger_ignores_a_non_positive_count() -> None:
    """``disable`` on an empty buffer records nothing rather than a zero series."""
    ledger = DropLedger()
    ledger.record(Lane.AFFECT, DropReason.BACKPRESSURE, 0)
    assert ledger.series() == {}
    assert ledger.count() == 0


def test_zeroizing_an_empty_frame_still_counts_it() -> None:
    """A frame with no samples is still a frame the trigger accounted for.

    Silence, a dropped payload and a lane that consumed the bytes already all
    look like this, and invariant 18's claim is about *every* frame in the
    buffer, not every frame that happened to carry audio.
    """
    empty = Frame(seq=0, t_monotonic_ms=0.0, duration_ms=10.0, samples=bytearray())
    assert zeroize_frames((empty,), ZeroizeTrigger.SHUTDOWN) == 1
    assert bytes(empty.samples) == b""
