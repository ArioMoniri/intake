"""INT-150 — doctor_links: one tokenized, expiring, countable clinician grant.

One table, and three things it deliberately does not hold.

- **No token.** ``token_fingerprint`` is SHA-256 of a 128-bit random token, so
  a database dump yields no access (CLAUDE.md invariant 6: a token is a
  credential). The unique index on it is the lookup path and the guarantee
  that one fingerprint names at most one grant.
- **No OTP state.** Codes, attempt counters and request windows stay in Redis
  behind the phone-OTP tier's own gate (``intake_api.auth_store.AuthStore``,
  INT-131). A second limiter here would be a second thing to keep in step.
- **No section list.** The scope lives on ``shares.scope_sections`` and is
  read through ``share_id``: one home for what is shared, so a link can never
  widen a share.

``views_used`` is incremented by the same guarded UPDATE that admits a view
(``WHERE views_used < view_limit AND revoked_at IS NULL AND expires_at > now``),
so the view limit is enforced atomically in one statement on both backends —
unlike the OTP request gate, which is read-decide-write by construction
(INT-263 records that limitation; this table does not inherit it).

RLS is ENABLED **and** FORCED with the same ``app.tenant_id`` GUC policy every
tenant-scoped table carries in 0001: an unset GUC reads as NULL and selects no
rows (fail closed). DELETE is granted to ``app_rw`` because a Doctor Link is
part of the clinical record's crypto-shred set (retention class
``doctor_link_tokens``); revocation is an UPDATE, not a delete.

Revision ID: 0011_int150
Revises: 0010_int170
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_int150"
down_revision = "0010_int170"
branch_labels = None
depends_on = None

_GRANTS = (
    "REVOKE ALL ON doctor_links FROM PUBLIC",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON doctor_links TO app_rw",
    # The clinician role reads the note through the API, never this table:
    # a token fingerprint is not clinical content and nothing on the clinic
    # side has a reason to enumerate grants.
)

_RLS_DDL = (
    "ALTER TABLE doctor_links ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE doctor_links FORCE ROW LEVEL SECURITY",
    """CREATE POLICY doctor_links_tenant_isolation ON doctor_links
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
)


def upgrade() -> None:
    op.create_table(
        "doctor_links",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("share_id", sa.Uuid(), nullable=False),
        sa.Column("token_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("recipient", JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("view_limit", sa.Integer(), nullable=False),
        sa.Column("views_used", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_doctor_links_tenant_id_tenants"
        ),
        sa.ForeignKeyConstraint(
            ["share_id"], ["shares.id"], name="fk_doctor_links_share_id_shares"
        ),
        sa.CheckConstraint("view_limit > 0", name="ck_doctor_links_view_limit_positive"),
        sa.CheckConstraint("views_used >= 0", name="ck_doctor_links_views_used_not_negative"),
        sa.UniqueConstraint("token_fingerprint", name="uq_doctor_links_token_fingerprint"),
    )
    op.create_index("ix_doctor_links_tenant_id", "doctor_links", ["tenant_id"])
    op.create_index("ix_doctor_links_share_id", "doctor_links", ["share_id"])
    for statement in (*_RLS_DDL, *_GRANTS):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS doctor_links_tenant_isolation ON doctor_links")
    op.drop_index("ix_doctor_links_share_id", table_name="doctor_links")
    op.drop_index("ix_doctor_links_tenant_id", table_name="doctor_links")
    op.drop_table("doctor_links")
