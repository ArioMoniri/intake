"""The patient interrupts by SPEAKING (INT-291).

CLAUDE.md invariant 9 gives the Talker six tools and one preemption. This
suite is about the thing that is neither: the patient starting to talk while
the agent is mid-sentence. files/02 §8.2 states the budget — *"Barge-in stop
≤ 150 ms"* — and files/08 §4 group B names the series, `voice.barge_in_stop_ms`,
which this issue moves from ``planned`` to ``live``.

**Why this is a separate path from INT-093's.** docs/evidence/INT-093.md is
explicit: ``voice.barge_in_stop_ms`` was *"deliberately NOT reused for the
stop leg: that series is the patient's barge-in, and folding a second cause
into it would make its ≤ 150 ms target unreadable for both."* So the RED path
keeps ``preempt.red_latency_ms`` and this path keeps the barge-in series.
:func:`test_the_two_stop_causes_stay_on_two_series` pins that they are two
families, not one.

**The clock model is INT-093's, unchanged.** One virtual monotonic clock
(``talker_harness.FakeClock``), shared by every participant, advancing only
when every task is parked. The whole suite runs in zero wall time and no test
sleeps. ``red_harness.MediaPlane`` is reused rather than re-doubled: its
``play`` is interruptible on that clock, so *"the playback was cut"* is
**observed** and not asserted.

**What this suite deliberately does not claim.** The stop measured here is the
server-side stop — patient-speech detection to the moment the outbound audio
path was cancelled. What the patient actually hears is bounded below by the
device's own flush of already-buffered audio, which is on-hardware evidence.
Calling this figure patient-perceived would be exactly the accuracy claim
CLAUDE.md invariant 20 forbids.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest
from intake_voice_runtime.metrics import BARGE_IN_STOP_MS, PREEMPT_RED_LATENCY_MS
from intake_voice_runtime.talker.barge_in import (
    STOP_BUDGET_MS,
    BargeInOutcome,
    BargeInPath,
    BargeInRefusal,
    SpeechOnset,
)
from red_harness import MediaPlane
from talker_harness import FakeClock

MODULE = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "voice-runtime"
    / "src"
    / "intake_voice_runtime"
    / "talker"
    / "barge_in.py"
)


def onset(at_ms: float, *, utterance_id: str = "u-1") -> SpeechOnset:
    return SpeechOnset(utterance_id=utterance_id, detected_at_ms=at_ms)


def path(clock: FakeClock, media: MediaPlane) -> BargeInPath:
    return BargeInPath(canceller=media, clock=clock)


# --- the budget comes from the blueprint, not from this file ----------------------


def test_the_stop_budget_is_the_one_files_02_states() -> None:
    """files/02 §8.2: *"Barge-in stop ≤ 150 ms."* Same number as the RED
    stop, and deliberately the same: both are "how long until the agent's
    audio is off", measured from two different causes."""
    assert STOP_BUDGET_MS == 150.0


def test_the_two_stop_causes_stay_on_two_series() -> None:
    """docs/evidence/INT-093.md's reasoning, pinned as a fact about the code."""
    assert BARGE_IN_STOP_MS is not PREEMPT_RED_LATENCY_MS
    assert BARGE_IN_STOP_MS._name != PREEMPT_RED_LATENCY_MS._name


# --- the stop -----------------------------------------------------------------------


def test_a_patient_speaking_cancels_the_outbound_audio() -> None:
    """The defect this issue exists for: before it, patient speech had no
    route to the audio path at all. Now it has exactly one."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=40.0)
    outcome = clock.run(path(clock, media).on_speech_onset(onset(0.0)))
    assert media.calls == ["cancel"]
    assert outcome.stop_ms == 40.0
    assert outcome.violations == ()


def test_the_stop_is_measured_from_DETECTION_not_from_arrival() -> None:
    """Same argument as INT-093's ``evaluated_at_ms``: stamping ``now()`` at
    the moment the runtime heard about the onset would silently discount the
    uplink hop from the very budget being policed. Fire a virtual minute in,
    and a path that measures from zero reads wrong rather than reading the
    same."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=40.0)
    controller = path(clock, media)

    async def scenario() -> BargeInOutcome:
        await clock.sleep(60.0)  # a virtual minute of conversation
        return await controller.on_speech_onset(onset(clock.now_ms()))

    outcome = clock.run(scenario())
    assert outcome.detected_at_ms == 60_000.0
    assert outcome.stop_ms == 40.0


