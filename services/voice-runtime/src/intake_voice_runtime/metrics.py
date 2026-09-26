"""The families this service emits (CLAUDE.md invariant 13).

Every one is already catalogued in ``observability/metrics_catalog.yaml`` from
files/08 §4 — this module flips them from `planned` to emitted, and the
catalogue entries move to `status: live` in the same change. Names are string
literals because ``tests/observability/test_metrics_catalog.py`` finds
declarations by AST, and a name built at runtime would slip past the gate.

Labels are ids and closed enumerations only (invariant 6): a tool name, a
violation class, a profile. No session id, no transcript, no free text.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, disable_created_metrics

__all__ = [
    "DELIVERY_INSERTION_WAIT_MS",
    "LANE_DROPPED_FRAMES",
    "POLICYGUARD_BLOCKS_TOTAL",
    "PREEMPT_RED_LATENCY_MS",
    "TALKER_TOOL_CALLS_TOTAL",
    "VENDOR_BREAKER_STATE",
    "VENDOR_BREAKER_TRANSITIONS_TOTAL",
    "VENDOR_FAILOVERS_TOTAL",
    "VOICE_TTS_CHARS",
    "WORK_FAILED_TOTAL",
    "WORK_LATENCY_MS",
    "WORK_QUEUE_DEPTH",
]

# The client's `_created` companion series would sit next to every counter
# and histogram without appearing in the catalogue (inv. 13) — off, as
# everywhere else on the platform.
disable_created_metrics()  # type: ignore[no-untyped-call]  # upstream def has no annotations

TALKER_TOOL_CALLS_TOTAL = Counter(
    "talker_tool_calls_total",
    "Talker tool calls by tool name; only the six names of invariant 9 ever appear.",
    ["tool"],
)

POLICYGUARD_BLOCKS_TOTAL = Counter(
    "policyguard_blocks_total",
    "PolicyGuard blocks by violation class and voice profile.",
    ["class", "profile"],
)

#: files/08 §4 targets p50 ≤ 2 s. Buckets bracket the files/12 §6 ladder —
#: the natural window, then the 20 / 45 / 90 s TRIAGE_YELLOW deadlines.
DELIVERY_INSERTION_WAIT_MS = Histogram(
    "delivery_insertion_wait_ms",
    "Wait until a safe insertion window delivered Backend speech, in milliseconds.",
    buckets=(100.0, 300.0, 1_000.0, 2_000.0, 5_000.0, 20_000.0, 45_000.0, 90_000.0, float("inf")),
)

# --- Layer B, the Work queue (INT-092) ------------------------------------------
#
# files/08 §4 C. The only label any of the three carries is ``type``, whose
# domain is the closed ``WorkType`` enumeration — no session id, no step text,
# no transcript (invariant 6). The queue itself holds ``input_hash`` rather
# than a transcript, so there is no patient text here to redact.

WORK_QUEUE_DEPTH = Gauge(
    "work_queue_depth",
    "Backend Work queued (not running) by work type.",
    ["type"],
)

#: files/08 §4 targets extract_slots p50 < 3 s. Buckets bracket that target and
#: the files/03 §4.3 note that Backend Work carries no spoken-loop constraint.
WORK_LATENCY_MS = Histogram(
    "work_latency_ms",
    "Backend Work execution time by work type, in milliseconds.",
    ["type"],
    buckets=(10.0, 50.0, 250.0, 1_000.0, 3_000.0, 10_000.0, 30_000.0, float("inf")),
)

WORK_FAILED_TOTAL = Counter(
    "work_failed_total",
    "Backend Work that ended in the failed state, by work type.",
    ["type"],
)


# --- observer lanes (INT-110) ---------------------------------------------------
#
# files/10 §9 names `lane.dropped_frames` among the observer-lane signals, and
# files/03 §4.7.6 makes it *"a tracked metric that is also a recorded field on
# every lane signal"* — so the same number appears here and as
# `LaneObservation.dropped_frames_in_window`. The one label is the closed
# `Lane` enumeration: no session id, no window id, no frame content
# (invariant 6). A lane that was never admitted has no child at all, which is
# how the exposition tells a refused lane apart from an idle one.

LANE_DROPPED_FRAMES = Counter(
    "lane_dropped_frames",
    "Audio frames dropped by an observer lane under backpressure, by lane.",
    ["lane"],
)

# --- the RED preemption path (INT-093) --------------------------------------------
#
# files/08 §4 C names exactly one id for this path — ``preempt.red_latency_ms``
# (≤ 300, p99 alert) — so exactly one family is emitted. The stop leg is
# deliberately NOT folded into ``voice.barge_in_stop_ms``: that series is the
# patient's barge-in and conflating two causes in one histogram would make the
# ≤ 150 ms target unreadable for both. A missed stop is a raised
# ``RedPathViolation`` instead, which is louder than a percentile.
#
# No labels, matching the catalogue row: a RED carries a session and a rule id
# and neither belongs on a series (invariant 6).

#: Rule evaluation → the pre-positioned script starting on the device. Buckets
#: bracket the two budgets of files/02 §8.2 (150 ms stop, 300 ms end to end)
#: and the p99 alert threshold of files/08 §5.
PREEMPT_RED_LATENCY_MS = Histogram(
    "preempt_red_latency_ms",
    "Rules-engine RED preemption latency, rule evaluation to script start, in milliseconds.",
    buckets=(50.0, 100.0, 150.0, 200.0, 300.0, 500.0, 1_000.0, float("inf")),
)


# --- the patient's barge-in (INT-291) ---------------------------------------------
#
# files/08 §4 group B names this series and its target: ``voice.barge_in_stop_ms``
# (≤ 150). It stays SEPARATE from ``preempt.red_latency_ms`` for the reason
# docs/evidence/INT-093.md records — *"that series is the patient's barge-in and
# conflating two causes in one histogram would make the ≤ 150 ms target
# unreadable for both"*. This issue is the other half of that sentence: the
# series moves ``planned`` → ``live`` because something now emits it.
#
# The label set is group B's own, and every member of it is a closed, non
# identifying dimension — tenant, profile, branch, vendor. No session id, no
# utterance id (invariant 6).

#: Patient-speech detection → the outbound audio path cancelled, in
#: milliseconds. Buckets bracket the files/02 §8.2 budget so the p95 either
#: sits under 150 or visibly does not.
BARGE_IN_STOP_MS = Histogram(
    "voice_barge_in_stop_ms",
    "Time to stop agent playback after the patient started speaking, in milliseconds.",
    ["tenant", "profile", "branch", "vendor"],
    buckets=(25.0, 50.0, 100.0, 150.0, 250.0, 500.0, 1_000.0, float("inf")),
)


# --- session cost metering (INT-101) ----------------------------------------------
#
# files/08 §4 group B names ``voice.tts_chars`` — *"Characters synthesised per
# turn (TTSMetrics)"* — and this issue is what makes something emit it: the
# metered synthesizer of ``intake_voice_runtime.metering.adapters`` charges the
# string it actually sent to the model, so the series moves in the opposite
# direction to ``voice.clip_cache_hit_ratio``, a clip-cache hit synthesising
# nothing (CLAUDE.md invariant 10).
#
# **The other two axes of files/08 §4 group J get no family here, and neither
# gap is closed by minting an id.**
#
# - Backend ``extract_slots`` tokens: group B's ``voice.talker_tokens`` is *the
#   Talker's* LLM per turn, and extraction is Layer B Work. Group J states
#   *"tokens/chars/audio-seconds by vendor"* WITHOUT an id, and this
#   catalogue's own trailing comment already records that row as id-less. The
#   ledger counts them; no series carries them.
# - ``voice.stt_audio_s``: catalogued, and nothing in this service can source
#   it. The Talker is handed transcripts, not audio, and the ASR adapter takes
#   opaque bytes with no declared sample format — so a duration here would be
#   derived from a guessed sample rate, about a recording invariant 3 says does
#   not exist. The row stays ``planned``.
# - ``cost.per_session``: no price exists (HB-I4, HB-I5), so no Gauge is
#   declared and the row stays ``planned``. See
#   ``intake_voice_runtime.metering.cost``.
#
# The label set is group B's own — tenant, profile, branch, vendor — all four
# non-identifying by construction (invariant 6), with ``vendor`` carrying the
# constant ``self-hosted`` because invariant 19 leaves no vendor to name.

#: Characters sent to a TTS model in one synthesis. Buckets bracket the shape
#: of the content rather than a target files/08 §4 does not state for this
#: series: a short confirmation, a scripted question, a follow-up, and the long
#: tail of a red-flag action script.
VOICE_TTS_CHARS = Histogram(
    "voice_tts_chars",
    "Characters synthesised per turn, by tenant, profile, branch and vendor.",
    ["tenant", "profile", "branch", "vendor"],
    buckets=(16.0, 32.0, 64.0, 128.0, 256.0, 512.0, 1_024.0, float("inf")),
)


# --- per-vendor circuit breakers and speech-lane failover (INT-100) ---------------
#
# files/10 §5 LLM10 names "circuit breakers per vendor" and §9's voice row
# names "vendor errors" as a console signal; neither is a files/08 §4 id, so
# these three carry no ``id`` — the precedent is INT-024's ``vendor_adapter_*``
# families. Every label value is a registry component name, a closed breaker
# state, or ``typed`` (the text lane, which is a profile rather than a
# component). No session id, no text (invariant 6).

#: One-hot: exactly one of ``closed``/``open``/``half_open`` is 1 per component.
#: A state set rather than a numeric code, so a dashboard reads the state by
#: name and an alert selects ``state="open"`` without knowing an encoding.
VENDOR_BREAKER_STATE = Gauge(
    "vendor_breaker_state",
    "Circuit breaker state per vendor component; 1 for the current state, 0 otherwise.",
    ["component", "state"],
)

VENDOR_BREAKER_TRANSITIONS_TOTAL = Counter(
    "vendor_breaker_transitions_total",
    "Circuit breaker state transitions by vendor component, from state and to state.",
    ["component", "from_state", "to_state"],
)

#: A session left a speech lane for the next one in the registry's order, or —
#: ``to_component="typed"`` — for the text lane because none was left.
VENDOR_FAILOVERS_TOTAL = Counter(
    "vendor_failovers_total",
    "Speech-lane failovers by the lane a session left and the lane it moved to.",
    ["from_component", "to_component"],
)
