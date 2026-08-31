"""INT-170 — PatientOverlay: confirmation is a type, staleness is a decision.

Acceptance under test, verbatim (docs/backlog/issues.yaml INT-170):
  "facts commit only with patient/clinician confirmation (type-level);
   12-month reconfirm; provenance shown; delta-mode works in simulator"

``legal: KVKK-11`` · ``sec_row: learning-loops`` · ``depends_on: [INT-031,
INT-081]``.

CLAUDE.md invariant 12's second sentence is this issue: *"``PatientOverlay``
facts require patient or clinician confirmation (type-level)."* INT-172 read
the first sentence the strong way — it did not assert the invariant, it removed
the representation, so ``level="RED"`` is a ``TypeError`` at the call site
rather than a rejection three layers later. This file holds the same posture
for the second sentence, in four parts:

1. **Confirmation is a different TYPE, not a flag.**
   :class:`~clinical_schemas.overlay.UnconfirmedObservation` is what extraction
   and record import produce; :class:`~clinical_schemas.overlay.ConfirmedFact`
   is the only thing the store accepts. There is no boolean anywhere that a
   caller could set, and no ``Confirmer`` member that is not a person. Proved
   by a cold ``mypy --strict`` run over a conforming fixture and over one that
   tries all five ways to get an unconfirmed value into the store — with the
   per-attempt assertion, because one loud failure could otherwise mask four
   silent successes.

2. **Twelve months is a decided semantics, not a timer.** A fact past the
   window stops being ASSERTED and stays VISIBLE: it is never pre-filled into a
   session, and it is still in the ledger with its provenance and its
   re-confirmation date. The reasoning is in
   :class:`~intake_api.overlay_store.FactStatus`. No wall clock anywhere: the
   store takes a clock with no default and the tests advance it.

3. **Provenance is unconstructable-if-absent.** Where from, when, and by whom —
   and patient and clinician are not interchangeable, so ``Confirmer`` keeps
   them apart all the way to the wire.

4. **Delta mode works in the simulator**, driven by a fact that went through
   the store rather than one written into a persona by hand.

Environment note, recorded rather than hidden: there is no Docker daemon here
and therefore no Postgres, so no live database was reached by any test in this
file. The store's persistence seam is a protocol with an in-process double
below; the SQLAlchemy repository behind it needs a ``learned_facts`` table that
does not exist yet (see docs/evidence/INT-170.md).
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import inspect
import sys
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from clinical_schemas.overlay import (
    RECONFIRM_AFTER,
    Confirmation,
    ConfirmedFact,
    Confirmer,
    LearnedFactSource,
    PatientOverlay,
    UnconfirmedObservation,
    confirm,
    fact_needs_reconfirmation,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from intake_api.auth import require_principal
from intake_api.consent_guard import ConsentGuard, route_policies, unguarded_data_routes
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID, PATIENT_ACCOUNT
from intake_api.errors import consent_required
from intake_api.learned_routes import get_overlay_store
from intake_api.learned_routes import router as learned_router
from intake_api.overlay_store import (
    OVERLAY_INVENTORY,
    READ_ACTION,
    WITHDRAW_ACTION,
    WITHDRAW_BASIS_REF,
    FactStatus,
    LedgerEntry,
    OverlayFactNotFound,
    PatientOverlayStore,
    SealedFactRow,
)
from intake_platform.db.inventory import INVENTORY_FIELDS
from intake_platform.envelope import EnvelopeCipher, FileKekProvider

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

TENANT = "kiracı-1"
PATIENT = "hasta-17"
KEY = "ilac.ilac_kullanimi"

#: The dev-tier principal the mounted router resolves to (INT-197).
DEV_TENANT = str(DEV_TENANT_ID)
DEV_PATIENT = str(DEV_PATIENT_ID)

#: The simulator's own frozen session clock (tests/sim/protocol.py). Facts are
#: dated relative to it so the store and the engine agree on "now" without
#: either of them reading a wall clock.
SIM_NOW = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


# =====================================================================================
# doubles — an in-process repository and audit sink, so no database is reached
# =====================================================================================


class FakeRepository:
    """The persistence seam, filled in memory.

    It holds SEALED rows and nothing else — the same bytes a Postgres row would
    hold — so a test that reads the double is reading what would be at rest
    (invariant 14: field-level envelope encryption for learned facts).
    """

    def __init__(self) -> None:
        self.rows: list[SealedFactRow] = []

    async def append(self, row: SealedFactRow) -> None:
        for existing in self.rows:
            if existing.fact_id == row.fact_id and existing.patient_ref == row.patient_ref:
                return  # content-addressed: a replayed confirmation is idempotent
        self.rows.append(row)

    async def list_for(self, *, tenant_ref: str, patient_ref: str) -> tuple[SealedFactRow, ...]:
        return tuple(
            row
            for row in self.rows
            if row.tenant_ref == tenant_ref and row.patient_ref == patient_ref
        )

    async def mark_withdrawn(
        self, *, tenant_ref: str, patient_ref: str, fact_id: str, at: datetime
    ) -> SealedFactRow | None:
        for index, row in enumerate(self.rows):
            if (
                row.tenant_ref == tenant_ref
                and row.patient_ref == patient_ref
                and row.fact_id == fact_id
            ):
                updated = dataclasses.replace(row, withdrawn_at=at)
                self.rows[index] = updated
                return updated
        return None


class RecordingAudit:
    """An audit sink that records, and can be made to fail."""

    def __init__(self, *, fails: bool = False) -> None:
        self.entries: list[tuple[str, str, str, str]] = []
        self.fails = fails

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None:
        if self.fails:
            raise RuntimeError("audit chain unavailable")
        self.entries.append((actor, action, resource_ref, consent_scope))

    @property
    def actions(self) -> list[str]:
        return [entry[1] for entry in self.entries]


class ManualClock:
    """A clock the test moves. No wall clock reaches this suite (docs/TDD.md
    rule 6) — a wall-clock expiry test is a flake, and this one would take a
    year to go red."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def build_store(
    *, now: datetime = SIM_NOW, audit: RecordingAudit | None = None
) -> tuple[PatientOverlayStore, FakeRepository, RecordingAudit, ManualClock]:
    repository = FakeRepository()
    sink = RecordingAudit() if audit is None else audit
    clock = ManualClock(now)
    store = PatientOverlayStore(
        repository=repository,
        sealer=EnvelopeCipher(FileKekProvider()),
        clock=clock,
        audit=sink,
    )
    return store, repository, sink, clock


