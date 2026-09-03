"""INT-296 — the session locale: one language per session, recorded on the row.

ONE column, and the reason it is a column rather than a lookup is the whole
issue: a session runs in exactly one language, fixed at the start, so the
clinician note, the audit entry and the metric label read the same value and
no turn can be assembled out of two languages.

**The value set is closed elsewhere.** ``intake_platform.locale.LOCALE_REGISTRY``
is the authority, and it holds exactly ``tr`` — which languages this product
supports is HUMAN_BLOCKERS.md HB-O5 (owner) and what they say clinically is
HB-C19 (clinician). No Postgres enum is created here on purpose: a native enum
would be a second value set, migrated on a different clock from the registry,
and the first time the two disagreed the database would win silently.

**Backfill is the true direction, not a default.** Every session written before
this column existed ran in Turkish, because Turkish is the only language this
product has ever spoken. ``server_default 'tr'`` therefore records what those
rows actually were rather than guessing at them.

**Inventory (invariant 18).** The annotation rides the column in
``models.Session.locale``. It is filed as operational metadata *while ``tr`` is
the only registered locale*, because the column then states the service's own
language and nothing about the patient. Enabling a second locale changes that —
a language choice can proxy ethnic origin, which is KVKK m.6 special category —
and the category, basis and recipients must be re-decided first (HB-L25).

Revision ID: 0011_int296
Revises: 0010_int170
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_int296"
down_revision = "0010_int170"
branch_labels = None
depends_on = None

_DEFAULT_LOCALE = "tr"


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "locale",
            sa.Text(),
            nullable=False,
            server_default=_DEFAULT_LOCALE,
            comment=(
                "INT-296 — the one language this session ran in. Closed value set: "
                "intake_platform.locale.LOCALE_REGISTRY (today exactly 'tr'). Never a "
                "free-text language name (invariant 6)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "locale")
