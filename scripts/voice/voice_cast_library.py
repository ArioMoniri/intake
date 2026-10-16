"""INT-449: read the vendor's Turkish voice library and shortlist by metadata.

The library is queried with filters only (``language=tr``, a sort, a page);
nothing else is sent. The shortlist is a pre-filter for the listening test,
not a verdict: the owner's ear and the continuity measurements decide.

**Eligibility** (:func:`exclusion`) is a hard filter:

- a native Turkish accent: the voice's own language label is ``tr`` and no
  accent label (its own, or a verified Turkish entry's) names a foreign accent;
- commercial use under the Voice Library terms on a paid plan: no ``famous``
  (iconic) voice, which carries its own licence, and no legacy custom rate,
  which is a cost multiplier the estimate cannot see;
- an adult voice.

**Fit** (:func:`score`) ranks the eligible voices for a calm, warm,
professional clinical delivery: standard (Istanbul) accent over regional,
calm/warm descriptors, conversational or informative use, a middle-aged or
young-adult voice, a professional clone, Turkish verified on the pinned model,
a long notice period, and a usage signal. Every term is in the code below and
the doc, and none of them is a quality claim (invariant 20).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import httpx
from voice_clips.gateway import ELEVENLABS_MODEL_ID

#: George, the voice ADR-028 pins (``intake_api.dev_voice.GEORGE_VOICE_ID``).
GEORGE_VOICE_ID: Final = "JBFqnCBsd6RMkjVDRZzb"
SHORTLIST_SIZE: Final = 8
LIBRARY_PAGE_SIZE: Final = 100
LIBRARY_PAGES: Final = 3
LIBRARY_SORTS: Final = ("usage_character_count_1y", "cloned_by_count")
TIMEOUT_S: Final = 60.0

#: Accent labels read as standard (Istanbul) Turkish. Any other accent on a
#: Turkish-language voice is a regional native accent; these markers are foreign.
STANDARD_ACCENTS: Final = frozenset({"standard", "turkish", "istanbul", "neutral", "türkçe"})
FOREIGN_MARKERS: Final = tuple(
    "american british english australian arab german french russian persian azer "
    "kurdish indian".split()
)
CALM_WARM: Final = frozenset(
    "calm warm soft gentle soothing pleasant smooth professional confident mature clear "
    "crisp formal friendly kind natural neutral relaxed reassuring trustworthy".split()
)
AVOID_TONE: Final = frozenset(
    "excited energetic intense dramatic raspy gravelly whispery childish sassy anxious "
    "aggressive robotic nasal seductive sarcastic".split()
)
USE_CASE_SCORE: Final[Mapping[str, float]] = {
    "conversational": 2.0,
    "informative_educational": 2.0,
    "narrative_story": 1.0,
    "entertainment_tv": -0.5,
    "characters_animation": -2.0,
    "asmr": -3.0,
}
GOOD_WORDS: Final = tuple(
    "calm warm professional clear natural medical health sakin sıcak profesyonel doğal "
    "net anlaşılır yumuşak samimi güven kurumsal sağlık".split()
)
BAD_WORDS: Final = tuple(
    "child çocuk cartoon anime villain horror asmr whisper fısıltı funny komik sexy "
    "seductive meme".split()
)


class CastRefused(RuntimeError):
    """The run would break the corpus, spend or lane rules. Nothing was sent."""


@dataclass(frozen=True)
class Voice:
    voice_id: str
    name: str
    source: str
    gender: str = ""
    age: str = ""
    accent: str = ""
    language: str = ""
    category: str = ""
    descriptive: str = ""
    use_case: str = ""
    description: str = ""
    usage_1y: int = 0
    cloned_by: int = 0
    rate: float | None = None
    fiat_rate: float | None = None
    notice_period_days: int | None = None
    live_moderation: bool = False
    verified: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)
    preview_url: str = ""


def _s(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    return str(value).strip() if value is not None else ""


def _verified(raw: Mapping[str, Any]) -> tuple[tuple[str, str, str], ...]:
    entries = raw.get("verified_languages") or ()
    return tuple(
        (_s(e, "language").lower(), _s(e, "model_id"), _s(e, "accent").lower())
        for e in entries
        if isinstance(e, Mapping)
    )


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def parse_library_voice(raw: Mapping[str, Any]) -> Voice:
    notice = _number(raw.get("notice_period"))
    return Voice(
        voice_id=_s(raw, "voice_id"),
        name=_s(raw, "name"),
        source="library",
        gender=_s(raw, "gender").lower(),
        age=_s(raw, "age").lower(),
        accent=_s(raw, "accent").lower(),
        language=_s(raw, "language").lower(),
        category=_s(raw, "category").lower(),
        descriptive=_s(raw, "descriptive").lower(),
        use_case=_s(raw, "use_case").lower(),
        description=_s(raw, "description"),
        usage_1y=int(_number(raw.get("usage_character_count_1y")) or 0),
        cloned_by=int(_number(raw.get("cloned_by_count")) or 0),
        rate=_number(raw.get("rate")),
        fiat_rate=_number(raw.get("fiat_rate")),
        notice_period_days=int(notice) if notice is not None else None,
        live_moderation=bool(raw.get("live_moderation_enabled")),
        verified=_verified(raw),
        preview_url=_s(raw, "preview_url"),
    )


def parse_premade_voice(raw: Mapping[str, Any]) -> Voice:
    labels = raw.get("labels") or {}
    return Voice(
        voice_id=_s(raw, "voice_id"),
        name=_s(raw, "name"),
        source="premade",
        gender=_s(labels, "gender").lower(),
        age=_s(labels, "age").lower(),
        accent=_s(labels, "accent").lower(),
        language=_s(labels, "language").lower(),
        category=_s(raw, "category").lower(),
        descriptive=(_s(labels, "descriptive") or _s(labels, "description")).lower(),
        use_case=_s(labels, "use_case").lower(),
        description=_s(raw, "description"),
        verified=_verified(raw),
        preview_url=_s(raw, "preview_url"),
    )


def accent_kind(voice: Voice) -> str:
    """``standard``, ``regional`` or ``foreign``, from the voice's own labels."""
    verified_tr = [a for lang, _m, a in voice.verified if lang == "tr" and a]
    if voice.language != "tr" or any(
        m in a for a in (voice.accent, *verified_tr) for m in FOREIGN_MARKERS
    ):
        return "foreign"
    # the voice's own label wins; a verified Turkish accent fills an empty one
    primary = voice.accent or (verified_tr[0] if verified_tr else "")
    if primary in STANDARD_ACCENTS or "istanbul" in primary or "standard" in primary:
        return "standard"
    return "regional"


