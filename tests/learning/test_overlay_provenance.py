"""INT-170 — the PatientOverlay store, its confirmation rules and /me/learned.

files/09 §6 names this suite ``learned_fact_provenance``: *"every
``PatientOverlay`` field has a confirmed source; unconfirmed LLM facts are
rejected at the type level."* CLAUDE.md invariant 12 says the same in one
clause — *``PatientOverlay`` facts require patient or clinician confirmation
(type-level)*.

The acceptance has four clauses and this module is organised around them, one
class each:

1. **"facts commit only with patient/clinician confirmation (type-level)"** —
   :class:`TestConfirmationIsTypeLevel`. The mechanism is an absence, not a
   guard: :class:`~clinical_schemas.overlay.FactCandidate` has **no ``source``
   field and no ``confirmed_at`` field at all**, so the unconfirmed form
   cannot be spelled as a confirmed one; the only route between them is
   :func:`~clinical_schemas.overlay.confirm`, which requires a
   :class:`~clinical_schemas.overlay.Confirmation` whose ``source`` type has
   no unconfirmed member. It is INT-172's ``CandidateRedFlag.level`` posture
   (``services/learning/src/intake_learning/proposals.py``) applied to the
   other half of invariant 12.
2. **"12-month reconfirm"** — :class:`TestTwelveMonthReconfirmation`. The
   window is :func:`~clinical_schemas.overlay.fact_needs_reconfirmation`,
   which INT-081's ``decide_delta`` and INT-258's ``activate_overlays``
   already share. This issue **reuses** it and defines no second window; a
   source scan asserts the absence of a re-derivation.
3. **"provenance shown"** — :class:`TestProvenanceShown`. Every stored fact
   carries its source, its confirming artefact and its confirmation instant
   back out through the store, and ``/v1/me/learned`` renders them
   (``tests/api/test_learned.py`` covers the route).
4. **"delta-mode works in simulator"** — :class:`TestDeltaModeOverTheStore`. A
   headless session driven end to end: seed the store, load the overlay, build
   a real plan, run the real ``decide_delta``. INT-082 owns the persona
   simulator (``tests/sim/test_scenarios.py``) and is not written here; what is
   proved here is that the object the simulator will read is the object this
   store produces.

Plus :class:`TestNoPhiEscapes` (invariant 6) and
:class:`TestStoreShape` (invariants 4 and 14).

Every id, key and Turkish string below is synthetic and carries no clinical
meaning (files/04 §7). No clinical content is authored: the authored base pack
is INT-043 (``awaiting-human``, HB-C1) and the eight patient overlays are
INT-056.
"""

from __future__ import annotations

import ast as python_ast
import inspect
import json
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_TESTS_DIR / "api"))

import pytest  # noqa: E402
from api_harness import run, sqlite_ddl_clone  # noqa: E402
from clinical_schemas.overlay import (  # noqa: E402
    CONFIRMING_ACTOR,
    RECONFIRM_AFTER,
    Confirmation,
    ConfirmingActor,
    FactCandidate,
    LearnedFact,
    LearnedFactSource,
    PatientOverlay,
    confirm,
    fact_needs_reconfirmation,
)
from intake_platform.db.models import KvkkRole, OverlayFact, Patient, Tenant  # noqa: E402
from intake_platform.envelope import EnvelopeCipher, FileKekProvider  # noqa: E402
from intake_platform.overlay import OverlayStore  # noqa: E402
from intake_voice_runtime.clinical_agent import DeltaMode, build_plan, decide_delta  # noqa: E402
from protocols.compile.resolve import (  # noqa: E402
    ResolvedProtocol,
    ResolvedSection,
    ResolvedSlot,
)
from protocols.dsl import Slot  # noqa: E402
from protocols.types import Delivery, SlotType  # noqa: E402
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
HASH = "0" * 64

TENANT_ID = uuid.UUID("d5f1a1d6-0170-4000-8000-000000000001")
PATIENT_ID = uuid.UUID("d5f1a1d6-0170-4000-8000-000000000002")
OTHER_TENANT_ID = uuid.UUID("d5f1a1d6-0170-4000-8000-000000000003")
OTHER_PATIENT_ID = uuid.UUID("d5f1a1d6-0170-4000-8000-000000000004")
PSEUDONYM = "dev." + "a" * 64
OTHER_PSEUDONYM = "dev." + "b" * 64

