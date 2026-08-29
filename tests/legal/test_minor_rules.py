"""INT-223 — minor & guardian rules engine (files/06 §6; TMK-339; HHY-24).

What this file pins:
- age bands come from a verified DOB only: 18 and 12 are the two thresholds
  files/06 §6 states verbatim; boundary birthdays (day-before / day-of /
  day-after, and the 29-February case) land on the fail-closed side;
- every legally-contested choice files/ and docs/legal do NOT state is a
  policy-table row with ``status: awaiting_human`` that FAILS CLOSED (most
  restrictive: guardian required, service refused where ambiguous) — never
  an invented value;
- enforcement rides the ONE consent enforcement point (ensure_consent,
  invariant 4): a minor subject is refused with a typed 403 naming the
  missing requirement and nothing else (invariant 6 — no DOB, no age, no
  narrative in the body);
- the guardian linkage store is BEHIND the ``guardian_link`` safety flag,
  default False: the write path refuses, the read path answers None, and
  only an explicit boolean can open it (the INT-023 safety-flag contract);
- the guardian_links schema carries the invariant-18 inventory annotation
  with an awaiting-human basis, and its migration ships the same RLS shape
  as every tenant-scoped table (static pin; live proof rides test_rls.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from api_harness import ApiHarness, run
from intake_api.age_context import NoAgeRecordSource
from intake_api.db import tenant_session
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID
from intake_platform.consent import UnknownPurposeError
from intake_platform.consent.guardian import (
    GUARDIAN_LINK_FLAG,
    GuardianLinkDisabledError,
    active_guardian_link,
    record_guardian_link,
)
from intake_platform.consent.minors import (
    ADOLESCENT_MIN_AGE,
    ADULT_AGE,
    POLICY_TABLE,
    AgeBand,
    AgeContext,
    ClinicPolicy,
    DobAssurance,
    PolicyEntry,
    PolicyStatus,
    RequiredActor,
    SectionAudience,
    _index_policy_rows,
    adolescent_private_visibility,
    classify,
    policy_entry,
    resolve_consent_actor,
)
from intake_platform.db.models import GuardianLink
from intake_platform.flags import SAFETY_FLAG_DEFAULTS, InMemoryProvider
from legal_harness import api_state
from sqlalchemy import func, select

REPO = Path(__file__).resolve().parents[2]

# A fixed evaluation date keeps every boundary test deterministic.
ON = date(2026, 8, 28)


def _verified(dob: date) -> AgeContext:
    return AgeContext.verified(dob)


# --- age thresholds are the files/06 §6 values, nothing else ------------------------


class TestThresholds:
    def test_thresholds_are_the_files06_values(self) -> None:
        assert ADULT_AGE == 18
        assert ADOLESCENT_MIN_AGE == 12

    def test_threshold_entries_cite_files06(self) -> None:
        for entry_id in ("adult_age", "adolescent_min_age"):
            entry = policy_entry(entry_id)
            assert entry.status is PolicyStatus.SET
            assert entry.source is not None and "06 §6" in entry.source


# --- classification: every band, every boundary -------------------------------------


class TestClassification:
    def test_adult_day_of_18th_birthday(self) -> None:
        assert classify(_verified(date(2008, 8, 28)), on=ON) is AgeBand.ADULT

    def test_adolescent_day_before_18th_birthday(self) -> None:
        assert classify(_verified(date(2008, 8, 29)), on=ON) is AgeBand.ADOLESCENT

    def test_adult_day_after_18th_birthday(self) -> None:
        assert classify(_verified(date(2008, 8, 27)), on=ON) is AgeBand.ADULT

    def test_adolescent_day_of_12th_birthday(self) -> None:
        assert classify(_verified(date(2014, 8, 28)), on=ON) is AgeBand.ADOLESCENT

    def test_child_day_before_12th_birthday(self) -> None:
        assert classify(_verified(date(2014, 8, 29)), on=ON) is AgeBand.CHILD

    def test_adolescent_day_after_12th_birthday(self) -> None:
        assert classify(_verified(date(2014, 8, 27)), on=ON) is AgeBand.ADOLESCENT

    def test_leap_day_birth_still_minor_on_28_feb(self) -> None:
        # awaiting-human row leap_day_maturity: until counsel answers, the
        # boundary falls on the LATER day — still 17 on 28 Feb of a non-leap
        # year (fail closed: guardian coverage lasts longer, never shorter).
        assert classify(_verified(date(2008, 2, 29)), on=date(2026, 2, 28)) is AgeBand.ADOLESCENT

    def test_leap_day_birth_adult_on_1_march(self) -> None:
        assert classify(_verified(date(2008, 2, 29)), on=date(2026, 3, 1)) is AgeBand.ADULT

    def test_leap_day_birth_on_a_leap_year_day_of(self) -> None:
        assert classify(_verified(date(2008, 2, 29)), on=date(2024, 2, 29)) is AgeBand.ADOLESCENT

    def test_absent_dob_classifies_unknown(self) -> None:
        assert classify(AgeContext.absent(), on=ON) is AgeBand.UNKNOWN

    def test_future_dob_classifies_unknown(self) -> None:
        assert classify(_verified(date(2030, 1, 1)), on=ON) is AgeBand.UNKNOWN

    def test_context_shape_is_validated(self) -> None:
        with pytest.raises(ValueError, match="dob"):
            AgeContext(dob=None, assurance=DobAssurance.VERIFIED)
        with pytest.raises(ValueError, match="dob"):
            AgeContext(dob=date(2000, 1, 1), assurance=DobAssurance.ABSENT)

    def test_jurisdiction_must_be_an_alpha2_code(self) -> None:
        with pytest.raises(ValueError, match="alpha-2"):
            AgeContext(dob=date(2000, 1, 1), assurance=DobAssurance.VERIFIED, jurisdiction="tr")


# --- actor resolution: the age band × consent actor table ---------------------------


class TestActorResolution:
    def test_verified_adult_consents_alone(self) -> None:
        decision = resolve_consent_actor(_verified(date(1990, 1, 1)), scope="core", on=ON)
        assert decision.permitted is True
        assert decision.required_actor is RequiredActor.SELF
        assert decision.adolescent_ack_required is False
        assert decision.missing == ()
        assert decision.policy_entry == "adult_actor"

    def test_verified_adolescent_needs_guardian_and_ack(self) -> None:
        decision = resolve_consent_actor(_verified(date(2012, 1, 1)), scope="core", on=ON)
        assert decision.permitted is False
        assert decision.required_actor is RequiredActor.GUARDIAN
        assert decision.adolescent_ack_required is True
        assert decision.missing == ("guardian_consent", "adolescent_ack")
        assert decision.policy_entry == "adolescent_actor"

    def test_verified_child_needs_guardian_only(self) -> None:
        decision = resolve_consent_actor(_verified(date(2020, 1, 1)), scope="core", on=ON)
        assert decision.permitted is False
        assert decision.required_actor is RequiredActor.GUARDIAN
        assert decision.adolescent_ack_required is False
        assert decision.missing == ("guardian_consent",)
        assert decision.policy_entry == "child_actor"

    def test_guardian_requirement_is_uniform_across_purposes(self) -> None:
        # files/06 §6: the guardian account holds THE legal consents — every
        # scope, not a subset; the share family resolves the same way.
        for scope in ("core", "voice", "wellbeing", "documents", "share:previsit_note"):
            decision = resolve_consent_actor(_verified(date(2012, 1, 1)), scope=scope, on=ON)
            assert decision.required_actor is RequiredActor.GUARDIAN, scope
            assert "guardian_consent" in decision.missing, scope

    def test_unverified_dob_fails_closed_even_when_adult_shaped(self) -> None:
        decision = resolve_consent_actor(
            AgeContext.unverified(date(1990, 1, 1)), scope="core", on=ON
        )
        assert decision.permitted is False
        assert decision.missing == ("verified_dob",)
        assert decision.policy_entry == "unverified_dob"

    def test_verified_future_dob_fails_closed(self) -> None:
        decision = resolve_consent_actor(_verified(date(2030, 1, 1)), scope="core", on=ON)
        assert decision.permitted is False
        assert decision.missing == ("verified_dob",)

    def test_absent_dob_is_the_status_quo_self_path(self) -> None:
        # INT-223 acceptance: "age from verified DOB" — under-18 status is
        # only ever established from a verified DOB; with no DOB record the
        # minor gate asserts nothing and ordinary consent state answers.
        decision = resolve_consent_actor(AgeContext.absent(), scope="core", on=ON)
        assert decision.permitted is True
        assert decision.band is AgeBand.UNKNOWN
        assert decision.required_actor is RequiredActor.SELF
        assert decision.policy_entry == "no_dob_recorded"

    def test_non_tr_jurisdiction_is_refused(self) -> None:
        ctx = AgeContext(dob=date(1990, 1, 1), assurance=DobAssurance.VERIFIED, jurisdiction="DE")
        decision = resolve_consent_actor(ctx, scope="core", on=ON)
        assert decision.permitted is False
        assert decision.missing == ("recognised_jurisdiction",)
        assert decision.policy_entry == "jurisdiction_tr_only"

    def test_scope_stays_on_the_closed_registry(self) -> None:
        with pytest.raises(UnknownPurposeError):
            resolve_consent_actor(_verified(date(1990, 1, 1)), scope="lane:acoustic", on=ON)


# --- the policy table: set entries carry sources, contested ones fail closed --------


class TestPolicyTable:
    def test_every_entry_is_set_or_awaiting_human_and_complete(self) -> None:
        assert POLICY_TABLE, "the policy table must not be empty"
        for entry in POLICY_TABLE:
            if entry.status is PolicyStatus.SET:
                assert entry.source, entry.id
            else:
                assert entry.status is PolicyStatus.AWAITING_HUMAN, entry.id
                assert entry.ask, entry.id
                assert entry.fail_closed, entry.id

    def test_entry_ids_are_unique(self) -> None:
        ids = [entry.id for entry in POLICY_TABLE]
        assert len(ids) == len(set(ids))

    def test_the_contested_questions_are_awaiting_human(self) -> None:
        for entry_id in (
            "unverified_dob",
            "adolescent_self_consent",
            "emancipation",
            "leap_day_maturity",
            "adolescent_private_guardian_default",
        ):
            entry = policy_entry(entry_id)
            assert entry.status is PolicyStatus.AWAITING_HUMAN, entry_id
            assert entry.ask is not None and "counsel" in entry.ask, entry_id

    def test_unknown_entry_id_raises(self) -> None:
        with pytest.raises(KeyError):
            policy_entry("not-a-policy-row")

    def test_a_settled_row_without_a_source_is_unwritable(self) -> None:
        with pytest.raises(ValueError, match="must cite its source"):
            PolicyEntry(id="unsourced", question="?", status=PolicyStatus.SET, value="18")

    def test_an_awaiting_human_row_without_its_ask_is_unwritable(self) -> None:
        with pytest.raises(ValueError, match="ask, owner, fail_closed"):
            PolicyEntry(
                id="askless",
                question="?",
                status=PolicyStatus.AWAITING_HUMAN,
                value="refuse",
                ask="who decides?",
                owner="counsel",
            )

    def test_duplicate_row_ids_are_refused_at_index_time(self) -> None:
        row = policy_entry("adult_age")
        with pytest.raises(ValueError, match="duplicate policy row id"):
            _index_policy_rows((row, row))

    def test_emancipation_is_not_recognised_until_counsel_answers(self) -> None:
        # No emancipation input exists on AgeContext at all: a claim cannot
        # even be expressed, so it cannot relax the guardian requirement.
        entry = policy_entry("emancipation")
        assert entry.fail_closed is not None and "guardian" in entry.fail_closed
        assert not hasattr(AgeContext.absent(), "emancipated")


# --- adolescent-private section visibility (files/06 §6) ----------------------------


class TestAdolescentPrivateSection:
    def test_clinician_delivery_is_unconditional(self) -> None:
        decision = adolescent_private_visibility(SectionAudience.CLINICIAN, clinic_policy=None)
        assert decision.visible is True
        assert decision.policy_entry == "adolescent_private_clinician_delivery"

    def test_guardian_visibility_without_a_recorded_policy_fails_closed(self) -> None:
        decision = adolescent_private_visibility(SectionAudience.GUARDIAN, clinic_policy=None)
        assert decision.visible is False
        assert decision.applied_policy is None
        assert decision.policy_entry == "adolescent_private_guardian_default"

    def test_guardian_visibility_follows_the_recorded_clinic_policy(self) -> None:
        allowing = ClinicPolicy(policy_id="clinic-policy-7", guardian_may_view=True)
        decision = adolescent_private_visibility(SectionAudience.GUARDIAN, clinic_policy=allowing)
        assert decision.visible is True
        assert decision.applied_policy == "clinic-policy-7"
        assert decision.policy_entry == "adolescent_private_guardian_clinic_policy"

    def test_denying_clinic_policy_is_recorded_too(self) -> None:
        denying = ClinicPolicy(policy_id="clinic-policy-8", guardian_may_view=False)
        decision = adolescent_private_visibility(SectionAudience.GUARDIAN, clinic_policy=denying)
        assert decision.visible is False
        assert decision.applied_policy == "clinic-policy-8"

    def test_clinic_policy_id_must_be_id_shaped(self) -> None:
        with pytest.raises(ValueError, match="policy_id"):
            ClinicPolicy(policy_id="not an id — narrative", guardian_may_view=True)


# --- enforcement: the ONE ensure_consent path, typed 403s, no PHI -------------------


class _FixedAgeSource:
    def __init__(self, ctx: AgeContext) -> None:
        self._ctx = ctx

    async def resolve(
        self, session: object, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> AgeContext:
        return self._ctx


class TestEnforcement:
    def test_default_source_reports_no_age_record(self) -> None:
        ctx = run(
            NoAgeRecordSource().resolve(None, tenant_id=DEV_TENANT_ID, patient_id=DEV_PATIENT_ID)
        )
        assert ctx.assurance is DobAssurance.ABSENT

    def test_absent_dob_keeps_the_status_quo(self, harness: ApiHarness) -> None:
        response = harness.client.get("/v1/visits", headers=harness.patient())
        assert response.status_code == 200

    def test_verified_adult_passes_the_gate(self, harness: ApiHarness) -> None:
        api_state(harness).age_context = _FixedAgeSource(AgeContext.verified(date(1990, 1, 1)))
        response = harness.client.get("/v1/visits", headers=harness.patient())
        assert response.status_code == 200

    def test_adolescent_subject_gets_a_typed_403_naming_the_requirement(
        self, harness: ApiHarness
    ) -> None:
        api_state(harness).age_context = _FixedAgeSource(AgeContext.verified(date(2012, 1, 1)))
        response = harness.client.get("/v1/visits", headers=harness.patient())
        assert response.status_code == 403
        assert response.json() == {"error": "guardian_consent_required", "scope": "core"}

    def test_child_subject_gets_the_same_guardian_refusal(self, harness: ApiHarness) -> None:
        api_state(harness).age_context = _FixedAgeSource(AgeContext.verified(date(2020, 1, 1)))
        response = harness.client.get("/v1/visits", headers=harness.patient())
        assert response.status_code == 403
        assert response.json() == {"error": "guardian_consent_required", "scope": "core"}

    def test_unverified_dob_gets_a_typed_403(self, harness: ApiHarness) -> None:
        api_state(harness).age_context = _FixedAgeSource(AgeContext.unverified(date(1990, 1, 1)))
        response = harness.client.get("/v1/visits", headers=harness.patient())
        assert response.status_code == 403
        assert response.json() == {"error": "dob_unverified", "scope": "core"}

    def test_non_tr_jurisdiction_gets_a_typed_403(self, harness: ApiHarness) -> None:
        ctx = AgeContext(dob=date(1990, 1, 1), assurance=DobAssurance.VERIFIED, jurisdiction="US")
        api_state(harness).age_context = _FixedAgeSource(ctx)
        response = harness.client.get("/v1/visits", headers=harness.patient())
        assert response.status_code == 403
        assert response.json() == {"error": "jurisdiction_unsupported", "scope": "core"}

    def test_refusal_body_never_carries_dob_or_age(self, harness: ApiHarness) -> None:
        api_state(harness).age_context = _FixedAgeSource(AgeContext.verified(date(2012, 6, 15)))
        response = harness.client.get("/v1/visits", headers=harness.patient())
        body = response.text
        assert "2012" not in body and "dob" not in body and "age" not in body
        assert set(response.json()) == {"error", "scope"}

    def test_minor_refusal_holds_even_with_seeded_consents(self, harness: ApiHarness) -> None:
        # The dev fixture seeds live consent rows; a minor's own grant must
        # not unlock anything — the age gate runs in the SAME evaluation as
        # the consent check, before consent rows can answer (invariant 4).
        api_state(harness).age_context = _FixedAgeSource(AgeContext.verified(date(2013, 3, 3)))
        for path in ("/v1/visits",):
            response = harness.client.get(path, headers=harness.patient())
            assert response.status_code == 403


# --- the guardian_link gate: default off, write refuses, read answers None ----------


class TestGuardianLinkGate:
    def test_guardian_link_is_a_safety_flag_defaulting_false(self) -> None:
        assert SAFETY_FLAG_DEFAULTS[GUARDIAN_LINK_FLAG] is False
        # a caller default can never open a safety flag (INT-023 contract)
        assert InMemoryProvider().get_bool(GUARDIAN_LINK_FLAG, True) is False

    def test_write_path_refuses_while_the_gate_is_off(self, harness: ApiHarness) -> None:
        audit = _RecordingAudit()

        async def _attempt() -> None:
            async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
                await record_guardian_link(
                    session,
                    tenant_id=DEV_TENANT_ID,
                    minor_patient_id=DEV_PATIENT_ID,
                    guardian_account_ref="account:guardian-unit",
                    relationship_ref="ack:desk-unit",
                    flags=InMemoryProvider(),
                    audit=audit,
                    actor="test:guardian",
                )

        with pytest.raises(GuardianLinkDisabledError):
            run(_attempt())
        assert audit.calls == []
        assert self._count_links(harness) == 0

    def test_write_path_works_and_audits_with_the_gate_explicitly_on(
        self, harness: ApiHarness
    ) -> None:
        audit = _RecordingAudit()
        flags_on = InMemoryProvider({GUARDIAN_LINK_FLAG: True})

        async def _link() -> None:
            async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
                await record_guardian_link(
                    session,
                    tenant_id=DEV_TENANT_ID,
                    minor_patient_id=DEV_PATIENT_ID,
                    guardian_account_ref="account:guardian-unit",
                    relationship_ref="ack:desk-unit",
                    flags=flags_on,
                    audit=audit,
                    actor="test:guardian",
                )

        run(_link())
        assert self._count_links(harness) == 1
        assert [call[1] for call in audit.calls] == ["guardian.link"]

    def test_read_path_answers_none_while_the_gate_is_off(self, harness: ApiHarness) -> None:
        flags_on = InMemoryProvider({GUARDIAN_LINK_FLAG: True})
        audit = _RecordingAudit()

        async def _seed_then_read_both_ways() -> tuple[GuardianLink | None, GuardianLink | None]:
            async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
                await record_guardian_link(
                    session,
                    tenant_id=DEV_TENANT_ID,
                    minor_patient_id=DEV_PATIENT_ID,
                    guardian_account_ref="account:guardian-unit",
                    relationship_ref="ack:desk-unit",
                    flags=flags_on,
                    audit=audit,
                    actor="test:guardian",
                )
            async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
                gated = await active_guardian_link(
                    session,
                    tenant_id=DEV_TENANT_ID,
                    minor_patient_id=DEV_PATIENT_ID,
                    flags=InMemoryProvider(),
                )
                open_read = await active_guardian_link(
                    session,
                    tenant_id=DEV_TENANT_ID,
                    minor_patient_id=DEV_PATIENT_ID,
                    flags=flags_on,
                )
            return gated, open_read

        gated, open_read = run(_seed_then_read_both_ways())
        assert gated is None  # a row on disk is unreadable while the gate is off
        assert open_read is not None

    def test_refs_must_be_id_shaped(self, harness: ApiHarness) -> None:
        flags_on = InMemoryProvider({GUARDIAN_LINK_FLAG: True})

        async def _attempt() -> None:
            async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
                await record_guardian_link(
                    session,
                    tenant_id=DEV_TENANT_ID,
                    minor_patient_id=DEV_PATIENT_ID,
                    guardian_account_ref="a guardian named in narrative form",
                    relationship_ref="ack:desk-unit",
                    flags=flags_on,
                    audit=_RecordingAudit(),
                    actor="test:guardian",
                )

        with pytest.raises(ValueError, match="guardian_account_ref"):
            run(_attempt())

    @staticmethod
    def _count_links(harness: ApiHarness) -> int:
        async def _count() -> int:
            async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
                value = await session.scalar(select(func.count()).select_from(GuardianLink))
                return int(value or 0)

        result: int = run(_count())
        return result


class _RecordingAudit:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None:
        self.calls.append((actor, action, resource_ref, consent_scope))


# --- schema + migration: inventory annotation and RLS, statically pinned ------------


class TestGuardianLinkSchema:
    def test_every_guardian_link_column_carries_an_awaiting_human_basis(self) -> None:
        # Persisting a guardian-minor relationship is a NEW personal-data
        # category (CLAUDE.md stop-and-ask): until counsel supplies the KVKK
        # basis, every column says so and the write path stays gated.
        table = GuardianLink.__table__
        for column in table.columns:
            annotation = column.info["inventory"]
            assert annotation["basis"].startswith("awaiting-human"), column.name

    def test_no_identity_shaped_columns(self) -> None:
        # refs only: the guardian is referenced by an id-shaped account ref,
        # never by name/TCKN/phone (invariant 14).
        names = {column.name for column in GuardianLink.__table__.columns}
        assert names == {
            "id",
            "tenant_id",
            "minor_patient_id",
            "guardian_account_ref",
            "relationship_ref",
            "verified_at",
            "revoked_at",
            "created_at",
        }

    def test_migration_ships_the_full_rls_shape(self) -> None:
        source = (REPO / "migrations" / "versions" / "0003_int223_guardian_links.py").read_text(
            encoding="utf-8"
        )
        assert "ALTER TABLE guardian_links ENABLE ROW LEVEL SECURITY" in source
        assert "ALTER TABLE guardian_links FORCE ROW LEVEL SECURITY" in source
        assert "CREATE POLICY guardian_links_tenant_isolation ON guardian_links" in source
        assert "WITH CHECK" in source
        assert "NULLIF(current_setting('app.tenant_id', true), '')::uuid" in source
        assert "REVOKE ALL ON guardian_links FROM PUBLIC" in source
        assert "GRANT SELECT, INSERT, UPDATE ON guardian_links TO app_rw" in source
        # links are consent-adjacent evidence: DELETE is granted to nobody
        assert "DELETE ON guardian_links" not in source

    def test_created_at_defaults_server_side(self, harness: ApiHarness) -> None:
        # the sqlite DDL clone in the harness carries the new table; a row
        # written with the gate on gets its instant from the server default
        flags_on = InMemoryProvider({GUARDIAN_LINK_FLAG: True})

        async def _link() -> GuardianLink:
            async with tenant_session(harness.engine, DEV_TENANT_ID) as session:
                return await record_guardian_link(
                    session,
                    tenant_id=DEV_TENANT_ID,
                    minor_patient_id=DEV_PATIENT_ID,
                    guardian_account_ref="account:guardian-unit",
                    relationship_ref="ack:desk-unit",
                    flags=flags_on,
                    audit=_RecordingAudit(),
                    actor="test:guardian",
                )

        row = run(_link())
        assert row.verified_at is None and row.revoked_at is None
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
        assert abs((datetime.now(UTC) - created).total_seconds()) < 60