def exclusion(voice: Voice) -> str | None:
    """Why a voice cannot be shortlisted, or None."""
    if not voice.voice_id or not voice.name:
        return "incomplete record"
    if accent_kind(voice) == "foreign":
        return "not a native Turkish accent"
    if voice.category == "famous":
        return "iconic voice: its own licence, not the library terms"
    if (voice.rate is not None and voice.rate != 1.0) or voice.fiat_rate is not None:
        return "legacy custom rate (a cost multiplier)"
    if any(k in voice.age for k in ("child", "kid", "teen")):
        return "not an adult voice"
    return None


def score(voice: Voice) -> float:
    """Metadata fit for a calm, warm, professional clinical voice. A pre-filter only."""
    total = 3.0 if accent_kind(voice) == "standard" else 1.0
    tones = set(voice.descriptive.replace(",", " ").split())
    total += 2.0 if tones & CALM_WARM else 0.0
    total -= 3.0 if tones & AVOID_TONE else 0.0
    total += USE_CASE_SCORE.get(voice.use_case, 0.0)
    total += {"middle_aged": 1.0, "young": 0.5}.get(voice.age, 0.0)
    total += {"professional": 1.0, "high_quality": 0.5}.get(voice.category, 0.0)
    text = voice.description.lower()
    total += min(2.0, 0.5 * sum(1 for w in GOOD_WORDS if w in text))
    total -= 3.0 if any(w in text for w in BAD_WORDS) else 0.0
    on_v2 = any(lang == "tr" and m == ELEVENLABS_MODEL_ID for lang, m, _a in voice.verified)
    total += 1.0 if on_v2 else 0.0
    total += min(2.0, math.log10(1 + voice.cloned_by) / 2)
    total += min(1.0, math.log10(1 + voice.usage_1y) / 8)
    notice = voice.notice_period_days
    total += 0.5 if notice is not None and notice >= 365 else 0.0
    total -= 0.25 if voice.live_moderation else 0.0
    return round(total, 3)


