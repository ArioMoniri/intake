"""INT-224 — "checklists as tests where automatable", and blocked where not.

The acceptance line is deliberately two-sided, and the second side is the one
that keeps this file honest. A store-compliance checklist is normally a
document full of paraphrased vendor policy that nobody re-reads after the
first submission. Two rules stop that here, and both are tests:

1. **A row that carries a check must cite a file in this repo** that states the
   obligation. Not a memory of a policy page — a path.
2. **A row whose obligation is a vendor's own published requirement may cite
   nothing at all.** It is marked ``vendor_published`` and carries a
   HUMAN_BLOCKERS id instead, because paraphrasing Apple's or Google's current
   wording is the same failure as inventing a clinical threshold: authoritative
   to every later reader, and no diff makes it look wrong. Those rows report
   BLOCKED for as long as HB-A12 is open, and BLOCKED is a verdict, not a pass.

So the automatable rows below are exactly the ones whose obligation this repo
already states in its own committed words — invariant 18, invariant 20,
ADR-022's verbatim App Review 1.4.1 quotation, and files/00 §2's ruling on the
Clinical Health Records capability.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

from intake_platform.flags import SAFETY_FLAG_DEFAULTS
from intake_platform.legal import claims
from intake_platform.store import facts as facts_mod
from intake_platform.store import listing as listing_mod
from intake_platform.store import taxonomy as taxonomy_mod
from intake_platform.store.declaration import build_declaration

__all__ = [
    "CHECKLIST",
    "CheckContext",
    "CheckResult",
    "ChecklistItem",
    "Verdict",
    "run_checklist",
]


class Verdict(StrEnum):
    SATISFIED = "satisfied"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CheckContext:
    repo: Path

    @property
    def app_json(self) -> Path:
        return self.repo / "apps" / "mobile" / "app.json"

    @property
    def locales(self) -> tuple[Path, ...]:
        base = self.repo / "apps" / "mobile" / "src" / "locales"
        return (base / "app-tr.json", base / "app-en.json")


@dataclass(frozen=True)
class CheckResult:
    verdict: Verdict
    detail: str


@dataclass(frozen=True)
class ChecklistItem:
    item_id: str
    store: str  # "apple" | "google" | "iarc" | "both"
    obligation: str
    #: A repo path stating the obligation, for rows we can source ourselves.
    source: str
    #: A HUMAN_BLOCKERS id, for rows nobody can close yet.
    blocker: str
    #: True when the obligation is a vendor's own published requirement, which
    #: may never be paraphrased from memory.
    vendor_published: bool
    check: Callable[[CheckContext], CheckResult] | None


# --- the automatable checks ------------------------------------------------------------


def _check_no_performance_claim(ctx: CheckContext) -> CheckResult:
    hits = claims.scan_declared_trees(ctx.repo)
    if hits:
        return CheckResult(
            Verdict.FAILED,
            "performance-claim patterns in the scanned trees: "
            + "; ".join(f"{hit.path}:{hit.line_no} [{hit.pattern}]" for hit in hits),
        )
    trees = ", ".join(tree.path for tree in claims.SCANNED_TREES)
    return CheckResult(Verdict.SATISFIED, f"no performance-claim pattern in {trees}")


def _check_no_device_claim(ctx: CheckContext) -> CheckResult:
    if SAFETY_FLAG_DEFAULTS["device_functions"]:
        return CheckResult(Verdict.FAILED, "device_functions no longer defaults off (invariant 18)")
    try:
        listings = listing_mod.load_all_listings(listing_mod.listing_dir(ctx.repo))
    except listing_mod.StoreListingMissingError:
        return CheckResult(
            Verdict.BLOCKED,
            "device_functions defaults off and no listing copy exists to scan yet",
        )
    findings = [
        f"{listing.path.name}:{finding.field} [{finding.detail}]"
        for listing in listings
        for finding in listing_mod.gate_listing(listing)
        if finding.kind == "device_claim"
    ]
    if findings:
        return CheckResult(Verdict.FAILED, "device-function claims: " + "; ".join(findings))
    return CheckResult(Verdict.SATISFIED, f"{len(listings)} listing(s) claim no gated function")


def _check_clinical_health_records_not_declared(ctx: CheckContext) -> CheckResult:
    mobile = ctx.repo / "apps" / "mobile"
    offenders = [
        str(path.relative_to(ctx.repo))
        for path in sorted(mobile.rglob("*"))
        if path.is_file()
        and path.suffix in {".json", ".js", ".ts", ".tsx"}
        and "healthkit.access" in path.read_text(encoding="utf-8", errors="ignore").lower()
    ]
    if offenders:
        return CheckResult(Verdict.FAILED, f"clinical records capability declared in {offenders}")
    return CheckResult(Verdict.SATISFIED, "no clinical-records entitlement anywhere in apps/mobile")


def _check_permissions_have_an_inventory_row(ctx: CheckContext) -> CheckResult:
    unclassified = facts_mod.unclassified_permissions(ctx.app_json, ctx.locales)
    if unclassified:
        return CheckResult(Verdict.FAILED, f"no inventory row for {list(unclassified)}")
    declared = facts_mod.declared_app_permissions(ctx.app_json, ctx.locales)
    return CheckResult(Verdict.SATISFIED, f"{len(declared)} declared capabilities all classified")


def _check_inactive_flows_stay_inactive(ctx: CheckContext) -> CheckResult:
    drift = facts_mod.inactive_flow_drift(ctx.app_json)
    if drift:
        return CheckResult(
            Verdict.FAILED,
            f"flows declared inactive that the shipped config switched on: {list(drift)}",
        )
    return CheckResult(Verdict.SATISFIED, "every flow declared inactive is still switched off")


def _check_labels_derive_from_the_inventory(ctx: CheckContext) -> CheckResult:
    directory = taxonomy_mod.taxonomy_dir(ctx.repo)
    snapshots = sorted(directory.glob("*.yaml")) if directory.is_dir() else []
    if not snapshots:
        return CheckResult(
            Verdict.BLOCKED,
            "the derivation is wired and exercised; no vendor form taxonomy is "
            "committed, so no label renders (HB-A12)",
        )
    rendered: list[str] = []
    for snapshot in snapshots:
        taxonomy = taxonomy_mod.load_taxonomy(snapshot)
        rows = build_declaration(taxonomy, facts_mod.data_facts())
        rendered.append(f"{snapshot.stem}: {len(rows)} row(s)")
    return CheckResult(Verdict.SATISFIED, "; ".join(rendered))


def _check_listing_is_hash_bound(ctx: CheckContext) -> CheckResult:
    try:
        listings = listing_mod.load_all_listings(listing_mod.listing_dir(ctx.repo))
    except listing_mod.StoreListingMissingError:
        return CheckResult(
            Verdict.BLOCKED,
            "the loader binds a sha256 over the file bytes; no listing copy exists "
            "to bind yet (HB-L21)",
        )
    unbound = [listing.path.name for listing in listings if len(listing.text_hash) != 64]
    if unbound:
        return CheckResult(Verdict.FAILED, f"listings without a bound hash: {unbound}")
    return CheckResult(Verdict.SATISFIED, f"{len(listings)} listing(s) hash-bound to their bytes")


#: A declared sensor permission and the shipped module that uses it.
#:
#: CHANGED AT INT-138. This rule used to assert that the manifest declared NO
#: camera permission at all, on the ground that the product had no video path —
#: true until the records screen gained a still capture of the patient's own
#: report. The obligation was never "no camera"; it is *no sensor the product
#: has no code path for*, which is what a store reviewer actually asks. So the
#: rule now demands the path rather than the absence, which also catches the
#: case the old form could not: a permission that outlives the feature it was
#: added for.
SENSOR_PERMISSION_PATHS: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(
    {
        "android.permission.CAMERA": (
            "apps/mobile/src/app/(tabs)/records.tsx",
            "launchCameraAsync",
        ),
        "android.permission.RECORD_AUDIO": (
            "apps/mobile/src/lib/livekit/nativeRoom.ts",
            "microphone",
        ),
    }
)

#: Name fragments that make a permission a SENSOR for this rule's purposes. A
#: declared permission matching one of these with no row above fails: the point
#: is that a new sensor cannot arrive unnoticed.
_SENSOR_MARKERS: Final[tuple[str, ...]] = ("CAMERA", "MICROPHONE", "RECORD_AUDIO", "LOCATION")


def _check_no_sensor_without_a_code_path(ctx: CheckContext) -> CheckResult:
    config = json.loads(ctx.app_json.read_text(encoding="utf-8"))["expo"]
    declared = sorted(set(config.get("android", {}).get("permissions", [])))
    sensors = [p for p in declared if any(marker in p for marker in _SENSOR_MARKERS)]
    unpathed: list[str] = []
    for permission in sensors:
        row = SENSOR_PERMISSION_PATHS.get(permission)
        if row is None:
            unpathed.append(f"{permission} (no recorded path)")
            continue
        relative, token = row
        module = ctx.repo / relative
        if not module.exists() or token not in module.read_text(encoding="utf-8"):
            unpathed.append(f"{permission} ({relative} no longer calls {token})")
    if unpathed:
        return CheckResult(
            Verdict.FAILED,
            f"the manifest asks for a sensor the product has no path for: {unpathed}",
        )
    return CheckResult(
        Verdict.SATISFIED,
        f"every declared sensor has a shipped code path: {sensors}",
    )


# --- the checklist ----------------------------------------------------------------------

CHECKLIST: Final[tuple[ChecklistItem, ...]] = (
    ChecklistItem(
        item_id="apple/no-unvalidatable-accuracy-claim",
        store="apple",
        obligation="No sensitivity, specificity, AUROC, WER or accuracy figure reaches a "
        "store listing or the legal and regulatory trees.",
        source="docs/adr/ADR-022-no-accuracy-claims.md",
        blocker="",
        vendor_published=False,
        check=_check_no_performance_claim,
    ),
    ChecklistItem(
        item_id="both/no-device-function-claim",
        store="both",
        obligation="No listing describes automated urgency direction, automated "
        "instrument interpretation or the acoustic module: device_functions stays off "
        "without a recorded CE certificate or clinical-investigation approval id.",
        source="CLAUDE.md",
        blocker="",
        vendor_published=False,
        check=_check_no_device_claim,
    ),
    ChecklistItem(
        item_id="apple/clinical-health-records-not-declared",
        store="apple",
        obligation="The Clinical Health Records capability is not declared: it is "
        "CA/UK/US only, non-functional in Türkiye, and a rejection risk if declared "
        "but unused.",
        source="files/00_STATE.md",
        blocker="",
        vendor_published=False,
        check=_check_clinical_health_records_not_declared,
    ),
    ChecklistItem(
        item_id="both/every-capability-has-an-inventory-row",
        store="both",
        obligation="Every platform capability the shipped manifest asks for is "
        "accounted for by an inventory row, or is recorded in writing as carrying no "
        "personal data.",
        source="packages/intake_platform/src/intake_platform/db/inventory.py",
        blocker="",
        vendor_published=False,
        check=_check_permissions_have_an_inventory_row,
    ),
    ChecklistItem(
        item_id="both/inactive-flows-stay-inactive",
        store="both",
        obligation="A data flow the declaration calls inactive is still switched off "
        "in the shipped configuration.",
        source="apps/mobile/src/lib/telemetry/expoTelemetry.ts",
        blocker="",
        vendor_published=False,
        check=_check_inactive_flows_stay_inactive,
    ),
    ChecklistItem(
        item_id="both/labels-derive-from-the-inventory",
        store="both",
        obligation="The privacy labels are generated from the single data inventory, "
        "so they cannot drift from what the product actually processes.",
        source="files/06_COMPLIANCE_TR.md",
        blocker="HB-A12",
        vendor_published=False,
        check=_check_labels_derive_from_the_inventory,
    ),
    ChecklistItem(
        item_id="both/listing-renders-from-docs-legal-hash-bound",
        store="both",
        obligation="Listing copy renders only from docs/legal with hash binding, so "
        "what was published is provable.",
        source="packages/intake_platform/src/intake_platform/legal/strings.py",
        blocker="HB-L21",
        vendor_published=False,
        check=_check_listing_is_hash_bound,
    ),
    ChecklistItem(
        item_id="apple/no-sensor-the-product-cannot-use",
        store="apple",
        obligation="The manifest asks for no sensor the product has no code path for; "
        "each declared sensor names the module that uses it.",
        source="packages/intake_platform/src/intake_platform/store/checklist.py",
        blocker="",
        vendor_published=False,
        check=_check_no_sensor_without_a_code_path,
    ),
    ChecklistItem(
        item_id="apple/app-privacy-answers",
        store="apple",
        obligation="Answer Apple's App Privacy questions with the data types its "
        "current form defines, in the form's own vocabulary.",
        source="",
        blocker="HB-A12",
        vendor_published=True,
        check=None,
    ),
    ChecklistItem(
        item_id="apple/health-sections-of-app-review",
        store="apple",
        obligation="Meet whatever the current health sections of the App Review "
        "Guidelines require of an app that reads HealthKit data.",
        source="",
        blocker="HB-A12",
        vendor_published=True,
        check=None,
    ),
    ChecklistItem(
        item_id="google/data-safety-answers",
        store="google",
        obligation="Answer Google Play's Data safety form with the categories its "
        "current form defines, including whether an ephemeral flow counts as collected.",
        source="",
        blocker="HB-A12",
        vendor_published=True,
        check=None,
    ),
    ChecklistItem(
        item_id="google/health-apps-policy",
        store="google",
        obligation="Establish whether this product falls inside Google Play's Health "
        "apps policy and satisfy whatever that policy currently requires.",
        source="",
        blocker="HB-A12",
        vendor_published=True,
        check=None,
    ),
    ChecklistItem(
        item_id="iarc/content-rating-questionnaire",
        store="iarc",
        obligation="Complete the IARC content-rating questionnaire; several of its "
        "answers are legal statements about the product rather than descriptions.",
        source="",
        blocker="HB-A12",
        vendor_published=True,
        check=None,
    ),
    ChecklistItem(
        item_id="both/ephemeral-audio-collection-determination",
        store="both",
        obligation="Decide whether microphone audio that is transmitted for "
        "transcription and never written counts as collected on each store's form.",
        source="",
        blocker="HB-L21",
        vendor_published=True,
        check=None,
    ),
    ChecklistItem(
        item_id="both/seller-identity-and-contacts",
        store="both",
        obligation="Name the seller's legal entity, the privacy-policy URL, the "
        "support contact and the KVKK contact that appear on both listings.",
        source="",
        blocker="HB-L21",
        vendor_published=True,
        check=None,
    ),
)


def run_checklist(ctx: CheckContext) -> tuple[tuple[ChecklistItem, CheckResult], ...]:
    """Every row with its verdict, in declaration order."""
    results: list[tuple[ChecklistItem, CheckResult]] = []
    for item in CHECKLIST:
        if item.check is None:
            results.append(
                (
                    item,
                    CheckResult(
                        Verdict.BLOCKED,
                        f"a published vendor requirement nobody may paraphrase — {item.blocker}",
                    ),
                )
            )
            continue
        results.append((item, item.check(ctx)))
    return tuple(results)