def a_fact(
    *,
    by: Confirmer = Confirmer.PATIENT,
    at: datetime = SIM_NOW,
    key: str = KEY,
    value: bool = False,
    source: LearnedFactSource = LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
    source_ref: str = "oturum-91",
    actor_ref: str = PATIENT,
) -> ConfirmedFact:
    return confirm(
        UnconfirmedObservation(key=key, value=value, observed_ref=source_ref, observed_at=at),
        by=by,
        actor_ref=actor_ref,
        at=at,
        source=source,
        source_ref=source_ref,
        confidence=1.0,
    )


def run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


# =====================================================================================
# 1 · "(type-level)" — the checker separates a confirmed fact from an unconfirmed one
# =====================================================================================


@pytest.fixture(scope="module")
def mypy_report() -> str:
    """One cold ``mypy --strict`` run over both fixtures.

    Both files in one invocation, following INT-110: the checker is the thing
    under test, so the conforming specimen and the offending one must be judged
    by the same run.
    """
    from mypy import api

    stdout, stderr, _status = api.run(
        [
            "--strict",
            "--no-error-summary",
            "--no-incremental",
            "--hide-error-context",
            str(FIXTURES / "overlay_confirmed_commit.py"),
            str(FIXTURES / "overlay_unconfirmed_commit.py"),
        ]
    )
    return stdout + stderr


def test_mypy_accepts_a_commit_of_a_confirmed_fact(mypy_report: str) -> None:
    """The positive control: the checker is not simply rejecting everything."""
    assert "overlay_confirmed_commit.py" not in mypy_report, (
        "the conforming specimen must type-check clean, or the negative control "
        f"below proves nothing:\n{mypy_report}"
    )


def test_mypy_rejects_every_way_an_unconfirmed_fact_could_be_committed(
    mypy_report: str,
) -> None:
    """Invariant 12's *(type-level)*, as the acceptance words it.

    Five attempts, five findings, asserted one at a time.
    """
    lines = [line for line in mypy_report.splitlines() if "overlay_unconfirmed_commit.py" in line]
    assert lines, f"mypy found nothing wrong with an unconfirmed commit:\n{mypy_report}"
    joined = "\n".join(lines)
    reported = {int(line.split(":")[1]) for line in lines}
    assert len(reported) == 5, (
        f"five attempts, five findings — fewer means one loud failure masked the rest:\n{joined}"
    )

    assert '"UnconfirmedObservation"' in joined, (
        f"the store accepted the shape extraction produces:\n{joined}"
    )
    assert "confirmation" in joined, (
        f"a ConfirmedFact was constructed with no confirmation at all:\n{joined}"
    )
    assert 'Unexpected keyword argument "confirmed"' in joined, (
        "a boolean confirmation flag was accepted — which is the design "
        f"(type-level) exists to rule out:\n{joined}"
    )
    assert 'has no attribute "MODEL"' in joined, (
        f"something other than a patient or a clinician confirmed a fact:\n{joined}"
    )
    assert "read-only" in joined or "frozen" in joined, (
        f"a committed fact's confirmation was re-pointed afterwards:\n{joined}"
    )


