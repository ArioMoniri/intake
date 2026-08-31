"""Observer lanes — the framework (INT-110; CLAUDE.md invariant 11, ADR-012).

files/03 §4.7: the lanes *"read the same audio/transcript stream, write only to
``ObserverState``, and merge into the Backend Agent at section boundaries as a
normal ``wellbeing_signal`` Work item"*. This package is the machinery all five
lanes run inside, and the framework modules beside this one hold **no lane of
their own**. ``linguistic`` (INT-112) is the first and lives in its own
subpackage, :mod:`.linguistic`; ``affect`` is INT-111, ``asr_quality``
INT-113, ``engagement`` INT-114 and ``acoustic`` INT-115, each with its own
model, its own evidence and its own approval. ⚠️ ``asr_quality`` and
``engagement`` have **no declared consent purpose** — files/03 §4.7 and
files/06 §2 contradict each other and HB-L23 owns the answer, so
:func:`.consent.consent_scope_for` refuses both by name and neither may run.

What the framework guarantees, and where each guarantee lives:

- **read-only, at compile time** — :mod:`.context`. A lane is handed a
  :class:`~intake_voice_runtime.observers.context.LaneContext` with no writer
  on it and returns a
  :class:`~intake_voice_runtime.observers.context.LaneObservation` with no
  carrier for a slot or a triage result, so the forbidden write has no
  expression. :mod:`.state` is the only writer, and what it writes is an
  ``ObserverState``.
- **never on the speech critical path** — :mod:`.scheduler`. ``offer`` is an
  ordinary function; ``pump`` is the lane tasks' own, and races each lane
  against its own deadline.
- **backpressure sheds frames** — :mod:`.buffer` and :mod:`.budget`, counted by
  :mod:`.metrics`.
- **per-lane consent (KVKK-6)** — :mod:`.consent`. A lane whose scope is not in
  the closed files/06 §2 list does not run at all.
- **`acoustic` is unreachable outside a registered investigation** —
  :mod:`.study`, four required fields and a gate that shuts on amendment.
- **bounded, zeroized buffers** — :mod:`.buffer`, ≤ 60 s by type and zeroed on
  every files/10 §3 trigger.

Nothing here opens a socket, spawns a process or touches a filesystem
(invariant 13), and nothing here imports the engine, the Work queue, the
Talker or the triage rules — asserted by AST walk in
``tests/lanes/test_isolation.py``, which also carries the negative control for
every gate.
"""

from __future__ import annotations

from intake_voice_runtime.observers.budget import MAX_WINDOW_MS, DropReason, LaneBudget
from intake_voice_runtime.observers.buffer import (
    Frame,
    WindowBuffer,
    WindowView,
    ZeroizeTrigger,
    zeroize_frames,
)
from intake_voice_runtime.observers.consent import (
    LANE_CONSENT_SCOPES,
    REFUSED_CONSENT_SCOPES,
    UNDECLARED_CONSENT_LANES,
    ConsentProbe,
    ConsentReading,
    LaneConsentError,
    LaneConsentScopeRefusedError,
    LaneConsentUndeclaredError,
    consent_scope_for,
)
from intake_voice_runtime.observers.context import (
    InteractionDelta,
    LaneContext,
    LaneObservation,
    Observer,
)
from intake_voice_runtime.observers.metrics import (
    LANE_DROPPED_FRAMES_ID,
    LANE_DROPPED_FRAMES_LABELS,
    LANE_DROPPED_FRAMES_NAME,
    DropLedger,
)
from intake_voice_runtime.observers.module_boundary import (
    LANE_MODULE,
    MODULE_INTENDED_PURPOSE,
    LaneModule,
)
from intake_voice_runtime.observers.scheduler import (
    FrameOffer,
    LaneAdmission,
    LaneOutcome,
    ObserverScheduler,
)
from intake_voice_runtime.observers.spec import LaneSpec
from intake_voice_runtime.observers.state import (
    MARKER_TARGET,
    NO_SIGNAL_INTERACTION,
    ObserverStateBuilder,
    ObserverStateRefusedError,
)
from intake_voice_runtime.observers.study import StudyAssertion, StudyGate, StudyGateState

__all__ = [
    "LANE_CONSENT_SCOPES",
    "LANE_DROPPED_FRAMES_ID",
    "LANE_DROPPED_FRAMES_LABELS",
    "LANE_DROPPED_FRAMES_NAME",
    "LANE_MODULE",
    "MARKER_TARGET",
    "MAX_WINDOW_MS",
    "MODULE_INTENDED_PURPOSE",
    "NO_SIGNAL_INTERACTION",
    "REFUSED_CONSENT_SCOPES",
    "UNDECLARED_CONSENT_LANES",
    "ConsentProbe",
    "ConsentReading",
    "DropLedger",
    "DropReason",
    "Frame",
    "FrameOffer",
    "InteractionDelta",
    "LaneAdmission",
    "LaneBudget",
    "LaneConsentError",
    "LaneConsentScopeRefusedError",
    "LaneConsentUndeclaredError",
    "LaneContext",
    "LaneModule",
    "LaneObservation",
    "LaneOutcome",
    "LaneSpec",
    "Observer",
    "ObserverScheduler",
    "ObserverStateBuilder",
    "ObserverStateRefusedError",
    "StudyAssertion",
    "StudyGate",
    "StudyGateState",
    "WindowBuffer",
    "WindowView",
    "ZeroizeTrigger",
    "consent_scope_for",
    "zeroize_frames",
]