#: The planted adversary, borrowed verbatim from
#: tests/observability/test_langfuse_gate.py (INT-175) the way
#: tests/learning/test_evidence_bundle.py (INT-172) and
#: tests/infra/test_siem_feed.py (INT-205) borrow it, so every PHI gate in the
#: tree agrees on what patient narrative looks like.
TURKISH_SYMPTOM = "Göğsümde iki gündür şiddetli bir ağrı var ve nefes almakta zorlanıyorum."


def _blob(value: object) -> str:
    """The whole structure as one searchable string, diacritics intact.

    JSON escaping is the trap INT-172 records: a raw sweep passes on an
    escaped Turkish sentence. Round-tripping through ``ensure_ascii=False``
    puts the Turkish letters back before the sweep looks for them.
    """
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


# --- the synthetic protocol the delta-mode scenario runs over ----------------


def _slot(**fields: object) -> Slot:
    return Slot.model_validate(fields)


def _resolved(section_id: str, key: str, slot: Slot) -> ResolvedSlot:
    return ResolvedSlot(
        section_id=section_id,
        key=key,
        fhir_link_id=f"{section_id}.{key}",
        slot=slot,
        delivery=Delivery.VOICE,
    )


def _protocol() -> ResolvedProtocol:
    section = ResolvedSection(
        id="oyku",
        delivery=Delivery.VOICE,
        allow_paraphrase=False,
        slots=(
            _resolved(
                "oyku",
                "belirti_var",
                _slot(
                    type=SlotType.BOOLEAN,
                    required=True,
                    must_ask=True,
                    ask_tr="Sentetik belirtiniz var mı?",
                    confirm_tr="Sentetik belirti hâlâ var, doğru mu?",
                    follow_up_tr="Sentetik belirti takip sorusu.",
                ),
            ),
            _resolved(
                "oyku",
                "not_metni",
                _slot(type=SlotType.STRING, ask_tr="Sentetik serbest metin sorusu."),
            ),
        ),
    )
    return ResolvedProtocol(
        pack_id="base.sentetik_overlay",
        version="1.0.0",
        chain=("base.sentetik_overlay",),
        sections=(section,),
        resolved_protocol_hash=HASH,
    )


# --- the store harness ------------------------------------------------------


class StoreHarness:
    """The INT-030 schema on SQLite (the tests/api DDL clone), two tenants
    seeded, and the real :class:`OverlayStore` over the real cipher."""

    def __init__(self, engine: AsyncEngine, store: OverlayStore) -> None:
        self.engine = engine
        self.store = store

    def confirm(
        self,
        candidate: FactCandidate,
        confirmation: Confirmation,
        *,
        tenant_id: uuid.UUID = TENANT_ID,
        patient_id: uuid.UUID = PATIENT_ID,
    ) -> LearnedFact:
        async def _run() -> LearnedFact:
            async with AsyncSession(self.engine) as session, session.begin():
                return await self.store.confirm_fact(
                    session,
                    tenant_id=tenant_id,
                    patient_id=patient_id,
                    candidate=candidate,
                    confirmation=confirmation,
                )

        result: LearnedFact = run(_run())
        return result

    def overlay(
        self, *, tenant_id: uuid.UUID = TENANT_ID, patient_id: uuid.UUID = PATIENT_ID
    ) -> PatientOverlay | None:
        async def _run() -> PatientOverlay | None:
            async with AsyncSession(self.engine) as session:
                return await self.store.load_overlay(
                    session, tenant_id=tenant_id, patient_id=patient_id
                )

        result: PatientOverlay | None = run(_run())
        return result

    def facts(
        self, *, tenant_id: uuid.UUID = TENANT_ID, patient_id: uuid.UUID = PATIENT_ID
    ) -> tuple[LearnedFact, ...]:
        async def _run() -> tuple[LearnedFact, ...]:
            async with AsyncSession(self.engine) as session:
                return await self.store.list_facts(
                    session, tenant_id=tenant_id, patient_id=patient_id
                )

        result: tuple[LearnedFact, ...] = run(_run())
        return result

    def forget(self, key: str) -> bool:
        async def _run() -> bool:
            async with AsyncSession(self.engine) as session, session.begin():
                return await self.store.forget_fact(
                    session, tenant_id=TENANT_ID, patient_id=PATIENT_ID, key=key
                )

        result: bool = run(_run())
        return result

    def set_shared(self, key: str, *, shared: bool) -> bool:
        async def _run() -> bool:
            async with AsyncSession(self.engine) as session, session.begin():
                return await self.store.set_shared(
                    session,
                    tenant_id=TENANT_ID,
                    patient_id=PATIENT_ID,
                    key=key,
                    shared=shared,
                )

        result: bool = run(_run())
        return result

    def rows(self) -> list[OverlayFact]:
        async def _run() -> list[OverlayFact]:
            async with AsyncSession(self.engine) as session:
                return list(await session.scalars(select(OverlayFact)))

        result: list[OverlayFact] = run(_run())
        return result


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[StoreHarness]:
    db = tmp_path / "overlay.db"
    ddl_engine = create_engine(f"sqlite+pysqlite:///{db}")
    sqlite_ddl_clone().create_all(ddl_engine)
    ddl_engine.dispose()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db}", poolclass=NullPool)

    async def _seed() -> None:
        async with AsyncSession(engine) as session, session.begin():
            for tenant_id, patient_id, pseudonym in (
                (TENANT_ID, PATIENT_ID, PSEUDONYM),
                (OTHER_TENANT_ID, OTHER_PATIENT_ID, OTHER_PSEUDONYM),
            ):
                session.add(
                    Tenant(
                        id=tenant_id,
                        display_name=f"int170-{tenant_id.int % 10}",
                        kvkk_role=KvkkRole.CONTROLLER,
                    )
                )
                session.add(Patient(id=patient_id, tenant_id=tenant_id, pseudonym=pseudonym))

    run(_seed())
    yield StoreHarness(engine, OverlayStore(EnvelopeCipher(FileKekProvider())))
    run(engine.dispose())