def test_a_patient_speaking_mid_sentence_cuts_the_playback_it_found() -> None:
    """The behavioural half, observed rather than asserted: 400 virtual ms of
    agent speech, the patient starts 100 ms in, and the playback lands in
    ``interrupted`` and not in ``completed``."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=40.0, ms_per_byte=1.0)
    controller = path(clock, media)

    async def scenario() -> BargeInOutcome:
        speaking = asyncio.ensure_future(media.play(b"x" * 400, label="q1"))
        await clock.sleep(0.1)
        result = await controller.on_speech_onset(onset(clock.now_ms()))
        await speaking
        return result

    outcome = clock.run(scenario())
    assert media.interrupted == ["q1"]
    assert media.completed == []
    assert outcome.stop_ms is not None and outcome.stop_ms <= STOP_BUDGET_MS


def test_the_budget_can_be_missed_and_the_stop_still_happens() -> None:
    """A missed barge-in budget must NOT tear the session down. INT-093 raises
    on a missed RED budget because a missed RED is a safety event; a barge-in
    that stopped 40 ms late is a quality event, and raising would take the
    conversation away from the patient who just asked for it. So the violation
    is **recorded on the outcome** and the caller decides."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=190.0)
    outcome = clock.run(path(clock, media).on_speech_onset(onset(0.0)))
    assert media.calls == ["cancel"]
    assert outcome.stop_ms == 190.0
    assert outcome.violations == (BargeInRefusal.STOP_BUDGET,)


def test_a_clean_stop_records_no_violation() -> None:
    """Negative control: without this, the whole class above is satisfied by a
    path that always records a violation."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=1.0)
    assert clock.run(path(clock, media).on_speech_onset(onset(0.0))).violations == ()


def test_the_stop_at_exactly_the_budget_is_inside_it() -> None:
    """A boundary chosen by the blueprint's own ``≤``, not by an implementer."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=STOP_BUDGET_MS)
    assert clock.run(path(clock, media).on_speech_onset(onset(0.0))).violations == ()


def test_an_unreachable_media_plane_is_recorded_rather_than_raised() -> None:
    """Nothing was playing, or the plane is already torn down. The patient
    still gets the turn — the cancel had nothing to cancel."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=5.0, cancel_raises=RuntimeError("gone"))
    outcome = clock.run(path(clock, media).on_speech_onset(onset(0.0)))
    assert outcome.media_plane_unreachable is True
    assert outcome.violations == ()


# --- one utterance, one stop --------------------------------------------------------


def test_two_onsets_from_one_utterance_stop_the_audio_once() -> None:
    """A detector that reports every frame above threshold must not become a
    stream of cancels. Dedupe is by ``utterance_id``, the same content-address
    shape INT-092's Work queue uses, so a retried report is a no-op."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=10.0)
    controller = path(clock, media)

    async def scenario() -> tuple[BargeInOutcome, BargeInOutcome]:
        first = await controller.on_speech_onset(onset(0.0, utterance_id="u-7"))
        second = await controller.on_speech_onset(onset(80.0, utterance_id="u-7"))
        return first, second

    first, second = clock.run(scenario())
    assert media.calls == ["cancel"]
    assert second == first


def test_a_second_utterance_stops_the_next_clip() -> None:
    """The dedupe is per utterance, not per session — a patient interrupts
    more than once in a visit."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=10.0)
    controller = path(clock, media)

    async def scenario() -> None:
        await controller.on_speech_onset(onset(0.0, utterance_id="u-1"))
        await controller.on_speech_onset(onset(500.0, utterance_id="u-2"))

    clock.run(scenario())
    assert media.calls == ["cancel", "cancel"]


# --- RED outranks the patient's own voice, and that is deliberate --------------------


def test_a_barge_in_cannot_cut_a_red_script() -> None:
    """CLAUDE.md invariant 21: inside RED the register inverts to the bare
    imperative plural *because ambiguity is the harm*. A patient talking over
    *Tutun · Arayın · Bakmayın* must not silence the three words that tell
    them what to do. The refusal is explicit and recorded — never a silent
    drop (invariant 17)."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=10.0)
    controller = path(clock, media)
    controller.red_in_flight = True
    outcome = clock.run(controller.on_speech_onset(onset(0.0)))
    assert outcome.refused_because is BargeInRefusal.RED_IN_FLIGHT
    assert outcome.stopped_at_ms is None
    assert media.calls == []


