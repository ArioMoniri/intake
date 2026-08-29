"""INT-030 — SqlAlchemyAuditStore: the AuditStore protocol (intake_platform.audit)
over the ``audit_chain`` table.

Unit lane: SQLite in-memory carries the table (its columns are dialect-neutral
on purpose), so append/last/entries and chain-resume semantics are proven
without docker. What SQLite cannot prove — that UPDATE and DELETE are refused
at the grant level — is exactly what tests/data/test_rls.py proves against
Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest
from intake_platform.audit import (
    AuditChain,
    AuditEntry,
    run_daily_verifier,
    verify_entries,
)
from intake_platform.db.audit_store import AuditChainRow, SqlAlchemyAuditStore
from intake_platform.db.models import Base
from sqlalchemy import Engine, create_engine, text


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng, tables=[AuditChainRow.__table__])
    yield eng
    eng.dispose()


def _append(chain: AuditChain, n: int) -> list[AuditEntry]:
    return [
        chain.append(
            actor="svc-audit-writer",
            action="int030.test",
            resource_ref=f"note:{index}",
            consent_scope_ref="scope:previsit_note",
        )
        for index in range(n)
    ]


def test_empty_store_reads_as_empty(engine: Engine) -> None:
    store = SqlAlchemyAuditStore(engine)
    assert store.last() is None
    assert store.entries() == ()


def test_append_last_entries_roundtrip_through_the_table(engine: Engine) -> None:
    store = SqlAlchemyAuditStore(engine)
    chain = AuditChain(store)
    written = _append(chain, 3)
    assert store.last() == written[-1]
    assert list(store.entries()) == written
    assert chain.verify().ok


def test_chain_resumes_from_the_persisted_tail(engine: Engine) -> None:
    first = AuditChain(SqlAlchemyAuditStore(engine))
    written = _append(first, 2)

    # a fresh process over the same table picks up seq and head, not genesis
    resumed = AuditChain(SqlAlchemyAuditStore(engine))
    assert resumed.head == written[-1].entry_hash
    entry = resumed.append(
        actor="svc-audit-writer",
        action="int030.resume",
        resource_ref="note:after-restart",
        consent_scope_ref="scope:previsit_note",
    )
    assert entry.seq == 3
    assert entry.prev_hash == written[-1].entry_hash
    assert run_daily_verifier(SqlAlchemyAuditStore(engine), expected_head=resumed.head).ok


def test_verifier_names_the_seq_of_a_row_edited_in_the_table(engine: Engine) -> None:
    """SQLite has no grants, so an UPDATE goes through — which is precisely
    why the verifier must catch it: the store faithfully returns what the
    table holds, and the chain math names the edited row."""
    store = SqlAlchemyAuditStore(engine)
    chain = AuditChain(store)
    _append(chain, 3)
    with engine.begin() as conn:
        conn.execute(text("UPDATE audit_chain SET actor = 'someone-else' WHERE seq = 2"))
    result = verify_entries(store.entries())
    assert not result.ok
    assert result.first_bad_seq == 2


def test_store_returns_frozen_entries_equal_to_what_was_written(engine: Engine) -> None:
    store = SqlAlchemyAuditStore(engine)
    chain = AuditChain(store)
    [entry] = _append(chain, 1)
    fetched = store.entries()[0]
    assert isinstance(fetched, AuditEntry)
    assert fetched == entry
    # frozen dataclass: tampering an in-memory copy cannot alter the stored row
    with pytest.raises(AttributeError):
        fetched.actor = "intruder"  # type: ignore[misc]
    assert replace(fetched, actor="intruder") != store.entries()[0]
