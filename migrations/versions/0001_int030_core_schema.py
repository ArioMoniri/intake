"""INT-030 — core schema: tenants, patients (pseudonymised), sessions, slots,
notes, consents, shares, documents, events, audit_chain; RLS enabled AND
forced per tenant-scoped table; least-privilege roles; guarded pgaudit probe.

Revision ID: 0001_int030
Revises: none (first revision)

Security DDL is spelled out statement-by-statement — never generated — so the
static gate (tests/data/test_schema_shape.py) and a human reviewer read the
exact policies Postgres will hold. Design notes:

- Policies read the ``app.tenant_id`` GUC, set from the OIDC claim and never
  from the request (files/10 §2). ``NULLIF(current_setting(...), '')`` makes
  an unset GUC read as NULL → no rows: fail closed, not fail open.
- FORCE ROW LEVEL SECURITY removes the table-owner bypass. In the compose dev
  tier the owner happens to be the bootstrap superuser (which Postgres always
  exempts); production runs a non-superuser owner, which is exactly whom
  FORCE exists for.
- Roles carry dev-only passwords here, mirroring
  scripts/security/identity_vault.sql; production credentials are dynamic
  from OpenBao (24 h TTL, files/10 §2) onto these same roles.
- audit_chain carries no RLS: rows are id-shaped by construction (invariant
  6) and the writer must read the global tail to resume the chain. Grants are
  the boundary — ``svc_audit_writer`` holds the only INSERT, and UPDATE or
  DELETE is granted to no principal anywhere (files/10 §2, invariant 40).
- pgaudit: the dev image (pgvector/pg16) does not ship the extension and it
  needs shared_preload_libraries at boot, so the migration probes
  pg_available_extensions at runtime and logs loudly instead of failing hard;
  production images must preload it and this same migration then installs and
  configures it.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001_int030"
down_revision = None
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _uuid_pk() -> sa.Column[object]:
    return sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _tenant_fk() -> sa.Column[object]:
    return sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False)


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _create_tables() -> None:
    op.create_table(
        "tenants",
        _uuid_pk(),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "kvkk_role",
            sa.Enum("controller", "processor", name="kvkk_role", native_enum=False, length=16),
            nullable=False,
        ),
        _created_at(),
    )
    op.create_table(
        "patients",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("pseudonym", sa.Text(), nullable=False),
        _created_at(),
        sa.UniqueConstraint("tenant_id", "pseudonym", name="uq_patients_tenant_id"),
    )
    op.create_table(
        "sessions",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("protocol_id", sa.Text(), nullable=False),
        sa.Column("protocol_version", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "created",
                "active",
                "completed",
                "cancelled",
                name="session_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_table(
        "slots",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("slot_id", sa.Text(), nullable=False),
        sa.Column(
            "sensitivity",
            sa.Enum("plain", "sensitive", name="slot_sensitivity", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("value", JSONB(), nullable=False),
        _created_at(),
        sa.UniqueConstraint("session_id", "slot_id", name="uq_slots_session_id"),
    )
    op.create_table(
        "notes",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        _created_at(),
    )
    op.create_table(
        "consents",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "shares",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("note_id", sa.Uuid(), sa.ForeignKey("notes.id"), nullable=False),
        sa.Column("scope_sections", JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_table(
        "documents",
        _uuid_pk(),
        _tenant_fk(),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("object_ref", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("provenance", JSONB(), nullable=False),
        _created_at(),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        _tenant_fk(),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        _created_at(),
    )
    op.create_table(
        "audit_chain",
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("timestamp_utc", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_ref", sa.String(128), nullable=False),
        sa.Column("consent_scope_ref", sa.String(128), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
    )
    for index_name, table_name, columns in (
        ("ix_patients_tenant_id", "patients", ["tenant_id"]),
        ("ix_sessions_tenant_id", "sessions", ["tenant_id"]),
        ("ix_sessions_patient_id", "sessions", ["patient_id"]),
        ("ix_slots_tenant_id", "slots", ["tenant_id"]),
        ("ix_slots_session_id", "slots", ["session_id"]),
        ("ix_notes_tenant_id", "notes", ["tenant_id"]),
        ("ix_notes_session_id", "notes", ["session_id"]),
        ("ix_notes_patient_id", "notes", ["patient_id"]),
        ("ix_consents_tenant_id", "consents", ["tenant_id"]),
        ("ix_consents_patient_id", "consents", ["patient_id"]),
        ("ix_shares_tenant_id", "shares", ["tenant_id"]),
        ("ix_shares_note_id", "shares", ["note_id"]),
        ("ix_documents_tenant_id", "documents", ["tenant_id"]),
        ("ix_documents_patient_id", "documents", ["patient_id"]),
        ("ix_events_tenant_id", "events", ["tenant_id"]),
        ("ix_events_tenant_type", "events", ["tenant_id", "event_type"]),
    ):
        op.create_index(index_name, table_name, columns)


# Roles: dev-tier bootstrap (identity_vault.sql style). Idempotent so reruns
# against a long-lived dev cluster never fail on an existing role.
_ROLES_DDL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_rw') THEN
        CREATE ROLE app_rw LOGIN PASSWORD 'app-rw-dev-only';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'clinician_ro') THEN
        CREATE ROLE clinician_ro LOGIN PASSWORD 'clinician-ro-dev-only';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'svc_audit_writer') THEN
        CREATE ROLE svc_audit_writer LOGIN PASSWORD 'svc-audit-writer-dev-only';
    END IF;
END
$$;
"""