def _candidate(
    key: str = "oyku.belirti_var",
    value: object = True,
    *,
    observed_at: datetime = NOW,
    confidence: float = 0.9,
) -> FactCandidate:
    return FactCandidate(
        key=key,
        value=value,  # type: ignore[arg-type]  # JsonValue is a type alias union
        origin_ref="sentetik-oturum",
        observed_at=observed_at,
        confidence=confidence,
    )


def _confirmation(
    source: LearnedFactSource = LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
    *,
    confirmed_at: datetime = NOW,
    source_ref: str = "sentetik-onay-karti",
) -> Confirmation:
    return Confirmation(source=source, source_ref=source_ref, confirmed_at=confirmed_at)


# --- clause 1 ---------------------------------------------------------------


class TestConfirmationIsTypeLevel:
    """ "facts commit only with patient/clinician confirmation (type-level)"."""

    def test_a_candidate_has_no_source_and_no_confirmed_at_field(self) -> None:
        """The mechanism, stated as the absence it is.

        A candidate cannot be spelled as a confirmed fact because the two
        fields a confirmation writes do not exist on it — the same reason
        INT-172's ``CandidateRedFlag`` cannot express ``RED``.
        """
        fields = set(FactCandidate.model_fields)
        assert "source" not in fields
        assert "confirmed_at" not in fields
        assert fields == {"key", "value", "origin_ref", "observed_at", "confidence"}

    def test_passing_a_source_to_a_candidate_is_refused_at_construction(self) -> None:
        with pytest.raises(ValidationError):
            FactCandidate(  # type: ignore[call-arg]
                key="oyku.belirti_var",
                value=True,
                origin_ref="sentetik-oturum",
                observed_at=NOW,
                confidence=1.0,
                source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
            )

    def test_a_candidate_is_not_a_learned_fact_in_either_direction(self) -> None:
        """No inheritance seam: neither class can stand in for the other."""
        assert not issubclass(FactCandidate, LearnedFact)
        assert not issubclass(LearnedFact, FactCandidate)

    def test_an_unconfirmed_candidate_cannot_enter_a_patient_overlay(self) -> None:
        """The overlay is the only object a rule or a triage input reads, and
        its ``facts`` field is typed ``tuple[LearnedFact, ...]``."""
        annotation = PatientOverlay.model_fields["facts"].annotation
        assert annotation == tuple[LearnedFact, ...]
        with pytest.raises(ValidationError):
            PatientOverlay(
                patient_ref=PSEUDONYM,
                version=1,
                facts=(_candidate(),),  # type: ignore[arg-type]
            )

    def test_every_learned_fact_source_is_a_confirmation_by_a_named_actor(self) -> None:
        """files/09 §3: patient (in-app card) or clinician (note acceptance).
        The map is total over the enum, so no source can arrive without one."""
        assert set(ConfirmingActor) == {ConfirmingActor.PATIENT, ConfirmingActor.CLINICIAN}
        assert set(CONFIRMING_ACTOR) == set(LearnedFactSource)
        assert all(actor in ConfirmingActor for actor in CONFIRMING_ACTOR.values())

    def test_confirm_is_the_only_route_from_a_candidate_to_a_fact(self) -> None:
        """AST scan: no other callable in the schema module takes a
        ``FactCandidate`` and returns a ``LearnedFact``."""
        module = python_ast.parse(
            (
                REPO / "packages" / "clinical-schemas" / "src" / "clinical_schemas" / "overlay.py"
            ).read_text(encoding="utf-8")
        )
        producers = [
            node.name
            for node in module.body
            if isinstance(node, python_ast.FunctionDef)
            and isinstance(node.returns, python_ast.Name)
            and node.returns.id == "LearnedFact"
        ]
        assert producers == ["confirm"]

    def test_confirm_requires_a_confirmation_and_carries_it_through(self) -> None:
        parameters = list(inspect.signature(confirm).parameters)
        assert parameters == ["candidate", "confirmation"]
        fact = confirm(_candidate(), _confirmation())
        assert fact.source is LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION
        assert fact.source_ref == "sentetik-onay-karti"
        assert fact.confirmed_at == NOW
        assert fact.confidence == 0.9

    def test_the_store_write_path_accepts_no_pre_built_learned_fact(self) -> None:
        """You cannot hand the store a fact you minted yourself: every public
        method's parameters are checked and none is annotated ``LearnedFact``.
        The store mints the fact through :func:`confirm` or not at all."""
        offenders: list[str] = []
        for name, method in inspect.getmembers(OverlayStore, inspect.isfunction):
            if name.startswith("_"):
                continue
            for parameter in inspect.signature(method).parameters.values():
                if parameter.annotation == "LearnedFact":
                    offenders.append(f"{name}.{parameter.name}")
        assert offenders == []

    def test_the_confirmed_fact_reaches_the_overlay_and_the_candidate_does_not(
        self, harness: StoreHarness
    ) -> None:
        candidate = _candidate()
        harness.confirm(candidate, _confirmation())
        overlay = harness.overlay()
        assert overlay is not None
        assert [fact.key for fact in overlay.facts] == ["oyku.belirti_var"]
        assert all(isinstance(fact, LearnedFact) for fact in overlay.facts)


