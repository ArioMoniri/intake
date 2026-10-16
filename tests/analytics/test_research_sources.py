"""INT-490 — the release is computed server-side from what is ALREADY stored.

The funnel and the locale read row metadata only — a session's protocol,
locale and instants; whether a note, a share or a document exists, and when.
No query here touches a content column (``notes.payload``, ``slots.value``,
``documents.object_ref`` …): the near-miss test listens to every statement and
fails on one that names a content column. The triage level lives only inside
the envelope-encrypted previsit document, so it is reported not collected
rather than decrypted for a staff read (files/10 §9: one path to patient
content, break-glass).

Stage semantics are "as of the end of the week": a share made after the week
closed does not move the week's figure, so two reads of a closed week agree.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from api_harness import run, sqlite_ddl_clone
from intake_platform.analytics.research import (
    FAMILY_VIEW_KINDS,
    QUESTION_VIEW_KINDS,
    AnalyticsRetention,
    Period,
    Stage,
    ViewKind,
)
from intake_platform.analytics.research.sources import (
    LIVE_VIEW_KINDS,
    SourceUnreadable,
    family_records,
    not_collected_reasons,
)
from intake_platform.consent.texts import ConsentTextCatalog
from intake_platform.db.models import (
    Consent,
    Document,
    IntakeSession,
    KvkkRole,
    Note,
    Patient,
    Share,
    Tenant,
)
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

WEEK = Period(2026, 30)
TENANT = uuid.UUID("2a7c9e41-6b3d-4f58-8e02-1d9c4b7a6e33")
OTHER = uuid.UUID("7e1b5c93-0d4a-4c26-b8f1-3a6e9d2c5b17")
AT = WEEK.start + timedelta(days=1)
CONTENT_COLUMNS = ("payload", "value", "object_ref", "provenance", "pseudonym", "recipient")


@pytest.fixture()
def engine(tmp_path: Path) -> Iterator[AsyncEngine]:
    db = tmp_path / "analytics.db"
    ddl = create_engine(f"sqlite+pysqlite:///{db}")
    sqlite_ddl_clone().create_all(ddl)
    ddl.dispose()
    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db}", poolclass=NullPool)
    yield async_engine
    run(async_engine.dispose())


class Seeder:
    def __init__(self, session: AsyncSession, tenant: uuid.UUID = TENANT) -> None:
        self.session = session
        self.tenant = tenant

    def patient(self) -> Patient:
        row = Patient(id=uuid.uuid4(), tenant_id=self.tenant, pseudonym=uuid.uuid4().hex)
        self.session.add(row)
        return row

    def visit(self, patient: Patient, **kwargs: object) -> IntakeSession:
        values: dict[str, object] = {
            "protocol_id": "int490.pack",
            "protocol_version": "v1",
            "created_at": AT,
        }
        values.update(kwargs)
        row = IntakeSession(id=uuid.uuid4(), tenant_id=self.tenant, patient_id=patient.id, **values)
        self.session.add(row)
        return row

    def note(self, visit: IntakeSession, at=AT) -> Note:  # type: ignore[no-untyped-def]
        row = Note(
            id=uuid.uuid4(),
            tenant_id=self.tenant,
            session_id=visit.id,
            patient_id=visit.patient_id,
            payload={"envelope": "opaque"},
            created_at=at,
        )
        self.session.add(row)
        return row

    def share(self, note: Note, at=AT) -> None:  # type: ignore[no-untyped-def]
        self.session.add(
            Share(
                tenant_id=self.tenant,
                note_id=note.id,
                scope_sections={"section_ids": []},
                expires_at=at + timedelta(hours=72),
                created_at=at,
            )
        )

    def document(self, visit: IntakeSession, at=AT) -> None:  # type: ignore[no-untyped-def]
        self.session.add(
            Document(
                tenant_id=self.tenant,
                patient_id=visit.patient_id,
                session_id=visit.id,
                object_ref="opaque",
                sha256="0" * 64,
                media_type="application/pdf",
                provenance={},
                created_at=at,
            )
        )

    def withdraw(self, patient: Patient, *, regrant: bool = False) -> None:
        self.session.add(
            Consent(
                tenant_id=self.tenant,
                patient_id=patient.id,
                scope="learning:service_improvement",
                version="v1",
                granted_at=AT - timedelta(days=30),
                revoked_at=AT - timedelta(days=2),
            )
        )
        if regrant:
            self.session.add(
                Consent(
                    tenant_id=self.tenant,
                    patient_id=patient.id,
                    scope="learning:service_improvement",
                    version="v1",
                    granted_at=AT - timedelta(days=1),
                )
            )


async def _tenants(session: AsyncSession) -> None:
    session.add(Tenant(id=TENANT, display_name="A", kvkk_role=KvkkRole.CONTROLLER))
    session.add(Tenant(id=OTHER, display_name="B", kvkk_role=KvkkRole.CONTROLLER))
    await session.flush()


async def _read(engine: AsyncEngine, catalog: ConsentTextCatalog):  # type: ignore[no-untyped-def]
    async with AsyncSession(engine) as session:
        return await family_records(session, tenant_id=TENANT, period=WEEK, catalog=catalog)


@pytest.fixture()
def catalog(tmp_path: Path) -> ConsentTextCatalog:
    return ConsentTextCatalog(tmp_path / "legal-not-authored")


def test_stages_are_the_furthest_reached_by_the_end_of_the_week(
    engine: AsyncEngine, catalog: ConsentTextCatalog
) -> None:
    async def seed() -> dict[str, uuid.UUID]:
        async with AsyncSession(engine) as session, session.begin():
            await _tenants(session)
            s = Seeder(session)
            people = {
                name: s.patient()
                for name in (
                    "opened",
                    "start_instant",
                    "document",
                    "note",
                    "sent",
                    "sent_late",
                    "completed",
                    "before_week",
                    "next_week",
                )
            }
            s.visit(people["opened"])
            s.visit(people["start_instant"], started_at=AT)
            s.document(s.visit(people["document"]))
            s.note(s.visit(people["note"]))
            s.share(s.note(s.visit(people["sent"])))
            s.share(s.note(s.visit(people["sent_late"])), at=WEEK.end + timedelta(hours=1))
            s.visit(people["completed"], completed_at=AT)
            s.visit(people["before_week"], created_at=WEEK.start - timedelta(seconds=1))
            s.visit(people["next_week"], created_at=WEEK.end)
            return {name: row.id for name, row in people.items()}

    ids = run(seed())
    records = {record.subject: record for record in run(_read(engine, catalog))}
    by_name = {name: records.get(pid) for name, pid in ids.items()}
    assert by_name["opened"].stage is Stage.INVITED  # type: ignore[union-attr]
    assert by_name["start_instant"].stage is Stage.STARTED  # type: ignore[union-attr]
    assert by_name["document"].stage is Stage.STARTED  # type: ignore[union-attr]
    assert by_name["note"].stage is Stage.FINISHED  # type: ignore[union-attr]
    assert by_name["sent"].stage is Stage.SHARED  # type: ignore[union-attr]
    assert by_name["sent_late"].stage is Stage.FINISHED  # type: ignore[union-attr]
    assert by_name["completed"].stage is Stage.FINISHED  # type: ignore[union-attr]
    assert by_name["before_week"] is None and by_name["next_week"] is None


def test_the_loop2_opt_out_is_honoured_and_a_later_grant_wins(
    engine: AsyncEngine, catalog: ConsentTextCatalog
) -> None:
    async def seed() -> tuple[uuid.UUID, uuid.UUID]:
        async with AsyncSession(engine) as session, session.begin():
            await _tenants(session)
            s = Seeder(session)
            out, back = s.patient(), s.patient()
            s.visit(out)
            s.visit(back)
            s.withdraw(out)
            s.withdraw(back, regrant=True)
            return out.id, back.id

    out, back = run(seed())
    subjects = {record.subject for record in run(_read(engine, catalog))}
    assert out not in subjects and back in subjects


def test_a_person_counts_once_per_version_their_latest_session_speaking(
    engine: AsyncEngine, catalog: ConsentTextCatalog
) -> None:
    async def seed() -> uuid.UUID:
        async with AsyncSession(engine) as session, session.begin():
            await _tenants(session)
            s = Seeder(session)
            twice = s.patient()
            s.share(s.note(s.visit(twice, created_at=AT)))
            s.visit(twice, created_at=AT + timedelta(hours=5))
            s.visit(twice, protocol_version="v2")
            return twice.id

    twice = run(seed())
    records = [r for r in run(_read(engine, catalog)) if r.subject == twice]
    assert sorted((r.protocol_version, r.stage) for r in records) == [
        ("v1", Stage.INVITED),
        ("v2", Stage.INVITED),
    ]
    assert all(r.triage is None and r.platform is None and not r.questions for r in records)


def test_another_tenants_rows_are_never_read(
    engine: AsyncEngine, catalog: ConsentTextCatalog
) -> None:
    async def seed() -> uuid.UUID:
        async with AsyncSession(engine) as session, session.begin():
            await _tenants(session)
            other = Seeder(session, tenant=OTHER)
            stranger = other.patient()
            other.visit(stranger)
            return stranger.id

    stranger = run(seed())
    assert stranger not in {r.subject for r in run(_read(engine, catalog))}


def test_no_statement_names_a_content_column(
    engine: AsyncEngine, catalog: ConsentTextCatalog
) -> None:
    async def seed() -> None:
        async with AsyncSession(engine) as session, session.begin():
            await _tenants(session)
            s = Seeder(session)
            for _ in range(3):
                visit = s.visit(s.patient())
                s.document(visit)
                s.share(s.note(visit))

    run(seed())
    statements: list[str] = []
    event.listen(
        engine.sync_engine,
        "before_cursor_execute",
        lambda conn, cursor, statement, *args: statements.append(statement.lower()),
    )
    run(_read(engine, catalog))
    selects = [s for s in statements if s.lstrip().startswith("select")]
    assert selects
    for statement in selects:
        for column in CONTENT_COLUMNS:
            assert f".{column}" not in statement and f" {column}," not in statement, column


def test_a_locale_outside_the_registry_refuses_the_read(
    engine: AsyncEngine, catalog: ConsentTextCatalog
) -> None:
    async def seed() -> None:
        async with AsyncSession(engine) as session, session.begin():
            await _tenants(session)
            s = Seeder(session)
            s.visit(s.patient(), locale="xx")

    run(seed())
    with pytest.raises(SourceUnreadable) as refused:
        run(_read(engine, catalog))
    assert refused.value.code == "locale_outside_registry"


def test_free_text_in_a_protocol_column_refuses_the_read(
    engine: AsyncEngine, catalog: ConsentTextCatalog
) -> None:
    async def seed() -> None:
        async with AsyncSession(engine) as session, session.begin():
            await _tenants(session)
            s = Seeder(session)
            s.visit(s.patient(), protocol_id="göğüs ağrısı")

    run(seed())
    with pytest.raises(SourceUnreadable) as refused:
        run(_read(engine, catalog))
    assert refused.value.code == "dimension_not_id_shaped"
    assert "göğüs" not in str(refused.value)


def test_what_is_live_and_what_is_not_collected_partition_every_view_kind() -> None:
    undecided = AnalyticsRetention(aggregates=None, raw_telemetry=None)
    reasons = not_collected_reasons(undecided)
    assert LIVE_VIEW_KINDS == {ViewKind.FUNNEL, ViewKind.LOCALE}
    assert set(reasons) | LIVE_VIEW_KINDS == set(ViewKind)
    assert not set(reasons) & LIVE_VIEW_KINDS
    assert reasons[ViewKind.TRIAGE] == "triage_level_not_recorded"
    for kind in QUESTION_VIEW_KINDS | {ViewKind.PLATFORM}:
        assert reasons[kind] == "raw_telemetry_retention_undecided"
    decided = AnalyticsRetention(aggregates=None, raw_telemetry=timedelta(days=7))
    assert not_collected_reasons(decided)[ViewKind.QUESTION_MODE] == "raw_telemetry_not_recorded"
    assert FAMILY_VIEW_KINDS >= LIVE_VIEW_KINDS