def test_the_confirmed_fact_carries_no_boolean_confirmation_flag() -> None:
    """The acceptance says *(type-level)*, and a flag is not a type.

    ``ConfirmedFact``'s only carrier of "who said so" is a ``Confirmation``,
    whose own fields are all required — so there is no field a caller could set
    to true, and none they could leave out.
    """
    names = {field.name for field in dataclasses.fields(ConfirmedFact)}
    assert names == {"key", "value", "confirmation", "confidence"}
    for banned in ("confirmed", "is_confirmed", "verified", "reviewed", "approved"):
        assert banned not in names

    rendered = {f.name: str(f.type) for f in dataclasses.fields(ConfirmedFact)}
    assert "bool" not in rendered["confirmation"]


def test_an_unconfirmed_observation_has_no_carrier_for_a_confirmation() -> None:
    """The other half of the same claim: the unconfirmed type cannot pretend.

    Nothing in it names a confirmer, a confirmation time or a confirmed
    provenance — so "an observation that says it was confirmed" is not a case
    to reject, it is a thing that cannot be written down.
    """
    names = {field.name for field in dataclasses.fields(UnconfirmedObservation)}
    assert names == {"key", "value", "observed_ref", "observed_at"}
    rendered = " ".join(str(f.type) for f in dataclasses.fields(UnconfirmedObservation))
    for banned in ("Confirmation", "Confirmer", "LearnedFactSource"):
        assert banned not in rendered


def test_a_confirmation_can_only_be_a_patient_or_a_clinician() -> None:
    """files/09 §3 and invariant 12 name two confirmers. The enum has two
    members, so a model-confirmed fact is unspellable rather than filtered."""
    assert {member.value for member in Confirmer} == {"patient", "clinician"}
    assert not hasattr(Confirmer, "MODEL")
    with pytest.raises(ValueError, match="not a valid Confirmer"):
        Confirmer("model")


def test_the_two_confirmers_are_not_interchangeable() -> None:
    """A clinician accepting a fact and a patient asserting it are different
    events with different weight; the ledger keeps them apart end to end."""
    store, _repository, _audit, _clock = build_store()
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))
    run(
        store.commit(
            tenant_ref=TENANT,
            patient_ref=PATIENT,
            fact=a_fact(
                key="alerji.penisilin",
                value=True,
                by=Confirmer.CLINICIAN,
                actor_ref="hekim-4",
                source=LearnedFactSource.CLINICIAN_ACCEPTED_NOTE,
                source_ref="not-33",
            ),
            actor="hekim-4",
        )
    )
    entries = run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))
    assert isinstance(entries, tuple)
    by_key = {entry.key: entry for entry in entries}
    assert by_key[KEY].confirmed_by is Confirmer.PATIENT
    assert by_key[KEY].confirmed_by_ref == PATIENT
    assert by_key["alerji.penisilin"].confirmed_by is Confirmer.CLINICIAN
    assert by_key["alerji.penisilin"].confirmed_by_ref == "hekim-4"


def test_the_store_commit_signature_names_the_confirmed_type_and_nothing_wider() -> None:
    """Read off the signature, so a later widening to ``object`` is caught."""
    hints = inspect.signature(PatientOverlayStore.commit, eval_str=True).parameters
    assert hints["fact"].annotation is ConfirmedFact


# =====================================================================================
# 2 · provenance — unconstructable if absent
# =====================================================================================


def test_a_confirmation_with_a_missing_field_cannot_be_built() -> None:
    """ "Provenance shown" starts before rendering: a fact with no provenance
    must not exist to be rendered."""
    for omitted in ("by", "actor_ref", "at", "source", "source_ref"):
        kwargs: dict[str, object] = {
            "by": Confirmer.PATIENT,
            "actor_ref": PATIENT,
            "at": SIM_NOW,
            "source": LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
            "source_ref": "oturum-91",
        }
        del kwargs[omitted]
        with pytest.raises(TypeError):
            Confirmation(**kwargs)  # type: ignore[arg-type]


def test_an_empty_provenance_reference_is_refused() -> None:
    """An empty string is the shape a missing value takes once the type stops
    catching it, so the value type catches it too."""
    for blank in ("", "   "):
        with pytest.raises(ValueError, match="actor_ref|source_ref"):
            Confirmation(
                by=Confirmer.PATIENT,
                actor_ref=blank,
                at=SIM_NOW,
                source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
                source_ref="oturum-91",
            )


