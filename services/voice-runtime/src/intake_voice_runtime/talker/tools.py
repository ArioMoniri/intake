"""The six tools, and nothing else (files/03 §4.2; ADR-009).

| tool | purpose |
|---|---|
| ``protocol_next`` | deterministic next step from the IntakeEngine snapshot |
| ``submit_utterance`` | hand the answer to Layer B — **never waits** |
| ``cancel_work`` | cancel a submitted Work; makes ``cancelled`` reachable |
| ``request_repeat_or_clarify`` | re-ask / slow mode / typed switch |
| ``patient_memory`` | recall/remember/forget, non-clinical keys only |
| ``respond_permission`` | relay a spoken, current-turn yes/no to a consent prompt |

``respond_permission`` carries the gate ladder files/12 §7.6 added, in order:
request open and ≤ 60 s → prompt hash matches → the span starts after the
prompt audio ended → **the span does not overlap agent playback** → lexical
whitelist → confidence ≥ 0.85 → read-back. The overlap gate is the definitive
fix for *"hı-hı"*: the agent's own backchannel sits inside a playback
interval, so a span overlapping it can never count as consent. A passing first
response is ``PROVISIONAL`` until a second affirmative on a child request.

Every gate returns a typed :class:`PermissionAck` rather than raising: the
Talker must always be able to say something back, and a refusal that surfaces
as an exception in a duplex loop becomes dead air.
"""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Final

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.ports import PatientMemoryKey, PatientRecord, WorkTicket
from intake_voice_runtime.steps import NextStep
from intake_voice_runtime.talker.registry import ToolRegistry

if TYPE_CHECKING:  # pragma: no cover - import cycle only at type-check time
    from intake_voice_runtime.talker.session import TalkerSession

__all__ = [
    "BACKCHANNEL_LEXEMES",
    "MIN_CONSENT_CONFIDENCE",
    "NO_LEXEMES",
    "PERMISSION_WINDOW_MS",
    "YES_LEXEMES",
    "ConsentDecision",
    "MemoryOp",
    "PermissionAck",
    "PermissionRequest",
    "PermissionState",
    "RepeatDirective",
    "RepeatReason",
    "build_talker_tools",
    "normalise_tr",
]

#: files/12 §7.6 — a consent prompt goes stale after a minute.
PERMISSION_WINDOW_MS: Final[float] = 60_000.0
#: files/12 §7.6 — below this, the transcript is not consent.
MIN_CONSENT_CONFIDENCE: Final[float] = 0.85


class MemoryOp(enum.StrEnum):
    RECALL = "recall"
    REMEMBER = "remember"
    FORGET = "forget"


class RepeatReason(enum.StrEnum):
    """Why the Talker is re-asking (files/03 §4.2, §4.4b, §4.5b T3)."""

    NOT_HEARD = "not_heard"
    SLOW_DOWN = "slow_down"
    CONNECTION_GAP = "connection_gap"
    TYPED_SWITCH = "typed_switch"


class ConsentDecision(enum.StrEnum):
    YES = "yes"
    NO = "no"


class PermissionState(enum.StrEnum):
    """files/12 §7.6: a first pass is provisional until the read-back."""

    PROVISIONAL = "provisional"
    GRANTED = "granted"
    DECLINED = "declined"
    REFUSED = "refused"


class PermissionRequest(FrozenModel):
    """A consent prompt the Talker is waiting on an answer to."""

    request_id: str = Field(min_length=1)
    prompt_text_hash: str = Field(min_length=64, max_length=64)
    opened_at_ms: float = Field(ge=0.0)
    prompt_audio_ended_ms: float = Field(ge=0.0)
    parent_request_id: str | None = Field(
        default=None, description="Set on the read-back child request."
    )


class PermissionAck(FrozenModel):
    """Always returned — a refusal is an outcome, not an exception."""

    request_id: str
    state: PermissionState
    reason: str = Field(min_length=1)


class RepeatDirective(FrozenModel):
    """What to say when re-asking. Verbatim — files/03 §4.4b is explicit."""

    text_tr: str = Field(min_length=1)
    clip_id: str | None = Field(default=None)
    reason: RepeatReason


#: files/12 §7.6 lexical whitelist. Turkish normalisation maps dotted/dotless
#: İ/I **before** ``lower()`` — ``"İZİN VERİYORUM".lower()`` yields ``i̇`` with a
#: combining dot in Python's default casing, which would miss the whitelist.
YES_LEXEMES: Final[frozenset[str]] = frozenset(
    {"evet", "tamam", "olur", "kabul ediyorum", "izin veriyorum", "onaylıyorum", "peki"}
)
NO_LEXEMES: Final[frozenset[str]] = frozenset(
    {"hayır", "olmaz", "istemiyorum", "izin vermiyorum", "kabul etmiyorum"}
)
#: Explicitly NOT consent: a backchannel is not a decision (files/12 §7.6).
BACKCHANNEL_LEXEMES: Final[frozenset[str]] = frozenset({"hı-hı", "hıhı", "hmm", "ıhı", "he"})


def normalise_tr(text: str) -> str:
    """Casefold Turkish safely: İ→i and I→ı before the ASCII fold."""
    return text.replace("İ", "i").replace("I", "ı").lower().strip()


def build_talker_tools(session: TalkerSession) -> ToolRegistry:
    """Register exactly the six tools of invariant 9, then seal the registry."""
    registry = ToolRegistry()

    def protocol_next() -> NextStep | None:
        """Lock-free read of the engine snapshot (files/12 §7.2)."""
        return session.protocol_next()

    def submit_utterance(step_id: str, transcript: str) -> WorkTicket:
        """Hand the answer to Layer B and return at once (ADR-009)."""
        return session.submit_utterance(step_id, transcript)

    def cancel_work(work_id: str, reason: str) -> WorkTicket:
        """Cancel a submitted Work (files/12 §7.1)."""
        return session.cancel_work(work_id, reason)

    def request_repeat_or_clarify(reason: RepeatReason) -> RepeatDirective:
        """Re-ask the current step **verbatim** (files/03 §4.4b)."""
        return session.request_repeat_or_clarify(reason)

    def patient_memory(
        op: MemoryOp, key: str | PatientMemoryKey, value: str | None = None
    ) -> PatientRecord | None:
        """Non-clinical memory only: the key set is closed (files/03 §4.2)."""
        return session.patient_memory(op, key, value)

    def respond_permission(
        *,
        request_id: str,
        decision: ConsentDecision,
        span_start_ms: float,
        span_end_ms: float,
        asr_confidence: float,
        prompt_text_hash: str,
    ) -> PermissionAck:
        """Relay a spoken, current-turn yes/no through the §7.6 gates."""
        return session.respond_permission(
            request_id=request_id,
            decision=decision,
            span_start_ms=span_start_ms,
            span_end_ms=span_end_ms,
            asr_confidence=asr_confidence,
            prompt_text_hash=prompt_text_hash,
        )

    for name, handler in (
        ("protocol_next", protocol_next),
        ("submit_utterance", submit_utterance),
        ("cancel_work", cancel_work),
        ("request_repeat_or_clarify", request_repeat_or_clarify),
        ("patient_memory", patient_memory),
        ("respond_permission", respond_permission),
    ):
        registry.register(name, handler)
    registry.seal()
    return registry
