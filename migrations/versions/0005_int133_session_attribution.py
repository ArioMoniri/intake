"""INT-133 — session attribution: the proxy flag every record reads.

files/06 §6: "Companion/proxy answers are always flagged ``proxy_reported``
on the record". This migration puts the three files/02 §3 / files/04 §5
provenance facts on ``sessions``, so a note, a slot or a document derived
from a session reads ONE flag instead of each carrying a settable copy that
could drift out of step with the others.

**No new personal-data category, and deliberately so.** These are the same
three facts the clinician note already carries and already exports to FHIR
(``clinical_schemas.note.ScreeningProvenance``): who answered, whether a
second person was there, and — new here — when the companion acknowledged
the role. Nothing identifies the companion: no name, no account ref, no
relationship, no free text (invariant 14/6). A persisted person↔person link
is the separate ``guardian_links`` table of 0003, which stays behind its
shut ``guardian_link`` gate.

``proxy_ack_at`` is an acknowledgement of ROLE, never of representation. The
proof-of-velâyet standard is the awaiting-human ``guardian_relationship_proof``
policy row (HUMAN_BLOCKERS HB-L20), and the age gate refuses every minor
subject before this column is ever written.

Backfill is the safe direction: existing rows become ``self_report`` with no
third party, which is what every session recorded before this issue actually
was — the companion path did not exist to produce anything else.

Revision ID: 0005_int133
Revises: 0004_int037
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_int133"
down_revision = "0004_int037"
branch_labels = None
depends_on = None

_ATTRIBUTION_VALUES = ("self_report", "proxy_report", "assisted_self_report")

# native_enum=False, exactly as 0001 carries session_status and
# slot_sensitivity: VARCHAR on the wire, the value set enforced by the ORM
# type rather than a postgres enum nobody can migrate cheaply.
_ATTRIBUTION_TYPE = sa.Enum(
    *_ATTRIBUTION_VALUES,
    name="session_attribution",
    native_enum=False,
    length=24,
)


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "attribution",
            _ATTRIBUTION_TYPE,
            nullable=False,
            server_default="self_report",
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "third_party_present",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "sessions",
        sa.Column("proxy_ack_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    for column in ("proxy_ack_at", "third_party_present", "attribution"):
        op.drop_column("sessions", column)
    # native_enum=False leaves no postgres type behind — nothing to drop
    # after the columns, the 0001 precedent for every enum in this schema.
