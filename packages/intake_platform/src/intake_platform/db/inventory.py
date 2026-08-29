"""Invariant 18 — every new data field carries the inventory annotation
{category, purpose, basis, retention, recipients} or the schema test fails.

The annotation rides in ``Column.info`` so it lives beside the column it
describes and drifts with a diff, not a wiki. tests/data/test_inventory.py is
the enforcing gate; the VERBİS inventory export (files/06 §9) is generated
from the same metadata rather than assembled by hand.

Retention strings quote the files/06 §3 matrix; bases name their KVKK ground.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "INVENTORY_FIELDS",
    "INVENTORY_KEY",
    "InventoryAnnotation",
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
REC_GUARDIAN_INTERNAL = (
    "internal services only while the guardian_link gate is shut; no recipient is defined "
    "beyond the PHI boundary until counsel answers"
)
