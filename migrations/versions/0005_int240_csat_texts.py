"""INT-240 — the satisfaction free-text store.

One table. The scores and reasons of a ``csat.v1`` response go into the
existing ``events`` row, whose ``payload`` column is declared id-shaped and
PHI-free because the rollups and the admin console read it. The patient's
sentence cannot go there: satisfaction feedback is written by the patient
about a hospital visit, so it carries symptoms and names (threat row
`experience`, threat [I]). ``csat_texts`` holds it instead, under the same
field-level envelope every other clinical payload gets — the column stores an
``EncryptedField`` JSON document, never plaintext (invariant 14).

The two foreign keys are the destruction mechanism, and both are
``ON DELETE CASCADE`` on purpose:

- ``session_id`` — a KVKK m.7/m.11 erasure deletes the subject's sessions
  (``intake_api.dsar.shred``, after de-linking telemetry), so the comment goes
  with them;
- ``event_id`` — the files/06 §3 ``satisfaction`` class ("Satisfaction: with
  account") destroys the event rows
  (``intake_platform.retention.executors.destroy_events``), so the comment goes
  with those too.

A third sweeper could fall out of step with the two that already exist. A
foreign key cannot, which is why erasure is expressed here rather than in code.

RLS is the shape 0001 gave every record table: ENABLE + FORCE + a
tenant-isolation policy with WITH CHECK, so a session cannot write another
tenant's row. No ``clinician_ro`` grant: a satisfaction comment is between the
patient and the service, and a clinician reading what a patient said about
them is not a use anybody consented to. No grant at all is the difference
between "not selected" and "not selectable".

Revision ID: 0005_int240
Revises: 0004_int037
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_int240"
down_revision = "0004_int037"
branch_labels = None
depends_on = None

_GRANTS = (
    "REVOKE ALL ON csat_texts FROM PUBLIC",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON csat_texts TO app_rw",
)

_RLS_DDL = (
    "ALTER TABLE csat_texts ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE csat_texts FORCE ROW LEVEL SECURITY",
    """CREATE POLICY csat_texts_tenant_isolation ON csat_texts
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
)


def upgrade() -> None:
    op.create_table(
        "csat_texts",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    for index_name, table_name, columns in (
        ("ix_csat_texts_tenant_id", "csat_texts", ["tenant_id"]),
        ("ix_csat_texts_session_id", "csat_texts", ["session_id"]),
    ):
        op.create_index(index_name, table_name, columns)
    for statement in _GRANTS:
        op.execute(statement)
    for statement in _RLS_DDL:
        op.execute(statement)


def downgrade() -> None:
    # Policies, grants and indexes fall with the table (0001 precedent).
    op.drop_table("csat_texts")
