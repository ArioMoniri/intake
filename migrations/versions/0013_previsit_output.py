"""previsit_outputs — the finished previsit, frozen, once per completed intake.

The owner directive's first half: when a previsit is done, its result is
written to SQL keyed so it can be found by patient. One table, and four things
it deliberately does not hold.

- **No patient number, no name, no TCKN.** The hospital's own key is resolved
  to ``patients.pseudonym`` through the Tokenizer at request time and echoed
  back from the request, so the direct identifier has no column anywhere
  (CLAUDE.md invariant 14). ``patient_id`` is the pseudonymised row.
- **No plaintext.** ``payload`` is an EncryptedField envelope, exactly like
  ``notes.payload`` — field-level envelope encryption, invariant 14.
- **No section scope.** What is shared lives on ``shares.scope_sections`` and
  is read through it, so a fetch can never widen what the patient sent. One
  home for scope, the same rule ``doctor_links`` obeys.
- **No row history.** ``UNIQUE (tenant_id, session_id)`` makes the finished
  previsit singular: a resend replaces the document. Who read it, and when, is
  the hash-chained audit's job, not this table's.

``payload_sha256`` is the digest of the canonical plaintext document. It is
there so a receiver can tell "I already have this previsit" without decrypting
anything, and so a resend that changed nothing is visible as such.

RLS is ENABLED **and** FORCED with the same ``app.tenant_id`` GUC policy every
tenant-scoped table carries in 0001: an unset GUC reads as NULL and selects no
rows (fail closed). The clinician role gets no grant here — the clinic side
reads a previsit through the API, which checks consent and audits the share;
a role that could SELECT this table directly would be a second, unaudited path
to the same clinical content.

Revision ID: 0013_previsit_output
Revises: 0012_int150
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013_previsit_output"
down_revision = "0012_int150"
branch_labels = None
depends_on = None

_GRANTS = (
    "REVOKE ALL ON previsit_outputs FROM PUBLIC",
    # DELETE because a finished previsit is part of the clinical record's
    # crypto-shred set: a DSAR erasure that left this row behind would leave
    # the whole previsit readable through the read-back.
    "GRANT SELECT, INSERT, UPDATE, DELETE ON previsit_outputs TO app_rw",
)

_RLS_DDL = (
    "ALTER TABLE previsit_outputs ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE previsit_outputs FORCE ROW LEVEL SECURITY",
    """CREATE POLICY previsit_outputs_tenant_isolation ON previsit_outputs
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
)


def upgrade() -> None:
    op.create_table(
        "previsit_outputs",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_previsit_outputs_tenant_id_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name="fk_previsit_outputs_session_id_sessions"
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name="fk_previsit_outputs_patient_id_patients"
        ),
        sa.UniqueConstraint("tenant_id", "session_id", name="uq_previsit_outputs_tenant_id"),
    )
    op.create_index("ix_previsit_outputs_tenant_id", "previsit_outputs", ["tenant_id"])
    op.create_index("ix_previsit_outputs_session_id", "previsit_outputs", ["session_id"])
    op.create_index("ix_previsit_outputs_patient_id", "previsit_outputs", ["patient_id"])
    for statement in (*_RLS_DDL, *_GRANTS):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS previsit_outputs_tenant_isolation ON previsit_outputs")
    op.drop_index("ix_previsit_outputs_patient_id", table_name="previsit_outputs")
    op.drop_index("ix_previsit_outputs_session_id", table_name="previsit_outputs")
    op.drop_index("ix_previsit_outputs_tenant_id", table_name="previsit_outputs")
    op.drop_table("previsit_outputs")
