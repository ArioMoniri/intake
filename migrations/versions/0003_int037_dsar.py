"""INT-037 — data-subject rights: the request tracker and the addendum store.

Two tables, both tenant-scoped and both under the same RLS shape 0001 gave
every record table (ENABLE + FORCE + a tenant-isolation policy with WITH
CHECK, so a session cannot write another tenant's row):

- ``dsar_requests`` — one row per KVKK m.11 right exercised, carrying the
  m.13 clock (``received_at`` → ``due_at``) and, for an erasure, the files/06
  §3 grace (``grace_ends_at``). Ids, a closed kind/status and timestamps only:
  the SLA queue is read by operations staff and must never hold content
  (invariant 6).
- ``dsar_rectifications`` — the correction as an ADDENDUM (files/02 §3: "an
  addendum rather than a silent rewrite"), the patient's own words under a
  field-level envelope like every other clinical payload.

No clinician read policy on either: a rights request is between the data
subject and the controller. ``clinician_ro`` gets no grant at all, which is
the difference between "not selected" and "not selectable".

Revision ID: 0003_int037
Revises: 0002_int038
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_int037"
down_revision = "0002_int038"
branch_labels = None
depends_on = None

_TABLES = ("dsar_requests", "dsar_rectifications")

_GRANTS = (
    "REVOKE ALL ON dsar_requests FROM PUBLIC",
    "REVOKE ALL ON dsar_rectifications FROM PUBLIC",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON dsar_requests TO app_rw",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON dsar_rectifications TO app_rw",
)

_RLS_DDL = (
    "ALTER TABLE dsar_requests ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE dsar_requests FORCE ROW LEVEL SECURITY",
    """CREATE POLICY dsar_requests_tenant_isolation ON dsar_requests
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    "ALTER TABLE dsar_rectifications ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE dsar_rectifications FORCE ROW LEVEL SECURITY",
    """CREATE POLICY dsar_rectifications_tenant_isolation ON dsar_rectifications
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
)


def upgrade() -> None:
    op.create_table(
        "dsar_requests",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "export",
                "delete",
                "rectify",
                name="dsar_kind",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "received",
                "scheduled",
                "completed",
                "cancelled",
                name="dsar_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legal_strings_hash", sa.String(64), nullable=True),
    )
    op.create_table(
        "dsar_rectifications",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("request_id", sa.Uuid(), sa.ForeignKey("dsar_requests.id"), nullable=False),
        sa.Column("target_ref", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    for index_name, table_name, columns in (
        ("ix_dsar_requests_tenant_id", "dsar_requests", ["tenant_id"]),
        ("ix_dsar_requests_patient_id", "dsar_requests", ["patient_id"]),
        ("ix_dsar_requests_tenant_status", "dsar_requests", ["tenant_id", "status"]),
        ("ix_dsar_rectifications_tenant_id", "dsar_rectifications", ["tenant_id"]),
        ("ix_dsar_rectifications_patient_id", "dsar_rectifications", ["patient_id"]),
        ("ix_dsar_rectifications_request_id", "dsar_rectifications", ["request_id"]),
    ):
        op.create_index(index_name, table_name, columns)
    for statement in _GRANTS:
        op.execute(statement)
    for statement in _RLS_DDL:
        op.execute(statement)


def downgrade() -> None:
    # Policies, grants and indexes fall with their tables (0001 precedent).
    for table_name in _TABLES:
        op.drop_table(table_name)
