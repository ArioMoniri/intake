"""INT-112 — the linguistic lane: TR lexicons, prosody stats, crisis bypass.

Acceptance line under test, verbatim (docs/backlog/issues.yaml INT-112):
  "crisis lexicon hits route deterministically to C-SSRS path (test); markers
   aggregate per section"

``sec_row: observer-lanes`` · ``depends_on: [INT-110, INT-080]``.

This is the first lane to run inside INT-110's framework, and it is the one
lane in files/03 §4.7.5 whose output column has two halves that must not be
confused:

- ``linguistic_markers{}`` — deterministic lexicon and timing markers, written
  through ``ObserverState`` like any other lane aggregate, under the
  ``lane:linguistic`` consent purpose (files/06 §2, KVKK-6);
- *"crisis lexicon hits **bypass the lane**"* — they do not enter
  ``ObserverState`` at all. They route, **regardless of wellbeing consent**
  (files/04 §4.2 defect 3), to the deterministic detector and its C-SSRS path.

Two things this issue may not build, and both are proved absent here rather
than described as absent:

- **the crisis lexicon does not exist** and must be clinician-authored, not
  model-generated (``files/protocols/base.life_threat.yaml``
  ``rf.crisis_disclosure_signposting.source_gap``; HUMAN_BLOCKERS **HB-C8**).
  So the shipped lexicon is an *unauthored* state that **refuses**, not an
  empty list that silently never matches — the two are indistinguishable in
  production and only one is honest.
  ``test_an_authored_lexicon_with_no_entries_cannot_be_constructed`` and
  ``test_scanning_an_unauthored_lexicon_refuses_rather_than_reporting_no_hits``
  are that difference.
- **C-SSRS is licence-BLOCKED** (Clario's exclusive electronic licence;
  HUMAN_BLOCKERS **HB-L2**). So the route resolves and the instrument behind it
  refuses by name. There is no fallback screener: files/04 §4.2 says the crisis
  response is signposting and *"a screener here would need the licence"*.

Every Turkish string in this file is synthetic and marked ``sentetik``, the
convention ``tests/sim/personas.py`` uses for the synthetic RED trigger and its
near miss. No Turkish crisis phrase is written down anywhere in this repository.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import pytest
from clinical_schemas.observers import Lane, ObserverState
from harness import (
    FakeClock,
    GrantingConsentProbe,
    build_session,
    frames,
    scripted_step,
)
from intake_platform.llm.units import render_quantity
from intake_voice_runtime.observers import (
    DropReason,
    InteractionDelta,
    LaneAdmission,
    LaneModule,
    LaneObservation,
    LaneOutcome,
    LaneSpec,
    Observer,
    ObserverScheduler,
    ObserverStateBuilder,
    ObserverStateRefusedError,
    ZeroizeTrigger,
)
from intake_voice_runtime.observers.linguistic import (
    CRISIS_GATE_FACT,
    CRISIS_INSTRUMENT_ID,
    CRISIS_RULE_ID,
    LICENCE_BLOCKED_INSTRUMENTS,
    NBSP,
    SECTION_MARKER_PREFIX,
    CrisisBypass,
    CrisisRoute,
    InstrumentLicenceBlockedError,
    LaneRefusal,
    Lexicon,
    LexiconEntry,
    LexiconStatus,
    LexiconUnauthoredError,
    LinguisticLane,
    LinguisticLexicons,
    MarkerCategory,
    ProsodyTotals,
    RefusalCode,
    TranscriptTurn,
    TranscriptWord,
    UnauthoredNote,
    linguistic_lane_spec,
    open_crisis_path,
    render_measure,
    resolve_instrument,
    syllables_tr,
    tokenize_tr,
    unauthored_lexicons,
)
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
LANE_PACKAGE = (
    REPO
    / "services"
    / "voice-runtime"
    / "src"
    / "intake_voice_runtime"
    / "observers"
    / "linguistic"
)

SESSION_REF = "11111111-2222-4333-8444-555555555555"

# --- the synthetic corpus ------------------------------------------------------------
#
# `sentetik_tetik` is the token pair a synthetic crisis entry gates on and
# `sentetik_yakin_tetik` is its near miss — one token different, the same
# shape as files/04's LT-04-P / LT-04-N pair. Nothing here is Turkish clinical
# content; the real entries are HB-C8 and belong to a clinician.

SYNTHETIC_CRISIS_ENTRY = LexiconEntry(
    entry_id="sentetik.kriz.01",
    tokens=("sentetik", "tetik"),
    signoff_ref="sentetik-imza-01",
)
SYNTHETIC_NEAR_MISS_TOKENS = ("sentetik", "yakin", "tetik")


def synthetic_crisis_lexicon(*entries: LexiconEntry) -> Lexicon:
    """An authored lexicon whose content is obviously synthetic."""
    return Lexicon(
        ref="lexicon.sentetik.kriz",
        status=LexiconStatus.AUTHORED,
        entries=entries or (SYNTHETIC_CRISIS_ENTRY,),
    )


def synthetic_marker_lexicon() -> Lexicon:
    return Lexicon(
        ref="lexicon.sentetik.belirtec",
        status=LexiconStatus.AUTHORED,
        entries=(
            LexiconEntry(
                entry_id="sentetik.belirtec.01",
                tokens=("sentetik", "belirtec"),
                category=MarkerCategory.HOPELESSNESS,
                signoff_ref="sentetik-imza-02",
            ),
            LexiconEntry(
                entry_id="sentetik.belirtec.02",
                tokens=("sentetik", "ikincil"),
                category=MarkerCategory.SOMATIC_WORRY,
                signoff_ref="sentetik-imza-03",
            ),
        ),
    )


def turn(
    *tokens: str,
    turn_ref: str = "sentetik-tur-01",
    section_ref: str = "oyku",
    word_ms: float = 200.0,
    gap_ms: float = 100.0,
    start_ms: float = 0.0,
) -> TranscriptTurn:
    """One final transcript turn with synthetic word timestamps."""
    words: list[TranscriptWord] = []
    cursor = start_ms
    for token in tokens:
        words.append(TranscriptWord(text=token, start_ms=cursor, end_ms=cursor + word_ms))
        cursor += word_ms + gap_ms
    return TranscriptTurn(turn_ref=turn_ref, section_ref=section_ref, words=tuple(words))


@dataclass
class ScriptedTranscript:
    """The runtime's transcript feed, as the lane needs it: drained, not awaited."""

    pending: list[TranscriptTurn] = field(default_factory=list)
    takes: int = 0

    def take(self) -> tuple[TranscriptTurn, ...]:
        self.takes += 1
        drained = tuple(self.pending)
        self.pending.clear()
        return drained


