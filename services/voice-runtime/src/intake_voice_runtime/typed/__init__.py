"""The ``typed`` profile — full parity fallback and kill-switch target (INT-096).

ADR-010: *"Exactly two profiles exist: ``residency_tr`` (production voice) and
``typed`` (full-parity fallback and kill-switch target)."* This package is the
second one, and what it is **not** is the load-bearing part: it is not a
second runtime, not a second session class and not a second turn loop. It
drives the same :class:`~intake_voice_runtime.clinical_agent.fsm.IntakeEngine`
through the same :class:`~intake_voice_runtime.talker.session.TalkerSession`,
submits to the same Work queue behind the same transcript vault, and registers
the same six tools (invariant 9). Everything here hangs off one seam,
:class:`~intake_voice_runtime.talker.egress.TurnEgress`.

That is the difference between parity and a pair of implementations that agree
today. A second session class was built for this issue once (docs/evidence/
INT-096.md records it) and roughly a third of its test suite existed only to
prove the copy still behaved like the original — which is the shape of a
property being *checked* rather than *held*.

Four things are load-bearing and each has its own module:

- :mod:`~intake_voice_runtime.typed.egress` — the transport itself: a screen,
  no clip store, no synthesizer, no audio sink.
- :mod:`~intake_voice_runtime.typed.affordance` — how a slot may be answered.
  CLAUDE.md invariant 22 forbids free numeric text entry on the clinical
  critical path, and a typed profile is exactly where a numeric text field
  would otherwise appear, so the rule is a refusal here and not a convention.
- :mod:`~intake_voice_runtime.typed.render` — the displayed prompt, verbatim
  from ``text_tr``, and the one rendering a clinical quantity may take.
- :mod:`~intake_voice_runtime.typed.switch` — the kill switch. One way,
  latched, and holding no engine reference.
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
from intake_voice_runtime.typed.egress import ClipOnTypedEgress, TypedEgress
from intake_voice_runtime.typed.lanes import AUDIO_DERIVED_LANES, lanes_without_input
from intake_voice_runtime.typed.render import (
    NBSP,
    TypedPrompt,
    numeric_rail,
    render_measure,
    typed_prompt,
)
from intake_voice_runtime.typed.switch import (
    KillSwitchNotArmed,
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
    "ClipOnTypedEgress",
    "FreeNumericEntryRefused",
    "KillSwitchNotArmed",
    "LaneSwitch",
    "LaneSwitchLatched",
    "LaneSwitchReason",
    "LaneSwitchRecord",
    "SlotFacts",
    "TypedEgress",
    "TypedPrompt",
    "free_numeric_critical_path_steps",
    "lanes_without_input",
    "numeric_rail",
    "render_measure",
    "slot_facts",
    "typed_prompt",
]
