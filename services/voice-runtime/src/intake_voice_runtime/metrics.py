"""The three families this service emits (CLAUDE.md invariant 13).

Every one is already catalogued in ``observability/metrics_catalog.yaml`` from
files/08 §4 — this module flips them from `planned` to emitted, and the
catalogue entries move to `status: live` in the same change. Names are string
literals because ``tests/observability/test_metrics_catalog.py`` finds
declarations by AST, and a name built at runtime would slip past the gate.

Labels are ids and closed enumerations only (invariant 6): a tool name, a
violation class, a profile. No session id, no transcript, no free text.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram, disable_created_metrics

__all__ = [
    "DELIVERY_INSERTION_WAIT_MS",
    "POLICYGUARD_BLOCKS_TOTAL",
    "TALKER_TOOL_CALLS_TOTAL",
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