def build_lane(
    *,
    transcript: ScriptedTranscript | None = None,
    lexicons: LinguisticLexicons | None = None,
) -> tuple[LinguisticLane, ScriptedTranscript]:
    feed = transcript if transcript is not None else ScriptedTranscript()
    lane = LinguisticLane(
        transcript=feed,
        lexicons=lexicons if lexicons is not None else unauthored_lexicons(),
    )
    return lane, feed


def spec() -> LaneSpec:
    """The lane's manifest with a test-sized window.

    The production window is five seconds of frames (``LINGUISTIC_WINDOW_MS``);
    a suite that offered five hundred frames per window would test the harness
    rather than the lane, so the budget is narrowed exactly the way INT-110's
    own ``lane_spec`` narrows it. ``test_the_lane_manifest_carries_its_module
    _intended_purpose`` pins the shipped defaults.
    """
    return linguistic_lane_spec(window_ms=20.0, max_queued_frames=8)


def build_scheduler(
    *, clock: FakeClock, granted: dict[str, str] | None = None
) -> tuple[ObserverScheduler, GrantingConsentProbe]:
    probe = GrantingConsentProbe(
        granted_scopes=dict(granted if granted is not None else {"lane:linguistic": "v3"})
    )
    scheduler = ObserverScheduler(session_ref=SESSION_REF, clock=clock, consent=probe)
    return scheduler, probe


def pump(scheduler: ObserverScheduler, clock: FakeClock, count: int = 2) -> tuple[LaneOutcome, ...]:
    """Offer ``count`` frames and pump one round of windows."""
    for frame in frames(count):
        scheduler.offer(frame)
    return clock.run(scheduler.pump())


# =====================================================================================
# 1 · the lexicon is EMPTY, and empty is a state that refuses (HB-C8)
# =====================================================================================


def test_the_shipped_crisis_lexicon_is_unauthored_and_names_its_blocker() -> None:
    """HUMAN_BLOCKERS rule 2: build the mechanism, wire the gate, fail closed,
    leave the content empty.

    ``rf.crisis_disclosure_signposting.source_gap`` says the phrase list
    *"does not exist and must be clinician-authored, not model-generated"*. So
    the constant this repository ships is an unauthored lexicon that names
    HB-C8, not a list somebody could quietly extend.
    """
    lexicons = unauthored_lexicons()
    assert lexicons.crisis.status is LexiconStatus.UNAUTHORED
    assert lexicons.markers.status is LexiconStatus.UNAUTHORED
    assert lexicons.crisis.entries == ()
    assert lexicons.crisis.blocker_ref == "HB-C8"


def test_an_authored_lexicon_with_no_entries_cannot_be_constructed() -> None:
    """The whole point of the issue, in one assertion.

    An empty list and an unauthored lexicon look identical in production — both
    never match — so the empty *authored* list must not be representable at all.
    """
    with pytest.raises(ValueError, match="unauthored"):
        Lexicon(ref="lexicon.sentetik.bos", status=LexiconStatus.AUTHORED, entries=())

    with pytest.raises(ValueError, match="unauthored"):
        Lexicon(
            ref="lexicon.sentetik.dolu",
            status=LexiconStatus.UNAUTHORED,
            entries=(SYNTHETIC_CRISIS_ENTRY,),
        )


def test_scanning_an_unauthored_lexicon_refuses_rather_than_reporting_no_hits() -> None:
    """A refusal, not a ``()``.

    ``scan`` on the shipped lexicon raises and names the blocker. A caller
    therefore cannot mistake "nobody has written the list" for "the patient
    said nothing" — which is the failure this test exists to make impossible.
    """
    lexicon = unauthored_lexicons().crisis
    with pytest.raises(LexiconUnauthoredError, match="HB-C8") as caught:
        lexicon.scan(("sentetik", "tetik"))
    assert caught.value.code is RefusalCode.CRISIS_LEXICON_UNAUTHORED

    authored = synthetic_crisis_lexicon()
    assert authored.scan(("sentetik", "baska", "sozcuk")) == ()