# --- clause 2 ---------------------------------------------------------------


class TestTwelveMonthReconfirmation:
    """ "12-month reconfirm" — one window, reused rather than re-derived."""

    def test_the_window_predicate_is_the_shared_one(self) -> None:
        fact = confirm(_candidate(), _confirmation())
        assert not fact_needs_reconfirmation(fact, NOW + timedelta(days=364))
        assert fact_needs_reconfirmation(fact, NOW + timedelta(days=366))
        assert RECONFIRM_AFTER == timedelta(days=365)

    def test_no_module_added_by_this_issue_re_derives_the_window(self) -> None:
        """INT-081's ``decide_delta`` and INT-258's ``activate_overlays``
        already share ``fact_needs_reconfirmation``; a third copy would drift.
        So the store and the route hold no duration of their own."""
        offenders: list[str] = []
        for path in (
            REPO / "packages" / "intake_platform" / "src" / "intake_platform" / "overlay",
            REPO / "services" / "api" / "src" / "intake_api" / "learned.py",
        ):
            sources = [path] if path.is_file() else sorted(path.rglob("*.py"))
            for source in sources:
                for number, line in enumerate(
                    source.read_text(encoding="utf-8").splitlines(), start=1
                ):
                    if "timedelta(" in line or "365" in line or "RECONFIRM_AFTER" in line:
                        offenders.append(f"{source.name}:{number}: {line.strip()}")
        assert offenders == [], (
            "the twelve-month window is fact_needs_reconfirmation's and nothing "
            f"else's (files/09 §3): {offenders}"
        )

    def test_re_confirming_a_key_replaces_the_fact_and_restarts_the_clock(
        self, harness: StoreHarness
    ) -> None:
        stale_at = NOW - timedelta(days=400)
        harness.confirm(_candidate(value=True), _confirmation(confirmed_at=stale_at))
        first = harness.facts()
        assert len(first) == 1
        assert fact_needs_reconfirmation(first[0], NOW)

        harness.confirm(
            _candidate(value=False),
            _confirmation(confirmed_at=NOW, source_ref="sentetik-yeni-onay"),
        )
        second = harness.facts()
        assert len(second) == 1, "re-confirmation replaces the fact; it does not add a second"
        assert second[0].value is False
        assert second[0].source_ref == "sentetik-yeni-onay"
        assert not fact_needs_reconfirmation(second[0], NOW)

    def test_a_stale_fact_is_served_by_the_store_and_withheld_by_the_reader(
        self, harness: StoreHarness
    ) -> None:
        """The store does not silently drop a stale fact: the patient must be
        able to see it in *Me → Hakkımda öğrendikleri* in order to re-confirm
        it, and INT-081's ``decide_delta`` is the gate that withholds it from
        the session — reporting it in ``withheld_fact_keys`` rather than
        losing it."""
        harness.confirm(_candidate(), _confirmation(confirmed_at=NOW - timedelta(days=400)))
        overlay = harness.overlay()
        assert overlay is not None
        assert [fact.key for fact in overlay.facts] == ["oyku.belirti_var"]

        decision = decide_delta(plan=build_plan(_protocol()), overlay_facts=overlay, now=NOW)
        assert decision.mode is DeltaMode.OFF
        assert decision.prefills == ()
        assert decision.withheld_fact_keys == ("oyku.belirti_var",)


