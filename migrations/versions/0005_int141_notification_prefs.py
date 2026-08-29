"""INT-141 — notification_preferences: the patient's opt-out and quiet window.

Unlike guardian_links (0003), this table is meant to be filled: a quiet-hours
setting that does not survive a restart is not a setting, and an opt-out that
evaporates on deploy is a promise the product breaks at 03:00 for everybody at
once. What it holds is two integers and a flag — no device token, no push
handle, no phone number (invariant 14): delivery addressing belongs to the
transport and its vendor contract, which does not exist yet.

Shape notes:

- **Both ends of the window or neither** (``ck_notification_preferences_quiet_window``).
  Half a window is not a window; accepting one end and defaulting the other
  would be the invented value HUMAN_BLOCKERS rule 1 forbids. No default window
  is written here either — files/10 §9 names the control and no file names an
  hour.
- **No timezone column.** Quiet hours are evaluated on Türkiye's fixed +03
  offset (``intake_platform.notifications.preferences``), the one jurisdiction
  this product encodes, so no per-patient location signal is collected to
  support one.
- **One row per patient per tenant**, replaced in place. The history of a
  preference is the hash-chained audit's business, not this table's.
- **No DELETE grant**: the row leaves through the retention engine's
  crypto-shred path with the record it configures, like every other class.
- RLS is ENABLED **and** FORCED with the same ``app.tenant_id`` GUC policy
  every tenant-scoped table carries in 0001 — an unset GUC reads as NULL and
  therefore selects no rows (fail closed).

Revision ID: 0005_int141
Revises: 0004_int037
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_int141"
down_revision = "0004_int037"
branch_labels = None
depends_on = None

_GRANTS = (
    "REVOKE ALL ON notification_preferences FROM PUBLIC",
    # SELECT + INSERT + UPDATE: a preference is set and changed, never erased
    # here; erasure runs through the retention engine like every record class.
    "GRANT SELECT, INSERT, UPDATE ON notification_preferences TO app_rw",
)

_RLS_DDL = (
    "ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE notification_preferences FORCE ROW LEVEL SECURITY",
    """CREATE POLICY notification_preferences_tenant_isolation ON notification_preferences
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
)


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("opted_out", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quiet_start_minute", sa.Integer(), nullable=True),
        sa.Column("quiet_end_minute", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "patient_id", name="uq_notification_preferences_tenant_id"
        ),
        sa.CheckConstraint(
            "(quiet_start_minute IS NULL) = (quiet_end_minute IS NULL)",
            name="quiet_window",
        ),
        sa.CheckConstraint(
            "quiet_start_minute IS NULL OR "
            "(quiet_start_minute BETWEEN 0 AND 1439 AND quiet_end_minute BETWEEN 0 AND 1439 "
            "AND quiet_start_minute <> quiet_end_minute)",
            name="quiet_window_bounds",
        ),
    )
    op.create_index(
        "ix_notification_preferences_tenant_id", "notification_preferences", ["tenant_id"]
    )
    op.create_index(
        "ix_notification_preferences_patient_id", "notification_preferences", ["patient_id"]
    )
    for statement in (*_GRANTS, *_RLS_DDL):
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS notification_preferences_tenant_isolation "
        "ON notification_preferences"
    )
    op.drop_index("ix_notification_preferences_patient_id", table_name="notification_preferences")
    op.drop_index("ix_notification_preferences_tenant_id", table_name="notification_preferences")
    op.drop_table("notification_preferences")