def test_the_bypass_refuses_while_the_lexicon_is_unauthored() -> None:
    """The refusal reaches the caller of the *bypass*, not only of the lexicon."""
    bypass = CrisisBypass(lexicon=unauthored_lexicons().crisis)
    with pytest.raises(LexiconUnauthoredError, match="HB-C8"):
        bypass.scan(turn("sentetik", "tetik"))


def test_no_lexicon_entry_exists_anywhere_in_the_shipped_package() -> None:
    """A second lock, on the source rather than on the value.

    A future edit that populates the constant would pass every test above by
    making the lexicon authored. This one walks the package and asserts that no
    module contains a ``LexiconEntry`` literal at all — the phrase list has no
    home in the source tree until a clinician gives it one.
    """
    offences: list[str] = []
    for path in sorted(LANE_PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source, filename=str(path))):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name == "LexiconEntry":
                    offences.append(f"{path.name}:{node.lineno}")
    assert offences == [], (
        "the crisis lexicon must be clinician-authored (HB-C8); a lexicon entry "
        f"constructed inside the shipped package is content this issue may not write: {offences}"
    )


# =====================================================================================
# 2 · crisis lexicon hits route deterministically to the C-SSRS path (acceptance)
# =====================================================================================


def test_a_crisis_hit_routes_to_the_c_ssrs_path() -> None:
    """The acceptance's first clause, with a synthetic lexicon standing in for
    the clinician-authored one."""
    bypass = CrisisBypass(lexicon=synthetic_crisis_lexicon())
    route = bypass.scan(turn("sentetik", "tetik"))

    assert isinstance(route, CrisisRoute)
    assert route.instrument_id == CRISIS_INSTRUMENT_ID == "C-SSRS"
    assert route.rule_id == CRISIS_RULE_ID == "rf.crisis_disclosure_signposting"
    assert route.entry_ref == "sentetik.kriz.01"
    assert route.section_ref == "oyku"
    assert route.consent_independent is True

    # The handoff is to the rules engine, on the fact that rule gates on —
    # `transcript.crisis_lexicon_hit == true` in base.life_threat.yaml. The
    # bypass supplies the fact; the level, register and location are the
    # rule's (invariants 1 and 21).
    assert CRISIS_GATE_FACT == "transcript.crisis_lexicon_hit"


def test_the_route_is_deterministic_for_the_same_transcript() -> None:
    """*"Deterministic"* is the load-bearing word: same transcript, same route,
    every time, with no model in the path."""
    bypass = CrisisBypass(lexicon=synthetic_crisis_lexicon())
    spoken = turn("bir", "sentetik", "tetik", "iki")

    routes = [bypass.scan(spoken) for _ in range(50)]
    assert all(route == routes[0] for route in routes)
    assert routes[0] is not None

    # Two bypasses built independently from the same entries agree, and the
    # order the entries were authored in does not change the answer.
    second = LexiconEntry(
        entry_id="sentetik.kriz.02", tokens=("sentetik", "ikinci"), signoff_ref="sentetik-imza-04"
    )
    forwards = CrisisBypass(lexicon=synthetic_crisis_lexicon(SYNTHETIC_CRISIS_ENTRY, second))
    backwards = CrisisBypass(lexicon=synthetic_crisis_lexicon(second, SYNTHETIC_CRISIS_ENTRY))
    assert forwards.scan(spoken) == backwards.scan(spoken) == routes[0]


def test_the_near_miss_negative_control_does_not_route() -> None:
    """files/04's LT-04-N shape: one token away from the positive, and it must
    not fire.

    The gate turns on the exact authored token sequence, so a loosening to
    substring matching breaks this test. It is **not** a licence to
    under-trigger: the real disambiguation is clinician-authored (HB-C8), which
    is precisely why the lexicon behind it is empty.
    """
    bypass = CrisisBypass(lexicon=synthetic_crisis_lexicon())
    assert bypass.scan(turn(*SYNTHETIC_NEAR_MISS_TOKENS)) is None
    assert bypass.scan(turn("sentetik")) is None
    assert bypass.scan(turn("tetik", "sentetik")) is None


def test_a_token_sequence_is_never_matched_as_a_substring() -> None:
    """The ``üre`` rule of invariant 22, applied to the lexicon.

    ``Üre nitrojeni`` *contains* ``üre`` and means something else entirely, so
    matching is by whole token sequence and never by substring — the posture
    ``intake_platform.llm.units.ANALYTE_NAMES`` already takes.
    """
    bypass = CrisisBypass(lexicon=synthetic_crisis_lexicon())
    assert bypass.scan(turn("sentetikler", "tetikleyici")) is None
    assert bypass.scan(turn("sentetiktetik")) is None