_CONNECT_DDL = """
DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO app_rw, clinician_ro, svc_audit_writer',
        current_database()
    );
END
$$;
"""

_GRANTS = (
    "REVOKE ALL ON tenants FROM PUBLIC",
    "REVOKE ALL ON patients FROM PUBLIC",
    "REVOKE ALL ON sessions FROM PUBLIC",
    "REVOKE ALL ON slots FROM PUBLIC",
    "REVOKE ALL ON notes FROM PUBLIC",
    "REVOKE ALL ON consents FROM PUBLIC",
    "REVOKE ALL ON shares FROM PUBLIC",
    "REVOKE ALL ON documents FROM PUBLIC",
    "REVOKE ALL ON events FROM PUBLIC",
    "REVOKE ALL ON audit_chain FROM PUBLIC",
    # app_rw: full DML on record tables; tenants are provisioned by the
    # platform path, so the app only reads them
    "GRANT SELECT ON tenants TO app_rw",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON patients TO app_rw",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON sessions TO app_rw",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON slots TO app_rw",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON notes TO app_rw",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON consents TO app_rw",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON shares TO app_rw",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON documents TO app_rw",
    # events are append-only: the app writes and reads, edits nothing
    "GRANT SELECT, INSERT ON events TO app_rw",
    # clinician surface: read-only over the clinical record set
    "GRANT SELECT ON patients TO clinician_ro",
    "GRANT SELECT ON sessions TO clinician_ro",
    "GRANT SELECT ON slots TO clinician_ro",
    "GRANT SELECT ON notes TO clinician_ro",
    "GRANT SELECT ON documents TO clinician_ro",
    # audit chain: the writer INSERTs (and reads the tail to resume);
    # the app runs the daily verifier read-only; UPDATE and DELETE are
    # granted to no principal anywhere (files/10 §2)
    "GRANT SELECT, INSERT ON audit_chain TO svc_audit_writer",
    "GRANT SELECT ON audit_chain TO app_rw",
)

