"""INT-170 — patient_overlays + overlay_facts: the Loop 1 learning store.

Two tables, and the table that is deliberately **absent** is as much of the
design as the two that are here.

- ``overlay_facts`` holds CONFIRMED learned facts only. There is no companion
  table for unconfirmed candidates and no nullable ``source`` column, because
  a nullable provenance is exactly the runtime check CLAUDE.md invariant 12
  refuses to depend on ("PatientOverlay facts require patient or clinician
  confirmation — type-level"). A ``FactCandidate`` is held on the patient's own
  device until they answer the confirmation card; only the answer is written
  here. Persisting unconfirmed proposals would additionally be a new category
  of personal data, which CLAUDE.md makes a stop-and-ask
  (docs/evidence/INT-170.md records the choice and its consequence).
- ``patient_overlays`` is the version header. files/09 §3 makes the overlay
  "versioned"; a version derived as ``max()`` over surviving facts would go
  BACKWARDS when the patient deletes the newest one, so the counter is a
  column that every mutation increments.

Shape notes:

- **``payload`` is always an envelope** (invariant 14: field-level envelope
  encryption for "transcripts/notes/learned facts"). It carries EncryptedField
  JSON over ``{"value", "confidence"}``; there is no plaintext-value column to
  fall back to, which is why ``confidence`` is inside it rather than beside it.
- **``fact_key`` is in the clear**, exactly as ``slots.slot_id`` is: it is an
  authored protocol reference, and delta mode matches it against a step id.
- **``source`` is a CHECK-constrained closed vocabulary** of the three
  ``LearnedFactSource`` members (a non-native ``sa.Enum``, the shape
  ``slots.sensitivity`` already uses). A fourth value would be an unconfirmed
  provenance arriving by SQL, and the database refuses it.
- **One row per (tenant, patient, fact_key)**; re-confirmation replaces it in
  place and restarts the twelve-month clock. The history of a confirmation is
  the hash-chained audit's business, not this table's.
- **DELETE is granted here**, unlike notification_preferences: files/09 §3
  promises the patient can delete any learned fact, and a deletion removes the
  row rather than tombstoning the key — a tombstone that keeps the key keeps
  the health fact. Bulk erasure still runs through the retention engine's
  crypto-shred path with the record (retention class ``clinical_record``).
- RLS is ENABLED **and** FORCED with the same ``app.tenant_id`` GUC policy
  every tenant-scoped table carries in 0001 — an unset GUC reads as NULL and
  therefore selects no rows (fail closed).

Revision ID: 0010_int170
Revises: 0009_int171
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010_int170"
down_revision = "0009_int171"
branch_labels = None
depends_on = None

#: The three confirmed provenances of clinical_schemas.overlay.LearnedFactSource.
#: files/09 §3 admits no fourth, and the vocabulary is closed in the database
#: for the same reason it is closed in the type: an unconfirmed provenance must
#: not be representable anywhere.
_SOURCES = ("confirmed_intake_extraction", "clinician_accepted_note", "confirmed_imported_record")

_GRANTS = (
    "REVOKE ALL ON patient_overlays FROM PUBLIC",
    "REVOKE ALL ON overlay_facts FROM PUBLIC",
    # SELECT + INSERT + UPDATE on the header: it is bumped, never erased on
    # its own; it goes with the patient record.
    "GRANT SELECT, INSERT, UPDATE ON patient_overlays TO app_rw",
    # DELETE on the facts, because files/09 §3 gives the patient that verb.
    "GRANT SELECT, INSERT, UPDATE, DELETE ON overlay_facts TO app_rw",
)

_RLS_DDL = (
    "ALTER TABLE patient_overlays ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE patient_overlays FORCE ROW LEVEL SECURITY",
    """CREATE POLICY patient_overlays_tenant_isolation ON patient_overlays
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    "ALTER TABLE overlay_facts ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE overlay_facts FORCE ROW LEVEL SECURITY",
    """CREATE POLICY overlay_facts_tenant_isolation ON overlay_facts
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
)


def upgrade() -> None:
    op.create_table(
        "patient_overlays",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("tenant_id", "patient_id", name="uq_patient_overlays_tenant_id"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
    )
    op.create_index("ix_patient_overlays_tenant_id", "patient_overlays", ["tenant_id"])
    op.create_index("ix_patient_overlays_patient_id", "patient_overlays", ["patient_id"])

    op.create_table(
        "overlay_facts",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("fact_key", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(*_SOURCES, name="learned_fact_source", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shared", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "patient_id", "fact_key", name="uq_overlay_facts_tenant_id"
        ),
    )
    op.create_index("ix_overlay_facts_tenant_id", "overlay_facts", ["tenant_id"])
    op.create_index("ix_overlay_facts_patient_id", "overlay_facts", ["patient_id"])

    for statement in (*_GRANTS, *_RLS_DDL):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS overlay_facts_tenant_isolation ON overlay_facts")
    op.execute("DROP POLICY IF EXISTS patient_overlays_tenant_isolation ON patient_overlays")
    op.drop_index("ix_overlay_facts_patient_id", table_name="overlay_facts")
    op.drop_index("ix_overlay_facts_tenant_id", table_name="overlay_facts")
    op.drop_table("overlay_facts")
    op.drop_index("ix_patient_overlays_patient_id", table_name="patient_overlays")
    op.drop_index("ix_patient_overlays_tenant_id", table_name="patient_overlays")
    op.drop_table("patient_overlays")