def test_the_ledger_shows_where_from_when_and_by_whom() -> None:
    """files/09 §3: every fact shows "where from". The ledger entry carries
    all four axes and a re-confirmation date, and none of them is optional."""
    store, _repository, _audit, _clock = build_store()
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))
    entries = run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))
    assert isinstance(entries, tuple)
    (entry,) = entries
    assert isinstance(entry, LedgerEntry)
    assert entry.key == KEY
    assert entry.source is LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION
    assert entry.source_ref == "oturum-91"
    assert entry.confirmed_by is Confirmer.PATIENT
    assert entry.confirmed_by_ref == PATIENT
    assert entry.confirmed_at == SIM_NOW
    assert entry.reconfirm_due_at == SIM_NOW + RECONFIRM_AFTER
    assert entry.status is FactStatus.ASSERTED
    assert entry.withdrawn_at is None

    optional = [
        field.name
        for field in dataclasses.fields(LedgerEntry)
        if field.name != "withdrawn_at" and "None" in str(field.type)
    ]
    assert optional == [], f"a provenance axis is optional on the ledger: {optional}"


# =====================================================================================
# 3 · twelve-month re-confirmation — a decided semantics, on an injected clock
# =====================================================================================


def test_the_store_has_no_default_clock() -> None:
    """A default would be a wall clock chosen once, by an engineer, for every
    future caller — which is the flake docs/TDD.md rule 6 forbids and the
    determinism files/13 §9.2 requires of anything the engine reads."""
    parameter = inspect.signature(PatientOverlayStore.__init__).parameters["clock"]
    assert parameter.default is inspect.Parameter.empty


def test_no_overlay_module_reads_a_wall_clock() -> None:
    """Asserted over the source, so no branch can reach one — not merely that
    today's happy path does not."""
    offences: list[str] = []
    for relative in ("overlay_store.py", "learned_routes.py"):
        path = REPO / "services" / "api" / "src" / "intake_api" / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"now", "utcnow", "today", "time"}:
                offences.append(f"{relative}:{node.lineno} .{node.attr}")
    assert offences == [], f"a wall clock is reachable from the overlay path: {offences}"


def test_a_fact_is_asserted_inside_the_window_and_stale_one_day_past_it() -> None:
    """ "12-month reconfirm", with the boundary asserted from both sides."""
    store, _repository, _audit, clock = build_store()
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))

    clock.advance(RECONFIRM_AFTER)
    (entry,) = run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))  # type: ignore[misc]
    assert entry.status is FactStatus.ASSERTED, "the last day of the window is inside it"

    clock.advance(timedelta(days=1))
    (entry,) = run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))  # type: ignore[misc]
    assert entry.status is FactStatus.STALE


def test_staleness_is_the_same_predicate_delta_mode_uses() -> None:
    """Two implementations of "in date" would drift, and the drift would be
    invisible: a fact the ledger calls current and the engine withholds.

    The store therefore calls ``fact_needs_reconfirmation`` itself rather than
    comparing timestamps of its own, and this pins the two answers equal across
    the boundary rather than pinning a constant.
    """
    store, _repository, _audit, clock = build_store()
    fact = a_fact()
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=fact, actor=PATIENT))
    for offset in (timedelta(0), RECONFIRM_AFTER, RECONFIRM_AFTER + timedelta(seconds=1)):
        clock.advance(offset)
        (entry,) = run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))  # type: ignore[misc]
        engine_view = fact.as_learned_fact()
        assert (entry.status is FactStatus.STALE) == fact_needs_reconfirmation(engine_view, clock())


def test_a_stale_fact_stops_being_asserted_and_stays_visible() -> None:
    """The decision, asserted: at twelve months plus a day the fact is no
    longer put in front of anybody as true, and it is not dropped either.

    A silently dropped allergy is not the same artefact as one marked stale:
    dropping it destroys the record of what the system was told, and takes the
    patient's KVKK-11 correction right with it — you cannot correct a fact you
    can no longer see.
    """
    store, _repository, _audit, clock = build_store()
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))
    clock.advance(RECONFIRM_AFTER + timedelta(days=1))

    (entry,) = run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))  # type: ignore[misc]
    assert entry.status is FactStatus.STALE
    assert entry.source_ref == "oturum-91"
    assert entry.confirmed_by is Confirmer.PATIENT
    assert entry.reconfirm_due_at < clock()

    overlay = run(store.overlay(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))
    assert isinstance(overlay, PatientOverlay)
    assert [fact.key for fact in overlay.facts] == [KEY], (
        "the stale fact is still HANDED to the engine; INT-081's decide_delta is "
        "what withholds it, and it records the withholding — filtering here "
        "would delete that record"
    )


