"""The ``typed`` profile — full parity fallback and kill-switch target (INT-096).

ADR-010: *"Exactly two profiles exist: ``residency_tr`` (production voice) and
``typed`` (full-parity fallback and kill-switch target)."* This package is the
second one. It is a **lane**, not a second runtime: it drives the same
``IntakeEngine`` (INT-081), submits to the same Backend Work queue (INT-092),
and registers the same six tools (invariant 9). What it does not have is any
audio port at all — no clip store, no synthesizer, no sink — which is how
invariant 3 becomes a structural fact of the typed path rather than a claim
about it.

Three things are load-bearing and each has its own module:

- :mod:`~intake_voice_runtime.typed.affordance` — how a slot may be answered.
  CLAUDE.md invariant 22 forbids free numeric text entry on the clinical
  critical path, and a typed lane is exactly where a numeric text field would
  otherwise appear, so the rule is a refusal here and not a convention.
- :mod:`~intake_voice_runtime.typed.render` — the displayed prompt, verbatim
  from ``text_tr`` (invariant 10 does not weaken when the channel stops being
  audio), and the one rendering a clinical quantity may take.
- :mod:`~intake_voice_runtime.typed.switch` — the kill switch. One way, latched,
  and it holds no engine reference: a flip cannot lose a bound slot value
  because there is nothing for it to lose one from.
"""

from __future__ import annotations

from intake_voice_runtime.typed.affordance import (
    NUMERIC_SLOT_TYPES,
    AffordanceKind,
    FreeNumericEntryRefused,
    SlotFacts,
    free_numeric_critical_path_steps,
    slot_facts,
)
from intake_voice_runtime.typed.lanes import AUDIO_DERIVED_LANES, lanes_without_input
from intake_voice_runtime.typed.render import (
    NBSP,
    TypedPrompt,
    numeric_rail,
    render_measure,
    typed_prompt,
)
from intake_voice_runtime.typed.session import TypedConfig, TypedSession, build_typed_tools
from intake_voice_runtime.typed.switch import (
    LaneSwitch,
    LaneSwitchLatched,
    LaneSwitchReason,
    LaneSwitchRecord,
)

__all__ = [
    "AUDIO_DERIVED_LANES",
    "NBSP",
    "NUMERIC_SLOT_TYPES",
    "AffordanceKind",
    "FreeNumericEntryRefused",
    "LaneSwitch",
    "LaneSwitchLatched",
    "LaneSwitchReason",
    "LaneSwitchRecord",
    "SlotFacts",
    "TypedConfig",
    "TypedPrompt",
    "TypedSession",
    "build_typed_tools",
    "free_numeric_critical_path_steps",
    "lanes_without_input",
    "numeric_rail",
    "render_measure",
    "slot_facts",
    "typed_prompt",
]