# --- clause 3 ---------------------------------------------------------------


class TestProvenanceShown:
    """ "provenance shown" — every fact answers "where from" (files/09 §3)."""

    @pytest.mark.parametrize("source", list(LearnedFactSource))
    def test_every_provenance_survives_the_round_trip(
        self, harness: StoreHarness, source: LearnedFactSource
    ) -> None:
        harness.confirm(_candidate(), _confirmation(source))
        facts = harness.facts()
        assert len(facts) == 1
        assert facts[0].source is source
        assert facts[0].source_ref == "sentetik-onay-karti"
        assert facts[0].confirmed_at == NOW
        assert CONFIRMING_ACTOR[facts[0].source] in ConfirmingActor

    def test_the_patient_can_delete_a_fact_and_the_row_goes_with_it(
        self, harness: StoreHarness
    ) -> None:
        """files/09 §3: every learned fact "can be corrected or deleted by the
        patient". A deletion removes the row rather than tombstoning the key —
        a tombstone that keeps the key keeps the health fact."""
        harness.confirm(_candidate(), _confirmation())
        assert harness.forget("oyku.belirti_var") is True
        assert harness.facts() == ()
        assert harness.rows() == []
        assert harness.forget("oyku.belirti_var") is False

    def test_the_share_scope_is_per_field_and_defaults_on(self, harness: StoreHarness) -> None:
        """files/09 §3 guardrails: "per-field share scope"."""
        harness.confirm(_candidate(), _confirmation())
        assert harness.facts()[0].shared is True
        assert harness.set_shared("oyku.belirti_var", shared=False) is True
        assert harness.facts()[0].shared is False
        assert harness.set_shared("yok.olan_anahtar", shared=False) is False

    def test_the_overlay_is_versioned_and_the_version_only_goes_up(
        self, harness: StoreHarness
    ) -> None:
        """files/09 §3: the overlay is "versioned". Version 1 is the empty
        overlay every patient starts with; each mutation is a new version, and
        a deletion is a mutation like any other."""
        empty = harness.overlay()
        assert empty is not None
        assert empty.version == 1
        assert empty.facts == ()
        assert empty.patient_ref == PSEUDONYM

        harness.confirm(_candidate(), _confirmation())
        after_commit = harness.overlay()
        assert after_commit is not None
        assert after_commit.version == 2

        harness.forget("oyku.belirti_var")
        after_delete = harness.overlay()
        assert after_delete is not None
        assert after_delete.version == 3
        assert after_delete.facts == ()


# --- clause 4 ---------------------------------------------------------------


