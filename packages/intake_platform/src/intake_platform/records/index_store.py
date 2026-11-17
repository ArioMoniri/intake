"""The record index on Postgres + pgvector, one namespace per transaction (INT-123).

Every method opens its own transaction and makes the same two statements
first: ``set_config('app.tenant_id', …, true)`` and ``set_config(
'app.patient_id', …, true)`` — transaction-local, so no namespace survives into
a pooled connection. The 0014 policies read those GUCs (a PERMISSIVE tenant
policy and a RESTRICTIVE patient policy), and every statement also carries the
two predicates explicitly, the ``intake_api.dsar.store`` convention: the policy
is the boundary, the predicate is what a reviewer reads.

The distance is pgvector's cosine distance ``<=>``, and the scan is exact —
one patient's rows are a few hundred at most, so an approximate index would
trade recall for speed nobody needs (see :mod:`intake_platform.db.vector`).

:func:`erase_record_index` is the async half the DSAR erasure calls. It sets
the patient GUC first because without it the RESTRICTIVE policy turns the
DELETE into a silent no-op — tests/records/test_vector_rls.py shows exactly
that on postgres. :func:`subject_record_index` is the read the DSAR subject
sweep makes (INT-395: the export and the erasure read one sweep), and it sets
the same GUC for the same reason: without it the export would list no vector
at all, silently (tests/integration/test_session_erasure.py).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Final, cast

from clinical_schemas.records import RecordItemKind
from sqlalchemy import Connection, Engine, delete, func, select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from intake_platform.db.models import RecordEmbedding
from intake_platform.db.vector import vector_literal
from intake_platform.records.index import IndexEntry, IndexHit, RecordNamespace

__all__ = ["PgRecordIndexStore", "erase_record_index", "subject_record_index"]

_SET_TENANT: Final = text("SELECT set_config('app.tenant_id', :tenant_id, true)")
_SET_PATIENT: Final = text("SELECT set_config('app.patient_id', :patient_id, true)")

_WRITE: Final = text(
    "INSERT INTO record_embeddings (tenant_id, patient_id, item_ref, document_ref, page, "
    "bbox, char_start, char_end, kind, model_ref, dimensions, embedding, consent_scope_ref) "
    "VALUES (:tenant_id, :patient_id, :item_ref, :document_ref, :page, CAST(:bbox AS jsonb), "
    ":char_start, :char_end, :kind, :model_ref, :dimensions, CAST(:embedding AS vector), "
    ":consent_scope_ref) "
    "ON CONFLICT (tenant_id, patient_id, item_ref, model_ref) DO NOTHING"
)

_NEAREST: Final = text(
    "SELECT item_ref, document_ref, page, bbox, char_start, char_end, kind, "
    "embedding <=> CAST(:query AS vector) AS distance "
    "FROM record_embeddings "
    "WHERE tenant_id = :tenant_id AND patient_id = :patient_id AND model_ref = :model_ref "
    "AND dimensions = :dimensions "
    "ORDER BY distance, item_ref LIMIT :k"
)

_ERASE: Final = text(
    "DELETE FROM record_embeddings WHERE tenant_id = :tenant_id AND patient_id = :patient_id"
)


def _ids(namespace: RecordNamespace) -> dict[str, str]:
    return {"tenant_id": str(namespace.tenant_id), "patient_id": str(namespace.patient_id)}


def _bbox(value: Any) -> tuple[float, float, float, float]:
    raw = json.loads(value) if isinstance(value, str) else value
    x0, y0, x1, y1 = (float(part) for part in raw)
    return (x0, y0, x1, y1)


class PgRecordIndexStore:
    """:class:`~intake_platform.records.index.RecordIndexStore` on Postgres."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @contextmanager
    def _namespaced(self, namespace: RecordNamespace) -> Iterator[Connection]:
        with self._engine.begin() as conn:
            conn.execute(_SET_TENANT, {"tenant_id": str(namespace.tenant_id)})
            conn.execute(_SET_PATIENT, {"patient_id": str(namespace.patient_id)})
            yield conn

    def write(self, entry: IndexEntry) -> None:
        with self._namespaced(entry.namespace) as conn:
            conn.execute(
                _WRITE,
                {
                    **_ids(entry.namespace),
                    "item_ref": entry.item_ref,
                    "document_ref": entry.document_ref,
                    "page": entry.page,
                    "bbox": json.dumps(list(entry.bbox)),
                    "char_start": entry.char_start,
                    "char_end": entry.char_end,
                    "kind": entry.kind.value,
                    "model_ref": entry.model_ref,
                    "dimensions": len(entry.vector),
                    "embedding": vector_literal(entry.vector),
                    "consent_scope_ref": entry.consent_scope_ref,
                },
            )

    def nearest(
        self,
        namespace: RecordNamespace,
        *,
        model_ref: str,
        vector: Sequence[float],
        k: int,
    ) -> tuple[IndexHit, ...]:
        with self._namespaced(namespace) as conn:
            rows = conn.execute(
                _NEAREST,
                {
                    **_ids(namespace),
                    "model_ref": model_ref,
                    "dimensions": len(vector),
                    "query": vector_literal(vector),
                    "k": k,
                },
            ).all()
        return tuple(
            IndexHit(
                item_ref=row.item_ref,
                document_ref=row.document_ref,
                page=int(row.page),
                bbox=_bbox(row.bbox),
                char_start=int(row.char_start),
                char_end=int(row.char_end),
                kind=RecordItemKind(row.kind),
                distance=float(row.distance),
            )
            for row in rows
        )

    def erase(self, namespace: RecordNamespace) -> int:
        with self._namespaced(namespace) as conn:
            result = conn.execute(_ERASE, _ids(namespace))
            return int(result.rowcount or 0)


async def _enter_patient_namespace(session: AsyncSession, patient_id: uuid.UUID) -> None:
    """Set ``app.patient_id`` for the rest of the caller's transaction, on
    postgres. SQLite has no RLS; its explicit predicates carry the scope."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(select(func.set_config("app.patient_id", str(patient_id), True)))


async def subject_record_index(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> tuple[RecordEmbedding, ...]:
    """One patient's index rows, oldest first, inside the caller's transaction.

    The DSAR subject sweep's read: it sets ``app.patient_id`` as
    :func:`erase_record_index` does, so the export lists exactly the rows the
    erasure then removes. The vector itself is never loaded (``raiseload``):
    a subject's answer names each row and what it indexes, and nothing on the
    DSAR path has a use for the model's coordinates.
    """
    await _enter_patient_namespace(session, patient_id)
    return tuple(
        (
            await session.scalars(
                select(RecordEmbedding)
                .options(defer(RecordEmbedding.embedding, raiseload=True))
                .where(
                    RecordEmbedding.tenant_id == tenant_id,
                    RecordEmbedding.patient_id == patient_id,
                )
                .order_by(RecordEmbedding.created_at, RecordEmbedding.id)
            )
        ).all()
    )


async def erase_record_index(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> int:
    """Delete one patient's vectors inside the caller's transaction.

    The caller has already set ``app.tenant_id`` (``tenant_session``); this
    sets ``app.patient_id`` for the rest of the transaction, which is what the
    RESTRICTIVE policy needs to let the DELETE see the rows at all. On a
    backend without RLS (the SQLite unit lane) the explicit predicates carry
    the scope alone.
    """
    await _enter_patient_namespace(session, patient_id)
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(RecordEmbedding).where(
                RecordEmbedding.tenant_id == tenant_id,
                RecordEmbedding.patient_id == patient_id,
            )
        ),
    )
    return int(result.rowcount or 0)
