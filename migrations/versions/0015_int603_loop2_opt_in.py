"""INT-603 — Loop 2 counts only patients who granted ``learning:service_improvement``.

0009 built ``analytics.v_loop2_sessions`` for an OPT-OUT purpose: a session
was in unless its patient's latest decision on the scope was a withdrawal, so
a patient with no row at all was counted ("where nothing is recorded the
patient is in, which is what default_granted means").

INT-603 legal review round 2 (the owner's KVKK approval; files/06 §2 now says
both learning purposes are off until the patient turns them on, D43) turned
the purpose OFF by default in the consent registry. The view
follows: a session is in only while its patient holds a LIVE grant of the
scope. A withdrawal revokes every live row (consent/service.py), so "a live
row exists" is exactly "the latest decision is a grant". No row, an opt-out
row written before INT-603, or a revoked grant all mean out — fail closed.

What SQL cannot see is the text hash: the platform evaluator calls a grant
whose text moved "stale" and refuses it, while this view still counts it.
That gap existed in 0009 too and is narrower than before (0009 counted
patients with no row at all); closing it needs the served text hash in the
database and is recorded in docs/evidence/INT-603.md.

The column list is unchanged, so ``CREATE OR REPLACE VIEW`` keeps the three
counting views that read it and their grants. The downgrade RAISES: going
back to 0009 would count patients who never granted the purpose, which
contradicts D43 (INT-603 legal review round 2).

Revision ID: 0015_int603
Revises: 0014_int123
"""

from __future__ import annotations

from alembic import op

revision = "0015_int603"
down_revision = "0014_int123"
branch_labels = None
depends_on = None

_OPT_IN_DDL = """CREATE OR REPLACE VIEW analytics.v_loop2_sessions AS
    SELECT s.id,
           s.tenant_id,
           s.patient_id,
           s.protocol_id,
           s.protocol_version,
           s.status,
           s.attribution,
           s.created_at
    FROM sessions s
    WHERE EXISTS (
        SELECT 1
        FROM consents g
        WHERE g.patient_id = s.patient_id
          AND g.tenant_id = s.tenant_id
          AND g.scope = 'learning:service_improvement'
          AND g.revoked_at IS NULL)"""


def upgrade() -> None:
    op.execute(_OPT_IN_DDL)


DOWNGRADE_REFUSAL = (
    "0015_int603 cannot be downgraded: restoring the 0009 view would count "
    "patients who never granted learning:service_improvement in Loop 2, "
    "which contradicts D43 (both learning purposes are off until the patient "
    "turns them on). Write a new forward migration instead."
)


def downgrade() -> None:
    # INT-603 legal review round 2: no silent path back to counting patients
    # who never granted the purpose.
    raise RuntimeError(DOWNGRADE_REFUSAL)