def test_the_route_carries_no_triage_level_and_no_matched_phrase() -> None:
    """Invariant 1 and invariant 6, as absent fields.

    A lexicon hit is a *route*, not a triage result: RED/YELLOW may only come
    from ``packages/protocols/triage``. And the worst possible leak here is the
    matched phrase, so the route has no carrier for one.
    """
    fields = set(CrisisRoute.model_fields)
    for forbidden in ("level", "triage", "register", "colour", "color", "priority", "score"):
        assert forbidden not in fields, f"a crisis route names {forbidden!r} (invariant 1)"
    for forbidden in ("text", "phrase", "utterance", "transcript", "words", "match_text"):
        assert forbidden not in fields, f"a crisis route names {forbidden!r} (invariant 6)"

    bypass = CrisisBypass(lexicon=synthetic_crisis_lexicon())
    route = bypass.scan(turn("sentetik", "tetik"))
    assert route is not None
    assert "sentetik tetik" not in route.model_dump_json()


def test_the_bypass_routes_with_no_consent_and_no_lane_registered() -> None:
    """files/04 §4.2 defect 3 — *"a consent-independent crisis response"*.

    The lane is consent-gated (``lane:linguistic``). The bypass is not the lane:
    it is reached with nothing granted, with no scheduler and with no lane
    registered at all, because *"the people most likely to decline are the
    people most needing to be caught"*.
    """
    clock = FakeClock()
    scheduler, probe = build_scheduler(clock=clock, granted={})
    lane, _feed = build_lane()
    assert scheduler.register(spec(), lane) is LaneAdmission.REFUSED_CONSENT_NOT_GRANTED
    assert scheduler.lanes == frozenset()

    bypass = CrisisBypass(lexicon=synthetic_crisis_lexicon())
    assert bypass.scan(turn("sentetik", "tetik")) is not None
    assert probe.reads == ["lane:linguistic"]


def test_a_crisis_hit_never_reaches_observer_state() -> None:
    """*"crisis lexicon hits bypass the lane"* — so the aggregate is untouched.

    The same transcript is given to the lane and to the bypass. The bypass
    routes; the lane's markers say nothing about it, because a crisis
    disclosure recorded in a consent-gated aggregate would be both the wrong
    record and the wrong lawful basis.
    """
    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    spoken = turn("sentetik", "tetik")
    lane, feed = build_lane(
        lexicons=LinguisticLexicons(
            crisis=synthetic_crisis_lexicon(), markers=synthetic_marker_lexicon()
        )
    )
    assert scheduler.register(spec(), lane) is LaneAdmission.ADMITTED
    feed.pending.append(spoken)
    pump(scheduler, clock)

    state = scheduler.observer_state()
    rendered = state.model_dump_json()
    assert CrisisBypass(lexicon=synthetic_crisis_lexicon()).scan(spoken) is not None
    for forbidden in ("crisis", "kriz", "C-SSRS", "cssrs", CRISIS_RULE_ID):
        assert forbidden not in rendered, (
            f"the lane's aggregate mentions {forbidden!r}; crisis hits bypass the lane"
        )


def test_no_model_sits_in_the_crisis_path() -> None:
    """A lane that called an LLM here would be a defect, so the package may not
    even name one — nor a source of non-determinism."""
    forbidden_roots = {
        "random",
        "secrets",
        "time",
        "torch",
        "transformers",
        "numpy",
        "httpx",
        "openai",
        "anthropic",
    }
    forbidden_dotted = ("intake_platform.llm", "intake_voice_runtime.talker", "protocols")
    offences: list[str] = []
    for path in sorted(LANE_PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source, filename=str(path))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for dotted in names:
                if dotted.split(".")[0] in forbidden_roots:
                    offences.append(f"{path.name}: {dotted}")
                if any(dotted == bad or dotted.startswith(f"{bad}.") for bad in forbidden_dotted):
                    offences.append(f"{path.name}: {dotted}")
    assert offences == [], f"the deterministic crisis path reached a model or a clock: {offences}"


def test_the_bypass_is_not_awaitable_and_takes_only_data() -> None:
    """No await, no callback, no injected scorer: one function of one value."""
    assert not inspect.iscoroutinefunction(CrisisBypass.scan)
    assert list(inspect.signature(CrisisBypass.scan).parameters) == ["self", "turn"]


# =====================================================================================
# 3 · the far end refuses — C-SSRS is licence-BLOCKED (HB-L2)
# =====================================================================================


def test_opening_the_crisis_path_refuses_with_a_named_licence_error() -> None:
    """The route resolves; the instrument behind it does not.

    files/04 header: *"an instrument whose licence is not GO does not compile
    into a pack"*. C-SSRS is BLOCKED — Clario's exclusive electronic licence —
    and the escalation policy the rule hands off to does not exist either
    (HB-C8), so both refusal codes are named at once rather than one hiding
    behind the other.
    """
    bypass = CrisisBypass(lexicon=synthetic_crisis_lexicon())
    route = bypass.scan(turn("sentetik", "tetik"))
    assert route is not None

    with pytest.raises(InstrumentLicenceBlockedError) as caught:
        open_crisis_path(route)

    message = str(caught.value)
    assert "C-SSRS" in message
    assert "HB-L2" in message
    assert "HB-C8" in message
    assert caught.value.codes == (
        RefusalCode.INSTRUMENT_LICENCE_BLOCKED,
        RefusalCode.CRISIS_PATH_POLICY_MISSING,
    )


