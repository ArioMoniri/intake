"""INT-123 — record_embeddings: the pgvector record index, one namespace per patient.

files/10 §5 LLM08: *"pgvector rows scoped by patient + consent; RLS; no shared
namespaces"*. This revision creates the one table that holds vectors and the
two policies that scope it.

- **Two policies, and the second one is RESTRICTIVE.** The tenant policy is
  the one every tenant-scoped table carries (0001): PERMISSIVE, on the
  ``app.tenant_id`` GUC. The patient policy adds ``app.patient_id``. Postgres
  ORs permissive policies together, so a second PERMISSIVE policy would admit
  a row that passes *either* — every patient in the tenant would read every
  other patient's vectors. As RESTRICTIVE it is ANDed with the tenant policy:
  a row is visible only inside its own tenant AND its own patient's namespace.
  An unset GUC reads as NULL through ``NULLIF`` and selects nothing.
- **FORCE ROW LEVEL SECURITY**, as everywhere (0001): the owner gets no bypass.
- **Least privilege.** ``app_rw`` gets SELECT, INSERT and DELETE — no UPDATE,
  because a vector is replaced by delete-and-insert and never edited in place.
  ``clinician_ro`` gets nothing: a clinician reads a cited item in the note,
  never a vector.
- **No item text.** The table holds the vector, the source box and the item
  id. The confirmed item is the source of truth and the note cites it from
  there.
- **The dimension is a row fact, not a column fact.** No embedding model is
  pinned (files/03 §4.9.1 has no row for one), so ``embedding`` is declared
  ``vector`` without a dimension and ``CHECK (vector_dims(embedding) =
  dimensions)`` binds each row to what its own model declared. Every read is an
  exact scan of one patient's rows, so there is no approximate index to size.
- **pgvector** ships in the compose and CI image (``pgvector/pgvector:pg16``,
  observability/registry.yaml row ``postgres``); production images must carry
  the same extension, as they must carry pgaudit (0001).

Revision ID: 0014_int123
Revises: 0013_previsit_output
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014_int123"
down_revision = "0013_previsit_output"
branch_labels = None
depends_on = None

#: clinical_schemas.records.RecordItemKind, closed in the database as in the type.
_KINDS = ("lab", "imaging", "procedure", "medication", "diagnosis", "allergy")

_GRANTS = (
    "REVOKE ALL ON record_embeddings FROM PUBLIC",
    "GRANT SELECT, INSERT, DELETE ON record_embeddings TO app_rw",
)

_RLS_DDL = (
    "ALTER TABLE record_embeddings ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE record_embeddings FORCE ROW LEVEL SECURITY",
    """CREATE POLICY record_embeddings_tenant_isolation ON record_embeddings
    AS PERMISSIVE FOR ALL TO app_rw
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""",
    """CREATE POLICY record_embeddings_patient_namespace ON record_embeddings
    AS RESTRICTIVE FOR ALL TO app_rw
    USING (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)
    WITH CHECK (patient_id = NULLIF(current_setting('app.patient_id', true), '')::uuid)""",
)


class _Vector(sa.types.UserDefinedType[object]):
    """``vector`` with no dimension — frozen here rather than imported, so this
    revision does not change when the application's column type does."""

    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "vector"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "record_embeddings",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("item_ref", sa.String(35), nullable=False),
        sa.Column("document_ref", sa.String(64), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("bbox", JSONB(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("model_ref", sa.String(160), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", _Vector(), nullable=False),
        sa.Column("consent_scope_ref", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "patient_id",
            "item_ref",
            "model_ref",
            name="uq_record_embeddings_tenant_id",
        ),
        sa.CheckConstraint("page >= 1", name="ck_record_embeddings_page_positive"),
        sa.CheckConstraint(
            "char_end > char_start AND char_start >= 0", name="ck_record_embeddings_char_span"
        ),
        sa.CheckConstraint("dimensions > 0", name="ck_record_embeddings_dimensions_positive"),
        sa.CheckConstraint(
            "vector_dims(embedding) = dimensions", name="ck_record_embeddings_dimensions_match"
        ),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{kind}'" for kind in _KINDS) + ")",
            name="ck_record_embeddings_record_item_kind",
        ),
    )
    op.create_index("ix_record_embeddings_tenant_id", "record_embeddings", ["tenant_id"])
    op.create_index("ix_record_embeddings_patient_id", "record_embeddings", ["patient_id"])
    op.create_index("ix_record_embeddings_document_ref", "record_embeddings", ["document_ref"])

    for statement in (*_GRANTS, *_RLS_DDL):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS record_embeddings_patient_namespace ON record_embeddings")
    op.execute("DROP POLICY IF EXISTS record_embeddings_tenant_isolation ON record_embeddings")
    op.drop_index("ix_record_embeddings_document_ref", table_name="record_embeddings")
    op.drop_index("ix_record_embeddings_patient_id", table_name="record_embeddings")
    op.drop_index("ix_record_embeddings_tenant_id", table_name="record_embeddings")
    op.drop_table("record_embeddings")
    # The extension stays: it is database-wide, and dropping it would fail or
    # cascade into anything else that came to use it (the pgaudit precedent).