def test_the_refusal_lifts_when_the_red_script_has_finished() -> None:
    """Negative control on the rule above: it is a gate, not a session kill."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=10.0)
    controller = path(clock, media)
    controller.red_in_flight = True
    clock.run(controller.on_speech_onset(onset(0.0, utterance_id="u-1")))
    controller.red_in_flight = False
    outcome = clock.run(controller.on_speech_onset(onset(400.0, utterance_id="u-2")))
    assert outcome.refused_because is None
    assert media.calls == ["cancel"]


# --- what this path is NOT ----------------------------------------------------------


def test_the_path_is_not_a_preemption_and_says_so_in_its_own_source() -> None:
    """CLAUDE.md invariant 9: *"only a rules-engine RED result may carry
    ``priority: preempt``"*. A barge-in is a patient-originated TRANSPORT
    event, not Backend Work, so it must not reach the Work queue, must not
    carry a Priority, and must not be reachable from a BackendResult. Asserted
    against the source the way INT-093 asserts its own non-re-sealing, because
    a type that is merely unused today is imported tomorrow.

    Docstrings are stripped first — prose about the preemption path is exactly
    what this module should contain, and only the *code* is the claim."""
    code = _code_of(MODULE)
    for forbidden in ("Priority", "BackendResult", "WorkTicket", "WorkRequest", "WorkSubmitter"):
        assert forbidden not in code, (
            f"{forbidden!r} reached the barge-in path; a patient interrupting is not "
            "Backend Work and must not be able to borrow the preemption channel"
        )


def test_the_path_holds_no_audio() -> None:
    """CLAUDE.md invariant 3. The port carries an id and a timestamp; there is
    no frames field to hold PCM in, and the canceller protocol has one member
    that takes nothing. Type-level, then confirmed on the stripped source."""
    assert set(SpeechOnset.model_fields) == {"utterance_id", "detected_at_ms"}
    code = _code_of(MODULE)
    for forbidden in ("bytes", "frames", "pcm", "PCM"):
        assert forbidden not in code, f"{forbidden!r} in the barge-in path (invariant 3)"


def test_the_onset_carries_an_id_and_never_a_transcript() -> None:
    """CLAUDE.md invariant 6: ids on a signal, never patient words. There is
    no field for a transcript, so a caller cannot put one there by accident."""
    with pytest.raises(ValueError):
        SpeechOnset.model_validate(
            {"utterance_id": "u-1", "detected_at_ms": 0.0, "transcript": "başım ağrıyor"}
        )


def test_a_negative_detection_stamp_is_refused() -> None:
    """A stamp before the session started is a caller defect, and a negative
    stop would be reported as an impossibly good one."""
    with pytest.raises(ValueError):
        SpeechOnset(utterance_id="u-1", detected_at_ms=-1.0)


# --- the metric ---------------------------------------------------------------------


def test_the_stop_lands_on_the_barge_in_series_with_the_group_b_labels() -> None:
    """files/08 §4 group B: *"per turn, labels: profile, tenant, branch,
    vendor"*. tests/observability/test_metrics_catalog.py enforces the same
    set from the other side; this asserts the child can actually be built."""
    clock = FakeClock()
    media = MediaPlane(clock=clock, cancel_cost_ms=30.0)
    controller = BargeInPath(
        canceller=media,
        clock=clock,
        labels={
            "tenant": "t1",
            "profile": "residency_tr",
            "branch": "kardiyoloji",
            "vendor": "self",
        },
    )
    before = _histogram_sum(BARGE_IN_STOP_MS, controller.labels)
    clock.run(controller.on_speech_onset(onset(0.0)))
    assert _histogram_sum(BARGE_IN_STOP_MS, controller.labels) - before == 30.0


def _code_of(path: Path) -> str:
    """The module's executable source, with every docstring removed.

    ``ast.unparse`` on a tree whose docstring nodes have been dropped is the
    honest way to scan for a forbidden *reference*: a comment or a docstring
    naming the preemption path is documentation, and only code is a claim.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def _histogram_sum(histogram: object, labels: dict[str, str]) -> float:
    child = histogram.labels(**labels)  # type: ignore[attr-defined]
    return float(child._sum.get())  # type: ignore[attr-defined]