def test_the_blocked_instruments_are_refused_by_name_whatever_a_table_says() -> None:
    """The negative control on the licence gate, and its positive control.

    A licence table is data, and data can be wrong or injected. C-SSRS and
    WHO-5 are refused *by name* — the posture ``consent.py`` takes for
    ``lane:acoustic`` — so a table that claims C-SSRS is GO changes nothing.
    """
    assert LICENCE_BLOCKED_INSTRUMENTS["C-SSRS"] == "HB-L2"
    assert LICENCE_BLOCKED_INSTRUMENTS["WHO-5"] == "HB-L3"

    with pytest.raises(InstrumentLicenceBlockedError, match="HB-L2"):
        resolve_instrument("C-SSRS", {"C-SSRS": "GO"})
    with pytest.raises(InstrumentLicenceBlockedError, match="HB-L3"):
        resolve_instrument("WHO-5", {"WHO-5": "GO"})

    # Fail closed on an instrument no table knows …
    with pytest.raises(InstrumentLicenceBlockedError, match="UNKNOWN"):
        resolve_instrument("sentetik-arac", {})
    # … and the positive control: the gate is not simply refusing everything.
    resolve_instrument("sentetik-arac", {"sentetik-arac": "GO"})


def test_there_is_no_fallback_screener_behind_the_refusal() -> None:
    """files/04 §4.2: the crisis response is signposting, *"not a screener"*,
    and *"a screener here would need the licence"*.

    So the package holds no second instrument to fall back to: the only
    instrument id it names is the blocked one, and the refusal is the end of
    the path rather than a branch into something cheaper.
    """
    assert inspect.signature(open_crisis_path).return_annotation in {"NoReturn", "typing.NoReturn"}

    named: set[str] = set()
    for path in sorted(LANE_PACKAGE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source, filename=str(path))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                token = node.value.strip()
                if token in {"PHQ-9", "PHQ-2", "GAD-7", "GAD-2", "HAQ-DI", "ASQ"}:
                    named.add(token)
    assert named == set(), f"the crisis path names a substitute instrument: {sorted(named)}"


# =====================================================================================
# 4 · markers aggregate per section (acceptance)
# =====================================================================================


def test_markers_aggregate_per_section() -> None:
    """The acceptance's second clause.

    files/03 §4.7.5's output column is a *per-section aggregate*: two sections
    in one session keep two aggregates, and neither one's counts bleed into the
    other.
    """
    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    lane, feed = build_lane(
        lexicons=LinguisticLexicons(
            crisis=synthetic_crisis_lexicon(), markers=synthetic_marker_lexicon()
        )
    )
    scheduler.register(spec(), lane)

    feed.pending.append(turn("bir", "iki", "uc", section_ref="oyku"))
    pump(scheduler, clock)
    feed.pending.append(turn("dort", "bes", turn_ref="sentetik-tur-02", section_ref="beklenti"))
    feed.pending.append(turn("alti", turn_ref="sentetik-tur-03", section_ref="oyku"))
    pump(scheduler, clock)

    markers = scheduler.observer_state().linguistic_markers
    oyku = markers[f"{SECTION_MARKER_PREFIX}oyku"]
    beklenti = markers[f"{SECTION_MARKER_PREFIX}beklenti"]
    assert isinstance(oyku, dict)
    assert isinstance(beklenti, dict)
    assert oyku["words"] == 4, "three words in the first window plus one in the second"
    assert oyku["turns"] == 2
    assert beklenti["words"] == 2
    assert beklenti["turns"] == 1


def test_the_marker_aggregate_carries_the_four_blueprint_categories() -> None:
    """files/03 §4.7.5 names the lexicons: negative affect, hopelessness,
    anhedonia, somatic worry. The category names are transcribed; the phrases
    behind them are not this issue's to write."""
    assert {category.value for category in MarkerCategory} == {
        "negative_affect",
        "hopelessness",
        "anhedonia",
        "somatic_worry",
    }

    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    lane, feed = build_lane(
        lexicons=LinguisticLexicons(
            crisis=synthetic_crisis_lexicon(), markers=synthetic_marker_lexicon()
        )
    )
    scheduler.register(spec(), lane)
    feed.pending.append(turn("sentetik", "belirtec", "sentetik", "ikincil"))
    pump(scheduler, clock)

    section = scheduler.observer_state().linguistic_markers[f"{SECTION_MARKER_PREFIX}oyku"]
    assert isinstance(section, dict)
    assert section["lexicon_status"] == "authored"
    assert section["marker.hopelessness"] == 1
    assert section["marker.somatic_worry"] == 1
    assert section["marker.anhedonia"] == 0


def test_an_unauthored_marker_lexicon_reports_its_status_and_no_zero_counts() -> None:
    """The same honesty as the crisis lexicon, one aggregate down.

    ``marker.hopelessness: 0`` from an unauthored lexicon is a measurement
    nobody made. The aggregate says ``unauthored`` and carries no category
    counts at all, so a reader can tell "none found" from "never looked".
    """
    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    lane, feed = build_lane()  # the shipped, unauthored lexicons
    scheduler.register(spec(), lane)
    feed.pending.append(turn("sentetik", "belirtec"))
    pump(scheduler, clock)

    section = scheduler.observer_state().linguistic_markers[f"{SECTION_MARKER_PREFIX}oyku"]
    assert isinstance(section, dict)
    assert section["lexicon_status"] == "unauthored"
    assert [key for key in section if key.startswith("marker.")] == []
    assert section["words"] == 2, "prosody is measured even while the lexicons are empty"


