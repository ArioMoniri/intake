"""INT-223 — guardian_links: the guardian↔minor relationship table, gated.

The table exists so the mechanism is real, migrated and RLS-protected; the
data does not, because persisting a guardian↔minor relationship is a NEW
personal-data category and CLAUDE.md makes that a stop-and-ask. The gate is
the ``guardian_link`` safety flag (default False,
``intake_platform.consent.guardian``): with it shut, both the write path and
the read path refuse, so this migration creates an empty table that no code
path can fill or consult.

Shape notes:

- **refs, not identities** (invariant 14): the minor is the pseudonymised
  patients row; the guardian is an id-shaped account ref; the relationship
  is an id-shaped evidence ref. No name, TCKN, phone or free text.
- **verified_at is NULL by design**: no proof-of-representation standard
  exists yet (policy row ``guardian_relationship_proof``), and a column that
  claimed verification without one would be the invented value rule 1
  forbids.
- **no DELETE grant**: a link is consent-adjacent evidence, so it is revoked
  (``revoked_at``) rather than erased; erasure runs through the retention
  engine's crypto-shred path like every other record class.
- RLS is ENABLED **and** FORCED with the same ``app.tenant_id`` GUC policy
  every tenant-scoped table carries in 0001 — an unset GUC reads as NULL and
  therefore selects no rows (fail closed).

Revision ID: 0003_int223
Revises: 0002_int038
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_int223"
down_revision = "0002_int038"
branch_labels = None
depends_on = None

_GRANTS = (
    "REVOKE ALL ON guardian_links FROM PUBLIC",
    # INSERT + UPDATE (revocation) only: a link is revoked, never erased,
    # and DELETE is granted to no principal anywhere (files/10 §2 posture).
    "GRANT SELECT, INSERT, UPDATE ON guardian_links TO app_rw",
)

_RLS_DDL = (
    "ALTER TABLE guardian_links ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE guardian_links FORCE ROW LEVEL SECURITY",
    """CREATE POLICY guardian_links_tenant_isolation ON guardian_links
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
)


def upgrade() -> None:
    op.create_table(
        "guardian_links",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("minor_patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("guardian_account_ref", sa.Text(), nullable=False),
        sa.Column("relationship_ref", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "minor_patient_id",
            "guardian_account_ref",
            name="uq_guardian_links_tenant_id",
        ),
    )
    op.create_index("ix_guardian_links_tenant_id", "guardian_links", ["tenant_id"])
    op.create_index("ix_guardian_links_minor_patient_id", "guardian_links", ["minor_patient_id"])
    for statement in (*_GRANTS, *_RLS_DDL):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS guardian_links_tenant_isolation ON guardian_links")
    op.drop_index("ix_guardian_links_minor_patient_id", table_name="guardian_links")
    op.drop_index("ix_guardian_links_tenant_id", table_name="guardian_links")
    op.drop_table("guardian_links")