_RLS_DDL = (
    # tenants — scoped by its own id
    "ALTER TABLE tenants ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE tenants FORCE ROW LEVEL SECURITY",
    """CREATE POLICY tenants_tenant_isolation ON tenants
    AS PERMISSIVE FOR ALL TO app_rw
    USING (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    # patients
    "ALTER TABLE patients ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE patients FORCE ROW LEVEL SECURITY",
    """CREATE POLICY patients_tenant_isolation ON patients
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    """CREATE POLICY patients_clinician_read ON patients
    FOR SELECT TO clinician_ro
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    # sessions
    "ALTER TABLE sessions ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE sessions FORCE ROW LEVEL SECURITY",
    """CREATE POLICY sessions_tenant_isolation ON sessions
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    """CREATE POLICY sessions_clinician_read ON sessions
    FOR SELECT TO clinician_ro
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    # slots
    "ALTER TABLE slots ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE slots FORCE ROW LEVEL SECURITY",
    """CREATE POLICY slots_tenant_isolation ON slots
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    """CREATE POLICY slots_clinician_read ON slots
    FOR SELECT TO clinician_ro
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    # notes
    "ALTER TABLE notes ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE notes FORCE ROW LEVEL SECURITY",
    """CREATE POLICY notes_tenant_isolation ON notes
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    """CREATE POLICY notes_clinician_read ON notes
    FOR SELECT TO clinician_ro
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    # consents — app-mediated only; no clinician policy on purpose
    "ALTER TABLE consents ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE consents FORCE ROW LEVEL SECURITY",
    """CREATE POLICY consents_tenant_isolation ON consents
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    # shares
    "ALTER TABLE shares ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE shares FORCE ROW LEVEL SECURITY",
    """CREATE POLICY shares_tenant_isolation ON shares
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    # documents
    "ALTER TABLE documents ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE documents FORCE ROW LEVEL SECURITY",
    """CREATE POLICY documents_tenant_isolation ON documents
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    """CREATE POLICY documents_clinician_read ON documents
    FOR SELECT TO clinician_ro
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    # events
    "ALTER TABLE events ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE events FORCE ROW LEVEL SECURITY",
    """CREATE POLICY events_tenant_isolation ON events
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
)


def _apply_pgaudit() -> None:
    """ "pgaudit on" where the server can honour it. The compose dev image
    (pgvector/pg16) ships without the extension and pgaudit additionally
    needs shared_preload_libraries at server boot — a migration cannot add
    either. So: probe, install when offered, and otherwise log loudly and
    keep going (a failed migration would block the schema without producing
    any audit coverage either)."""
    bind = op.get_bind()
    available = bind.execute(
        sa.text("SELECT count(*) FROM pg_available_extensions WHERE name = 'pgaudit'")
    ).scalar()
    if not available:
        logger.warning(
            "pgaudit is NOT available on this Postgres server (the dev image "
            "pgvector/pg16 does not ship it). Continuing without it; production "
            "images MUST preload pgaudit via shared_preload_libraries so this "
            "migration installs and configures it there (files/10 §2; INT-030 "
            "acceptance 'pgaudit on')."
        )
        return
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pgaudit")
        op.execute(
            """
DO $$
BEGIN
    EXECUTE format(
        'ALTER DATABASE %I SET pgaudit.log = ''write, ddl, role''',
        current_database()
    );
END
$$;
"""
        )
        logger.info("pgaudit installed; pgaudit.log = 'write, ddl, role' for this database")
    except Exception:
        logger.exception(
            "pgaudit is available but installing/configuring it failed — the "
            "schema migration continues, but 'pgaudit on' is NOT satisfied on "
            "this server until this is resolved"
        )


def upgrade() -> None:
    _create_tables()
    op.execute(_ROLES_DDL)
    op.execute(_CONNECT_DDL)
    for statement in _GRANTS:
        op.execute(statement)
    for statement in _RLS_DDL:
        op.execute(statement)
    _apply_pgaudit()


def downgrade() -> None:
    # Policies, grants and indexes fall with their tables. Roles stay: they
    # are cluster-wide, shared with any other database on the instance, and
    # re-created idempotently on upgrade (identity_vault.sql precedent).
    for table_name in (
        "audit_chain",
        "events",
        "documents",
        "shares",
        "consents",
        "notes",
        "slots",
        "sessions",
        "patients",
        "tenants",
    ):
        op.drop_table(table_name)
