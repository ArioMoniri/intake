"""SQLAlchemy AuditStore over the ``audit_chain`` table (INT-030, completing
the seam intake_platform.audit left open: append → INSERT, last → ORDER BY seq
DESC LIMIT 1, entries → ORDER BY seq scan).

The table is INSERT-shaped on purpose: in Postgres, ``svc_audit_writer`` holds
the only INSERT grant and no principal anywhere holds UPDATE or DELETE
(files/10 §2, invariant 40's grant half) — the migration emits those grants
and tests/data/test_rls.py proves them live. The store itself exposes no
update/delete either, mirroring the AuditStore protocol.

Column types are dialect-neutral (no JSONB, no UUID) so the unit lane can
carry the table on SQLite; ``timestamp_utc`` stays the ISO **text** the entry
hash was computed over — parsing it into a datetime and re-serialising is a
rehash-breaking transformation the store must never perform.
"""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import Engine, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import BigInteger

from intake_platform.audit import AuditEntry
from intake_platform.db.inventory import (
    BASIS_LEGAL_OBLIGATION,
    CAT_AUDIT,
    REC_AUDITOR,
    RET_CONSENT_AUDIT,
    inv,
)
from intake_platform.db.models import Base

__all__ = ["AuditChainRow", "SqlAlchemyAuditStore"]


def _audit_inv(purpose: str) -> dict[str, object]:
    annotation: dict[str, object] = dict(
        inv(CAT_AUDIT, purpose, BASIS_LEGAL_OBLIGATION, RET_CONSENT_AUDIT, REC_AUDITOR)
    )
    return annotation


class AuditChainRow(Base):
    """One persisted chain link — the closed AuditEntry field set and nothing
    else (invariant 6: a column that does not exist cannot accumulate PHI)."""

    __tablename__ = "audit_chain"

    seq: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        info=_audit_inv("chain position; monotonic so a gap alerts on its own"),
    )
    timestamp_utc: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info=_audit_inv("ISO instant exactly as hashed (stored as text, never re-serialised)"),
    )
    actor: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        info=_audit_inv("id-shaped acting principal (never a display name)"),
    )
    action: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        info=_audit_inv("dotted action name (read/share/export/…)"),
    )
    resource_ref: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        info=_audit_inv("id-shaped reference to the touched resource"),
    )
    consent_scope_ref: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        info=_audit_inv("the consent scope the access was checked against (invariant 4)"),
    )
    prev_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        info=_audit_inv("SHA-256 of the predecessor entry (the chain link)"),
    )
    entry_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        info=_audit_inv("SHA-256 over this entry's canonical form"),
    )


def _to_entry(row: AuditChainRow) -> AuditEntry:
    return AuditEntry(
        seq=row.seq,
        timestamp_utc=row.timestamp_utc,
        actor=row.actor,
        action=row.action,
        resource_ref=row.resource_ref,
        consent_scope_ref=row.consent_scope_ref,
        prev_hash=row.prev_hash,
        entry_hash=row.entry_hash,
    )


class SqlAlchemyAuditStore:
    """AuditStore implementation. Connect it with the ``svc_audit_writer``
    engine to write (AuditChain does the hashing) or the app engine to run
    the daily verifier read-only."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, entry: AuditEntry) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(AuditChainRow(**asdict(entry)))

    def last(self) -> AuditEntry | None:
        statement = select(AuditChainRow).order_by(AuditChainRow.seq.desc()).limit(1)
        with Session(self._engine) as session:
            row = session.scalars(statement).first()
        return None if row is None else _to_entry(row)

    def entries(self) -> tuple[AuditEntry, ...]:
        statement = select(AuditChainRow).order_by(AuditChainRow.seq)
        with Session(self._engine) as session:
            return tuple(_to_entry(row) for row in session.scalars(statement))