def shortlist(voices: Sequence[Voice], size: int = SHORTLIST_SIZE) -> list[Voice]:
    """The best-scoring eligible voices, half female and half male where possible."""
    eligible = sorted(
        (v for v in voices if exclusion(v) is None and v.voice_id != GEORGE_VOICE_ID),
        key=lambda v: (-score(v), v.name, v.voice_id),
    )
    picked = [v for v in eligible if v.gender == "female"][: (size + 1) // 2]
    picked += [v for v in eligible if v.gender == "male"][: size // 2]
    picked += [v for v in eligible if v not in picked][: size - len(picked)]
    return sorted(picked, key=lambda v: (-score(v), v.name))


#: Words in a voice's own name or description that claim expressiveness or emotion
#: (English and Turkish stems). Round 2 looks for these on top of eligibility.
EXPRESSIVE_WORDS: Final = tuple("expressive emotion duygu empath empati heartfelt içten".split())


def expressive_extras(
    voices: Sequence[Voice], exclude: frozenset[str], per_gender: int = 1
) -> list[Voice]:
    """Round 2: eligible, middle-aged native voices whose own description names
    expressiveness or emotion, best metadata score first, ``per_gender`` each."""
    pool = [
        v
        for v in voices
        if exclusion(v) is None
        and v.voice_id not in exclude
        and v.age == "middle_aged"
        and not set(v.descriptive.replace(",", " ").split()) & AVOID_TONE
        and not any(w in v.description.lower() for w in BAD_WORDS)
        and any(w in f"{v.name} {v.description}".lower() for w in EXPRESSIVE_WORDS)
    ]
    picked: list[Voice] = []
    for gender in ("female", "male"):
        same = sorted((v for v in pool if v.gender == gender), key=lambda v: (-score(v), v.name))
        picked += same[:per_gender]
    return picked


def george() -> Voice:
    return Voice(
        voice_id=GEORGE_VOICE_ID,
        name="George (current, control)",
        source="control",
        gender="male",
        accent="british",
        language="en",
        category="premade",
    )


def vendor_client(
    base_url: str, api_key: str, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """The key travels in a header only; it is never printed, logged or stored."""
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={"xi-api-key": api_key},
        timeout=TIMEOUT_S,
        transport=transport,
    )


def vendor_status(response: httpx.Response) -> str:
    """The vendor's machine status token (``detail.status``, e.g. ``quota_exceeded``),
    or ``unknown``. Only a short snake_case token is kept: never the body or a message,
    which could echo request data."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return "unknown"
    status = detail.get("status") if isinstance(detail, Mapping) else None
    ok = isinstance(status, str) and 0 < len(status) <= 40
    return status if ok and status.replace("_", "").isalpha() and status.islower() else "unknown"


def get_json(client: httpx.Client, path: str, params: Mapping[str, Any]) -> Any:
    response = client.get(path, params=dict(params))
    if response.status_code // 100 != 2:
        raise CastRefused(f"{path} answered HTTP {response.status_code} (the key is not echoed)")
    return response.json()


def fetch_library(client: httpx.Client) -> list[Voice]:
    """Turkish-language library voices, by one-year usage and by clone count."""
    seen: dict[str, Voice] = {}
    for sort in LIBRARY_SORTS:
        for page in range(LIBRARY_PAGES):
            params = {"language": "tr", "page_size": LIBRARY_PAGE_SIZE, "page": page, "sort": sort}
            data = get_json(client, "/v1/shared-voices", params)
            for raw in data.get("voices") or ():
                voice = parse_library_voice(raw)
                seen.setdefault(voice.voice_id, voice)
            if not data.get("has_more"):
                break
    return list(seen.values())


def fetch_premade(client: httpx.Client) -> list[Voice]:
    """Premade voices that list Turkish. Optional: a refusal here is not fatal."""
    try:
        data = get_json(client, "/v2/voices", {"voice_type": "default", "page_size": 100})
    except (CastRefused, httpx.HTTPError):
        return []
    voices = [parse_premade_voice(raw) for raw in data.get("voices") or ()]
    return [v for v in voices if any(lang == "tr" for lang, _m, _a in v.verified)]


def fetch_models(client: httpx.Client) -> dict[str, float] | None:
    """Text-to-speech models that list Turkish, with their character cost multiplier."""
    try:
        data = get_json(client, "/v1/models", {})
    except (CastRefused, httpx.HTTPError):
        return None
    models: dict[str, float] = {}
    for raw in data if isinstance(data, list) else ():
        langs = {_s(lang, "language_id").lower() for lang in raw.get("languages") or ()}
        if raw.get("can_do_text_to_speech") and "tr" in langs:
            rates = raw.get("model_rates") or {}
            models[_s(raw, "model_id")] = _number(rates.get("character_cost_multiplier")) or 1.0
    return models
