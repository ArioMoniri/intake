"""Delivery profiles: how one scripted utterance is said, never what (INT-415).

The mobile composer tags every utterance with one of seven delivery contexts
(``apps/mobile/src/lib/dialogue/deliveryContext.ts``). This module maps each
context to a **delivery profile**: the ElevenLabs ``voice_settings`` the clip
lane sends, plus the pinned model id. A profile changes the delivery and never
the words. The text is the scripted ``text_tr``, verbatim (invariant 10), with
every numeral already expanded by the compiler (invariant 22).

**Why the table lives here, beside the gateway.** Both of its consumers already
depend on this package: the offline clip build (``voice_clips.build``, ADR-028)
and the dev on-demand route (``intake_api.dev_voice``). The mobile app never
imports it, so "server-side only" is structural, not a convention: the device
names a context and never sees a setting. The protocols package is the wrong
home, because it is I/O-free and vendor-free by construction. Vendor voice
settings are an adapter concern, and the self-hosted ``residency_tr`` TTS has
different controls altogether (docs/voice/on-prem-tts-wiring.md).

**The profile id and its version are part of every clip cache key.** The same
text in two contexts is two clips, and a retuned profile (version bump) misses
the cache instead of quietly replaying clips tuned under the old settings.

**These are voice-tuning values, not clinical values.** They decide pace,
steadiness and expressiveness of George's voice. They decide nothing a
clinician reads, and no triage level. The rationale for each row is in
docs/evidence/INT-415.md, and a listening review by the owner is still owed
before the numbers are called settled. Two things are fixed by rule rather
than by ear, and tests assert both: RED scripts and instrument items are the
most stable profiles with zero style exaggeration, and the identity knobs
(similarity, speaker boost) are equal across profiles, so a delivery change is
never a voice change (files/03 §4.9.1 row 11).

**The vendor's bounds are enforced at construction** (ElevenLabs API reference
and product guide, retrieved 27 Sep 2026, cited in docs/evidence/INT-415.md):
stability, similarity and style are 0..1 and speed is 0.7..1.2. Style is
capped lower still, at :data:`MAX_STYLE`. The vendor advises keeping it at 0,
and the owner asked for modest warmth, not exaggeration.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, get_args

from voice_clips.errors import ClipCacheError
from voice_clips.gateway import ELEVENLABS_MODEL_ID

__all__ = [
    "DEFAULT_DELIVERY_CONTEXT",
    "DELIVERY_CONTEXTS",
    "DELIVERY_PROFILES",
    "MAX_STYLE",
    "PINNED_CONTEXTS",
    "SPEED_MAX",
    "SPEED_MIN",
    "DeliveryContext",
    "DeliveryProfile",
    "DeliveryProfileError",
    "ElevenLabsVoiceSettings",
    "UnknownDeliveryContextError",
    "delivery_context_for_subject",
    "delivery_profile",
]

#: The seven contexts, in the mobile contract's order (deliveryContext.ts).
#: A test reads that file and compares the two, byte for byte.
DeliveryContext = Literal[
    "welcome",
    "routine",
    "sensitive",
    "instrument",
    "acknowledgement",
    "red",
    "closing",
]
DELIVERY_CONTEXTS: Final[tuple[DeliveryContext, ...]] = get_args(DeliveryContext)
DEFAULT_DELIVERY_CONTEXT: Final[DeliveryContext] = "routine"

#: Contexts a compiled manifest row can pin by its subject alone. A rule's
#: action script is RED delivery and an instrument item is instrument delivery,
#: whatever a caller labels them. The on-demand route holds a request to the pin.
PINNED_CONTEXTS: Final[frozenset[DeliveryContext]] = frozenset({"red", "instrument"})

#: ElevenLabs' documented speed range for ``voice_settings.speed``.
SPEED_MIN: Final = 0.7
SPEED_MAX: Final = 1.2
#: Stability, similarity and style are unit intervals in the vendor API; style
#: is held to a modest ceiling here (the vendor advises 0). INT-440 lifted it
#: from 0.3 to 0.4 at the owner's request (3 Oct 2026: "more emotion"), so the
#: owner's "v3 expressive" proposal can be rendered for listening
#: (scripts/voice/render_bundled_clips.py). The served table below is unchanged
#: by that, and RED and instrument rows stay at style 0 by test.
_UNIT_MAX: Final = 1.0
MAX_STYLE: Final = 0.4

#: A compiled rule id (``protocols.dsl.RuleId``) and an instrument item subject
#: (``<InstrumentId>.<item SlotKey>``, protocols.compile.emit_clips). Slot link
#: ids are snake_case and never match either. Tests pin these against the
#: compiler's own types.
_RULE_SUBJECT: Final = re.compile(r"^rf\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_INSTRUMENT_SUBJECT: Final = re.compile(r"^[A-Z][A-Za-z0-9-]*\.[a-z][a-z0-9_]*$")


class DeliveryProfileError(ClipCacheError):
    """A delivery profile that the vendor would reject, or that breaks a rule."""


class UnknownDeliveryContextError(DeliveryProfileError):
    """A context outside the seven. Refused, never mapped to a default."""


def _in_range(name: str, value: float, low: float, high: float) -> None:
    if not isinstance(value, float | int) or isinstance(value, bool) or not math.isfinite(value):
        raise DeliveryProfileError(f"voice setting {name} must be a finite number, got {value!r}")
    if not low <= value <= high:
        raise DeliveryProfileError(
            f"voice setting {name}={value} is outside {low}..{high} (the vendor's "
            "documented range, or this table's modest-style ceiling)"
        )


@dataclass(frozen=True)
class ElevenLabsVoiceSettings:
    """The five ``voice_settings`` fields of the text-to-speech request."""

    stability: float
    similarity_boost: float
    style: float
    use_speaker_boost: bool
    speed: float

    def __post_init__(self) -> None:
        _in_range("stability", self.stability, 0.0, _UNIT_MAX)
        _in_range("similarity_boost", self.similarity_boost, 0.0, _UNIT_MAX)
        _in_range("style", self.style, 0.0, MAX_STYLE)
        _in_range("speed", self.speed, SPEED_MIN, SPEED_MAX)
        if not isinstance(self.use_speaker_boost, bool):
            raise DeliveryProfileError(
                f"use_speaker_boost must be a bool, got {self.use_speaker_boost!r}"
            )

    def as_request(self) -> dict[str, float | bool]:
        """The ``voice_settings`` object exactly as the request body carries it."""
        return {
            "stability": float(self.stability),
            "similarity_boost": float(self.similarity_boost),
            "style": float(self.style),
            "use_speaker_boost": self.use_speaker_boost,
            "speed": float(self.speed),
        }


@dataclass(frozen=True)
class DeliveryProfile:
    """One row of the table: a context, its version, the model and the settings."""

    context: DeliveryContext
    version: int
    model_id: str
    voice_settings: ElevenLabsVoiceSettings

    def __post_init__(self) -> None:
        if self.context not in DELIVERY_CONTEXTS:
            raise UnknownDeliveryContextError(_unknown(self.context))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise DeliveryProfileError(f"profile version must be an int >= 1, got {self.version!r}")

    @property
    def profile_id(self) -> str:
        return f"delivery.{self.context}"

    @property
    def key(self) -> str:
        """``delivery.<context>@v<version>``, the segment every clip key carries."""
        return f"{self.profile_id}@v{self.version}"


def _unknown(context: object) -> str:
    return (
        f"delivery context {context!r} is not one of {', '.join(DELIVERY_CONTEXTS)}; "
        "an unknown context is refused rather than mapped to a default"
    )


def _profile(
    context: DeliveryContext,
    *,
    stability: float,
    style: float,
    speed: float,
    version: int = 1,
) -> DeliveryProfile:
    """One table row. Similarity and speaker boost are the identity knobs, so
    they take the vendor defaults and are the same in every row."""
    return DeliveryProfile(
        context=context,
        version=version,
        model_id=ELEVENLABS_MODEL_ID,
        voice_settings=ElevenLabsVoiceSettings(
            stability=stability,
            similarity_boost=0.75,
            style=style,
            use_speaker_boost=True,
            speed=speed,
        ),
    )


#: The table (v1 of every row). The rationale per row is in
#: docs/evidence/INT-415.md. Retune a row by editing it AND bumping its
#: ``version``: the version is in the clip key, so the retune re-synthesises
#: instead of replaying clips made under the old settings.
DELIVERY_PROFILES: Final[Mapping[DeliveryContext, DeliveryProfile]] = MappingProxyType(
    {
        # warmest: lowest stability (more natural variation), modest style
        "welcome": _profile("welcome", stability=0.40, style=0.20, speed=0.98),
        # calm, neutral, professional: near the vendor's own defaults
        "routine": _profile("routine", stability=0.55, style=0.05, speed=1.00),
        # steadier and slower than routine, no exaggeration
        "sensitive": _profile("sensitive", stability=0.65, style=0.00, speed=0.92),
        # validated items: very stable, no exaggeration, slightly slower
        "instrument": _profile("instrument", stability=0.80, style=0.00, speed=0.95),
        # brief and warm: a little livelier than routine, never slower
        "acknowledgement": _profile("acknowledgement", stability=0.48, style=0.15, speed=1.02),
        # the most stable of all, no exaggeration, clear rather than rushed
        "red": _profile("red", stability=0.85, style=0.00, speed=0.95),
        # warm like the welcome, a touch steadier
        "closing": _profile("closing", stability=0.42, style=0.20, speed=0.97),
    }
)


def delivery_profile(context: str) -> DeliveryProfile:
    """The profile for ``context``, or :class:`UnknownDeliveryContextError`."""
    for known in DELIVERY_CONTEXTS:
        if context == known:
            return DELIVERY_PROFILES[known]
    raise UnknownDeliveryContextError(_unknown(context))


def delivery_context_for_subject(subject: str) -> DeliveryContext:
    """The context a compiled clip-manifest row is spoken in, from its subject.

    The manifest records whose text a row is (a slot link id, a rule id or an
    instrument item id) and nothing about delivery, so this is the one fact the
    builder can read: a rule's action script is ``red``, an instrument item is
    ``instrument``, and every slot question is ``routine``. Welcome, closing,
    acknowledgement and sensitive lead-ins are composed on the device
    (INT-414) and never appear in a compiled manifest.
    """
    if _RULE_SUBJECT.match(subject):
        return "red"
    if _INSTRUMENT_SUBJECT.match(subject):
        return "instrument"
    return "routine"