def test_the_lane_writes_only_the_linguistic_aggregate() -> None:
    """Invariant 11's routing half, for this lane specifically.

    ``linguistic`` is M2, so ``ObserverStateBuilder`` refuses an
    ``InteractionState`` field from it — and the lane never offers one.
    """
    assert linguistic_lane_spec().module is LaneModule.CLINICAL_SIGNALS

    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    lane, feed = build_lane()
    scheduler.register(spec(), lane)
    feed.pending.append(turn("bir", "iki"))
    outcomes = pump(scheduler, clock)

    assert [outcome.dropped for outcome in outcomes] == [None]
    assert outcomes[0].observation is not None
    assert outcomes[0].observation.interaction is None
    state = scheduler.observer_state()
    assert isinstance(state, ObserverState)
    assert state.asr_quality == {}
    assert state.engagement == {}
    assert state.interaction.pace == "normal"


# =====================================================================================
# 5 · invariant 6 — no PHI in the aggregate, the observation or the route
# =====================================================================================


def test_no_transcript_text_reaches_the_marker_aggregate() -> None:
    """*"A crisis marker that logged the matched phrase would be the worst
    possible leak."* Neither does an ordinary marker log an ordinary word."""
    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    lane, feed = build_lane(
        lexicons=LinguisticLexicons(
            crisis=synthetic_crisis_lexicon(), markers=synthetic_marker_lexicon()
        )
    )
    scheduler.register(spec(), lane)
    feed.pending.append(turn("sentetik", "belirtec", "gizli", "sozcuk"))
    outcomes = pump(scheduler, clock)

    rendered = scheduler.observer_state().model_dump_json()
    assert outcomes[0].observation is not None
    for word in ("gizli", "sozcuk", "belirtec"):
        assert word not in rendered, f"the transcript word {word!r} reached ObserverState"
        assert word not in outcomes[0].observation.model_dump_json()


def test_the_lane_retains_no_transcript_after_the_window() -> None:
    """The window is consumed and nothing about it is kept.

    Invariant 3 is about audio and this is text, but the reasoning is the same:
    a lane that accumulates utterances becomes a second transcript store with
    none of the controls the first one has.
    """
    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    lane, feed = build_lane()
    scheduler.register(spec(), lane)
    feed.pending.append(turn("gizli", "sozcuk"))
    pump(scheduler, clock)

    assert "gizli" not in repr(vars(lane))
    assert scheduler.retained_bytes() == 0


