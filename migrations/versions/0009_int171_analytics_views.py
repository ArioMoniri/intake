"""INT-171 — the de-identified analytics schema and its read-only reader.

files/10 §7, verbatim: ``services/learning`` runs *"with read-only credentials
on de-identified views (never on raw tables)"*. This migration is that
sentence expressed as grants.

Three aggregate views in an ``analytics`` schema, over a fourth that applies
the Loop-2 opt-out before anything is counted (files/06 §2 makes
``learning:service_improvement`` an opt-out purpose; files/09 §5 promises the
opt-out costs no feature). Each one groups first, so
what the reader sees is already counts: the quasi-identifiers, a distinct
subject count, a distinct tenant count and the measures. No row survives the
``GROUP BY``, so no pseudonym, session key or tenant key reaches the reader —
a count of pseudonyms is not the pseudonyms.

What is deliberately absent is the point of the design. There is no narrative
column in any definition here, and none of the tables that hold narrative is
read at all. Turkish clinical free text cannot be de-identified to a standard
this repo is willing to assert (files/10 §3 on Turkish recall;
files/HUMAN_BLOCKERS.md HB-L6 on the claim itself), so the answer is exclusion
rather than redaction. ``intake_platform.analytics.views`` carries the long
form of that reasoning.

``svc_learning_reader`` gets CONNECT, USAGE on the schema and SELECT on the
three views. Nothing else, anywhere: the base tables answer "permission
denied" for that role, which is the difference between "not selected" and "not
selectable" (the 0008 formulation). The views are owner-owned rather than
``security_invoker``, because a Loop-2 pattern must hold across at least two
clinics (files/09 §4) and so is cross-tenant by construction; the control that
makes that safe is the k >= 10 floor applied at the query layer, and the
control that makes it *bounded* is that a clinic can only ever appear as part
of a count, never as a label.

The k floor is not baked into the view bodies. A ``HAVING`` clause would
suppress a thin cell and serve the rest, and a reader who receives every cell
but one recovers the missing one by subtraction from any wider aggregate over
the same population. The gate refuses the whole artefact instead, which is a
query-layer decision — where the INT-171 acceptance puts it.

Revision ID: 0009_int171
Revises: 0008_int240
"""

from __future__ import annotations

from alembic import op

revision = "0009_int171"
down_revision = "0008_int240"
branch_labels = None
depends_on = None

_VIEW_NAMES = (
    "v_session_outcomes",
    "v_step_coverage",
    "v_attribution_mix",
    "v_loop2_sessions",
)

# The Loop-2 opt-out, applied before anything is counted. files/06 §2 makes
# `learning:service_improvement` an opt-out purpose and files/09 §5 promises
# the opt-out "costs no feature" — costing the patient nothing means their
# sessions are not in the aggregate, and an opt-out nothing honours is the
# same decoration as a k helper nobody calls (invariant 4: every read of
# clinical data checks a consent scope).
#
# A withdrawal writes a row with `revoked_at` set even where the purpose was
# granted by default (intake_platform.consent.service writes an explicit
# opt-out row), and a withdrawal of `core` cascades here. A later grant wins,
# which is the inner NOT EXISTS; where nothing is recorded the patient is in,
# which is what "default_granted" means.
#
# The view carries row-level ids so the three counting views can group over
# it. It is plumbing the owner runs: svc_learning_reader is granted nothing
# on it.
_LOOP2_SESSIONS_DDL = """CREATE VIEW analytics.v_loop2_sessions AS
    SELECT s.id,
           s.tenant_id,
           s.patient_id,
           s.protocol_id,
           s.protocol_version,
           s.status,
           s.attribution,
           s.created_at
    FROM sessions s
    WHERE NOT EXISTS (
        SELECT 1
        FROM consents c
        WHERE c.patient_id = s.patient_id
          AND c.scope = 'learning:service_improvement'
          AND c.revoked_at IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM consents g
              WHERE g.patient_id = c.patient_id
                AND g.scope = c.scope
                AND g.revoked_at IS NULL
                AND g.granted_at >= c.revoked_at))"""

