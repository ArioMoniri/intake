"""INT-482 — the EAS Metadata ``store.config.json``, rendered from served copy only.

``eas metadata:push`` reads ``apps/mobile/store.config.json`` and writes it to
App Store Connect, so that file is a published legal artefact under another
name. It gets the treatment every other one gets here: nobody writes it. It is
a function of the hash-bound listing copy in ``docs/legal/store/listing`` and
the submission answers in ``docs/legal/store/submission``, and of nothing else
(``scripts/release/render_store_config.py`` writes it and checks it for drift).

Three refusals, none of them a default:

1. **No served copy, no file.** The listing loader fails closed on an empty
   directory (HB-L21), and so does this. Each listing also passes both
   :func:`~intake_platform.store.listing.gate_listing` gates and the strict
   claims scan (invariant 20), and fits the field limits the committed EAS
   reference states (:data:`EAS_REFERENCE`; ``eas metadata:push`` validates
   again).
2. **Links never come from copy.** A listing field holding a URL is refused.
   The privacy-policy link is bound to the signed ``gizlilik`` document of the
   INT-210 set (invariant 18), and the URL must name that document's sha256,
   so a link can only point at the bytes counsel signed.
3. **Release is manual.** ``automaticRelease`` is pinned to ``false``. The
   production host receives simulated patients only (HB-I5, HB-L11), so an
   approval must never publish the app by itself.

The submission file carries no reviewer contact and no reviewer sign-in: those
are entered in App Store Connect at submission and never committed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any, Final

import yaml

from intake_platform.legal import claims
from intake_platform.legal.document_index import LegalDocumentSet
from intake_platform.store import listing as listing_mod

__all__ = [
    "ADVISORY_ASC_FLAG_KEYS",
    "ADVISORY_ASC_LEVEL_KEYS",
    "ADVISORY_ASC_OVERRIDE_KEYS",
    "ADVISORY_FLAG_KEYS",
    "ADVISORY_LEVELS",
    "ADVISORY_LEVEL_KEYS",
    "APP_STORE",
    "CATEGORIES",
    "CONTENT_RIGHTS",
    "EAS_REFERENCE",
    "INFO_COPY_FIELDS",
    "INFO_LIMITS",
    "LEGAL_LINK_FIELDS",
    "SUPPORTED_LOCALES",
    "URL",
    "AppStoreSubmission",
    "BoundLegalLink",
    "StoreConfigError",
    "StoreConfigRender",
    "bind_legal_link",
    "build_store_config",
    "load_submission",
    "render_for_repo",
    "serialise",
    "store_config_path",
    "submission_path",
]

#: Where the schema names, limits, locales, categories and age-rating keys
#: below are read from. Expo's own reference, committed with the repo.
EAS_REFERENCE: Final[str] = ".claude/skills/eas-app-stores/references/app-store-metadata.md"

APP_STORE: Final[str] = "app-store"

#: The ``apple.info.<locale>`` fields listing copy may fill. Links are absent
#: on purpose: they come only through :func:`bind_legal_link`.
INFO_COPY_FIELDS: Final[tuple[str, ...]] = (
    "title",
    "subtitle",
    "description",
    "keywords",
    "promoText",
    "releaseNotes",
)

#: The reference's limits; ``keywords`` counts the comma-joined string.
INFO_LIMITS: Final[Mapping[str, int]] = {
    "title": 30,
    "subtitle": 30,
    "keywords": 100,
    "promoText": 170,
    "description": 4000,
}

SUPPORTED_LOCALES: Final[frozenset[str]] = frozenset(
    "ar-SA ca cs da de-DE el en-AU en-CA en-GB en-US es-ES es-MX fi fr-CA fr-FR he hi hr "
    "hu id it ja ko ms nl-NL no pl pt-BR pt-PT ro ru sk sv th tr uk vi zh-Hans zh-Hant".split()
)

CATEGORIES: Final[frozenset[str]] = frozenset(
    "BOOKS BUSINESS DEVELOPER_TOOLS EDUCATION ENTERTAINMENT FINANCE FOOD_AND_DRINK GAMES "
    "GRAPHICS_AND_DESIGN HEALTH_AND_FITNESS KIDS LIFESTYLE MAGAZINES_AND_NEWSPAPERS MEDICAL "
    "MUSIC NAVIGATION NEWS PHOTO_AND_VIDEO PRODUCTIVITY REFERENCE SHOPPING SOCIAL_NETWORKING "
    "SPORTS STICKERS TRAVEL UTILITIES WEATHER".split()
)

ADVISORY_LEVELS: Final[tuple[str, ...]] = ("NONE", "INFREQUENT_OR_MILD", "FREQUENT_OR_INTENSE")
ADVISORY_LEVEL_KEYS: Final[tuple[str, ...]] = (
    "alcoholTobaccoOrDrugUseOrReferences",
    "contests",
    "gamblingSimulated",
    "horrorOrFearThemes",
    "matureOrSuggestiveThemes",
    "medicalOrTreatmentInformation",
    "profanityOrCrudeHumor",
    "sexualContentGraphicAndNudity",
    "sexualContentOrNudity",
    "violenceCartoonOrFantasy",
    "violenceRealistic",
    "violenceRealisticProlongedGraphicOrSadistic",
)
ADVISORY_FLAG_KEYS: Final[tuple[str, ...]] = ("gambling", "unrestrictedWebAccess", "seventeenPlus")

#: INT-495: the age-rating attributes the live App Store Connect API asks for
#: beyond the EAS schema above (ageRatingDeclaration attributes, read from
#: Apple's API reference on 2026-10-16). EAS cannot push them; the ASC writer
#: (scripts/store/asc_plan.py) does. Override, regional-rating and kids-band
#: attributes are left to App Store Connect's own derivation.
ADVISORY_ASC_LEVEL_KEYS: Final[tuple[str, ...]] = ("gunsOrOtherWeapons",)
ADVISORY_ASC_FLAG_KEYS: Final[tuple[str, ...]] = (
    "advertising",
    "ageAssurance",
    "healthOrWellnessTopics",
    "lootBox",
    "messagingAndChat",
    "parentalControls",
    "socialMedia",
    "socialMediaAgeRestricted",
    "userGeneratedContent",
)

#: INT-502 (legal review B8): the live override that sets the top age band.
#: Apple's AgeRatingDeclaration attributes, read 2026-10-29: ``ageRatingOverrideV2``
#: takes one of these values and replaces the deprecated ``ageRatingOverride``,
#: which was the only key with ``SEVENTEEN_PLUS``.
ADVISORY_ASC_OVERRIDE_KEYS: Final[Mapping[str, tuple[str, ...]]] = {
    "ageRatingOverrideV2": (
        "NONE",
        "NINE_PLUS",
        "THIRTEEN_PLUS",
        "SIXTEEN_PLUS",
        "EIGHTEEN_PLUS",
        "UNRATED",
    ),
}

#: The two answers of the app's ``contentRightsDeclaration`` (Apple's API reference).
CONTENT_RIGHTS: Final[tuple[str, ...]] = (
    "DOES_NOT_USE_THIRD_PARTY_CONTENT",
    "USES_THIRD_PARTY_CONTENT",
)

#: ``apple.info`` link field → the INT-210 document it must point at.
LEGAL_LINK_FIELDS: Final[Mapping[str, str]] = {"privacyPolicyUrl": "gizlilik"}

#: Anything that reads as a link inside copy.
URL: Final[re.Pattern[str]] = re.compile(r"(?i)\bhttps?://|\bwww\.")

_STRICT: Final[tuple[str, ...]] = ("performance", "satisfaction", "bare_percentage")


class StoreConfigError(Exception):
    """A served artefact that cannot become ``store.config.json``."""


@dataclass(frozen=True)
class _LinkRequest:
    document_id: str
    url: str


@dataclass(frozen=True)
class AppStoreSubmission:
    """The App Store answers that are not listing copy."""

    categories: tuple[str, ...]
    advisory: Mapping[str, str | bool]
    advisory_sources: Mapping[str, str]
    review_notes: str
    legal_links: Mapping[str, _LinkRequest]
    support_url: str | None
    copyright: str | None
    #: INT-495: answers only the App Store Connect API takes; empty when absent.
    advisory_asc: Mapping[str, str | bool] = dataclass_field(default_factory=dict)
    advisory_asc_sources: Mapping[str, str] = dataclass_field(default_factory=dict)
    content_rights: str | None = None
    content_rights_source: str | None = None


@dataclass(frozen=True)
class BoundLegalLink:
    field: str
    document_id: str
    url: str
    text_hash: str
    version: str


@dataclass(frozen=True)
class StoreConfigRender:
    config: Mapping[str, Any]
    #: Why each absent field is absent, naming the blocker that owes it.
    blocked: tuple[str, ...]
    #: Repo-relative source path → sha256 of the bytes the render read.
    sources: Mapping[str, str]


def store_config_path(repo: Path) -> Path:
    return repo / "apps" / "mobile" / "store.config.json"


def submission_path(repo: Path) -> Path:
    return repo / "docs" / "legal" / "store" / "submission" / f"{APP_STORE}.yaml"


def _gate_text(text: str, *, where: str) -> None:
    if URL.search(text):
        raise StoreConfigError(f"{where}: a link inside copy; links come only from docs/legal")
    hits = claims.scan_text(text, groups=_STRICT, path=where)
    if hits:
        raise StoreConfigError(f"{where}: performance-claim pattern {[h.pattern for h in hits]}")
    device = listing_mod.device_claim_hits(text, field=where)
    if device:
        raise StoreConfigError(f"{where}: device-function claim {[h.pattern for h in device]}")


# --- the submission file ----------------------------------------------------------------


def _advisory(
    raw: object,
    where: str,
    *,
    section: str = "advisory",
    level_keys: tuple[str, ...] = ADVISORY_LEVEL_KEYS,
    flag_keys: tuple[str, ...] = ADVISORY_FLAG_KEYS,
    enum_keys: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[dict[str, str | bool], dict[str, str]]:
    if not isinstance(raw, Mapping):
        raise StoreConfigError(f"{where}: {section} must be a mapping")
    enums = dict(enum_keys or {})
    expected = set(level_keys) | set(flag_keys) | set(enums)
    if set(raw) != expected:
        raise StoreConfigError(
            f"{where}: {section} keys differ from the schema: missing "
            f"{sorted(expected - set(raw))}, unknown {sorted(set(raw) - expected)}"
        )
    answers: dict[str, str | bool] = {}
    sources: dict[str, str] = {}
    for key in (*level_keys, *flag_keys, *enums):
        entry = raw[key]
        if not isinstance(entry, Mapping) or not str(entry.get("source", "")).strip():
            raise StoreConfigError(f"{where}: {section}.{key} needs an answer and a source")
        answer = entry.get("answer")
        if key in level_keys and isinstance(answer, str) and answer in ADVISORY_LEVELS:
            answers[key] = answer
        elif key in flag_keys and isinstance(answer, bool):
            answers[key] = answer
        elif key in enums and isinstance(answer, str) and answer in enums[key]:
            answers[key] = answer
        else:
            raise StoreConfigError(f"{where}: {section}.{key} has no valid answer")
        sources[key] = str(entry["source"])
    return answers, sources


def _optional_https(raw: object, where: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.startswith("https://"):
        raise StoreConfigError(f"{where}: must be an https URL or null")
    return raw


def load_submission(path: Path) -> AppStoreSubmission:
    """The served (or, in tests, the draft) App Store submission answers."""
    where = str(path)
    try:
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise StoreConfigError(f"{where}: not readable as YAML") from exc
    if not isinstance(body, Mapping):
        raise StoreConfigError(f"{where}: top level is not a mapping")
    categories = body.get("categories")
    if not isinstance(categories, list) or not categories or not set(categories) <= CATEGORIES:
        raise StoreConfigError(f"{where}: categories must be a non-empty list from the reference")
    advisory, advisory_sources = _advisory(body.get("advisory"), where)
    notes = body.get("review_notes")
    if not isinstance(notes, str) or not notes.strip():
        raise StoreConfigError(f"{where}: review_notes is empty")
    _gate_text(notes, where=f"{where}:review_notes")
    links: dict[str, _LinkRequest] = {}
    for field_name, request in (body.get("legal_links") or {}).items():
        if not isinstance(request, Mapping):
            raise StoreConfigError(f"{where}: legal_links.{field_name} must be a mapping")
        links[str(field_name)] = _LinkRequest(str(request["document"]), str(request["url"]))
    copyright_line = body.get("copyright")
    if copyright_line is not None and not isinstance(copyright_line, str):
        raise StoreConfigError(f"{where}: copyright must be text or null")
    asc_answers: dict[str, str | bool] = {}
    asc_sources: dict[str, str] = {}
    if body.get("advisory_asc") is not None:
        asc_answers, asc_sources = _advisory(
            body["advisory_asc"],
            where,
            section="advisory_asc",
            level_keys=ADVISORY_ASC_LEVEL_KEYS,
            flag_keys=ADVISORY_ASC_FLAG_KEYS,
            enum_keys=ADVISORY_ASC_OVERRIDE_KEYS,
        )
    rights, rights_source = _content_rights(body.get("content_rights"), where)
    return AppStoreSubmission(
        categories=tuple(str(c) for c in categories),
        advisory=advisory,
        advisory_sources=advisory_sources,
        review_notes=notes.strip(),
        legal_links=links,
        support_url=_optional_https(body.get("support_url"), f"{where}:support_url"),
        copyright=copyright_line,
        advisory_asc=asc_answers,
        advisory_asc_sources=asc_sources,
        content_rights=rights,
        content_rights_source=rights_source,
    )


def _content_rights(raw: object, where: str) -> tuple[str | None, str | None]:
    if raw is None:
        return None, None
    if (
        not isinstance(raw, Mapping)
        or raw.get("answer") not in CONTENT_RIGHTS
        or not str(raw.get("source", "")).strip()
    ):
        raise StoreConfigError(f"{where}: content_rights needs an answer and a source")
    return str(raw["answer"]), str(raw["source"])


# --- legal links --------------------------------------------------------------------------


def bind_legal_link(
    documents: LegalDocumentSet, *, field: str, document_id: str, url: str
) -> BoundLegalLink:
    """A link to a signed, hash-bound document, or a refusal (invariant 18).

    The document must render — signed, summarised, hash-matching — and the URL
    must name its sha256, so a link cannot outlive the bytes it was made for.
    A ``LegalDocumentError`` from the set propagates unchanged.
    """
    if LEGAL_LINK_FIELDS.get(field) != document_id:
        raise StoreConfigError(
            f"{field}: links only to {LEGAL_LINK_FIELDS.get(field)!r}, not {document_id!r}"
        )
    document = documents.render(document_id)
    if not url.startswith("https://"):
        raise StoreConfigError(f"{field}: a legal link must be https")
    if document.text_hash not in url:
        raise StoreConfigError(f"{field}: the URL must name the signed sha256 {document.text_hash}")
    return BoundLegalLink(field, document_id, url, document.text_hash, document.version)


# --- the render ---------------------------------------------------------------------------


def _info(listing: listing_mod.StoreListing) -> dict[str, Any]:
    where = listing.path.name
    if listing.locale not in SUPPORTED_LOCALES:
        raise StoreConfigError(f"{where}: {listing.locale!r} is not an EAS locale")
    unknown = sorted(set(listing.fields) - set(INFO_COPY_FIELDS))
    if unknown:
        raise StoreConfigError(f"{where}: fields outside apple.info copy: {unknown}")
    findings = listing_mod.gate_listing(listing)
    if findings:
        raise StoreConfigError(f"{where}: listing gate {[f.detail for f in findings]}")
    info: dict[str, Any] = {}
    for name in INFO_COPY_FIELDS:
        if name not in listing.fields:
            continue
        value = listing.fields[name].strip()
        _gate_text(value, where=f"{where}:{name}")
        if len(value) > INFO_LIMITS.get(name, len(value)):
            raise StoreConfigError(
                f"{where}:{name} is {len(value)} long; the limit is {INFO_LIMITS[name]}"
            )
        if name == "keywords":
            words = [word.strip() for word in value.split(",")]
            if not all(words):
                raise StoreConfigError(f"{where}:keywords has an empty keyword")
            info[name] = words
        else:
            info[name] = value
    return info


def build_store_config(
    listings: Sequence[listing_mod.StoreListing],
    submission: AppStoreSubmission | None,
    links: Sequence[BoundLegalLink] = (),
) -> StoreConfigRender:
    """``store.config.json`` as data, plus why each absent field is absent."""
    apple_listings = sorted((x for x in listings if x.store == APP_STORE), key=lambda x: x.locale)
    if not apple_listings:
        raise listing_mod.StoreListingMissingError(
            "no served App Store listing — the copy is owed by HB-L21 and is pending "
            "legal-lane review"
        )
    blocked: list[str] = []
    info = {listing.locale: _info(listing) for listing in apple_listings}
    bound = {link.field: link for link in links}
    for field_name in LEGAL_LINK_FIELDS:
        if field_name in bound:
            for entry in info.values():
                entry[field_name] = bound[field_name].url
        else:
            blocked.append(
                f"{field_name}: needs the signed {LEGAL_LINK_FIELDS[field_name]} document "
                "(HB-L27) and its URL (HB-L21(e))"
            )
    apple: dict[str, Any] = {}
    if submission is None:
        blocked.append(
            "categories, advisory and review notes: no served submission at "
            "docs/legal/store/submission/app-store.yaml"
        )
    else:
        apple["categories"] = list(submission.categories)
        apple["advisory"] = dict(submission.advisory)
        apple["review"] = {"notes": submission.review_notes}
        if submission.copyright is not None:
            apple["copyright"] = submission.copyright
        if submission.support_url is not None:
            for entry in info.values():
                entry["supportUrl"] = submission.support_url
    if submission is None or submission.copyright is None:
        blocked.append("copyright: the seller's legal entity is owed by HB-L21(e)")
    if submission is None or submission.support_url is None:
        blocked.append("supportUrl: the seller's support contact is owed by HB-L21(e)")
    apple["info"] = info
    apple["release"] = {"automaticRelease": False}
    return StoreConfigRender({"configVersion": 0, "apple": apple}, tuple(blocked), {})


def render_for_repo(repo: Path) -> StoreConfigRender:
    """The render over ``repo``'s served files, or the refusal that says why not."""
    listings = listing_mod.load_all_listings(listing_mod.listing_dir(repo))
    path = submission_path(repo)
    submission = load_submission(path) if path.exists() else None
    links: list[BoundLegalLink] = []
    if submission is not None:
        documents = LegalDocumentSet(repo / "docs" / "legal")
        links = [
            bind_legal_link(documents, field=name, document_id=req.document_id, url=req.url)
            for name, req in submission.legal_links.items()
        ]
    result = build_store_config(listings, submission, links)
    sources = {
        str(listing.path.relative_to(repo)): listing.text_hash
        for listing in listings
        if listing.store == APP_STORE
    }
    if path.exists():
        sources[str(path.relative_to(repo))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return StoreConfigRender(result.config, result.blocked, sources)


def serialise(config: Mapping[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"