def test_reconfirming_appends_and_supersedes_rather_than_overwriting() -> None:
    """Re-confirmation is a new confirmation event, not an edit of an old one:
    the history is what makes the ledger a transparency artefact."""
    store, _repository, _audit, clock = build_store()
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))
    clock.advance(RECONFIRM_AFTER + timedelta(days=1))
    later = a_fact(at=clock())
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=later, actor=PATIENT))

    entries = run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))
    assert isinstance(entries, tuple)
    assert len(entries) == 2, "the earlier confirmation is history, not garbage"
    statuses = {entry.status for entry in entries}
    assert statuses == {FactStatus.ASSERTED, FactStatus.SUPERSEDED}

    overlay = run(store.overlay(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))
    assert isinstance(overlay, PatientOverlay)
    assert len(overlay.facts) == 1
    assert overlay.facts[0].confirmed_at == clock()


def test_committing_the_same_confirmation_twice_is_one_fact() -> None:
    """A fact id is content-addressed over its provenance, so a replayed
    confirmation is idempotent instead of doubling the ledger."""
    store, repository, _audit, _clock = build_store()
    fact = a_fact()
    first = run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=fact, actor=PATIENT))
    second = run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=fact, actor=PATIENT))
    assert isinstance(first, LedgerEntry) and isinstance(second, LedgerEntry)
    assert first.fact_id == second.fact_id
    assert len(repository.rows) == 1


# =====================================================================================
# 4 · the store: consent, audit, withdrawal (invariants 4 and 14; KVKK-11)
# =====================================================================================


def test_every_read_is_audited_before_it_answers() -> None:
    """Invariant 4, in files/10 §2's order: the audit is written AHEAD of the
    read, so an enumeration that fails midway still left its trace."""
    store, _repository, audit, _clock = build_store()
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))
    audit.entries.clear()
    run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))
    assert audit.actions == [READ_ACTION]
    (_actor, _action, resource_ref, consent_scope) = audit.entries[0]
    assert resource_ref == f"patient:{PATIENT}"
    assert consent_scope == "scope:learning:personal"


def test_a_read_that_cannot_be_audited_does_not_answer() -> None:
    """Fail closed: an unauditable read of clinical data is not a read."""
    store, _repository, _audit, _clock = build_store(audit=RecordingAudit(fails=True))
    with pytest.raises(RuntimeError, match="audit"):
        run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))


def test_withdrawal_is_reachable_and_audited_against_kvkk_11() -> None:
    """KVKK-11 is on this issue: a patient may correct or withdraw a fact about
    themselves. The audit names the statutory basis, not a consent scope — the
    right does not rest on the purpose it acts against."""
    store, _repository, audit, _clock = build_store()
    entry = run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))
    assert isinstance(entry, LedgerEntry)
    audit.entries.clear()
    withdrawn = run(
        store.withdraw(tenant_ref=TENANT, patient_ref=PATIENT, fact_id=entry.fact_id, actor=PATIENT)
    )
    assert isinstance(withdrawn, LedgerEntry)
    assert withdrawn.status is FactStatus.WITHDRAWN
    assert withdrawn.withdrawn_at is not None
    assert audit.actions == [WITHDRAW_ACTION]
    assert audit.entries[0][3] == WITHDRAW_BASIS_REF


def test_a_withdrawn_fact_is_never_asserted_again() -> None:
    store, _repository, _audit, _clock = build_store()
    entry = run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))
    assert isinstance(entry, LedgerEntry)
    run(
        store.withdraw(tenant_ref=TENANT, patient_ref=PATIENT, fact_id=entry.fact_id, actor=PATIENT)
    )
    overlay = run(store.overlay(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))
    assert isinstance(overlay, PatientOverlay)
    assert overlay.facts == ()
    (ledger_entry,) = run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))  # type: ignore[misc]
    assert ledger_entry.status is FactStatus.WITHDRAWN, "tombstoned, never deleted"


def test_withdrawing_an_unknown_fact_refuses_rather_than_succeeding_quietly() -> None:
    store, _repository, _audit, _clock = build_store()
    with pytest.raises(OverlayFactNotFound):
        run(store.withdraw(tenant_ref=TENANT, patient_ref=PATIENT, fact_id="0" * 32, actor=PATIENT))


def test_a_fact_of_one_patient_is_invisible_to_another() -> None:
    store, _repository, _audit, _clock = build_store()
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))
    entries = run(store.ledger(tenant_ref=TENANT, patient_ref="hasta-99", actor="hasta-99"))
    assert entries == ()
    other_tenant = run(store.ledger(tenant_ref="kiracı-2", patient_ref=PATIENT, actor=PATIENT))
    assert other_tenant == ()


