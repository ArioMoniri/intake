"""The charging surface: a ledger, a label set, and three ways to spend.

:class:`SessionMeter` is the object the rest of the runtime talks to. It is
deliberately thin — the arithmetic is the ledger's and the policy is
``budgets``' — and it exists for two reasons the ledger cannot serve:

1. **It owns the label set**, so a series is never emitted with labels invented
   at the call site. files/08 §4 group B fixes the per-turn labels for every
   ``voice.*`` series at ``{tenant, profile, branch, vendor}`` and the
   catalogue is schema-checked against the PHI-risk denylist
   (``intake_platform.slo.PHI_RISK_LABEL_NAMES``, invariant 6). The session key
   is **not** among them: a per-session identifier on a series would make the
   cardinality of the exposition the number of patients seen.
2. **It is where "which series exists" is answered**, and today that answer is
   short. ``voice.tts_chars`` is catalogued (files/08 §4 group B,
   *"Characters synthesised per turn"*) and is emitted here. The other two are
   not, and neither gap is filled by inventing an id:

   * **Backend extraction tokens have no catalogued home.** Group B's
     ``voice.talker_tokens`` is *the Talker's* LLM; ``extract_slots`` is Layer
     B. Group J states *"tokens/chars/audio-seconds by vendor"* **without an
     id**, and the catalogue's own trailing comment already records that row as
     id-less. So the ledger counts them and no series carries them.
   * **``voice.stt_audio_s`` has no source in this tree.** The series is
     catalogued, but nothing in ``services/voice-runtime`` sees patient audio:
     the Talker is handed transcripts, and the ASR adapter takes opaque
     ``bytes`` with no declared sample format. :meth:`charge_audio_seconds`
     therefore takes a **measured** duration from its caller and there is no
     byte-length overload — a duration inferred from a guessed sample rate is
     an invented number, and it would be one about a recording invariant 3
     says does not exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from intake_voice_runtime.metering.components import ChargeClass, MeteredComponent
from intake_voice_runtime.metering.ledger import Admission, SessionLedger
from intake_voice_runtime.metrics import VOICE_TTS_CHARS
from intake_voice_runtime.profiles import VoiceProfile

__all__ = ["UNKNOWN_LABEL", "SELF_HOSTED", "SessionMeter", "TurnLabels"]

#: What the group B ``vendor`` label carries. There is no vendor — CLAUDE.md
#: invariant 19 makes every model self-hosted — and the label keeps its name
#: because the catalogue's label set is pinned against files/08 §4. The same
#: constant is spelled in ``intake_voice_runtime.talker.barge_in``.
SELF_HOSTED: Final = "self-hosted"

#: For a dimension the caller genuinely does not know. Never a patient value.
UNKNOWN_LABEL: Final = "unknown"


@dataclass(frozen=True)
class TurnLabels:
    """files/08 §4 group B's per-turn label set, and nothing else.

    Every member is a closed, non-identifying dimension. ``vendor`` is fixed
    rather than a parameter: a caller that could set it could label a
    self-hosted turn with a vendor name that has not existed since files/00
    §0b.
    """

    tenant: str = UNKNOWN_LABEL
    profile: VoiceProfile = VoiceProfile.RESIDENCY_TR
    branch: str = UNKNOWN_LABEL

    def as_dict(self) -> dict[str, str]:
        return {
            "tenant": self.tenant,
            "profile": self.profile.value,
            "branch": self.branch,
            "vendor": SELF_HOSTED,
        }


@dataclass
class SessionMeter:
    """Charge one session's spend, and gate the elective lane.

    Every method is an ordinary function. Nothing here is awaitable, opens a
    socket, or touches a disk, so a metered turn costs the same virtual time as
    an unmetered one (CLAUDE.md invariant 9) — and a test proves it on the fake
    clock rather than trusting the claim.
    """

    ledger: SessionLedger
    labels: TurnLabels = field(default_factory=TurnLabels)

    def admits(self, component: MeteredComponent, charge_class: ChargeClass) -> Admission:
        return self.ledger.admits(component, charge_class)

    # --- the three axes -------------------------------------------------------------

    def charge_tts_chars(self, text_tr: str) -> float:
        """Charge one synthesis, and observe the catalogued histogram.

        The unit is characters of the string that was actually sent to the
        model — a clip-cache hit never reaches here, which is why
        ``voice.clip_cache_hit_ratio`` and this series move in opposite
        directions (files/08 §4 group B).
        """
        chars = float(len(text_tr))
        total = self.ledger.record(MeteredComponent.TTS, chars)
        VOICE_TTS_CHARS.labels(**self.labels.as_dict()).observe(chars)
        return total

    def charge_extraction_tokens(self, input_tokens: int, output_tokens: int) -> float:
        """Charge what the serving endpoint *reported*, never an estimate.

        ``Completion`` carries zeros when the endpoint reported no usage block,
        and zero is then the true count of tokens anything here has counted. A
        tokeniser run locally to fill the gap would be a second opinion about a
        number we do not own.
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("a reported token count cannot be negative")
        return self.ledger.record(
            MeteredComponent.LLM_EXTRACTION, float(input_tokens + output_tokens)
        )

    def charge_audio_seconds(self, seconds: float) -> float:
        """Charge a **measured** duration. There is no byte-length overload.

        See this module's docstring: nothing in the runtime holds audio, and a
        duration derived from a guessed sample format would be an invented
        number about a recording that does not exist (CLAUDE.md invariants 1
        and 3, files/HUMAN_BLOCKERS.md rule 1).
        """
        return self.ledger.record(MeteredComponent.ASR, seconds)

    # --- reporting ------------------------------------------------------------------

    def totals(self) -> Mapping[MeteredComponent, float]:
        return self.ledger.totals()

    def overruns(self) -> tuple[MeteredComponent, ...]:
        """Components past a declared limit — the alert surface for a TARGET."""
        return tuple(
            component for component in MeteredComponent if self.ledger.over_budget(component)
        )
