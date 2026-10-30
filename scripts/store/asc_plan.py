"""INT-495 — the App Store Connect draft for Önvizit, planned from served copy.

The plan is the list of App Store Connect resources the writer would edit, the
field names it would set on each, and every field it cannot set with the
blocker that owes it. It is built from the same gated, hash-bound render that
writes ``apps/mobile/store.config.json`` (``eas_metadata.render_for_repo``) plus
the submission answers the EAS schema cannot carry (``advisory_asc``,
``content_rights``). No network, no credentials, and no value is ever printed:
:func:`render_plan` writes field names only.

What the plan deliberately leaves out is as important as what it holds:

- **App Privacy** has no App Store Connect API resource (the API index read on
  2026-10-16 lists none), so the owner enters it in the web UI from the
  inventory-derived sheet;
- **What's New** is not available for an app's first version;
- **assets** (the product page header and the screenshots) wait for INT-502's
  capture from the merged design stack;
- **links and the copyright line** wait for HB-L27 and HB-L21(e).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import asc_assets
from intake_platform.store import eas_metadata

__all__ = [
    "AGE_RATING_KEYS",
    "ASC_LOCALES",
    "KEYWORDS_MAX_BYTES",
    "Plan",
    "PlanError",
    "Step",
    "build_plan",
    "check_keywords",
    "keyword_bytes",
    "render_plan",
]

#: EAS locale → App Store Connect locale.
ASC_LOCALES: Final[Mapping[str, str]] = {"tr": "tr", "en-US": "en-US"}

#: App Store Connect counts keywords in bytes (platform version information,
#: read 2026-10-16); a Turkish letter outside ASCII is two of them.
KEYWORDS_MAX_BYTES: Final[int] = 100

#: The ageRatingDeclaration attributes the plan sets: the EAS levels and the two
#: EAS flags that exist in the live API (``seventeenPlus`` does not), plus the
#: live-only keys the submission answers in ``advisory_asc``.
AGE_RATING_KEYS: Final[tuple[str, ...]] = (
    *eas_metadata.ADVISORY_LEVEL_KEYS,
    "gambling",
    "unrestrictedWebAccess",
    *eas_metadata.ADVISORY_ASC_LEVEL_KEYS,
    *eas_metadata.ADVISORY_ASC_FLAG_KEYS,
    *eas_metadata.ADVISORY_ASC_OVERRIDE_KEYS,
)

_INTERNAL: Final[str] = "INT-502 (GitHub #856)"


class PlanError(ValueError):
    """Served copy that App Store Connect would refuse."""


@dataclass(frozen=True)
class Step:
    resource: str
    locale: str | None
    fields: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    steps: tuple[Step, ...]
    #: (resource, locale) → field → value. Read by the writer, never printed.
    values: Mapping[tuple[str, str | None], Mapping[str, Any]]
    blocked: tuple[str, ...]
    notes: tuple[str, ...]


def keyword_bytes(words: list[str]) -> int:
    return len(",".join(words).encode("utf-8"))


def check_keywords(words: list[str], *, where: str) -> str:
    joined = ",".join(words)
    if keyword_bytes(words) > KEYWORDS_MAX_BYTES:
        raise PlanError(
            f"{where}: keywords are {keyword_bytes(words)} bytes; App Store Connect "
            f"takes {KEYWORDS_MAX_BYTES}"
        )
    return joined


def _locale(eas_locale: str) -> str:
    try:
        return ASC_LOCALES[eas_locale]
    except KeyError as exc:
        raise PlanError(f"{eas_locale!r} has no App Store Connect locale here") from exc


def _export_compliance(repo: Path) -> str:
    config = json.loads((repo / "apps" / "mobile" / "app.json").read_text(encoding="utf-8"))
    plist = config["expo"].get("ios", {}).get("infoPlist", {})
    if plist.get("ITSAppUsesNonExemptEncryption") is False:
        return (
            "export compliance: answered in the binary (ITSAppUsesNonExemptEncryption "
            "false in apps/mobile/app.json); no API write"
        )
    raise PlanError("apps/mobile/app.json does not declare ITSAppUsesNonExemptEncryption false")


def _asset_blocks(manifest: asc_assets.AssetManifest, locales: list[str]) -> list[str]:
    blocked: list[str] = []
    for entry in manifest.entries:
        for locale in locales:
            files = entry.files.get(locale, ())
            reason = "no capture yet" if not files else "upload not built here"
            if entry.placement_group is None:
                reason += "; placement group not yet read from the reference data"
            blocked.append(
                f"{entry.placement_type}[{locale}] ({entry.asset_id}): {reason} — {_INTERNAL} "
                "captures from the merged design stack and uploads"
            )
    return blocked


def build_plan(repo: Path, manifest: Path | None = None) -> Plan:
    """The draft plan over ``repo``'s served files, or the refusal that says why not."""
    render = eas_metadata.render_for_repo(repo)
    apple = render.config["apple"]
    path = eas_metadata.submission_path(repo)
    submission = eas_metadata.load_submission(path) if path.exists() else None
    steps: list[Step] = []
    values: dict[tuple[str, str | None], dict[str, Any]] = {}
    blocked = [reason for reason in render.blocked if not reason.startswith("categories")]

    def add(resource: str, locale: str | None, fields: dict[str, Any]) -> None:
        steps.append(Step(resource, locale, tuple(fields)))
        values[(resource, locale)] = fields

    locales = sorted(apple["info"])
    for eas_locale in locales:
        info = apple["info"][eas_locale]
        locale = _locale(eas_locale)
        app_info = {"name": info["title"], "subtitle": info["subtitle"]}
        if "privacyPolicyUrl" in info:
            app_info["privacyPolicyUrl"] = info["privacyPolicyUrl"]
        add("appInfoLocalizations", locale, app_info)
        version = {
            "description": info["description"],
            "keywords": check_keywords(list(info["keywords"]), where=eas_locale),
            "promotionalText": info["promoText"],
        }
        for source, target in (("supportUrl", "supportUrl"), ("marketingUrl", "marketingUrl")):
            if source in info:
                version[target] = info[source]
        add("appStoreVersionLocalizations", locale, version)

    if submission is None:
        blocked.append(
            "category, age rating, content rights and review notes: no served submission "
            "(docs/legal/store/submission/app-store.yaml)"
        )
    else:
        add("appInfos", None, {"primaryCategory": submission.categories[0]})
        if submission.content_rights is None:
            blocked.append("contentRightsDeclaration: the submission states no content_rights")
        else:
            add("apps", None, {"contentRightsDeclaration": submission.content_rights})
        if not submission.advisory_asc:
            blocked.append("age rating: the live API's keys need advisory_asc in the submission")
        else:
            merged = {**submission.advisory, **submission.advisory_asc}
            add("ageRatingDeclarations", None, {key: merged[key] for key in AGE_RATING_KEYS})
        # INT-502 legal review B5/R1: one hold, read here and by the EAS render.
        if submission.review_notes_hold is None:
            add("appStoreReviewDetails", None, {"notes": submission.review_notes})
        else:
            blocked.append(
                "appStoreReviewDetails.notes: held until the notes are true of the store "
                f"build ({submission.review_notes_hold}; legal review B5)"
            )
    if "copyright" in apple:
        add("appStoreVersions", None, {"copyright": apple["copyright"]})

    blocked.append(
        "App Privacy: no App Store Connect API resource; the owner enters it in the web UI "
        "from docs/legal/drafts/store/privacy-answers.draft.yaml (HB-L21(a), HB-A12)"
    )
    blocked.append(
        "whatsNew: not available for an app's first version; a later version adds "
        "releaseNotes to the served listing"
    )
    blocked.extend(
        _asset_blocks(asc_assets.load_manifest(manifest or asc_assets.MANIFEST), locales)
    )
    return Plan(tuple(steps), values, tuple(blocked), (_export_compliance(repo),))


def render_plan(plan: Plan) -> str:
    """Field names, notes and blocked fields; never a value."""
    lines = ["DRY RUN — nothing is sent to App Store Connect. Field names only."]
    for step in plan.steps:
        where = f"{step.resource}[{step.locale}]" if step.locale else step.resource
        lines.append(f"PLAN {where} {','.join(step.fields)}")
    lines.extend(f"NOTE {note}" for note in plan.notes)
    lines.extend(f"BLOCKED {reason}" for reason in plan.blocked)
    return "\n".join(lines) + "\n"