def test_the_row_at_rest_holds_no_plaintext() -> None:
    """Invariant 14 names learned facts among the field-level envelope-encrypted
    columns. The store seals before the repository sees anything, so the
    repository — and the table behind it — cannot hold plaintext."""
    store, repository, _audit, _clock = build_store()
    run(
        store.commit(
            tenant_ref=TENANT,
            patient_ref=PATIENT,
            fact=a_fact(key="alerji.penisilin", value=True),
            actor=PATIENT,
        )
    )
    (row,) = repository.rows
    blob = row.sealed
    for secret in ("alerji.penisilin", "oturum-91", "confirmed_intake_extraction"):
        assert secret not in blob
    assert set(dataclasses.asdict(row)) == {
        "fact_id",
        "tenant_ref",
        "patient_ref",
        "sealed",
        "committed_at",
        "withdrawn_at",
    }


def test_a_sealed_row_cannot_be_opened_against_another_fact_id() -> None:
    """The envelope is bound to its own row (AAD), so moving a ciphertext
    between rows fails authentication instead of re-attributing a fact."""
    store, repository, _audit, _clock = build_store()
    run(store.commit(tenant_ref=TENANT, patient_ref=PATIENT, fact=a_fact(), actor=PATIENT))
    (row,) = repository.rows
    repository.rows[0] = dataclasses.replace(row, fact_id="f" * 32)
    with pytest.raises(Exception, match="authentication|Tamper"):
        run(store.ledger(tenant_ref=TENANT, patient_ref=PATIENT, actor=PATIENT))


# =====================================================================================
# 5 · invariant 18 — every new data field carries its inventory annotation
# =====================================================================================


def test_every_persisted_field_carries_a_complete_inventory_annotation() -> None:
    """The learned-fact row is new personal data. The annotation is declared
    here beside the type, and the gate binds now rather than when the table
    lands (CLAUDE.md invariant 18; files/06 §3)."""
    row_fields = {field.name for field in dataclasses.fields(SealedFactRow)}
    assert set(OVERLAY_INVENTORY) == row_fields, (
        "a persisted field without an inventory row cannot be defended to the "
        "Board: no purpose, no lawful basis, no retention clock"
    )
    for name, annotation in OVERLAY_INVENTORY.items():
        assert set(annotation) == set(INVENTORY_FIELDS), name
        for field_name in INVENTORY_FIELDS:
            value = annotation[field_name]
            assert isinstance(value, str) and value.strip(), f"{name}.{field_name}"


def test_the_sealed_value_is_declared_special_category_health() -> None:
    annotation = OVERLAY_INVENTORY["sealed"]
    assert annotation["category"] == "special_category_health"
    assert "learning:personal" in annotation["purpose"]


# =====================================================================================
# 6 · the /me/learned API — invariant 4 declared, fail-closed when unwired
# =====================================================================================


def mount(store: PatientOverlayStore | None, *, granting: bool = True) -> Iterator[TestClient]:
    """Mount the router on a bare app.

    The router is not in ``app.py`` yet — that wire is one line in a file this
    issue does not own (docs/evidence/INT-170.md names it), and mounting it here
    tests the contract the wire will carry. The principal and the consent guard
    are overridden because both are INT-131's and INT-038's own tested surfaces;
    what is under test is that this route HAS a guard and declares the right
    scope, which ``route_policies`` asserts separately.
    """
    app = FastAPI()
    app.include_router(learned_router)
    app.dependency_overrides[require_principal] = lambda: PATIENT_ACCOUNT
    if store is not None:
        app.dependency_overrides[get_overlay_store] = lambda: store

    def _guard_stub(guard: ConsentGuard) -> Callable[[], Awaitable[None]]:
        async def _run() -> None:
            if not granting:
                raise consent_required(guard.policy.enforced[0])

        return _run

    # This FastAPI keeps included routers as lazy wrappers, so the guards are
    # read off the router itself — the same Depends objects the app resolves.
    for route in learned_router.routes:
        for dependency in getattr(route, "dependencies", ()):
            call = dependency.dependency
            if isinstance(call, ConsentGuard):
                app.dependency_overrides[call] = _guard_stub(call)
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def wired_client() -> Iterator[TestClient]:
    store, _repository, _audit, _clock = build_store()
    run(
        store.commit(
            tenant_ref=DEV_TENANT,
            patient_ref=DEV_PATIENT,
            fact=a_fact(actor_ref=DEV_PATIENT),
            actor="dev-patient",
        )
    )
    yield from mount(store)