def test_the_lane_reads_no_audio_at_all() -> None:
    """files/03 §4.7.5: this lane's input is *"final transcripts + STT word
    timestamps"*. It is handed audio windows by the framework and reads none of
    them, so there is no path from a sample byte into a marker."""
    offences = [
        f"{path.name}:{node.lineno}"
        for path in sorted(LANE_PACKAGE.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if isinstance(node, ast.Attribute) and node.attr == "samples"
    ]
    assert offences == [], f"the linguistic lane touched audio samples: {offences}"


# =====================================================================================
# 6 · invariant 22 — numbers crossing a representation boundary
# =====================================================================================


def test_every_numeric_marker_carries_a_matching_render() -> None:
    """Invariant 22, transposed: *"no numeric slot value is spoken without a
    matching ``inline`` render on the same ``work_id``"*.

    The aggregate is the boundary this lane's numbers cross, so every numeric
    marker in it is paired with its rendered atom on the same section.
    """
    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    lane, feed = build_lane()
    scheduler.register(spec(), lane)
    feed.pending.append(turn(*("bir",) * 4))
    pump(scheduler, clock)

    section = scheduler.observer_state().linguistic_markers[f"{SECTION_MARKER_PREFIX}oyku"]
    assert isinstance(section, dict)
    numeric = {
        key: value
        for key, value in section.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    assert numeric, "the section aggregate carried no measurement at all"
    for key in numeric:
        assert f"{key}_render" in section, f"{key} crossed the boundary with no render"
        assert isinstance(section[f"{key}_render"], str)


def test_no_render_groups_its_digits_and_the_unit_is_one_atom() -> None:
    """``useGrouping:false``, and number + unit as one non-breaking atom."""
    assert render_measure(Decimal("1500"), "ms") == f"1500{NBSP}ms"
    assert render_measure(Decimal("2.500"), None) == "2.500"
    assert "," not in render_measure(Decimal("12345.6"), "syl/s")
    assert " " not in render_measure(Decimal("12345.6"), "syl/s")


def test_the_render_agrees_with_the_repositorys_one_rendering() -> None:
    """One rendering of a clinical quantity, not two.

    The lane package may not import ``intake_platform.llm`` — that import pulls
    an HTTP client into a package invariant 13 says has no network capability —
    so agreement is asserted here instead, and a drift breaks this test rather
    than surfacing as two different numbers on a clinician's screen.
    """
    for raw in ("0", "1", "1500", "12345.6", "0.001", "2.500"):
        value = Decimal(raw)
        assert render_measure(value, None) == render_quantity(value)


def test_prosody_statistics_are_deterministic_and_threshold_free() -> None:
    """The same words with the same timestamps give the same numbers, always.

    No pause threshold is invented: ``pause_ratio`` is inter-word gap time over
    the turn's span, which needs no cut-off — and a cut-off nobody has supplied
    is exactly what HUMAN_BLOCKERS rule 1 forbids.
    """
    clock = FakeClock()
    results = []
    for _ in range(3):
        scheduler, _probe = build_scheduler(clock=clock)
        lane, feed = build_lane()
        scheduler.register(spec(), lane)
        feed.pending.append(turn("bir", "iki", "uc", word_ms=200.0, gap_ms=100.0))
        pump(scheduler, clock)
        results.append(scheduler.observer_state().linguistic_markers)
    assert results[0] == results[1] == results[2]

    section = results[0][f"{SECTION_MARKER_PREFIX}oyku"]
    assert isinstance(section, dict)
    # three 200 ms words with two 100 ms gaps: span 800 ms, gaps 200 ms.
    assert section["span_ms"] == 800.0
    assert section["pause_ratio"] == 0.25


def test_turkish_syllables_are_counted_by_vowel() -> None:
    """Every Turkish syllable carries exactly one vowel — orthography, not a
    clinical judgement, and the only thing ``syllables/s`` needs."""
    assert syllables_tr("bir") == 1
    assert syllables_tr("sentetik") == 3
    assert syllables_tr("ığdır") == 2
    assert syllables_tr("") == 0


def test_tokenisation_is_turkish_lowercase_and_punctuation_free() -> None:
    """``I``/``İ`` do not lowercase the way Python's default does, and a lexicon
    that missed that would silently never match a capitalised utterance."""
    assert tokenize_tr("İyi, IYI. iyi!") == ("iyi", "ıyı", "iyi")
    assert tokenize_tr("İYİ") == ("iyi",)
    assert tokenize_tr("  ") == ()


# =====================================================================================
# 7 · the lane inside INT-110's framework — invariants 11, 3 and KVKK-6
# =====================================================================================


def test_the_lane_satisfies_the_observer_protocol_unchanged() -> None:
    lane, _feed = build_lane()
    assert isinstance(lane, Observer)
    assert lane.lane is Lane.LINGUISTIC
    hints = inspect.get_annotations(LinguisticLane.observe, eval_str=True)
    assert hints["return"] is LaneObservation


def test_the_lane_manifest_carries_its_module_intended_purpose() -> None:
    """Invariant 29: the string is regulatory text for the technical file, so
    it is the files/03 §4.7.1 M2 statement verbatim, not a paraphrase."""
    spec = linguistic_lane_spec()
    assert spec.lane is Lane.LINGUISTIC
    assert spec.intended_purpose == (
        "to route deterministic safety signposting, and to schedule validated instruments"
    )
    assert spec.budget.window_ms <= 60_000.0


def test_the_lane_runs_only_with_the_declared_consent_purpose() -> None:
    """KVKK-6: ``lane:linguistic`` is one of the two purposes files/06 §2
    declares, so this lane resolves where ``asr_quality`` and ``engagement``
    cannot (HB-L23)."""
    clock = FakeClock()
    scheduler, probe = build_scheduler(clock=clock, granted={})
    lane, _feed = build_lane()
    assert scheduler.register(spec(), lane) is LaneAdmission.REFUSED_CONSENT_NOT_GRANTED

    granting, probe = build_scheduler(clock=clock)
    assert granting.register(spec(), lane) is LaneAdmission.ADMITTED
    assert probe.reads == ["lane:linguistic"]


def test_withdrawing_the_linguistic_consent_stops_the_lane_and_zeroizes() -> None:
    """files/06 §2.2 at the lane boundary: the scope is re-read every window."""
    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    lane, feed = build_lane()
    scheduler.register(spec(), lane)
    offered = frames(4)
    for frame in offered:
        scheduler.offer(frame)

    stopped = scheduler.withdraw("lane:linguistic")

    assert stopped == (Lane.LINGUISTIC,)
    assert scheduler.lanes == frozenset()
    assert scheduler.retained_bytes() == 0
    assert scheduler.drops.count(lane=Lane.LINGUISTIC, reason=DropReason.CONSENT_WITHDRAWN) == 4
    assert clock.run(scheduler.pump()) == ()
    assert feed.takes == 0, "a withdrawn lane must not read the transcript"
    for frame in offered:
        assert not any(frame.samples)


def test_ending_the_session_zeroizes_the_lanes_window() -> None:
    """Invariant 3: the buffer the framework fills for this lane is zeroed on
    the trigger, even though the lane itself never reads a sample."""
    clock = FakeClock()
    scheduler, _probe = build_scheduler(clock=clock)
    lane, _feed = build_lane()
    scheduler.register(spec(), lane)
    offered = frames(4)
    for frame in offered:
        scheduler.offer(frame)

    assert scheduler.end_session() == 4
    assert scheduler.retained_bytes() == 0
    for frame in offered:
        assert not any(frame.samples)
    assert ZeroizeTrigger.SESSION_END in set(ZeroizeTrigger)


def test_a_real_turn_costs_the_same_with_the_linguistic_lane_running() -> None:
    """Invariant 11's *"never on the speech critical path"*, for this lane.

    INT-110 proved it for a lane stalled 30 s; this proves the property was not
    bought by the lane doing nothing — the real lane, with a real transcript
    feed, costs the turn exactly nothing.
    """
    baseline_clock = FakeClock()
    baseline = build_session(baseline_clock, steps=[scripted_step()])
    without = float(baseline_clock.run(baseline.take_turn("iki gündür ağrıyor")).elapsed_ms)

    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    scheduler, _probe = build_scheduler(clock=clock)
    lane, feed = build_lane(
        lexicons=LinguisticLexicons(
            crisis=synthetic_crisis_lexicon(), markers=synthetic_marker_lexicon()
        )
    )
    scheduler.register(spec(), lane)

    async def scenario() -> float:
        async def pump_forever() -> None:
            while True:
                await scheduler.pump()
                await clock.sleep(0.005)

        pump = asyncio.ensure_future(pump_forever())
        for frame in frames(8):
            scheduler.offer(frame)
        feed.pending.append(turn("sentetik", "belirtec"))
        await asyncio.sleep(0)
        outcome = await session.take_turn("iki gündür ağrıyor")
        pump.cancel()
        return float(outcome.elapsed_ms)

    with_lane = float(clock.run(scenario()))
    assert without > 0.0
    assert with_lane == without


def test_the_state_builder_still_refuses_an_interaction_field_from_this_lane() -> None:
    """The negative control on the lane's own module boundary (invariant 22).

    ``linguistic`` is M2. If a future edit made it emit an ``InteractionState``
    field, ``ObserverStateBuilder`` refuses and the scheduler disables the lane
    — the framework's guarantee, re-asserted against this lane by name.
    """
    builder = ObserverStateBuilder(session_ref=SESSION_REF)
    builder.apply(Lane.LINGUISTIC, LaneObservation(confidence=1.0, markers={"words": 1}))
    assert builder.state().linguistic_markers == {"words": 1}

    with pytest.raises(ObserverStateRefusedError, match="M1"):
        builder.apply(
            Lane.LINGUISTIC,
            LaneObservation(confidence=1.0, interaction=InteractionDelta(break_offer=True)),
        )


# =====================================================================================
# 8 · the remaining refusals, each with its own control
# =====================================================================================


def test_a_phrase_pasted_into_one_token_is_refused() -> None:
    """The token contract, enforced at authoring time.

    ``("sentetik tetik",)`` looks like a two-word phrase and would match as a
    substring of nothing at all — or, with a sloppier matcher, of any word
    containing it. An entry whose tokens are not what ``tokenize_tr`` produces
    does not construct.
    """
    with pytest.raises(ValidationError, match="normalised Turkish token"):
        LexiconEntry(
            entry_id="sentetik.kriz.03",
            tokens=("sentetik tetik",),
            signoff_ref="sentetik-imza-05",
        )
    with pytest.raises(ValidationError, match="normalised Turkish token"):
        LexiconEntry(
            entry_id="sentetik.kriz.04", tokens=("Sentetik",), signoff_ref="sentetik-imza-06"
        )


def test_an_authored_lexicon_may_not_also_carry_a_blocker() -> None:
    """The two states stay mutually exclusive from both directions."""
    note = UnauthoredNote(blocker_ref="HB-C8", refusal_code=RefusalCode.CRISIS_LEXICON_UNAUTHORED)
    with pytest.raises(ValidationError, match="no blocker"):
        Lexicon(
            ref="lexicon.sentetik.karisik",
            status=LexiconStatus.AUTHORED,
            entries=(SYNTHETIC_CRISIS_ENTRY,),
            unauthored=note,
        )
    with pytest.raises(ValidationError, match="must name the blocker"):
        Lexicon(ref="lexicon.sentetik.sessiz", status=LexiconStatus.UNAUTHORED)


def test_a_refusal_without_a_code_cannot_be_raised() -> None:
    """A refusal nobody can act on is the failure this whole issue is about."""
    with pytest.raises(ValueError, match="no code"):
        LaneRefusal("something went wrong")


def test_a_word_that_ends_before_it_starts_is_refused() -> None:
    """Prosody is arithmetic on timestamps, so the timestamps must be ordered."""
    with pytest.raises(ValidationError, match="cannot end before it starts"):
        TranscriptWord(text="sentetik", start_ms=200.0, end_ms=100.0)


def test_a_turn_with_no_words_counts_as_a_turn_and_measures_nothing() -> None:
    """A silent turn is still a turn. It moves no timing total, because there
    is no timestamp to move one with — and inventing a zero-length span would
    make ``pause_ratio`` a number nobody measured."""
    totals = ProsodyTotals()
    totals.add_turn(TranscriptTurn(turn_ref="sentetik-tur-09", section_ref="oyku"))

    names = {measurement.name for measurement in totals.measurements()}
    assert totals.turns == 1
    assert totals.words == 0
    assert "pause_ratio" not in names, "a ratio over a zero span is undefined, not zero"
    assert "speech_rate_syl_per_s" not in names
