"""INT-030 — the invariant-18 schema test: every column of every table carries
a complete data-inventory annotation {category, purpose, basis, retention,
recipients} (CLAUDE.md invariant 18; files/06 §3 retention matrix; VERBİS
inventory export in files/06 §9 is generated from these annotations).

A column without an annotation is a field nobody can defend to the Board:
no recorded purpose, no lawful basis, no retention clock. The test makes the
omission a build failure instead of an audit finding.
"""

from __future__ import annotations

import pytest
from intake_platform.db import models
from intake_platform.db.inventory import INVENTORY_FIELDS, INVENTORY_KEY, inv
from sqlalchemy import Table

EXPECTED_TABLES = {
    "tenants",
    "patients",
    "sessions",
    "slots",
    "notes",
    "consents",
    "guardian_links",
    "shares",
    # INT-150 — one tokenized, expiring, countable clinician grant over a
    # share. It holds no token (a SHA-256 fingerprint), no OTP state (that
    # is the shared Redis gate) and no section list (that stays on shares).
    "doctor_links",
    "documents",
    "events",
    "audit_chain",
    # INT-037 — data-subject rights
    "dsar_requests",
    "dsar_rectifications",
    # INT-240 — the satisfaction free text, split out of events.payload so
    # that column's "id-shaped values only, no PHI" declaration stays true
    # (invariant 6)
    "csat_texts",
    # INT-141 — notification opt-out and quiet hours
    "notification_preferences",
    # INT-170 — the Loop 1 learning store: the overlay version header and the
    # patient's CONFIRMED learned facts. There is no third table: an
    # unconfirmed candidate has nowhere to be written (invariant 12).
    "patient_overlays",
    "overlay_facts",
    # Owner directive — the finished previsit as a hospital receives it: one
    # frozen, versioned, envelope-encrypted document per completed previsit.
    # Its recipients annotation is the awaiting-human one: no DPA names a
    # hospital reader yet, so no recipient beyond the PHI boundary is defined.
    "previsit_outputs",
    # INT-123 — the pgvector record index: one CONFIRMED record item's vector
    # and source box per row, in one patient's RLS namespace. No item text.
    "record_embeddings",
    # INT-582 (D36) — the PUBLIC half of each patient passkey: credential id,
    # public key, counter, backup flags, an opaque handle. A new category
    # (authentication_credential) on the legal-obligation (KVKK m.12) basis.
    "patient_passkeys",
}


def _tables() -> dict[str, Table]:
    return dict(models.Base.metadata.tables)


def test_all_core_tables_are_registered() -> None:
    assert set(_tables()) == EXPECTED_TABLES


def test_every_column_of_every_table_carries_a_complete_inventory_annotation() -> None:
    missing: list[str] = []
    for table_name, table in sorted(_tables().items()):
        for column in table.columns:
            annotation = column.info.get(INVENTORY_KEY)
            where = f"{table_name}.{column.name}"
            if not isinstance(annotation, dict):
                missing.append(f"{where}: no inventory annotation at all")
                continue
            if set(annotation) != set(INVENTORY_FIELDS):
                missing.append(
                    f"{where}: inventory keys {sorted(annotation)} != {sorted(INVENTORY_FIELDS)}"
                )
                continue
            for field_name in INVENTORY_FIELDS:
                value = annotation[field_name]
                if not isinstance(value, str) or not value.strip():
                    missing.append(f"{where}: inventory field {field_name!r} is empty")
    assert not missing, "invariant 18 — columns without a defensible inventory:\n" + "\n".join(
        missing
    )


def test_clinical_payload_columns_are_marked_special_category() -> None:
    """notes.payload and slots.value are the two envelope-bearing clinical
    columns; their KVKK category must say so (m.6 special category), because
    the retention engine (INT-036) and the DSAR export both route on it."""
    tables = _tables()
    for table_name, column_name in (("notes", "payload"), ("slots", "value")):
        annotation = tables[table_name].columns[column_name].info[INVENTORY_KEY]
        assert annotation["category"] == "special_category_health"
        assert "crypto-shred" in annotation["retention"]


def test_passkey_columns_carry_the_d36_annotation_and_hold_no_secret() -> None:
    """INT-582 (D36): the new personal-data category is annotated on every
    column that holds passkey material — the authenticator category, the
    KVKK m.12 security basis, the patient-deletable record clock, and a
    recipient list with no clinic in it. The near miss: the table has no
    column a secret, an identifier or a device model could sit in."""
    table = _tables()["patient_passkeys"]
    material = (
        "credential_id",
        "public_key",
        "user_handle",
        "sign_count",
        "backup_eligible",
        "backup_state",
        "last_used_at",
        "recovery_requested_at",
    )
    for name in material:
        annotation = table.columns[name].info[INVENTORY_KEY]
        assert annotation["category"] == "authentication_credential", name
        assert annotation["basis"].startswith("KVKK m.5/2-ç"), name
        assert "KVKK m.12/1" in annotation["basis"], name
        assert "patient-deletable" in annotation["retention"], name
        assert "never shared with a clinic" in annotation["recipients"], name
    assert not {"private_key", "secret", "phone", "aaguid", "name", "device_name"} & set(
        table.columns.keys()
    )


def test_inv_refuses_an_empty_field() -> None:
    """The helper is the write path of invariant 18: a half-filled annotation
    must be unwritable, not merely detectable later."""
    with pytest.raises(ValueError, match="must not be empty"):
        inv("operational_metadata", "  ", "a-basis", "a-retention", "a-recipient")


def test_audit_columns_declare_the_worm_retention() -> None:
    tables = _tables()
    for column in tables["audit_chain"].columns:
        annotation = column.info[INVENTORY_KEY]
        assert annotation["category"] == "audit_trail"
        assert "10" in annotation["retention"], "consent & audit: 10 years (06 §3)"