def test_the_learned_routes_declare_their_consent_scopes() -> None:
    """Invariant 4: /me/learned is a read of clinical data, so it declares a
    scope; ``unguarded_data_routes`` is the scan that makes silence fail."""
    app = FastAPI()
    app.include_router(learned_router)
    policies = route_policies(app)
    assert policies[("GET", "/v1/me/learned")].enforced == ("learning:personal",)
    assert unguarded_data_routes(app) == []


def test_the_withdrawal_route_is_not_gated_on_the_purpose_it_withdraws() -> None:
    """The trap the DSAR and notification-preference routes both document: a
    purpose whose withdrawal locks the correction of the facts it produced is
    not a purpose, it is a cage. So the delete route declares ``core``."""
    app = FastAPI()
    app.include_router(learned_router)
    policies = route_policies(app)
    delete = policies[("DELETE", "/v1/me/learned/{fact_id}")]
    assert delete.enforced == ("core",)
    assert "learning:personal" not in delete.enforced


def test_the_route_answers_503_when_the_store_is_not_wired() -> None:
    """An empty ledger and an unreadable one look identical to a patient, and
    only one of them is true (the INT-016 access-log posture)."""
    for client in mount(None):
        response = client.get("/v1/me/learned")
        assert response.status_code == 503
        assert response.json()["detail"]["error"] == "overlay_store_unconfigured"


def test_the_response_shows_provenance_for_every_fact(wired_client: TestClient) -> None:
    body = wired_client.get("/v1/me/learned").json()
    assert body["reconfirm_after_days"] == RECONFIRM_AFTER.days
    (fact,) = body["facts"]
    assert fact["key"] == KEY
    assert fact["status"] == "asserted"
    assert fact["confirmed_by"] == "patient"
    assert fact["confirmed_by_ref"] == DEV_PATIENT
    assert fact["source"] == "confirmed_intake_extraction"
    assert fact["source_ref"] == "oturum-91"
    assert fact["confirmed_at"].startswith("2026-03-01")
    assert fact["reconfirm_due_at"].startswith("2027-03-01")
    assert fact["withdrawn_at"] is None


def test_the_read_route_refuses_when_the_consent_guard_refuses() -> None:
    store, _repository, _audit, _clock = build_store()
    for client in mount(store, granting=False):
        response = client.get("/v1/me/learned")
        assert response.status_code == 403
        assert response.json()["detail"]["scope"] == "learning:personal"


