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


<<<<<<< HEAD
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
=======
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
>>>>>>> origin/main
)
