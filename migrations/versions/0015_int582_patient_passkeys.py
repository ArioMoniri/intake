"""INT-582 — patient_passkeys: the public half of each patient passkey (D36).

D36 (owner, 28 Oct 2026) steps four patient actions up to a passkey — a
Doctor Link, a phone change, a data export, a data delete — against a SIM
swap. The API verifies each step-up assertion against the public key kept
here. Nothing secret is stored: a credential id, an X9.62 P-256 public key,
its signature counter, the two backup flags and an opaque per-patient user
handle (32 random bytes). No phone, no name, no device model (the AAGUID is
not kept — nothing needs it).

Shape notes:

- **One row per credential**, unique per tenant on ``credential_id``.
- **The counter is an unsigned 32-bit value** (``ck_patient_passkeys_sign_count_u32``),
  held in a BIGINT because INTEGER stops at 2^31 - 1.
- **DELETE is granted**: a passkey leaves when its holder removes it (a
  step-up of its own) or when the recovery cool-off ends, and a DSAR erasure
  removes the subject's rows like every other record-clock class.
- RLS is ENABLED **and** FORCED with the same ``app.tenant_id`` GUC policy
  every tenant-scoped table carries — an unset GUC reads as NULL and selects
  no rows (fail closed).

Revision ID: 0015_int582
Revises: 0014_int123
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_int582"
down_revision = "0014_int123"
branch_labels = None
depends_on = None

_GRANTS = (
    "REVOKE ALL ON patient_passkeys FROM PUBLIC",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON patient_passkeys TO app_rw",
)

_RLS_DDL = (
    "ALTER TABLE patient_passkeys ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE patient_passkeys FORCE ROW LEVEL SECURITY",
    """CREATE POLICY patient_passkeys_tenant_isolation ON patient_passkeys
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
)


def upgrade() -> None:
    op.create_table(
        "patient_passkeys",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("credential_id", sa.String(1366), nullable=False),
        sa.Column("public_key", sa.String(88), nullable=False),
        sa.Column("user_handle", sa.String(44), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("backup_eligible", sa.Boolean(), nullable=False),
        sa.Column("backup_state", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recovery_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "credential_id", name="uq_patient_passkeys_tenant_id"),
        sa.CheckConstraint("sign_count >= 0 AND sign_count <= 4294967295", name="sign_count_u32"),
    )
    op.create_index("ix_patient_passkeys_tenant_id", "patient_passkeys", ["tenant_id"])
    op.create_index("ix_patient_passkeys_patient_id", "patient_passkeys", ["patient_id"])
    for statement in (*_GRANTS, *_RLS_DDL):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS patient_passkeys_tenant_isolation ON patient_passkeys")
    op.drop_index("ix_patient_passkeys_patient_id", table_name="patient_passkeys")
    op.drop_index("ix_patient_passkeys_tenant_id", table_name="patient_passkeys")
    op.drop_table("patient_passkeys")
