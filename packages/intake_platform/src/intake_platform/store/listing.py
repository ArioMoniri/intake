"""INT-224 — the store listing as a regulatory document, with two gates.

A store listing is marketing copy that a regulator reads. Two independent
regimes bite on it and both are already invariants here:

**Invariant 20 / App Review 1.4.1.** ADR-022 quotes it verbatim: an app that
makes a health-accuracy claim it cannot validate is rejected. So listing copy
lives under ``docs/legal/store`` — inside the tree
:mod:`intake_platform.legal.claims` already scans — rather than in a marketing
folder beside the gate.

**Invariant 18 / `device_functions`.** files/06 §0.3 names the two functions
that make this product a Class IIb medical device: automated red-flag triage
that directs a patient's urgency, and automated interpretation of screening
instruments (plus the investigational acoustic module, §0.7). A listing that
describes either is claiming a capability that stays off without a recorded CE
certificate or clinical-investigation approval id. That must fail closed here,
not be caught by a reviewer: App Review noticing is the *bad* outcome, because
by then the claim has been published.

The lexicon is phrase-shaped and not token-shaped, and the reason is Turkish.
The fixed copy of files/06 §7 that we are **required** to show contains the
word ``tanı`` twice — *"tanı niteliği taşımaz"*, *"tanı değildir"* — and the
static device-off safety line contains ``112``. A token-level lexicon would
reject the disclaimers and the emergency line: exactly the copy that keeps us
on the right side of the boundary. Every pattern below is chosen to leave them
alone, and the near-miss control in tests/legal/test_store_labels.py is what
holds that true.

Nothing here authors listing copy. ``docs/legal/store/listing`` is empty and
the loader says so (HB-L21): the seller's legal entity, the support and privacy
URLs and the Turkish marketing text are all human deliverables.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from intake_platform.legal import claims

__all__ = [
    "DEVICE_CLAIM_PATTERNS",
    "LISTING_GATE_GROUPS",
    "DeviceClaimHit",
    "DeviceClaimPattern",
    "ListingFinding",
    "StoreListing",
    "StoreListingError",
    "StoreListingInvalidError",
    "StoreListingMissingError",
    "device_claim_hits",
    "gate_listing",
    "listing_dir",
    "load_all_listings",
    "load_listing",
]

#: The claim groups a listing is scanned with. ``bare_percentage`` is not among
#: them: "%100 Türkçe" or "%20 daha hızlı hazırlık" is marketing, not a health
#: performance claim, and the metrics invariant 20 names are covered by name.
LISTING_GATE_GROUPS: Final[tuple[str, ...]] = ("performance", "satisfaction")

_MISSING_HINT = (
    "no store listing committed at {path} — the seller's legal entity, the support and "
    "privacy URLs and the Turkish marketing copy are human deliverables owed by "
    "HUMAN_BLOCKERS.md HB-L21, and nothing may be authored on their behalf"
)


class StoreListingError(Exception):
    """Base for listing-loading failures."""


class StoreListingMissingError(StoreListingError):
    """No listing has been authored. Fail closed."""


class StoreListingInvalidError(StoreListingError):
    """A listing exists but breaks the format contract."""


@dataclass(frozen=True)
class StoreListing:
    store: str
    locale: str
    text_hash: str
    path: Path
    fields: Mapping[str, str]


# --- the device-function lexicon -------------------------------------------------------


@dataclass(frozen=True)
class DeviceClaimPattern:
    name: str
    regex: re.Pattern[str]
    #: Which gated function the phrase claims.
    function: str
    #: Where that function is defined.
    source: str


@dataclass(frozen=True, order=True)
class DeviceClaimHit:
    field: str
    pattern: str
    matched: str


_TRIAGE = "automated red-flag triage directing a patient's urgency (files/06 §0.3)"
_INSTRUMENT = "automated interpretation of screening instruments (files/06 §0.3, Annex IV)"
_ACOUSTIC = "the investigational acoustic module (files/06 §0.7)"
_DIAGNOSIS = "diagnosis, reserved to physicians by 1219 s. Kanun m.1/m.8 (files/06 §0.4)"
_DEVICE = "describing the product as a medical device (files/06 §0.3 Stage A/B)"

DEVICE_CLAIM_PATTERNS: Final[tuple[DeviceClaimPattern, ...]] = (
    DeviceClaimPattern(
        "triage_tr",
        re.compile(r"(?i)\btriyaj\w*"),
        _TRIAGE,
        "files/06 §0.3 — automated triage is MDSW under Rule 11",
    ),
    DeviceClaimPattern(
        "triage_en",
        re.compile(r"(?i)\btriage\b"),
        _TRIAGE,
        "files/06 §0.3 — automated triage is MDSW under Rule 11",
    ),
    DeviceClaimPattern(
        "urgency_tr",
        re.compile(r"(?i)\bacili[yğ]et\w*\s+(?:düzey\w*|seviye\w*|belirle\w*|ata\w*)"),
        _TRIAGE,
        "files/08 §0 — the flag 'changes what the product is'",
    ),
    DeviceClaimPattern(
        "urgency_en",
        re.compile(r"(?i)\burgency\s+(?:level|score|assessment|triage)"),
        _TRIAGE,
        "files/08 §0 — the flag 'changes what the product is'",
    ),
    DeviceClaimPattern(
        "red_zone_tr",
        re.compile(r"(?i)\bkırmızı\s+alan\w*"),
        _TRIAGE,
        "RG 13/9/2022 EK-4 zones; assigning one is the device function",
    ),
    DeviceClaimPattern(
        "instrument_score_tr",
        re.compile(
            r"(?i)\b(?:PHQ-?9|GAD-?7|C-?SSRS|WHO-?5|HAQ-?DI)\b[^.\n]{0,40}"
            r"(?:puan\w*|skor\w*|yorum\w*|değerlendir\w*)"
        ),
        _INSTRUMENT,
        "MDCG 2019-11 Annex IV, quoted in files/06 §0.7",
    ),
    DeviceClaimPattern(
        "instrument_score_en",
        re.compile(
            r"(?i)\b(?:scores?|interprets?|rates?)\b[^.\n]{0,30}"
            r"\b(?:depression|anxiety|PHQ-?9|GAD-?7)\b"
        ),
        _INSTRUMENT,
        "MDCG 2019-11 Annex IV, quoted in files/06 §0.7",
    ),
    DeviceClaimPattern(
        "mood_score_tr",
        re.compile(r"(?i)\b(?:depresyon|anksiyete|kaygı)\s*(?:skor\w*|puan\w*|risk\w*)"),
        _INSTRUMENT,
        "MDCG 2019-11 Annex IV names the depression-scoring case verbatim",
    ),
    DeviceClaimPattern(
        "voice_biomarker_tr",
        re.compile(
            r"(?i)\bses\w*\s*(?:biyobelirte\w*|analiz\w*)\s*(?:ile|den|dan)?\s*"
            r"(?:depresyon|anksiyete|kaygı)"
        ),
        _ACOUSTIC,
        "files/06 §0.7 — investigational only, no shadow mode",
    ),
    DeviceClaimPattern(
        "voice_biomarker_en",
        re.compile(r"(?i)\bvoice\s+biomarker\b"),
        _ACOUSTIC,
        "files/06 §0.7 — investigational only, no shadow mode",
    ),
    DeviceClaimPattern(
        "diagnosis_tr",
        re.compile(r"(?i)\b(?:tanı|teşhis)\s+(?:koy\w*|konur|konulur|konuyor|konabilir)"),
        _DIAGNOSIS,
        "files/06 §0.4 — the app never names a suspected diagnosis",
    ),
    DeviceClaimPattern(
        "diagnosis_en",
        re.compile(r"(?i)\b(?:diagnoses|diagnosing|diagnostic\s+(?:tool|app|software))\b"),
        _DIAGNOSIS,
        "files/06 §0.4 — the app never names a suspected diagnosis",
    ),
    DeviceClaimPattern(
        "medical_device_tr",
        re.compile(r"(?i)\btıbbi\s+cihaz\w*"),
        _DEVICE,
        "invariant 18 — no CE certificate or approval id is recorded",
    ),
    DeviceClaimPattern(
        "medical_device_en",
        re.compile(r"(?i)\bmedical\s+device\b"),
        _DEVICE,
        "invariant 18 — no CE certificate or approval id is recorded",
    ),
)


#: Turkish negation shapes, taken from files/00 §2's no-truncate list
#: (``-m(ı|i|u|ü)yor``, ``-maz/-mez``, ``-sız/-siz/-suz/-süz``), plus ``değil``
#: and the English forms. A sentence that DENIES a capability is not claiming
#: it, and rejecting the denial would reject exactly the copy that keeps us on
#: the right side of the boundary — "bir tıbbi cihaz değildir" is the clearest
#: case.
_NEGATION = re.compile(
    r"(?i)\bdeğil\w*|\w+m(?:ı|i|u|ü)yor\b|\w+m[ae]z\b|\w+s(?:ı|i|u|ü)z\b"
    r"|\bnot\b|\bnever\b|\bwithout\b"
)

#: How far either side of a match a denial still counts as denying it. Turkish
#: puts the negation after the phrase ("tıbbi cihaz değildir"), English before
#: it ("is not a medical device"), so both directions are read — and both are
#: bounded, so a denial of one capability cannot excuse a claim about another.
_NEGATION_WINDOW = 60

#: Where a denial stops reaching: the end of the sentence, or a contrastive
#: conjunction, which resets the polarity mid-sentence ("triyaj yapmaz **ama**
#: aciliyet düzeyi belirler" claims the second thing while denying the first).
_BARRIER = re.compile(r"(?i)[.;!?\n]|\b(?:ama|fakat|ancak|yalnız|but|however|though)\b")


def _is_denied(text: str, start: int, end: int) -> bool:
    after = text[end : end + _NEGATION_WINDOW]
    barrier = _BARRIER.search(after)
    if barrier is not None:
        after = after[: barrier.start()]
    before = text[max(0, start - _NEGATION_WINDOW) : start]
    barriers = list(_BARRIER.finditer(before))
    if barriers:
        before = before[barriers[-1].end() :]
    return _NEGATION.search(after) is not None or _NEGATION.search(before) is not None


def device_claim_hits(text: str, *, field: str = "<text>") -> tuple[DeviceClaimHit, ...]:
    """Every `device_functions` claim in ``text``, denials excepted."""
    hits: list[DeviceClaimHit] = []
    for pattern in DEVICE_CLAIM_PATTERNS:
        for match in pattern.regex.finditer(text):
            if _is_denied(text, match.start(), match.end()):
                continue
            hits.append(DeviceClaimHit(field, pattern.name, match.group(0)))
    return tuple(sorted(hits))


# --- loading and gating ----------------------------------------------------------------


def listing_dir(repo: Path) -> Path:
    """Under ``docs/legal`` so invariant 18's binding rule and invariant 20's
    claims gate both already reach it."""
    return repo / "docs" / "legal" / "store" / "listing"


def _locale_from_name(path: Path) -> tuple[str, str]:
    stem = path.name.removesuffix(".yaml").removesuffix(".yml")
    store, _, locale = stem.rpartition(".")
    if not store or not locale:
        raise StoreListingInvalidError(
            f"{path}: a listing file is named <store>.<locale>.yaml — 805 s. Kanun makes "
            "the Turkish text the governing one, so the locale is part of the identity"
        )
    return store, locale


def load_listing(path: Path) -> StoreListing:
    """One listing file, hash-bound to its own bytes (invariant 18)."""
    store, locale = _locale_from_name(path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise StoreListingMissingError(_MISSING_HINT.format(path=path)) from exc
    try:
        body: Any = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise StoreListingInvalidError(f"{path}: not readable as UTF-8 YAML") from exc
    if not isinstance(body, dict):
        raise StoreListingInvalidError(f"{path}: top level is not a mapping")
    fields = body.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise StoreListingInvalidError(f"{path}: no fields block")
    # Deliberately no required-key list: which fields a store's form demands is
    # that store's published fact, and inventing one here would be inventing a
    # vendor requirement. The only rule is that a value is text.
    for key, value in fields.items():
        if not isinstance(value, str) or not value.strip():
            raise StoreListingInvalidError(f"{path}: field {key!r} is not a non-empty string")
    return StoreListing(
        store=store,
        locale=locale,
        text_hash=hashlib.sha256(raw).hexdigest(),
        path=path,
        fields={str(key): value for key, value in fields.items()},
    )


def load_all_listings(directory: Path) -> tuple[StoreListing, ...]:
    """Every committed listing, or a fail-closed error when none exist."""
    paths = sorted(directory.glob("*.yaml")) if directory.is_dir() else []
    if not paths:
        raise StoreListingMissingError(_MISSING_HINT.format(path=directory))
    return tuple(load_listing(path) for path in paths)


@dataclass(frozen=True, order=True)
class ListingFinding:
    kind: str  # "performance_claim" | "device_claim"
    field: str
    detail: str


def gate_listing(listing: StoreListing) -> tuple[ListingFinding, ...]:
    """Both gates over one listing: no performance claim, no device claim."""
    findings: list[ListingFinding] = []
    for field_name, value in sorted(listing.fields.items()):
        for hit in claims.scan_text(value, groups=LISTING_GATE_GROUPS, path=field_name):
            findings.append(ListingFinding("performance_claim", field_name, hit.pattern))
        for claim in device_claim_hits(value, field=field_name):
            findings.append(ListingFinding("device_claim", field_name, claim.pattern))
    return tuple(sorted(findings))
