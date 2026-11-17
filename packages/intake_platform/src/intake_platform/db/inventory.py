"""Invariant 18 — every new data field carries the inventory annotation
{category, purpose, basis, retention, recipients} or the schema test fails.

The annotation rides in ``Column.info`` so it lives beside the column it
describes and drifts with a diff, not a wiki. tests/data/test_inventory.py is
the enforcing gate; the VERBİS inventory export (files/06 §9) is generated
from the same metadata rather than assembled by hand.

Retention strings quote the files/06 §3 matrix; bases name their KVKK ground.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, TypedDict

__all__ = [
    "BASIS_EVENTS_BY_TYPE",
    "BASIS_SATISFACTION_CONSENT",
    "EVENT_TYPE_BASES",
    "INVENTORY_FIELDS",
    "INVENTORY_KEY",
    "SUBJECT_DATA_CATEGORIES",
    "SUBJECT_ERASABLE_MARKERS",
    "InventoryAnnotation",
    "grants_subject_erasure",
    "holds_subject_data",
    "inv",
]

INVENTORY_KEY = "inventory"
INVENTORY_FIELDS = ("category", "purpose", "basis", "retention", "recipients")


class InventoryAnnotation(TypedDict):
    category: str
    purpose: str
    basis: str
    retention: str
    recipients: str


def inv(
    category: str, purpose: str, basis: str, retention: str, recipients: str
) -> dict[str, InventoryAnnotation]:
    """Build the ``Column.info`` payload; an empty field is refused here so a
    half-filled annotation cannot even be written, let alone merged."""
    for field_name, value in (
        ("category", category),
        ("purpose", purpose),
        ("basis", basis),
        ("retention", retention),
        ("recipients", recipients),
    ):
        if not value.strip():
            raise ValueError(f"inventory field {field_name!r} must not be empty (invariant 18)")
    annotation = InventoryAnnotation(
        category=category,
        purpose=purpose,
        basis=basis,
        retention=retention,
        recipients=recipients,
    )
    return {INVENTORY_KEY: annotation}


# --- KVKK categories ----------------------------------------------------------------

CAT_OPERATIONAL = "operational_metadata"
CAT_PSEUDONYM = "pseudonymised_identity"
CAT_HEALTH = "special_category_health"
CAT_CONSENT = "consent_record"
CAT_AUDIT = "audit_trail"
# INT-223: a guardian↔minor relationship is a family-status fact about two
# people, not a consent row and not a health fact — it gets its own category
# so the VERBİS export never files it under either.
CAT_GUARDIANSHIP = "guardianship_link"

# --- lawful bases (KVKK m.5/m.6) ------------------------------------------------------

BASIS_CONTRACT = "KVKK m.5/2-c — processing necessary for the service contract"
BASIS_HEALTH_CONSENT = "KVKK m.6 — special-category health data under açık rıza per consent scope"
BASIS_LEGAL_OBLIGATION = "KVKK m.5/2-ç — legal obligation (KVKK m.12 security; KSVY audit duties)"
# INT-536 (INT-529 F5, COUNSEL_BRIEF §2.9): both satisfaction write routes
# require the `satisfaction` consent scope (files/06 §2: açık rıza, default
# off; services/api/src/intake_api/satisfaction.py), so the score rests on
# açık rıza, never on the contract. The comment text is health data and keeps
# BASIS_HEALTH_CONSENT.
BASIS_SATISFACTION_CONSENT = (
    "KVKK m.5/1 — açık rıza per consent scope satisfaction (files/06 §2); "
    "both satisfaction write routes require the scope"
)
#: ``events`` holds rows of more than one purpose, and a column carries one
#: annotation, so its basis is stated per ``event_type``. Each one is enforced
#: on that type's write path. tests/data/test_satisfaction_basis.py holds every
#: ``Event(...)`` writer in the tree to a type declared here (INT-536).
EVENT_TYPE_BASES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "csat.v1": BASIS_SATISFACTION_CONSENT,
        "nps.v1": BASIS_SATISFACTION_CONSENT,
        "wait.v1": BASIS_CONTRACT,
    }
)
BASIS_EVENTS_BY_TYPE = "per event_type, enforced on each type's write path: " + "; ".join(
    f"{event_type} — {basis}" for event_type, basis in EVENT_TYPE_BASES.items()
)
# INT-224: crash and error diagnostics are the one off-schema flow whose KVKK
# ground no file in this repo states. The reporter ships inert (no default DSN)
# and the basis is refused rather than assumed — counsel names it before the
# flow may be declared active (HUMAN_BLOCKERS.md HB-L21).
BASIS_AWAITING_HUMAN_DIAGNOSTICS = (
    "awaiting-human — no file states the KVKK m.5 ground for crash and error "
    "diagnostics; counsel names it (HB-L21) before the reporter is given an endpoint"
)
# INT-223: persisting a guardian↔minor link is a new personal-data category,
# which CLAUDE.md makes a stop-and-ask. No ground is asserted here — the table
# ships behind the closed guardian_link gate until counsel names one
# (intake_platform.consent.minors POLICY_TABLE row ``guardian_link_basis``).
BASIS_AWAITING_HUMAN_GUARDIAN = (
    "awaiting-human — the KVKK m.5/m.6 ground for a guardian↔minor link is unassigned; "
    "counsel names it (policy row guardian_link_basis) before the guardian_link gate opens"
)

# --- retention (files/06 §3 matrix; enforced by INT-036) ------------------------------

RET_RECORD = "life of the record; patient-deletable, 30-day grace, then crypto-shred (06 §3)"
RET_CONSENT_AUDIT = "10 years for hospital tenants; WORM copy; audit is append-only (06 §3)"
RET_SHARE = "share expiry ≤ 72 h default; grant row retained with the record for audit (06 §3)"
RET_EVENTS = "telemetry window: 30 d hot / 1 y cold; PHI-free by construction (06 §3)"
RET_TENANT = "life of the tenant contract plus statutory retention on the DPA (06 §3)"
# INT-141: files/06 §3 has no row for a notification preference, and inventing
# a clock would be inventing a retention. It rides the record clock the matrix
# already defines, for a stated reason rather than by default.
RET_NOTIFICATION_PREFERENCE = (
    "life of the patient record, on the 06 §3 record clock: patient-deletable, "
    "30-day grace, then crypto-shred — a delivery preference cannot outlive the "
    "account it configures, and an account that is gone has nobody to message"
)
RET_DSAR = (
    "record of a KVKK m.11/m.13 rights exercise: kept with the consent & audit tier, "
    "10 years (06 §3), which also carries the DEST-2017 ≥ 3-year floor for the "
    "destruction records among them (06 §1 KVKK-7)"
)
# INT-240: files/06 §3 "Satisfaction: with account." — an EVENT-based clock
# rather than a duration: the row becomes due the moment the account is deleted
# and not before (retention/retention_policy.yaml data_class `satisfaction`,
# status: sourced, dsar_erasable: true). No survey cadence, sampling rate or
# window is invented here; the blueprint states none and this issue asks for none.
RET_SATISFACTION = (
    "with account: due the moment the account is deleted, never before; "
    "DSAR-erasable (06 §3 satisfaction row)"
)
# Owner directive (the previsit OUTPUT store): the frozen hospital-facing copy
# rides the files/06 §3 RECORD clock, and that is a reading of the matrix
# rather than a new period. The row is a projection of the note it derives
# from, it lives in the same database under the same tenant, and it is reached
# by the same DSAR erasure and the same crypto-shred; a derived copy that
# outlived the record it derives from would be the invention here, not this.
# What is NOT decided by this constant is the retention of the copy the
# HOSPITAL holds once it has fetched — that is a DPA clause, it is named per
# row in infra/previsit_output/recipients.yaml, and the registry refuses a row
# that does not name it.
RET_PREVISIT_OUTPUT = (
    "life of the record, on the 06 §3 record clock: patient-deletable, 30-day grace, "
    "then crypto-shred — a frozen projection of the note cannot outlive the note. "
    "The receiving hospital's own retention is a DPA clause named per recipient row "
    "(infra/previsit_output/recipients.yaml retention_ref), never a period set here"
)
# INT-223: files/06 §3 has no row for guardian linkage, and inventing one
# would be inventing a retention clock. The gate stays shut instead.
RET_AWAITING_HUMAN_GUARDIAN = (
    "awaiting-human — files/06 §3 holds no guardian-linkage row; counsel sets the period "
    "(policy row guardian_link_basis) and the gate stays shut until then"
)

# --- recipients ------------------------------------------------------------------------

REC_INTERNAL = "internal services only; never leaves the PHI boundary"
REC_CLINICIAN = "tenant clinicians via a consented share (Doctor Link / clinic console)"
REC_PATIENT_CLINICIAN = "the patient (own record) and tenant clinicians via consented share"
REC_AUDITOR = "supervisory authority or auditor on lawful request; WORM export"
# INT-224: the health-platform reads (HealthKit / Health Connect) never leave
# the handset. There is no recipient at all until the patient chooses to add a
# summary to the note, at which point notes.payload's own row applies.
REC_ON_DEVICE = (
    "nobody: the data stays on the patient's own device until the patient adds a "
    "summary to the note, from which point the notes.payload row governs"
)
# Owner directive: the previsit output exists TO BE fetched by a hospital
# system, but no DPA names one and no reader is approved, so there is no
# recipient beyond the PHI boundary to declare yet. Same shape as the guardian
# row above: the column ships annotated with the absence rather than with a
# recipient somebody assumed, and the recipient registry is empty so the
# read-back refuses everyone.
REC_HOSPITAL_SYSTEM_AWAITING_HUMAN = (
    "internal services only while the recipient registry is empty; the hospital system "
    "that will fetch this is defined by an executed DPA and a recorded tier-3 approval "
    "(infra/previsit_output/recipients.yaml), neither of which exists"
)
REC_GUARDIAN_INTERNAL = (
    "internal services only while the guardian_link gate is shut; no recipient is defined "
    "beyond the PHI boundary until counsel answers"
)

# --- what an annotation says about the data subject (INT-395) --------------------------
#
# The DSAR erasure and export are checked against these two readings, not
# against a hand-kept table list (tests/data/test_session_delete_contract.py):
# a new column annotated with one of these categories or clocks puts its table
# under the subject's KVKK m.11 access and erasure rights by that fact alone.

#: The categories that describe the data subject rather than the platform. A
#: column in one of them holds the subject's personal data, so the DSAR export
#: must answer for its table. Operational metadata and the audit trail are the
#: two categories that describe how the platform runs.
SUBJECT_DATA_CATEGORIES = frozenset({CAT_PSEUDONYM, CAT_HEALTH, CAT_CONSENT, CAT_GUARDIANSHIP})

#: The retention wording that gives the subject the erasure verb over a row:
#: the 06 §3 record clock's "patient-deletable" and the satisfaction row's
#: "DSAR-erasable". A clock carrying either puts its table on the DSAR erasure.
SUBJECT_ERASABLE_MARKERS = ("patient-deletable", "DSAR-erasable")


def grants_subject_erasure(retention: str) -> bool:
    """Whether a retention clock lets the data subject have the row erased."""
    return any(marker in retention for marker in SUBJECT_ERASABLE_MARKERS)


def holds_subject_data(annotation: Mapping[str, str]) -> bool:
    """Whether an annotated column holds the subject's personal data: it is in
    a subject category, or it sits on a clock the subject can erase (a row the
    subject may destroy is a row the subject may also see)."""
    return annotation["category"] in SUBJECT_DATA_CATEGORIES or grants_subject_erasure(
        annotation["retention"]
    )
