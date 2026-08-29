"""INT-038 — consent text binding: the files/06 §2 record made complete.

Each consent stores {version, text_hash, ts, channel, evidence}; 0001
carried scope/version/granted_at/revoked_at, this revision adds the three
missing members:

- ``text_hash``   — SHA-256 of the exact docs/legal file bytes shown
                    (invariant 18: texts render only from docs/legal with
                    hash binding; a stale hash means re-prompt);
- ``channel``     — which aydınlatma surface collected the grant
                    (files/06 §1 KVKK-10: app|kiosk|clinician|admin|web);
- ``evidence_ref``— id of the acceptance-evidence record, an id and never
                    the evidence itself (invariant 6).

Nullable on purpose: rows seeded by the INT-197 dev fixture predate binding
and stay readable; the consent service always writes all three, and the
guard treats a NULL/mismatching hash as stale (absent) the moment the
purpose's canonical text exists. No RLS/grant change: the columns inherit
the consents policies and the app_rw grants from 0001.

Revision ID: 0002_int038
Revises: 0001_int030
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_int038"
down_revision = "0001_int030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("consents", sa.Column("text_hash", sa.String(64), nullable=True))
    op.add_column("consents", sa.Column("channel", sa.Text(), nullable=True))
    op.add_column("consents", sa.Column("evidence_ref", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("consents", "evidence_ref")
    op.drop_column("consents", "channel")
    op.drop_column("consents", "text_hash")
