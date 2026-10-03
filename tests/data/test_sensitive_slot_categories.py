"""INT-349 — sensitive intake categories at rest, and the register that gates them.

Owner decision D3 (2026-09-26) approved eight categories of personal data for
the specialty review queue and left INT-349 open for what the approval did not
decide. This file holds the storage and register halves:

- **Encryption.** An answer to a slot whose category is not ``general_health``
  is written with field-level envelope encryption through the existing
  ``EnvelopeCipher`` (invariant 14) — ``slots.sensitivity`` is never ``plain``
  for it — and the stored row, read back raw, holds no plaintext. The
  control proves ``general_health`` answers are stored exactly as before.
- **Register.** docs/legal/data-categories.yaml has exactly one row per
  non-general category. Its legal fields are counsel's, and they ship empty
  (invariant 18). The loader's refusals and the compiler gate are tested with
  the protocols package (tests/protocols/test_data_register.py and
  tests/protocols/test_data_category_gate.py).

Every answer below is synthetic (files/04 §7).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from intake_api import store
from intake_platform.db.models import Base, KvkkRole, Slot, SlotSensitivity, Tenant
from intake_platform.envelope import EnvelopeCipher, FileKekProvider, TamperError
from protocols.data_register import (
    COUNSEL_FIELDS,
    DATA_REGISTER_PATH,
    OTHER_SUBJECT_CATEGORIES,
    load_data_register,
)
from protocols.types import DataCategory
from sqlalchemy import (
    JSON,
    DateTime,
    DefaultClause,
    MetaData,
    create_engine,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_REGISTER = REPO_ROOT / DATA_REGISTER_PATH
NON_GENERAL = tuple(c for c in DataCategory if c is not DataCategory.GENERAL_HEALTH)
# A marker no ciphertext, base64 alphabet or JSON key could produce by accident.
ANSWER_MARKER = "SENTETİK-yanıt-İNT349-çğış"


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


def _sqlite_metadata() -> MetaData:
    """The INT-030 metadata re-typed for SQLite CREATE TABLE (JSONB → JSON)."""
    clone = MetaData()
    for table in Base.metadata.sorted_tables:
        copied = table.to_metadata(clone)
        for column in copied.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            if column.server_default is not None:
                column.server_default = (
                    DefaultClause(text("CURRENT_TIMESTAMP"))
                    if isinstance(column.type, DateTime)
                    else None
                )
    return clone


@pytest.fixture
def db(tmp_path: Path) -> tuple[AsyncEngine, Path]:
    """TENANT is a hospital-controller deployment (``kvkk_role: processor``),
    the one deployment in which the store admits every category (INT-474), so
    the at-rest property below is proven for all eight. The consumer side of
    that gate is tests/data/test_deployment_role_store_gate.py."""
    path = tmp_path / "slots.db"
    ddl = create_engine(f"sqlite+pysqlite:///{path}")
    _sqlite_metadata().create_all(ddl)
    with ddl.begin() as conn:
        conn.execute(
            insert(Tenant).values(
                id=TENANT,
                display_name="Sentetik Hastane",
                kvkk_role=KvkkRole.PROCESSOR,
                created_at=datetime(2026, 10, 4, tzinfo=UTC),
            )
        )
    ddl.dispose()
    return create_async_engine(f"sqlite+aiosqlite:///{path}", poolclass=NullPool), path


@pytest.fixture
def cipher() -> EnvelopeCipher:
    return EnvelopeCipher(FileKekProvider())


TENANT = uuid.UUID("00000000-0000-4000-8000-000000000349")
VISIT = uuid.UUID("00000000-0000-4000-8000-000000003490")


def _answer() -> dict[str, object]:
    return {"text": ANSWER_MARKER, "confirmed": True}


async def _write(
    engine: AsyncEngine,
    cipher: EnvelopeCipher,
    category: DataCategory | str,
    *,
    slot_id: str = "sorular.su_an_guvende",
    value: dict[str, object] | None = None,
    session_id: uuid.UUID = VISIT,
) -> None:
    async with AsyncSession(engine) as session, session.begin():
        await store.write_slot_answer(
            session,
            cipher=cipher,
            tenant_id=TENANT,
            session_id=session_id,
            slot_id=slot_id,
            data_category=category,
            value=_answer() if value is None else value,
        )


async def _raw_rows(engine: AsyncEngine) -> list[tuple[str, str, str]]:
    """What is at rest, read back as SQL text — never through the ORM mapper."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT slot_id, sensitivity, value FROM slots"))
        return [(str(r[0]), str(r[1]), str(r[2])) for r in result.all()]


