"""INT-101 — session budgets and cost metering per component/profile.

Acceptance (docs/backlog/issues.yaml, verbatim): *"token/char/audio-second
budgets enforced; cost.per_session emitted; exhaustion degrades gracefully"*.
sec_row: `llm-boundary` — files/10 §5 LLM10 *"unbounded consumption: per-session
token/char/audio budgets, max turns, circuit breakers per vendor, cost alerts,
queue backpressure"*.

The suite is built around the sentence the acceptance leaves ambiguous. A
"budget" is three different objects and they fail in three different
directions:

* a **cap** refuses work — and a cap that fires mid-intake abandons a patient;
* a **target** refuses nothing and raises an alert;
* an **accounting** record refuses nothing and reports.

§1 pins which kind each component gets and why, §2 proves the refusing kind
fails in the direction that keeps the conversation alive, §3 that the ledger
holds nothing a person could be recovered from, §4 that none of it sits on the
speech critical path, and §5 that no price was invented to make
``cost.per_session`` a number.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from pathlib import Path
from typing import Any

import pytest
import test_typed_parity as parity
from intake_platform.slo import PHI_RISK_LABEL_NAMES, MetricDef, load_metrics_catalog
from intake_voice_runtime.composition import (
    build_residency_tr_session,
    build_typed_session,
)
from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall
from intake_voice_runtime.metering import (
    UNIT_OF,
    AdmissionReason,
    BudgetKind,
    ChargeClass,
    CostNotPriced,
    ElectiveWorkRefused,
    MeteredComponent,
    MeteredExtractionGateway,
    MeteredSpeechSynthesizer,
    MeterUnit,
    PriceBook,
    SessionBudget,
    SessionLedger,
    SessionMeter,
    TurnLabels,
    Unpriced,
    budget_for,
    priced_cost,
    published_budgets,
)
from intake_voice_runtime.metrics import VOICE_TTS_CHARS
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.clips import ClipCatalogue, ClipRef
from protocols.dsl import clip_text_hash
from pydantic import ValidationError
from talker_harness import (
    VOICE_ID,
    FakeClock,
    RecordedClipStore,
    RecordingSynthesizer,
    StalledBackend,
    build_session,
    scripted_step,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_ID = "11111111-2222-4333-8444-555555555555"


def _catalogued(name: str) -> MetricDef:
    catalog = load_metrics_catalog(REPO_ROOT / "observability" / "metrics_catalog.yaml")
    return next(metric for metric in catalog.metrics if metric.name == name)


def _histogram_sum(histogram: object, labels: dict[str, str]) -> float:
    child = histogram.labels(**labels)  # type: ignore[attr-defined]
    return float(child._sum.get())  # type: ignore[attr-defined]


def _labels() -> TurnLabels:
    return TurnLabels(tenant="t-1", profile=VoiceProfile.RESIDENCY_TR, branch="genel")


def _capped(limit: float | None) -> dict[MeteredComponent, SessionBudget]:
    """A policy whose extraction cap is declared — a *test* fixture.

    Declaring a limit here is not the product asserting one: the published
    declaration is checked in §1 and ships every limit unset. What this policy
    exists for is to exercise the enforcement path that a declared limit would
    take, which is otherwise unreachable while HB (the open blocker) stands.
    """
    published = dict(published_budgets())
    extraction = published[MeteredComponent.LLM_EXTRACTION]
    published[MeteredComponent.LLM_EXTRACTION] = SessionBudget(
        component=extraction.component,
        unit=extraction.unit,
        kind=extraction.kind,
        limit=limit,
        source="tests/voice/test_budgets.py fixture",
        open_reason=None if limit is not None else extraction.open_reason,
    )
    return published


# --- §1 · three kinds, one per component, each saying why ---------------------------


def test_every_metered_component_declares_exactly_one_unit() -> None:
    assert set(UNIT_OF) == set(MeteredComponent)
    assert set(UNIT_OF.values()) == set(MeterUnit)


def test_the_extraction_budget_is_a_cap() -> None:
    """Backend Work is off the speech path (inv. 9), so a refusal is survivable."""
    assert budget_for(MeteredComponent.LLM_EXTRACTION).kind is BudgetKind.CAP


def test_the_tts_budget_is_a_target_not_a_cap() -> None:
    """Invariant 10 speaks `text_tr` verbatim; a cap would silence a sentence."""
    assert budget_for(MeteredComponent.TTS).kind is BudgetKind.TARGET


def test_the_asr_budget_is_accounting_only() -> None:
    """The only cap that bounds audio seconds is a session-length cap, and
    that is HB-C5 — a clinical decision about what gets cut."""
    assert budget_for(MeteredComponent.ASR).kind is BudgetKind.ACCOUNTING


def test_no_budget_limit_is_published_and_none_is_invented() -> None:
    for component, budget in published_budgets().items():
        assert budget.limit is None, (
            f"{component} ships a limit no file publishes — a plausible number is "
            "worse than a missing one (files/HUMAN_BLOCKERS.md rule 1)"
        )
        if budget.kind is not BudgetKind.ACCOUNTING:
            assert budget.open_reason, f"{component} must say why its limit is unset"


def test_a_cap_with_no_limit_must_say_why() -> None:
    with pytest.raises(ValidationError):
        SessionBudget(
            component=MeteredComponent.LLM_EXTRACTION,
            unit=MeterUnit.TOKENS,
            kind=BudgetKind.CAP,
            limit=None,
            source="test",
            open_reason=None,
        )


def test_an_accounting_budget_may_not_carry_a_limit() -> None:
    with pytest.raises(ValidationError):
        SessionBudget(
            component=MeteredComponent.ASR,
            unit=MeterUnit.AUDIO_SECONDS,
            kind=BudgetKind.ACCOUNTING,
            limit=1.0,
            source="test",
            open_reason=None,
        )


def test_a_budget_whose_unit_is_not_its_components_is_refused() -> None:
    with pytest.raises(ValidationError):
        SessionBudget(
            component=MeteredComponent.TTS,
            unit=MeterUnit.TOKENS,
            kind=BudgetKind.TARGET,
            limit=None,
            source="test",
            open_reason="test",
        )


# --- §2 · enforcement: fails closed on elective, never on obligatory ----------------


def test_an_undeclared_cap_refuses_elective_work() -> None:
    """Rule 2: build the mechanism, wire the gate, make it fail closed.

    With no limit declared nobody can know that elective spend is affordable,
    so it is not spent. That is the closed direction, and it costs a patient
    nothing.
    """
    ledger = SessionLedger(SESSION_ID)
    admission = ledger.admits(MeteredComponent.LLM_EXTRACTION, ChargeClass.ELECTIVE)
    assert not admission.admitted
    assert admission.reason is AdmissionReason.CAP_UNDECLARED


def test_an_undeclared_cap_never_refuses_obligatory_work() -> None:
    ledger = SessionLedger(SESSION_ID)
    admission = ledger.admits(MeteredComponent.LLM_EXTRACTION, ChargeClass.OBLIGATORY)
    assert admission.admitted
    assert admission.reason is AdmissionReason.OBLIGATORY


def test_a_declared_cap_admits_elective_work_within_it() -> None:
    ledger = SessionLedger(SESSION_ID, budgets=_capped(100.0))
    ledger.record(MeteredComponent.LLM_EXTRACTION, 40.0)
    admission = ledger.admits(MeteredComponent.LLM_EXTRACTION, ChargeClass.ELECTIVE)
    assert admission.admitted
    assert admission.reason is AdmissionReason.WITHIN_CAP


def test_a_declared_cap_refuses_elective_work_once_exhausted() -> None:
    ledger = SessionLedger(SESSION_ID, budgets=_capped(100.0))
    ledger.record(MeteredComponent.LLM_EXTRACTION, 100.0)
    admission = ledger.admits(MeteredComponent.LLM_EXTRACTION, ChargeClass.ELECTIVE)
    assert not admission.admitted
    assert admission.reason is AdmissionReason.CAP_EXHAUSTED


def test_an_exhausted_cap_still_admits_obligatory_work() -> None:
    """*"Exhaustion degrades gracefully"* — the conversation stays alive.

    A patient's answer that is never extracted is a red-flag phrase nobody
    evaluated (the failure HB-C21 is about), so the obligatory lane is never
    refused. What exhaustion costs is the elective lane, and the note records
    the gap.
    """
    ledger = SessionLedger(SESSION_ID, budgets=_capped(10.0))
    ledger.record(MeteredComponent.LLM_EXTRACTION, 10_000.0)
    admission = ledger.admits(MeteredComponent.LLM_EXTRACTION, ChargeClass.OBLIGATORY)
    assert admission.admitted
    assert ledger.over_budget(MeteredComponent.LLM_EXTRACTION)


def test_a_target_component_refuses_nothing_and_still_reports_the_overrun() -> None:
    budgets = dict(published_budgets())
    budgets[MeteredComponent.TTS] = SessionBudget(
        component=MeteredComponent.TTS,
        unit=MeterUnit.CHARS,
        kind=BudgetKind.TARGET,
        limit=50.0,
        source="tests/voice/test_budgets.py fixture",
        open_reason=None,
    )
    ledger = SessionLedger(SESSION_ID, budgets=budgets)
    ledger.record(MeteredComponent.TTS, 500.0)

    for charge_class in ChargeClass:
        assert ledger.admits(MeteredComponent.TTS, charge_class).admitted
    assert ledger.admits(MeteredComponent.TTS, ChargeClass.ELECTIVE).reason is (
        AdmissionReason.NOT_CAPPED
    )
    assert ledger.over_budget(MeteredComponent.TTS)


def test_an_accounting_component_refuses_nothing_and_has_nothing_to_overrun() -> None:
    ledger = SessionLedger(SESSION_ID)
    ledger.record(MeteredComponent.ASR, 3_600.0)
    for charge_class in ChargeClass:
        assert ledger.admits(MeteredComponent.ASR, charge_class).admitted
    assert not ledger.over_budget(MeteredComponent.ASR)
    assert ledger.total(MeteredComponent.ASR) == 3_600.0


def test_a_negative_quantity_is_refused_rather_than_netted_off() -> None:
    ledger = SessionLedger(SESSION_ID)
    with pytest.raises(ValueError):
        ledger.record(MeteredComponent.TTS, -1.0)


# --- §3 · the ledger holds no audio and no identifier (inv. 3, inv. 6) --------------


def test_the_ledger_keeps_running_totals_not_a_sequence_of_charges() -> None:
    """Invariant 3 reaches further than bytes.

    A per-utterance list of audio durations is a reconstruction of the
    turn-taking timeline of a recording nobody kept. The ledger therefore holds
    a scalar per component and a count, and has no container a charge history
    could occupy.
    """
    ledger = SessionLedger(SESSION_ID)
    for seconds in (1.5, 2.5, 9.0):
        ledger.record(MeteredComponent.ASR, seconds)

    assert ledger.total(MeteredComponent.ASR) == 13.0
    assert ledger.charges(MeteredComponent.ASR) == 3

    # The attribute set is pinned: a field added to hold per-charge data fails
    # here rather than passing review as "just for debugging".
    assert set(vars(ledger)) == {
        "_session_key",
        "_budgets",
        "_totals",
        "_charges",
        "_refusals",
        # INT-439: a reference to the deployment's monthly spend ledger, which
        # holds one integer total per (month, charge class) — never a charge list.
        "_spend",
    }
    for name, value in vars(ledger).items():
        assert not isinstance(value, list | tuple | set), (
            f"SessionLedger.{name} is a sequence — a charge history is the turn-taking "
            "timeline of a recording nobody kept (CLAUDE.md invariant 3)"
        )
    for name in ("_totals", "_charges", "_refusals"):
        assert all(isinstance(item, int | float) for item in vars(ledger)[name].values())


def test_the_ledger_never_retains_the_session_id() -> None:
    ledger = SessionLedger(SESSION_ID)
    assert ledger.session_key == hashlib.sha256(SESSION_ID.encode("utf-8")).hexdigest()
    assert SESSION_ID not in repr(ledger)
    assert SESSION_ID not in str(vars(ledger))


def test_the_turn_labels_are_free_of_every_phi_risk_name() -> None:
    labels = _labels().as_dict()
    assert set(labels) == {"tenant", "profile", "branch", "vendor"}
    assert not set(labels) & PHI_RISK_LABEL_NAMES
    assert labels["vendor"] == "self-hosted", (
        "there is no vendor under CLAUDE.md invariant 19; the group B label keeps "
        "its name and states the fact"
    )


def test_the_session_key_is_never_a_metric_label() -> None:
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels())
    assert meter.ledger.session_key not in meter.labels.as_dict().values()


# --- §4 · nothing here sits on the speech critical path (inv. 9) --------------------


def test_no_metering_entry_point_is_awaitable() -> None:
    for owner in (SessionLedger, SessionMeter, MeteredSpeechSynthesizer):
        for name, value in vars(owner).items():
            if name.startswith("_") or not callable(value):
                continue
            assert not inspect.iscoroutinefunction(value), (
                f"{owner.__name__}.{name} is a coroutine — the Talker would await "
                "an accounting write (CLAUDE.md invariant 9)"
            )


def _turn_latency(*, metered: bool, stall_s: float) -> float:
    clock = FakeClock()
    backend = StalledBackend(clock=clock, stall_s=stall_s)
    synthesizer: Any = RecordingSynthesizer()
    if metered:
        synthesizer = MeteredSpeechSynthesizer(
            inner=synthesizer,
            meter=SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels()),
        )
    session = build_session(
        clock,
        steps=[scripted_step()],
        backend=backend,
        synthesizer=synthesizer,
        clip_store=RecordedClipStore(),
    )

    async def scenario() -> float:
        work = asyncio.ensure_future(backend.work())
        outcome = await session.take_turn("iki gündür ağrıyor")
        work.cancel()
        return float(outcome.elapsed_ms)

    return float(clock.run(scenario()))


def test_a_metered_turn_takes_exactly_as_long_as_an_unmetered_one() -> None:
    assert _turn_latency(metered=True, stall_s=10.0) == _turn_latency(metered=False, stall_s=10.0)


def test_metering_does_not_reintroduce_a_wait_on_backend_work() -> None:
    assert _turn_latency(metered=True, stall_s=10.0) == _turn_latency(
        metered=True, stall_s=10_000.0
    )


# --- §5 · cost is not priced, and no price was invented ----------------------------


def test_the_shipped_price_book_is_empty() -> None:
    assert Unpriced.rates == {}


def test_pricing_an_unpriced_component_refuses() -> None:
    ledger = SessionLedger(SESSION_ID)
    ledger.record(MeteredComponent.TTS, 120.0)
    with pytest.raises(CostNotPriced):
        priced_cost(ledger, Unpriced)


def test_a_supplied_price_book_prices_what_it_was_given() -> None:
    ledger = SessionLedger(SESSION_ID)
    ledger.record(MeteredComponent.TTS, 100.0)
    ledger.record(MeteredComponent.LLM_EXTRACTION, 10.0)
    ledger.record(MeteredComponent.ASR, 2.0)
    book = PriceBook(
        rates={
            MeteredComponent.TTS: 0.5,
            MeteredComponent.LLM_EXTRACTION: 2.0,
            MeteredComponent.ASR: 1.0,
        },
        source="tests/voice/test_budgets.py fixture",
    )
    assert priced_cost(ledger, book) == {
        MeteredComponent.TTS: 50.0,
        MeteredComponent.LLM_EXTRACTION: 20.0,
        MeteredComponent.ASR: 2.0,
    }


def test_a_price_book_may_not_carry_a_negative_rate() -> None:
    with pytest.raises(ValidationError):
        PriceBook(rates={MeteredComponent.TTS: -1.0}, source="test")


def test_cost_per_session_is_still_planned_in_the_catalogue() -> None:
    """Nothing emits it, so it may not claim to be live.

    ``cost.per_session`` is denominated in USD (files/08 §4 J). Under
    invariant 19 every model is self-hosted, so there is no per-token price to
    read off an invoice, and no GPU-hour rate exists either — HB-I4 and HB-I5
    record that there is neither a card nor a capacity contract. A rate
    invented here would be a plausible number with no diff that makes it look
    wrong.
    """
    entry = _catalogued("cost_per_session")
    assert entry.status == "planned"
    assert entry.unit == "USD"


def test_voice_tts_chars_is_live_in_the_catalogue() -> None:
    entry = _catalogued("voice_tts_chars")
    assert entry.status == "live"
    assert sorted(entry.labels) == ["branch", "profile", "tenant", "vendor"]


def test_backend_extraction_tokens_have_no_catalogued_series() -> None:
    """The finding, pinned so it cannot be quietly closed by inventing an id.

    files/08 §4 group B's ``voice.talker_tokens`` is *the Talker's* LLM, per
    turn. Backend `extract_slots` tokens are group J's *"tokens/chars/
    audio-seconds by vendor"*, which §4 states **without an id** — and the
    catalogue's own trailing comment already records that row as id-less. So
    the ledger counts them and no series carries them.
    """
    catalog = load_metrics_catalog(REPO_ROOT / "observability" / "metrics_catalog.yaml")
    assert _catalogued("voice_talker_tokens").status == "planned"
    assert not [m for m in catalog.metrics if "extraction_token" in m.name]
    assert _catalogued("voice_stt_audio_s").status == "planned"


# --- §6 · the metered adapters -----------------------------------------------------


class _RecordingGateway:
    """A recorded extraction lane. Nothing here opens a socket."""

    def __init__(self, completion: Completion) -> None:
        self.completion = completion
        self.calls = 0

    def complete(self, call: ExtractionCall) -> Completion:
        self.calls += 1
        return self.completion


def _call() -> ExtractionCall:
    from intake_voice_runtime.extraction.boundary import wrap_patient_data

    return ExtractionCall(
        instructions="yalnızca verilen metinden çıkar",
        data=wrap_patient_data("iki gündür başım ağrıyor"),
        json_schema={"type": "object", "properties": {}},
    )


def test_the_metered_synthesizer_charges_the_characters_it_synthesised() -> None:
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels())
    synthesizer = MeteredSpeechSynthesizer(inner=RecordingSynthesizer(), meter=meter)

    text = "Nereniz ağrıyor?"
    synthesizer.synthesize(text, "residency-tr-01")

    assert meter.ledger.total(MeteredComponent.TTS) == float(len(text))
    assert meter.ledger.charges(MeteredComponent.TTS) == 1


def test_the_metered_synthesizer_observes_the_catalogued_histogram() -> None:
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels())
    synthesizer = MeteredSpeechSynthesizer(inner=RecordingSynthesizer(), meter=meter)
    labels = meter.labels.as_dict()

    before = _histogram_sum(VOICE_TTS_CHARS, labels)
    synthesizer.synthesize("Merhaba", "residency-tr-01")
    after = _histogram_sum(VOICE_TTS_CHARS, labels)

    assert after - before == 7.0


def test_the_metered_synthesizer_never_refuses_to_speak() -> None:
    """A target overrun is an alert, not silence (invariant 10)."""
    budgets = dict(published_budgets())
    budgets[MeteredComponent.TTS] = SessionBudget(
        component=MeteredComponent.TTS,
        unit=MeterUnit.CHARS,
        kind=BudgetKind.TARGET,
        limit=1.0,
        source="tests/voice/test_budgets.py fixture",
        open_reason=None,
    )
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID, budgets=budgets), labels=_labels())
    synthesizer = MeteredSpeechSynthesizer(inner=RecordingSynthesizer(), meter=meter)

    for _ in range(5):
        assert synthesizer.synthesize("Nereniz ağrıyor?", "residency-tr-01")
    assert meter.ledger.over_budget(MeteredComponent.TTS)


def test_a_clip_cache_hit_costs_no_tts_characters() -> None:
    """Invariant 10's first branch is free; only the second one synthesises.

    The negative control is the same turn with an empty catalogue: it *does*
    charge, so the zero above is a cache hit rather than a meter that never
    fires.
    """
    text = "Nereniz ağrıyor?"

    def run(*, cached: bool) -> tuple[SessionMeter, RecordedClipStore]:
        clock = FakeClock()
        meter = SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels())
        store = RecordedClipStore()
        catalogue = (
            ClipCatalogue(
                voice=VOICE_ID,
                resolved_protocol_hash="a" * 64,
                refs={
                    clip_text_hash(text): ClipRef(
                        text_hash=clip_text_hash(text),
                        clip_id="clip-s1",
                        text_tr=text,
                        scripted=True,
                    )
                },
            )
            if cached
            else ClipCatalogue.empty(VOICE_ID)
        )
        session = build_session(
            clock,
            steps=[scripted_step(text_tr=text)],
            synthesizer=MeteredSpeechSynthesizer(inner=RecordingSynthesizer(), meter=meter),
            clip_store=store,
            catalogue=catalogue,
        )

        async def scenario() -> None:
            await session.take_turn("iki gündür ağrıyor")

        clock.run(scenario())
        return meter, store

    hit, hit_store = run(cached=True)
    miss, miss_store = run(cached=False)

    assert hit_store.served == ["clip-s1"]
    assert hit.ledger.total(MeteredComponent.TTS) == 0.0
    assert miss_store.served == []
    assert miss.ledger.total(MeteredComponent.TTS) == float(len(text))


def test_the_metered_gateway_charges_the_tokens_the_endpoint_reported() -> None:
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels())
    inner = _RecordingGateway(Completion(text="{}", input_tokens=120, output_tokens=30))
    gateway = MeteredExtractionGateway(inner=inner, meter=meter)

    gateway.complete(_call())

    assert meter.ledger.total(MeteredComponent.LLM_EXTRACTION) == 150.0


def test_an_endpoint_that_reported_no_usage_charges_nothing_rather_than_an_estimate() -> None:
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels())
    gateway = MeteredExtractionGateway(inner=_RecordingGateway(Completion(text="{}")), meter=meter)

    gateway.complete(_call())

    assert meter.ledger.total(MeteredComponent.LLM_EXTRACTION) == 0.0
    assert meter.ledger.charges(MeteredComponent.LLM_EXTRACTION) == 1


def test_the_metered_gateway_refuses_an_elective_call_the_cap_cannot_afford() -> None:
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID, budgets=_capped(10.0)), labels=_labels())
    meter.ledger.record(MeteredComponent.LLM_EXTRACTION, 10.0)
    inner = _RecordingGateway(Completion(text="{}", input_tokens=1, output_tokens=1))
    gateway = MeteredExtractionGateway(inner=inner, meter=meter, charge_class=ChargeClass.ELECTIVE)

    with pytest.raises(ElectiveWorkRefused):
        gateway.complete(_call())
    assert inner.calls == 0, "the refusal must land before the endpoint is dialled"


def test_the_metered_gateway_never_refuses_an_obligatory_call() -> None:
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID, budgets=_capped(10.0)), labels=_labels())
    meter.ledger.record(MeteredComponent.LLM_EXTRACTION, 10_000.0)
    inner = _RecordingGateway(Completion(text="{}", input_tokens=5, output_tokens=5))
    gateway = MeteredExtractionGateway(inner=inner, meter=meter)

    assert gateway.complete(_call()).text == "{}"
    assert inner.calls == 1


def test_an_undeclared_cap_refuses_the_elective_lane_outright() -> None:
    """The published policy declares no limit, so elective work never runs."""
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels())
    inner = _RecordingGateway(Completion(text="{}"))
    gateway = MeteredExtractionGateway(inner=inner, meter=meter, charge_class=ChargeClass.ELECTIVE)

    with pytest.raises(ElectiveWorkRefused):
        gateway.complete(_call())


def test_the_meter_refuses_to_derive_audio_seconds_from_bytes() -> None:
    """No ``charge_audio_bytes``: a duration inferred from a guessed sample
    format is an invented number, and the ASR seam declares no format."""
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels())
    assert not hasattr(meter, "charge_audio_bytes")
    meter.charge_audio_seconds(4.5)
    assert meter.ledger.total(MeteredComponent.ASR) == 4.5


# --- §7 · per profile, through the composition root ---------------------------------
#
# The brief for this issue put it in one sentence: a budget that assumes a
# voice turn will be wrong for half the sessions. INT-096 established that
# there are exactly two profiles and that `typed` awaits no playback — so a
# typed session's character axis is structurally zero, and only a differential
# run against the same protocol, the same answers and the same gateway shows
# that the zero is the profile rather than a meter that never fired.


def _meter() -> SessionMeter:
    return SessionMeter(ledger=SessionLedger(parity.SESSION), labels=_labels())


def _drive(stack: Any, clock: FakeClock) -> None:
    parity.drive(stack, clock, parity.SCRIPT)


def test_a_voice_session_spends_characters_and_a_typed_session_spends_none() -> None:
    voice_meter, typed_meter = _meter(), _meter()

    voice_clock = FakeClock()
    voice = build_residency_tr_session(
        protocol=parity._protocol(),
        reference_time=parity.NOW,
        session_id=parity.SESSION,
        voice_id=VOICE_ID,
        protocol_hash=parity.HASH,
        clock=voice_clock,
        gateway=parity.ScriptedGateway(parity.ANSWERS),
        synthesizer=RecordingSynthesizer(),
        clip_store=RecordedClipStore(),
        sink=parity.RecordingSink(clock=voice_clock),
        memory=parity.InMemoryPatientMemory(),
        tenant_id=parity.TENANT,
        screen=parity.RecordingScreen(),
        meter=voice_meter,
    )
    _drive(voice, voice_clock)

    typed_clock = FakeClock()
    typed = build_typed_session(
        protocol=parity._protocol(),
        reference_time=parity.NOW,
        session_id=parity.SESSION,
        protocol_hash=parity.HASH,
        clock=typed_clock,
        gateway=parity.ScriptedGateway(parity.ANSWERS),
        memory=parity.InMemoryPatientMemory(),
        tenant_id=parity.TENANT,
        screen=parity.RecordingScreen(),
        meter=typed_meter,
    )
    _drive(typed, typed_clock)

    assert voice.profile is VoiceProfile.RESIDENCY_TR
    assert typed.profile is VoiceProfile.TYPED
    assert voice_meter.ledger.total(MeteredComponent.TTS) > 0.0
    assert typed_meter.ledger.total(MeteredComponent.TTS) == 0.0


def test_both_profiles_spend_the_same_tokens_on_the_same_answers() -> None:
    """The clinical work is identical, so the model axis must be too."""
    voice_meter, typed_meter = _meter(), _meter()

    voice_clock = FakeClock()
    voice = build_residency_tr_session(
        protocol=parity._protocol(),
        reference_time=parity.NOW,
        session_id=parity.SESSION,
        voice_id=VOICE_ID,
        protocol_hash=parity.HASH,
        clock=voice_clock,
        gateway=parity.ScriptedGateway(parity.ANSWERS),
        synthesizer=RecordingSynthesizer(),
        clip_store=RecordedClipStore(),
        sink=parity.RecordingSink(clock=voice_clock),
        memory=parity.InMemoryPatientMemory(),
        tenant_id=parity.TENANT,
        screen=parity.RecordingScreen(),
        meter=voice_meter,
    )
    _drive(voice, voice_clock)

    typed_clock = FakeClock()
    typed = build_typed_session(
        protocol=parity._protocol(),
        reference_time=parity.NOW,
        session_id=parity.SESSION,
        protocol_hash=parity.HASH,
        clock=typed_clock,
        gateway=parity.ScriptedGateway(parity.ANSWERS),
        memory=parity.InMemoryPatientMemory(),
        tenant_id=parity.TENANT,
        screen=parity.RecordingScreen(),
        meter=typed_meter,
    )
    _drive(typed, typed_clock)

    extraction = MeteredComponent.LLM_EXTRACTION
    assert voice_meter.ledger.total(extraction) > 0.0
    assert voice_meter.ledger.total(extraction) == typed_meter.ledger.total(extraction)


def test_a_session_composed_without_a_meter_is_unchanged() -> None:
    """The absence is visible, not a stub. Nothing is metered, nothing refused."""
    clock = FakeClock()
    stack = build_typed_session(
        protocol=parity._protocol(),
        reference_time=parity.NOW,
        session_id=parity.SESSION,
        protocol_hash=parity.HASH,
        clock=clock,
        gateway=parity.ScriptedGateway(parity.ANSWERS),
        memory=parity.InMemoryPatientMemory(),
        tenant_id=parity.TENANT,
        screen=parity.RecordingScreen(),
    )
    _drive(stack, clock)
    assert stack.meter is None


# --- §8 · the refusals and reads that have no other caller yet ----------------------


def test_a_ledger_needs_a_session_id_to_tokenise() -> None:
    with pytest.raises(ValueError, match="session id"):
        SessionLedger("")


def test_a_policy_missing_a_component_is_refused() -> None:
    partial = dict(published_budgets())
    del partial[MeteredComponent.ASR]
    with pytest.raises(ValueError, match="every component"):
        SessionLedger(SESSION_ID, budgets=partial)


def test_the_ledger_reads_back_its_policy_refusals_and_totals() -> None:
    ledger = SessionLedger(SESSION_ID)
    assert ledger.budget(MeteredComponent.TTS).kind is BudgetKind.TARGET
    assert ledger.refusals(MeteredComponent.LLM_EXTRACTION) == 0
    ledger.admits(MeteredComponent.LLM_EXTRACTION, ChargeClass.ELECTIVE)
    assert ledger.refusals(MeteredComponent.LLM_EXTRACTION) == 1
    ledger.record(MeteredComponent.TTS, 8.0)
    assert ledger.totals()[MeteredComponent.TTS] == 8.0


def test_a_negative_reported_token_count_is_refused() -> None:
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID), labels=_labels())
    with pytest.raises(ValueError, match="negative"):
        meter.charge_extraction_tokens(-1, 0)


def test_the_meter_reports_totals_and_the_components_past_a_declared_limit() -> None:
    budgets = dict(published_budgets())
    budgets[MeteredComponent.TTS] = SessionBudget(
        component=MeteredComponent.TTS,
        unit=MeterUnit.CHARS,
        kind=BudgetKind.TARGET,
        limit=2.0,
        source="tests/voice/test_budgets.py fixture",
        open_reason=None,
    )
    meter = SessionMeter(ledger=SessionLedger(SESSION_ID, budgets=budgets), labels=_labels())

    assert meter.overruns() == ()
    meter.charge_tts_chars("Merhaba")
    assert meter.totals()[MeteredComponent.TTS] == 7.0
    assert meter.overruns() == (MeteredComponent.TTS,)


def test_an_accounting_budget_states_its_source_and_needs_no_open_reason() -> None:
    asr = budget_for(MeteredComponent.ASR)
    assert asr.open_reason is None
    assert "HB-C5" in asr.source
    assert not asr.declared
