"""INT-482 — the store-neutral privacy answer sheet, derived from the inventory.

GitHub #825 asks for the App Privacy and Data safety answers *"derived from the
data inventory annotations"*. :mod:`intake_platform.store.declaration` already
folds those facts into a store's form, but only through a committed snapshot of
the vendor's taxonomy, and HB-A12 keeps that directory empty. So nothing could
be reviewed before the snapshot lands, and the legal lane would meet the
answers for the first time on the submission screen.

This module is the step before the taxonomy, and it is useful on its own: one
row per inventory fact (:func:`~intake_platform.store.facts.data_facts`), with
the store-relevant questions answered **in our words** — is it stored, does it
leave the handset, who can end up holding it, can the patient delete it, and
which determination is still open. It names no vendor data type, because those
are the vendors' published words (HB-A12) and are applied by ``declaration``.

Two directions are closed, as in ``declaration``: :func:`check_sheet` refuses a
row with no fact behind it and a fact with no row, so the committed draft can
be compared with this derivation and can never be edited into disagreement
with the schema. ``python -m intake_platform.store.answers`` prints the sheet
for regeneration.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

import yaml

from intake_platform.db.inventory import REC_ON_DEVICE
from intake_platform.store.facts import OFF_SCHEMA_FLOWS, DataFact, data_facts

__all__ = [
    "CAVEATS",
    "OPEN_DETERMINATIONS",
    "PRODUCT_ANSWERS",
    "STATUS",
    "ProductAnswer",
    "answer_row",
    "answer_sheet",
    "check_sheet",
    "main",
    "render_yaml",
]

#: The review state of every answer here. The legal-reviewer runs on the PR;
#: nothing in this sheet is submitted until that review and HB-L21 close.
STATUS: Final[str] = "pending legal-lane review"

#: Determinations the inventory cannot make, keyed by the fact they hang on.
#: An ``awaiting-human`` annotation adds its own entry (see :func:`answer_row`).
OPEN_DETERMINATIONS: Final[Mapping[str, tuple[str, ...]]] = {
    "flow:voice_audio": (
        "HB-L21(a): whether audio that is transmitted for transcription and never "
        "written counts as collected on each store's form",
    ),
    "flow:phone_sign_in": (
        "INT-358: the SMS vendor, its DPA and the KVKK m.9 cross-border decision; until "
        "the owner records them no vendor is admitted and phone sign-in answers 503",
        "counsel: whether a phone number used to sign in to a health intake app is "
        "health data under KVKK m.6 (question 16 of the INT-358 counsel brief)",
    ),
}

_AWAITING = "awaiting-human"
_DELETABLE = "patient-deletable"


@dataclass(frozen=True)
class ProductAnswer:
    """A whole-product answer, with the files that make it true."""

    answer_id: str
    answer: str
    sources: tuple[str, ...]


#: Answers about the product rather than one fact. Each names the files a test
#: re-reads (tests/legal/test_store_privacy_answers.py), so none is asserted
#: from memory.
PRODUCT_ANSWERS: Final[tuple[ProductAnswer, ...]] = (
    ProductAnswer(
        "tracking",
        "none: the app asks for no tracking authorisation and links no "
        "tracking-transparency module",
        ("apps/mobile/app.json", "apps/mobile/package.json"),
    ),
    ProductAnswer(
        "advertising",
        "none: no inventory purpose is advertising or marketing",
        ("packages/intake_platform/src/intake_platform/store/facts.py",),
    ),
    ProductAnswer(
        "encryption_in_transit",
        "yes: the production build talks to the API over https only",
        ("apps/mobile/eas.json",),
    ),
    ProductAnswer(
        "deletion",
        "yes: the patient requests deletion in the app (Profilim, Verileriniz); the "
        "server runs it after a grace period, then crypto-shreds",
        ("apps/mobile/src/lib/dsar/requests.ts", "services/api/src/intake_api/dsar/router.py"),
    ),
    ProductAnswer(
        "health_platform",
        "Apple Health and Health Connect data is read only and never written back; it "
        "stays on the handset unless the patient adds a summary to the note",
        ("apps/mobile/src/lib/health/healthKitConnector.ts",),
    ),
)

#: What a reader must know before using any answer.
CAVEATS: Final[Mapping[str, str]] = {
    "synthetic_scope": (
        "Until an in-country host or counsel's cross-border decision exists (HB-I5, "
        "HB-L11), the production host receives simulated patients only "
        "(docs/release/production-checklist.md). These answers describe the product as "
        "built. They do not say that real patient data is processed today, and no public "
        "release may go live while that scope holds."
    ),
    "vendor_vocabulary": (
        "No vendor data type is named here. A row becomes an App Privacy type or a Data "
        "safety category only through intake_platform.store.declaration and a committed "
        "snapshot of the vendor's form (HB-A12)."
    ),
    "seller_identity": (
        "The seller's legal entity, privacy-policy URL and support contact are owed by "
        "HB-L21(e); the privacy policy itself is the unsigned gizlilik document (HB-L27)."
    ),
}


def _deletion(fact: DataFact) -> str:
    if not fact.persisted:
        return "nothing is stored"
    deletable = [_DELETABLE in retention for retention in fact.retentions]
    if all(deletable):
        return "yes"
    if any(deletable):
        return "partly: see retentions"
    return "no: kept for the period in retentions"


def _open(fact: DataFact) -> list[str]:
    found = list(OPEN_DETERMINATIONS.get(fact.fact_id, ()))
    for field_name, values in (
        ("basis", fact.bases),
        ("retention", fact.retentions),
        ("recipients", fact.recipients),
    ):
        if any(_AWAITING in value for value in values):
            found.append(f"counsel: the {field_name} is awaiting-human in the inventory")
    return found


def answer_row(fact: DataFact) -> dict[str, Any]:
    """One fact, with the store-relevant questions answered in our words."""
    return {
        "inventory": fact.fact_id,
        "category": fact.category,
        "stored": fact.persisted,
        "leaves_device": any(r != REC_ON_DEVICE for r in fact.recipients),
        "shared": fact.sharing.value,
        "patient_deletion": _deletion(fact),
        "purposes": list(fact.purposes),
        "bases": list(fact.bases),
        "retentions": list(fact.retentions),
        "recipients": list(fact.recipients),
        # How many columns the fact folds; the names are in facts.data_facts().
        "columns": len(fact.columns),
        "open_determinations": _open(fact),
    }


def answer_sheet(facts: Sequence[DataFact] | None = None) -> dict[str, Any]:
    """The whole sheet, as plain data, sorted and deterministic."""
    rows = facts if facts is not None else data_facts()
    return {
        "provenance": {
            "issue": "INT-482",
            "status": STATUS,
            "derived_from": "intake_platform.store.facts.data_facts",
            "regenerate": "uv run python -m intake_platform.store.answers",
        },
        "caveats": [{"id": key, "text": text} for key, text in CAVEATS.items()],
        "product": [
            {"id": row.answer_id, "answer": row.answer, "sources": list(row.sources)}
            for row in PRODUCT_ANSWERS
        ],
        "answers": [answer_row(fact) for fact in rows],
        "not_declared": [
            {
                "flow": flow.flow_id,
                "reason": "switched off in the shipped configuration; "
                "intake_platform.store.facts.inactive_flow_drift fails the day it is on",
            }
            for flow in OFF_SCHEMA_FLOWS.values()
            if not flow.active
        ],
    }


#: Every key a row carries; a row missing one is refused, not defaulted.
_REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "inventory",
    "category",
    "stored",
    "leaves_device",
    "shared",
    "patient_deletion",
    "purposes",
    "bases",
    "retentions",
    "recipients",
    "columns",
    "open_determinations",
)


def check_sheet(
    sheet: Mapping[str, Any], facts: Sequence[DataFact] | None = None
) -> tuple[str, ...]:
    """Every disagreement between ``sheet`` and the inventory, or ``()``."""
    expected = {fact.fact_id: answer_row(fact) for fact in (facts or data_facts())}
    errors: list[str] = []
    seen: set[str] = set()
    for row in sheet.get("answers", []):
        missing = [key for key in _REQUIRED_KEYS if key not in row]
        if missing:
            errors.append(f"{row.get('inventory', '<no inventory id>')}: missing {missing}")
            continue
        fact_id = row["inventory"]
        if fact_id not in expected:
            errors.append(f"{fact_id}: no inventory fact behind this answer")
            continue
        seen.add(fact_id)
        for key, value in expected[fact_id].items():
            if row[key] != value:
                errors.append(f"{fact_id}: {key} disagrees with the inventory")
    errors.extend(
        f"{fact_id}: inventory fact with no answer" for fact_id in sorted(set(expected) - seen)
    )
    return tuple(errors)


def render_yaml(sheet: Mapping[str, Any]) -> str:
    return yaml.safe_dump(dict(sheet), allow_unicode=True, sort_keys=False, width=88)


def main() -> int:
    sys.stdout.write(render_yaml(answer_sheet()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