async def _read(
    engine: AsyncEngine, cipher: EnvelopeCipher, slot_id: str = "sorular.su_an_guvende"
) -> dict[str, object] | None:
    async with AsyncSession(engine) as session:
        return await store.read_slot_answer(
            session, cipher=cipher, tenant_id=TENANT, session_id=VISIT, slot_id=slot_id
        )


# --------------------------------------------------------------------------
# Encryption at rest.
# --------------------------------------------------------------------------


def test_general_health_maps_to_plain_and_every_other_category_to_sensitive() -> None:
    assert store.slot_sensitivity(DataCategory.GENERAL_HEALTH) is SlotSensitivity.PLAIN
    assert {store.slot_sensitivity(c) for c in NON_GENERAL} == {SlotSensitivity.SENSITIVE}


@pytest.mark.parametrize("category", NON_GENERAL, ids=lambda c: c.value)
def test_a_tagged_answer_leaves_no_plaintext_at_rest(
    db: tuple[AsyncEngine, Path], cipher: EnvelopeCipher, category: DataCategory
) -> None:
    engine, path = db
    _run(_write(engine, cipher, category))
    rows = _run(_raw_rows(engine))
    assert len(rows) == 1
    _, sensitivity, stored = rows[0]
    assert sensitivity == SlotSensitivity.SENSITIVE.value
    assert set(json.loads(stored)) == {"key_version", "wrapped_dek", "nonce", "ciphertext"}
    assert ANSWER_MARKER not in stored
    assert "confirmed" not in stored
    _run(engine.dispose())
    # the whole database file, not only the column: nothing wrote the answer
    # anywhere on disk in the clear
    at_rest = path.read_bytes()
    assert ANSWER_MARKER.encode("utf-8") not in at_rest
    assert json.dumps(ANSWER_MARKER).encode("ascii") not in at_rest


def test_a_tagged_answer_round_trips_through_the_tenant_key(
    db: tuple[AsyncEngine, Path], cipher: EnvelopeCipher
) -> None:
    engine, _ = db
    _run(_write(engine, cipher, DataCategory.PERSONAL_SAFETY))
    assert _run(_read(engine, cipher)) == _answer()
    _run(engine.dispose())


def test_control_a_general_health_answer_is_stored_exactly_as_before(
    db: tuple[AsyncEngine, Path], cipher: EnvelopeCipher
) -> None:
    """INT-030's plain representation is unchanged: the JSON value itself."""
    engine, _ = db
    _run(_write(engine, cipher, DataCategory.GENERAL_HEALTH, slot_id="ziyaret.basvuru_nedeni"))
    [(slot_id, sensitivity, stored)] = _run(_raw_rows(engine))
    assert (slot_id, sensitivity) == ("ziyaret.basvuru_nedeni", SlotSensitivity.PLAIN.value)
    assert json.loads(stored) == _answer()
    assert _run(_read(engine, cipher, "ziyaret.basvuru_nedeni")) == _answer()
    _run(engine.dispose())