class TestDeltaModeOverTheStore:
    """ "delta-mode works in simulator" — the headless end-to-end run.

    INT-082 owns the persona simulator (``tests/sim/test_scenarios.py``) and is
    not written here. What this class proves is the half INT-170 owns: the
    object a simulated session reads is the object this store produces, and
    delta mode turns on from stored, confirmed facts and from nothing else.
    """

    def test_a_stored_confirmed_fact_turns_delta_mode_on_with_a_confirm_step(
        self, harness: StoreHarness
    ) -> None:
        harness.confirm(_candidate(), _confirmation())
        overlay = harness.overlay()
        assert overlay is not None

        plan = build_plan(_protocol())
        decision = decide_delta(plan=plan, overlay_facts=overlay, now=NOW)

        assert decision.mode is DeltaMode.ON
        assert [prefill.slot_ref for prefill in decision.prefills] == ["oyku.belirti_var"]
        prefill = decision.prefills[0]
        assert prefill.value is True
        assert prefill.confirm_tr == "Sentetik belirti hâlâ var, doğru mu?"
        assert prefill.source_ref == "sentetik-onay-karti"

    def test_an_empty_store_leaves_delta_mode_off(self, harness: StoreHarness) -> None:
        overlay = harness.overlay()
        assert overlay is not None
        decision = decide_delta(plan=build_plan(_protocol()), overlay_facts=overlay, now=NOW)
        assert decision.mode is DeltaMode.OFF
        assert decision.prefills == ()

    def test_a_candidate_that_was_never_confirmed_changes_nothing(
        self, harness: StoreHarness
    ) -> None:
        """The negative control. A candidate is built, and because there is no
        way to store one and no way to put one in an overlay, the session it
        would have changed is byte-for-byte the session with no overlay."""
        _candidate(value=False)  # built, and there is nowhere for it to go
        overlay = harness.overlay()
        assert overlay is not None
        assert overlay.facts == ()
        plan = build_plan(_protocol())
        assert decide_delta(plan=plan, overlay_facts=overlay, now=NOW) == decide_delta(
            plan=plan, overlay_facts=None, now=NOW
        )

    def test_a_fact_whose_slot_has_no_confirm_text_is_asked_in_full(
        self, harness: StoreHarness
    ) -> None:
        """``oyku.not_metni`` carries no ``confirm_tr``: there is no improvised
        confirmation (invariant 10), so the question is asked in full and the
        fact is reported as unconfirmable rather than dropped."""
        harness.confirm(_candidate(key="oyku.not_metni", value="sentetik"), _confirmation())
        overlay = harness.overlay()
        assert overlay is not None
        decision = decide_delta(plan=build_plan(_protocol()), overlay_facts=overlay, now=NOW)
        assert decision.mode is DeltaMode.OFF
        assert decision.unconfirmable_fact_keys == ("oyku.not_metni",)


# --- invariants 4, 6 and 14 -------------------------------------------------


class TestStoreShape:
    """Invariant 14 (field-level envelope encryption for learned facts) and
    the tenant boundary every query carries explicitly."""

    def test_the_fact_value_is_an_envelope_at_rest_never_plaintext(
        self, harness: StoreHarness
    ) -> None:
        harness.confirm(_candidate(key="oyku.not_metni", value=TURKISH_SYMPTOM), _confirmation())
        rows = harness.rows()
        assert len(rows) == 1
        payload = dict(rows[0].payload)
        assert set(payload) == {"key_version", "wrapped_dek", "nonce", "ciphertext"}
        assert TURKISH_SYMPTOM not in _blob(payload)

    def test_a_fact_never_crosses_the_tenant_boundary(self, harness: StoreHarness) -> None:
        harness.confirm(_candidate(), _confirmation())
        assert harness.facts(tenant_id=OTHER_TENANT_ID, patient_id=OTHER_PATIENT_ID) == ()
        other = harness.overlay(tenant_id=OTHER_TENANT_ID, patient_id=OTHER_PATIENT_ID)
        assert other is not None
        assert other.facts == ()

    def test_an_unknown_patient_has_no_overlay_rather_than_an_invented_one(
        self, harness: StoreHarness
    ) -> None:
        assert harness.overlay(patient_id=uuid.uuid4()) is None


class TestNoPhiEscapes:
    """Invariant 6, swept on the decoded blob (INT-172's escaping trap)."""

    def test_a_planted_symptom_sentence_reaches_no_row_and_no_metric_label(
        self, harness: StoreHarness
    ) -> None:
        from prometheus_client import REGISTRY, generate_latest

        harness.confirm(_candidate(key="oyku.not_metni", value=TURKISH_SYMPTOM), _confirmation())
        harness.set_shared("oyku.not_metni", shared=False)
        harness.forget("oyku.not_metni")

        exposition = generate_latest(REGISTRY).decode("utf-8")
        for probe in (TURKISH_SYMPTOM, "Göğsümde", "ağrı"):
            assert probe not in exposition
        assert _blob([dict(row.payload) for row in harness.rows()]).count("Göğsümde") == 0