def test_the_withdrawal_route_tombstones_the_fact(wired_client: TestClient) -> None:
    body = wired_client.get("/v1/me/learned").json()
    fact_id = body["facts"][0]["fact_id"]
    response = wired_client.delete(f"/v1/me/learned/{fact_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "withdrawn"
    after = wired_client.get("/v1/me/learned").json()
    assert after["facts"][0]["status"] == "withdrawn"


def test_withdrawing_a_fact_that_is_not_there_is_a_404(wired_client: TestClient) -> None:
    assert wired_client.delete(f"/v1/me/learned/{'0' * 32}").status_code == 404


# =====================================================================================
# 7 · delta mode works in the simulator — driven by a fact from the store
# =====================================================================================


@dataclasses.dataclass(frozen=True)
class SimApi:
    """The slice of INT-082's simulator this file drives."""

    run_scenario: Callable[..., object]
    personas: dict[str, object]
    scenarios: dict[str, object]
    reference_time: datetime
    protocol: Callable[[], object]


@pytest.fixture(scope="module")
def sim() -> Iterator[SimApi]:
    """INT-082's headless simulator, imported rather than edited.

    tests/sim's modules import each other by bare name, so the directory goes
    on the path exactly as it does when its own suite runs.
    """
    path = str(REPO / "tests" / "sim")
    if path not in sys.path:
        sys.path.insert(0, path)
    import driver
    import personas
    import protocol
    import scenarios

    yield SimApi(
        run_scenario=driver.run_scenario,
        personas=personas.PERSONAS,
        scenarios=scenarios.SCENARIOS,
        reference_time=protocol.REFERENCE_TIME,
        protocol=protocol.sim_protocol,
    )


def overlay_from_store(*, confirmed_at: datetime, patient_ref: str) -> PatientOverlay:
    """One committed, patient-confirmed fact, materialised through the store —
    not a persona's hand-written overlay."""
    store, _repository, _audit, _clock = build_store(now=confirmed_at)
    run(
        store.commit(
            tenant_ref=TENANT,
            patient_ref=patient_ref,
            fact=a_fact(at=confirmed_at, actor_ref=patient_ref),
            actor=patient_ref,
        )
    )
    overlay = run(store.overlay(tenant_ref=TENANT, patient_ref=patient_ref, actor=patient_ref))
    assert isinstance(overlay, PatientOverlay)
    return overlay


def _persona_with(sim: SimApi, overlay: PatientOverlay) -> object:
    persona = sim.personas["P12-frequent-attender-delta"]
    return persona.model_copy(update={"overlay": overlay})  # type: ignore[attr-defined]


def _run_im07(sim: SimApi, overlay: PatientOverlay) -> object:
    from intake_voice_runtime.profiles import VoiceProfile

    return sim.run_scenario(
        sim.scenarios["IM-07"], _persona_with(sim, overlay), profile=VoiceProfile.TYPED
    )


def test_a_fact_committed_through_the_store_turns_delta_mode_on(sim: SimApi) -> None:
    """IM-07, with the overlay coming out of INT-170's store: a confirmed fact
    is CONFIRMED instead of re-asked (files/09 §3; files/03 §5)."""
    from intake_voice_runtime.steps import StepKind

    overlay = overlay_from_store(confirmed_at=sim.reference_time, patient_ref="sentetik-hasta")
    result = _run_im07(sim, overlay)
    assert result.delta_mode == "on"  # type: ignore[attr-defined]
    assert StepKind.CONFIRM in result.asked_kinds  # type: ignore[attr-defined]
    assert KEY in result.asked  # type: ignore[attr-defined]


def test_a_stale_fact_is_withheld_by_the_engine_and_the_step_is_asked_in_full(
    sim: SimApi,
) -> None:
    """The other half of the expiry decision, end to end.

    The store still HANDS the fact over (it is history, not a deletion), and
    INT-081's ``decide_delta`` withholds it and says so — so the question is
    asked in full rather than confirmed from a year-old answer.
    """
    from intake_voice_runtime.clinical_agent import IntakeEngine
    from intake_voice_runtime.steps import StepKind

    stale_at = sim.reference_time - RECONFIRM_AFTER - timedelta(days=1)
    overlay = overlay_from_store(confirmed_at=stale_at, patient_ref="sentetik-hasta")
    assert [fact.key for fact in overlay.facts] == [KEY]

    engine = IntakeEngine(
        protocol=sim.protocol(),  # type: ignore[arg-type]
        reference_time=sim.reference_time,
        overlay_facts=overlay,
    )
    assert engine.delta.withheld_fact_keys == (KEY,)
    assert engine.delta.prefills == ()

    result = _run_im07(sim, overlay)
    assert result.delta_mode == "off"  # type: ignore[attr-defined]
    asked = dict(
        zip(result.asked, result.asked_kinds, strict=True)  # type: ignore[attr-defined]
    )
    assert asked[KEY] is not StepKind.CONFIRM


def test_a_withdrawn_fact_reaches_the_simulator_not_at_all(sim: SimApi) -> None:
    store, _repository, _audit, _clock = build_store(now=sim.reference_time)
    entry = run(
        store.commit(
            tenant_ref=TENANT,
            patient_ref="sentetik-hasta",
            fact=a_fact(at=sim.reference_time, actor_ref="sentetik-hasta"),
            actor="sentetik-hasta",
        )
    )
    assert isinstance(entry, LedgerEntry)
    run(
        store.withdraw(
            tenant_ref=TENANT,
            patient_ref="sentetik-hasta",
            fact_id=entry.fact_id,
            actor="sentetik-hasta",
        )
    )
    overlay = run(
        store.overlay(tenant_ref=TENANT, patient_ref="sentetik-hasta", actor="sentetik-hasta")
    )
    assert isinstance(overlay, PatientOverlay)
    assert overlay.facts == ()
    result = _run_im07(sim, overlay)
    assert result.delta_mode == "off"  # type: ignore[attr-defined]


# =====================================================================================
# 8 · invariant 12 — the learning service cannot reach the store that writes facts
# =====================================================================================


def test_the_learning_service_cannot_reach_the_overlay_store() -> None:
    """Learning is proposal-only. The overlay store is a WRITER of patient
    facts, so it lives in ``services/api`` — which ``tests/learning/
    test_proposal_scope.py`` already names as a forbidden import root for the
    package. This pins the placement so a later move into
    ``services/learning`` cannot happen quietly.
    """
    store_module = REPO / "services" / "api" / "src" / "intake_api" / "overlay_store.py"
    assert store_module.is_file()

    reaches: list[str] = []
    for path in (REPO / "services" / "learning" / "src").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for name in ("intake_api", "overlay_store", "ConfirmedFact", "PatientOverlay"):
            if name in source:
                reaches.append(f"{path.relative_to(REPO)} -> {name}")
    assert reaches == [], (
        "services/learning named the overlay write path; invariant 12 makes the "
        f"loop proposal-only: {reaches}"
    )