def test_a_corrected_tagged_answer_stays_encrypted(
    db: tuple[AsyncEngine, Path], cipher: EnvelopeCipher
) -> None:
    engine, _ = db
    _run(_write(engine, cipher, DataCategory.SUBSTANCE_USE, value={"text": "ilk"}))
    _run(_write(engine, cipher, DataCategory.SUBSTANCE_USE))
    [(_, sensitivity, stored)] = _run(_raw_rows(engine))
    assert sensitivity == SlotSensitivity.SENSITIVE.value
    assert ANSWER_MARKER not in stored
    assert _run(_read(engine, cipher)) == _answer()
    _run(engine.dispose())


def test_an_envelope_moved_to_another_slot_does_not_open(
    db: tuple[AsyncEngine, Path], cipher: EnvelopeCipher
) -> None:
    """The ciphertext is bound to its session and slot (AES-GCM AAD), so a row
    edit that moves one answer under another question fails authentication."""
    engine, _ = db
    _run(_write(engine, cipher, DataCategory.SEXUAL_HEALTH, slot_id="sorular.a"))
    _run(_write(engine, cipher, DataCategory.SEXUAL_HEALTH, slot_id="sorular.b", value={"x": 1}))

    async def _swap() -> None:
        async with AsyncSession(engine) as session, session.begin():
            rows = {r.slot_id: r for r in (await session.scalars(select(Slot))).all()}
            rows["sorular.b"].value = dict(rows["sorular.a"].value)

    _run(_swap())
    with pytest.raises(TamperError):
        _run(_read(engine, cipher, "sorular.b"))
    _run(engine.dispose())


def test_an_unknown_category_is_refused_before_anything_is_written(
    db: tuple[AsyncEngine, Path], cipher: EnvelopeCipher
) -> None:
    engine, _ = db
    with pytest.raises(ValueError, match="sexual"):
        _run(_write(engine, cipher, "sexual"))
    assert _run(_raw_rows(engine)) == []
    _run(engine.dispose())


def test_control_create_visit_still_writes_its_visit_facts_plain(
    db: tuple[AsyncEngine, Path],
) -> None:
    engine, _ = db

    async def _visit() -> None:
        async with AsyncSession(engine) as session, session.begin():
            await store.create_visit(
                session,
                tenant_id=TENANT,
                patient_id=uuid.uuid4(),
                hospital="Sentetik Hastane",
                department="Sentetik Bölüm",
                date=None,
            )

    _run(_visit())
    assert {s for _, s, _ in _run(_raw_rows(engine))} == {SlotSensitivity.PLAIN.value}
    _run(engine.dispose())


# --------------------------------------------------------------------------
# The committed register.
# --------------------------------------------------------------------------


def test_the_committed_register_has_one_row_per_non_general_category() -> None:
    register = load_data_register(COMMITTED_REGISTER)
    assert set(register.rows) == set(NON_GENERAL)
    for category, row in register.rows.items():
        assert row.category is category
        assert row.purpose.strip(), f"{category.value}: purpose is engineering's to state"


def test_the_committed_register_asserts_no_legal_value_today() -> None:
    """Every counsel field ships empty: nobody but counsel names a KVKK basis,
    a retention clock, recipients or a consent scope (D3 §3; invariant 17).
    This test is meant to change on the day counsel's answers land — in the
    same diff as those answers, so the change is visible."""
    register = load_data_register(COMMITTED_REGISTER)
    for category, row in register.rows.items():
        for name in COUNSEL_FIELDS:
            assert getattr(row, name) is None, f"{category.value}.{name} was filled"
        missing = register.missing(category)
        assert {"basis", "retention", "recipients", "consent_scope"} <= set(missing)
        assert "counsel_reviewed_at" in missing
        if category in OTHER_SUBJECT_CATEGORIES:
            assert "other_subject_basis_and_notice" in missing


def test_general_health_is_never_missing_anything() -> None:
    register = load_data_register(COMMITTED_REGISTER)
    assert register.missing(DataCategory.GENERAL_HEALTH) == ()
