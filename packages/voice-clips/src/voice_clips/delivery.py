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

**These are voice-tuning values, not clinical values.** They decide the
steadiness and the warmth of the cast voice. They decide nothing a clinician
reads, and no triage level. The rows are the owner's blind pick E04 (INT-449,
D20; docs/voice/casting-2026-10.md): ``eleven_v3`` in ``CLIPGEN_VOICE_ID`` at
Natural stability, with closed-table emotion tags that exist on the wire only.
Two things are fixed by rule rather than by ear, and tests assert both: RED
scripts and instrument items are the most stable profiles (Robust), with zero
style exaggeration and never a tag; and the identity knobs (similarity,
speaker boost) are equal across profiles, so a delivery change is never a voice
change (files/03 §4.9.1 row 11).

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
    "CLIPGEN_VOICE_ID",
    "DEFAULT_DELIVERY_CONTEXT",
    "DELIVERY_CONTEXTS",
    "DELIVERY_PROFILES",
    "MAX_STYLE",
    "PINNED_CONTEXTS",
    "PROFILE_VERSION",
    "SPEED_MAX",
    "SPEED_MIN",
    "UNTAGGED_CONTEXTS",
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

#: The table's version: v4 is the INT-449 cast take E04 on eleven_v3 (D20);
#: v2 was the INT-424 retune of George on eleven_multilingual_v2. It is in
#: every profile key and so in every clip key: a bump re-synthesises instead of
#: replaying older takes, so no clip made under v2 is ever served as v4.
PROFILE_VERSION: Final = 4

#: ElevenLabs' documented speed range for ``voice_settings.speed``.
SPEED_MIN: Final = 0.7
SPEED_MAX: Final = 1.2
#: Stability, similarity and style are unit intervals in the vendor API; style
#: is held to a modest ceiling here (the vendor advises 0).
_UNIT_MAX: Final = 1.0
MAX_STYLE: Final = 0.3

#: The cast voice (INT-449, GitHub #762; D20): "Marcus - Warm, Clear and
#: Professional", the native Turkish ElevenLabs library voice the owner picked
#: from the blind casting page as E04 on 3 Oct 2026 ("use E04 voice"),
#: replacing George (an English voice). One voice for every context (files/03
#: §4.9.1 row 11). The casting record is docs/voice/casting-2026-10.md.
CLIPGEN_VOICE_ID: Final = "2PwDxni9MpXdYqgALrBh"

#: Contexts that never carry an audio tag, on any model (ADR-034; invariant 21
#: wants RED the most stable delivery, and an instrument item is validated
#: wording).
UNTAGGED_CONTEXTS: Final = frozenset({"red", "instrument"})
#: An audio tag is one lowercase ASCII word in brackets. ``[pause]`` is a
#: timing instruction inside the line, which ADR-034 never allows.
_TAG: Final = re.compile(r"\[[a-z]+\]")
_REFUSED_TAG_WORDS: Final = frozenset({"pause"})

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
    """One row of the table: a context, its version, the model, the settings,
    the voice and the row's audio tags.

    ``tags`` (INT-449, the ADR-034 render-time-tags amendment) exist only on
    the wire: the gateway prepends :attr:`wire_prefix` to the request text.
    They are never part of ``text_tr``, the catalogue or ``clip_text_hash``, so
    the spoken words stay the script's, verbatim (invariant 10)."""

    context: DeliveryContext
    version: int
    model_id: str
    voice_settings: ElevenLabsVoiceSettings
    voice_id: str = CLIPGEN_VOICE_ID
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.context not in DELIVERY_CONTEXTS:
            raise UnknownDeliveryContextError(_unknown(self.context))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise DeliveryProfileError(f"profile version must be an int >= 1, got {self.version!r}")
        if self.tags and self.context in UNTAGGED_CONTEXTS:
            raise DeliveryProfileError(f"{self.context} never carries an audio tag (ADR-034)")
        for tag in self.tags:
            if not _TAG.fullmatch(tag) or tag.strip("[]") in _REFUSED_TAG_WORDS:
                raise DeliveryProfileError(
                    f"audio tag {tag!r} is not one lowercase word in brackets, or is a "
                    "timing instruction; tags come from this table only (ADR-034)"
                )

    @property
    def wire_prefix(self) -> str:
        """The row's tags and one space, or nothing: what the wire puts in front."""
        return " ".join(self.tags) + " " if self.tags else ""

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
    tags: tuple[str, ...] = (),
    version: int = PROFILE_VERSION,
) -> DeliveryProfile:
    """One table row. Similarity and speaker boost are the identity knobs, so
    they take the vendor defaults and are the same in every row; style stays at
    0 and speed at the default, as the cast take E04 was heard."""
    return DeliveryProfile(
        context=context,
        version=version,
        model_id=ELEVENLABS_MODEL_ID,
        voice_settings=ElevenLabsVoiceSettings(
            stability=stability,
            similarity_boost=0.75,
            style=0.0,
            use_speaker_boost=True,
            speed=1.0,
        ),
        voice_id=CLIPGEN_VOICE_ID,
        tags=tags,
    )


#: eleven_v3's stability levels (the vendor's product guide): Natural is the
#: level the owner heard E04 at; Robust is the most stable.
_NATURAL: Final = 0.5
_ROBUST: Final = 1.0


#: The table (v4 of every row: the INT-449 cast take E04 on eleven_v3, D20;
#: v1 and v2 were George on eleven_multilingual_v2, docs/evidence/INT-415.md and
#: docs/evidence/INT-424.md). Retune a row by editing it AND bumping
#: :data:`PROFILE_VERSION`: the version is in the clip key, so the retune
#: re-synthesises instead of replaying clips made under the old settings.
#: Warmth and softness are carried by the closed-table tags; RED and instrument
#: are Robust (the most stable) and never tagged.
DELIVERY_PROFILES: Final[Mapping[DeliveryContext, DeliveryProfile]] = MappingProxyType(
    {
        "welcome": _profile("welcome", stability=_NATURAL, tags=("[warmly]",)),
        "routine": _profile("routine", stability=_NATURAL, tags=("[calm]",)),
        "sensitive": _profile("sensitive", stability=_NATURAL, tags=("[softly]", "[reassuring]")),
        "instrument": _profile("instrument", stability=_ROBUST),
        "acknowledgement": _profile("acknowledgement", stability=_NATURAL, tags=("[gently]",)),
        "red": _profile("red", stability=_ROBUST),
        "closing": _profile("closing", stability=_NATURAL, tags=("[warmly]",)),
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
