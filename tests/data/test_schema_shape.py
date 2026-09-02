"""INT-030 — schema shape, unit lane (no docker).

What this file pins:
- the pseudonymised-patients design: no raw-identifier column exists anywhere
  in the model metadata, and ``patients`` is exactly {id, tenant_id,
  pseudonym, created_at} — the pseudonym is the Tokenizer's output
  (intake_platform.tokenization); the raw value lives only in identity_vault;
- envelope columns: notes.payload and sensitive slot values are EncryptedField
  JSON (intake_platform.envelope), never plaintext, and the JSON helpers
  roundtrip losslessly through the real cipher;
- documents reference the object store — no inline payload column exists;
- the migration's security DDL, statically: RLS enabled AND forced on every
  tenant-scoped table, a tenant-isolation policy plus the clinician read
  policy, least-privilege roles, INSERT-only audit_chain, and the guarded
  pgaudit probe (the live proof runs in tests/data/test_rls.py).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from intake_platform.db import models
from intake_platform.db.envelope_json import encrypted_field_from_json, encrypted_field_to_json
from intake_platform.envelope import EncryptedField, EnvelopeCipher, FileKekProvider
from sqlalchemy import LargeBinary
from sqlalchemy.dialects.postgresql import JSONB

REPO = Path(__file__).resolve().parents[2]

TENANT_SCOPED = (
    "patients",
    "sessions",
    "slots",
    "notes",
    "consents",
    "shares",
    "documents",
    "events",
    # INT-037 — the DSAR tracker and the rectification addenda
    "dsar_requests",
    "dsar_rectifications",
    # INT-240 — the satisfaction free text (envelope-encrypted; erased by the
    # session and event cascades rather than by a sweeper of its own)
    "csat_texts",
    # INT-141 — the patient's notification opt-out and quiet window
    "notification_preferences",
    # INT-170 — the PatientOverlay version header and its confirmed facts
    # (the fact value is envelope-encrypted, like notes.payload)
    "patient_overlays",
    "overlay_facts",
)

CLINICIAN_READ = ("patients", "sessions", "slots", "notes", "documents")

# Column names that would mean a direct identifier landed in an app table
# (invariant 14: identifiers tokenized; the vault holds the raw value).
FORBIDDEN_COLUMN_NAMES = frozenset(
    {
        "name",
        "first_name",
        "last_name",
        "full_name",
        "phone",
        "phone_number",
        "msisdn",
        "telefon",
        "tckn",
        "tc_kimlik",
        "tc_kimlik_no",
        "national_id",
        "address",
        "email",
        "birth_date",
        "date_of_birth",
        "text",
    }
)


def _migration_source() -> str:
    """The whole migration tree, not just INT-030's file: a tenant-scoped
    table added by a later revision must bring its own RLS, and a scan that
    only read 0001 would report the strongest possible pass for a table it
    never looked at."""
    candidates = sorted((REPO / "migrations" / "versions").glob("*.py"))
    assert candidates, "no migrations found under migrations/versions/"
    joined = "\n".join(path.read_text(encoding="utf-8") for path in candidates)
    assert "0001_int030" in joined, "the INT-030 migration file is missing"
    return joined


# --- model metadata ---------------------------------------------------------------


def test_no_table_defines_a_raw_identifier_column() -> None:
    offenders = [
        f"{table.name}.{column.name}"
        for table in models.Base.metadata.tables.values()
        for column in table.columns
        if column.name in FORBIDDEN_COLUMN_NAMES
    ]
    assert not offenders, (
        "raw-identifier-shaped column in an app table (identifiers are tokenized, "
        "invariant 14): " + ", ".join(offenders)
    )


def test_patients_is_pseudonym_only() -> None:
    columns = {column.name for column in models.Patient.__table__.columns}
    assert columns == {"id", "tenant_id", "pseudonym", "created_at"}, (
        "patients must stay pseudonym-only — a new column here is a new place for identity to leak"
    )


def test_every_tenant_scoped_table_carries_tenant_id() -> None:
    for table_name in TENANT_SCOPED:
        table = models.Base.metadata.tables[table_name]
        column = table.columns["tenant_id"]
        fks = {fk.target_fullname for fk in column.foreign_keys}
        assert fks == {"tenants.id"}, f"{table_name}.tenant_id must reference tenants.id"
        assert not column.nullable, f"{table_name}.tenant_id must be NOT NULL for RLS"


def test_no_inline_payload_bytes_anywhere() -> None:
    binary = [
        f"{table.name}.{column.name}"
        for table in models.Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, LargeBinary)
    ]
    assert not binary, "document bytes belong in the object store, not a row: " + ", ".join(binary)
    document_columns = {column.name for column in models.Document.__table__.columns}
    assert "payload" not in document_columns and "content" not in document_columns
    assert "object_ref" in document_columns and "sha256" in document_columns


def test_envelope_bearing_columns_are_jsonb() -> None:
    assert isinstance(models.Note.__table__.columns["payload"].type, JSONB)
    assert isinstance(models.Slot.__table__.columns["value"].type, JSONB)
    assert isinstance(models.Event.__table__.columns["payload"].type, JSONB)


def test_slot_sensitivity_enum_decides_the_envelope() -> None:
    values = {member.value for member in models.SlotSensitivity}
    assert values == {"plain", "sensitive"}


# --- EncryptedField JSON helpers (what the JSONB carries) --------------------------


def test_encrypted_field_json_roundtrips_through_the_real_cipher() -> None:
    cipher = EnvelopeCipher(FileKekProvider())
    field = cipher.encrypt_field("tenant-a", b'{"summary_tr": "unit fixture body"}')
    payload = encrypted_field_to_json(field)
    # storable as JSONB, and lossless on the way back
    restored = encrypted_field_from_json(json.loads(json.dumps(payload)))
    assert restored == field
    assert cipher.decrypt_field("tenant-a", restored) == b'{"summary_tr": "unit fixture body"}'


def test_encrypted_field_json_never_carries_plaintext() -> None:
    cipher = EnvelopeCipher(FileKekProvider())
    field = cipher.encrypt_field("tenant-a", b"very-private-note-body")
    serialised = json.dumps(encrypted_field_to_json(field))
    assert "very-private-note-body" not in serialised


def test_encrypted_field_json_rejects_malformed_payloads() -> None:
    cipher = EnvelopeCipher(FileKekProvider())
    good = encrypted_field_to_json(cipher.encrypt_field("tenant-a", b"body"))
    with pytest.raises(ValueError, match="exactly"):
        encrypted_field_from_json({key: value for key, value in good.items() if key != "nonce"})
    with pytest.raises(ValueError, match="key_version"):
        encrypted_field_from_json({**good, "key_version": "1"})
    with pytest.raises(ValueError, match="key_version"):
        encrypted_field_from_json({**good, "key_version": True})
    with pytest.raises(ValueError, match="base64"):
        encrypted_field_from_json({**good, "nonce": "not*base64"})
    with pytest.raises(ValueError, match="string"):
        encrypted_field_from_json({**good, "wrapped_dek": 7})


def test_encrypted_field_json_shape_is_the_dataclass() -> None:
    cipher = EnvelopeCipher(FileKekProvider())
    payload = encrypted_field_to_json(cipher.encrypt_field("tenant-a", b"body"))
    assert set(payload) == {"key_version", "wrapped_dek", "nonce", "ciphertext"}
    assert isinstance(payload["key_version"], int)
    restored = encrypted_field_from_json(payload)
    assert isinstance(restored, EncryptedField)


# --- migration security DDL (static assertions; live proof in test_rls.py) ---------


def test_migration_enables_and_forces_rls_on_every_tenant_table() -> None:
    source = _migration_source()
    for table_name in TENANT_SCOPED:
        assert f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY" in source, table_name
        assert f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY" in source, table_name
        assert f"CREATE POLICY {table_name}_tenant_isolation ON {table_name}" in source
    # tenants itself is scoped by its own id
    assert "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY" in source
    assert "ALTER TABLE tenants FORCE ROW LEVEL SECURITY" in source


def test_migration_policies_read_the_tenant_guc_and_fail_closed() -> None:
    source = _migration_source()
    guc = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    assert guc in source, "policies must read app.tenant_id and see NULL (no rows) when unset"
    for table_name in TENANT_SCOPED:
        policy = re.search(
            rf"CREATE POLICY {table_name}_tenant_isolation ON {table_name}.*?(?=CREATE POLICY|"
            rf"ALTER TABLE|\Z)",
            source,
            re.S,
        )
        assert policy is not None, table_name
        assert "WITH CHECK" in policy.group(0), (
            f"{table_name}: without WITH CHECK a session can write another tenant's rows"
        )


def test_migration_defines_the_clinician_read_policy_shape() -> None:
    source = _migration_source()
    for table_name in CLINICIAN_READ:
        assert f"CREATE POLICY {table_name}_clinician_read ON {table_name}" in source
    assert "FOR SELECT TO clinician_ro" in source


def test_migration_creates_least_privilege_roles() -> None:
    source = _migration_source()
    for role in ("app_rw", "clinician_ro", "svc_audit_writer"):
        assert f"CREATE ROLE {role}" in source
    assert "GRANT SELECT, INSERT ON audit_chain TO svc_audit_writer" in source
    assert "GRANT SELECT, INSERT ON events TO app_rw" in source


def test_migration_grants_no_update_or_delete_on_append_only_tables() -> None:
    source = _migration_source()
    for line in source.splitlines():
        if "GRANT" not in line:
            continue
        for table_name in ("audit_chain", "events"):
            if f"ON {table_name}" in line:
                assert "UPDATE" not in line and "DELETE" not in line, (
                    f"append-only table {table_name} must never receive UPDATE/DELETE: {line!r}"
                )


def test_migration_probes_pgaudit_instead_of_failing_hard() -> None:
    source = _migration_source()
    assert "pg_available_extensions" in source, "pgaudit must be probed, not assumed"
    assert "CREATE EXTENSION IF NOT EXISTS pgaudit" in source
    assert "logger" in source, "an absent pgaudit must be logged loudly, never ignored silently"