_VIEW_DDL = (
    "CREATE SCHEMA IF NOT EXISTS analytics",
    _LOOP2_SESSIONS_DDL,
    # Session outcomes: which pack ran, in which week, and how it ended.
    """CREATE VIEW analytics.v_session_outcomes AS
    SELECT s.protocol_id,
           s.protocol_version,
           (date_trunc('week', s.created_at))::date              AS week_start,
           count(DISTINCT s.patient_id)                          AS subjects,
           count(DISTINCT s.tenant_id)                           AS tenants,
           count(*)                                              AS sessions,
           count(*) FILTER (WHERE s.status = 'completed')        AS completed,
           count(*) FILTER (WHERE s.status = 'cancelled')        AS cancelled
    FROM analytics.v_loop2_sessions s
    GROUP BY s.protocol_id, s.protocol_version, (date_trunc('week', s.created_at))::date""",
    # Step coverage: which protocol step got an answer. The slot id names the
    # question; what the patient answered is not projected and not granted.
    """CREATE VIEW analytics.v_step_coverage AS
    SELECT s.protocol_id,
           sl.slot_id,
           (date_trunc('week', s.created_at))::date              AS week_start,
           count(DISTINCT s.patient_id)                          AS subjects,
           count(DISTINCT s.tenant_id)                           AS tenants,
           count(DISTINCT sl.session_id)                         AS sessions_answered
    FROM slots sl
    JOIN analytics.v_loop2_sessions s ON s.id = sl.session_id
    GROUP BY s.protocol_id, sl.slot_id, (date_trunc('week', s.created_at))::date""",
    # Attribution mix: self / proxy / assisted self report, as a count.
    """CREATE VIEW analytics.v_attribution_mix AS
    SELECT s.protocol_id,
           s.attribution,
           (date_trunc('week', s.created_at))::date              AS week_start,
           count(DISTINCT s.patient_id)                          AS subjects,
           count(DISTINCT s.tenant_id)                           AS tenants,
           count(*)                                              AS sessions
    FROM analytics.v_loop2_sessions s
    GROUP BY s.protocol_id, s.attribution, (date_trunc('week', s.created_at))::date""",
)

_ROLE_DDL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'svc_learning_reader') THEN
        CREATE ROLE svc_learning_reader LOGIN PASSWORD 'svc-learning-reader-dev-only';
    END IF;
END
$$;
"""

_CONNECT_DDL = """
DO $$
BEGIN
    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO svc_learning_reader',
        current_database()
    );
END
$$;
"""

_GRANTS = (
    "REVOKE ALL ON SCHEMA analytics FROM PUBLIC",
    "GRANT USAGE ON SCHEMA analytics TO svc_learning_reader",
    "REVOKE ALL ON analytics.v_loop2_sessions FROM PUBLIC",
    "REVOKE ALL ON analytics.v_session_outcomes FROM PUBLIC",
    "REVOKE ALL ON analytics.v_step_coverage FROM PUBLIC",
    "REVOKE ALL ON analytics.v_attribution_mix FROM PUBLIC",
    "GRANT SELECT ON analytics.v_session_outcomes TO svc_learning_reader",
    "GRANT SELECT ON analytics.v_step_coverage TO svc_learning_reader",
    "GRANT SELECT ON analytics.v_attribution_mix TO svc_learning_reader",
)


def upgrade() -> None:
    for statement in _VIEW_DDL:
        op.execute(statement)
    op.execute(_ROLE_DDL)
    op.execute(_CONNECT_DDL)
    for statement in _GRANTS:
        op.execute(statement)


def downgrade() -> None:
    for name in _VIEW_NAMES:
        op.execute(f"DROP VIEW IF EXISTS analytics.{name}")
    op.execute("DROP SCHEMA IF EXISTS analytics")
    # The role stays: it is cluster-wide, shared with any other database on the
    # instance, and re-created idempotently on upgrade (the 0001 precedent).
