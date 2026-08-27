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
    "shares",
    "documents",
    "events",
    "audit_chain",
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
