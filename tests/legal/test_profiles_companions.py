"""INT-133 — profiles, companions, guardian flows, proxy acknowledgement.

INT-223 built the RULES ENGINE (age bands, required actor, the closed
guardian-linkage gate). This file pins the PROFILE AND FLOW layer on top of
it, and above all pins that the layer **consumes** INT-223's decisions
rather than softening them:

- the three attribution values of files/02 §3 (``self_report``,
  ``proxy_report``, ``assisted_self_report``) are derived from a declared
  role + speaker, never asserted by a caller, and files/06 §6's "companion/
  proxy answers are always flagged ``proxy_reported`` on the record" holds
  for every record the API emits — created, listed, read, and on the note;
- files/13 §13's third-party rule rides the same derivation: a third party
  present forces every sensitive section to text and safeguarding is not
  asked at all;
- a companion may not proceed without the proxy acknowledgement, and an
  acknowledgement is **never** proof of representation — an acknowledged
  companion on a minor subject is still refused, because
  ``guardian_relationship_proof`` is awaiting-human;
- every flow that cannot proceed fails closed with a typed refusal and
  NAMES the HB-L20 policy row that gates it, internally. Those row ids are
  real ``POLICY_TABLE`` rows with ``status: awaiting_human`` — and they
  never travel on the wire, because a body saying
  ``adolescent_self_consent`` would disclose the subject's age band
  (invariant 6);
- the four refusals INT-223 chose stay refused: no adolescent self-consent
  path, no emancipation input, no guardian-disclosure default, and the
  ``guardian_link`` gate stays shut.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from api_harness import ApiHarness
from intake_api.consent_guard import unguarded_data_routes
from intake_platform.consent.minors import (
    AgeBand,
    AgeContext,
    ClinicPolicy,
    DobAssurance,
    PolicyStatus,
    RequiredActor,
    SectionAudience,
    policy_entry,
)
from intake_platform.flags import InMemoryProvider
from intake_platform.profiles import (
    ADOLESCENT_PRIVATE_SECTION,
    Attribution,
    AttributionDecision,
    ProfileFlowOutcome,
    ProfileFlowStep,
    ProxyAcknowledgement,
    SensitiveDelivery,
    Speaker,
    SubjectRole,
    blocking_policy_rows,
    release_adolescent_private_section,
    resolve_attribution,
    resolve_profile_flow,
)
from legal_harness import api_state

ON = date(2026, 8, 28)
ACK_AT = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)

ADULT = AgeContext.verified(date(1990, 1, 1))
ADOLESCENT = AgeContext.verified(date(2012, 1, 1))
CHILD = AgeContext.verified(date(2020, 1, 1))
NO_DOB = AgeContext.absent()
UNVERIFIED = AgeContext.unverified(date(1990, 1, 1))
NON_TR = AgeContext(dob=date(1990, 1, 1), assurance=DobAssurance.VERIFIED, jurisdiction="US")

ACKED = ProxyAcknowledgement(acknowledged=True, at=ACK_AT)
NOT_ACKED = ProxyAcknowledgement(acknowledged=False, at=None)


class _FixedAgeSource:
    def __init__(self, ctx: AgeContext) -> None:
        self._ctx = ctx

    async def resolve(
        self, session: object, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> AgeContext:
        return self._ctx


# --- attribution: the three files/02 §3 values, derived and never asserted ----------


class TestAttribution:
    def test_the_value_set_is_exactly_the_three_files_02_values(self) -> None:
        assert {member.value for member in Attribution} == {
            "self_report",
            "proxy_report",
            "assisted_self_report",
        }

    def test_self_alone_is_self_report_and_nothing_is_forced(self) -> None:
        decision = resolve_attribution(role=SubjectRole.SELF, speaker=Speaker.PATIENT)
        assert decision.permitted
        assert decision.attribution is Attribution.SELF_REPORT
        assert decision.proxy_reported is False
        assert decision.third_party_present is False
        assert decision.sensitive_delivery is SensitiveDelivery.PROTOCOL
        assert decision.safeguarding_asked is True

    def test_companion_speaking_is_proxy_report_and_carries_the_flag(self) -> None:
        decision = resolve_attribution(
            role=SubjectRole.COMPANION, speaker=Speaker.COMPANION, acknowledgement=ACKED
        )
        assert decision.permitted
        assert decision.attribution is Attribution.PROXY_REPORT
        assert decision.proxy_reported is True

    def test_patient_speaking_on_a_companion_device_is_assisted_self_report(self) -> None:
        decision = resolve_attribution(
            role=SubjectRole.COMPANION, speaker=Speaker.PATIENT, acknowledgement=ACKED
        )
        assert decision.attribution is Attribution.ASSISTED_SELF_REPORT
        # files/02 §3: the patient's own words — the note records the patient
        # as the speaker and the assistance as CONTEXT, so the answers are
        # not proxy-reported...
        assert decision.proxy_reported is False
        # ...but a third party is present BY DEFINITION, which is the whole
        # reason the value exists.
        assert decision.third_party_present is True

    def test_a_companion_role_with_no_acknowledgement_is_refused(self) -> None:
        decision = resolve_attribution(
            role=SubjectRole.COMPANION, speaker=Speaker.COMPANION, acknowledgement=NOT_ACKED
        )
        assert decision.permitted is False
        assert decision.refusal_code == "proxy_acknowledgement_required"

    def test_a_companion_role_with_no_acknowledgement_object_is_refused(self) -> None:
        decision = resolve_attribution(role=SubjectRole.COMPANION, speaker=Speaker.COMPANION)
        assert decision.permitted is False
        assert decision.refusal_code == "proxy_acknowledgement_required"

    def test_a_self_role_cannot_declare_a_companion_speaker(self) -> None:
        with pytest.raises(ValueError):
            resolve_attribution(role=SubjectRole.SELF, speaker=Speaker.COMPANION)

    def test_an_acknowledgement_without_an_instant_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError):
            ProxyAcknowledgement(acknowledged=True, at=None)

    def test_an_instant_without_an_acknowledgement_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError):
            ProxyAcknowledgement(acknowledged=False, at=ACK_AT)


class TestThirdPartyRule:
    """files/13 §13 — a third party present is a CONFOUND, not a feature."""

    def test_a_declared_third_party_forces_text_only_and_stops_safeguarding(self) -> None:
        decision = resolve_attribution(
            role=SubjectRole.SELF, speaker=Speaker.PATIENT, third_party_present=True
        )
        assert decision.attribution is Attribution.SELF_REPORT
        assert decision.sensitive_delivery is SensitiveDelivery.TEXT_ONLY
        assert decision.safeguarding_asked is False

    def test_assisted_self_report_gets_the_same_regime_without_being_declared(self) -> None:
        decision = resolve_attribution(
            role=SubjectRole.COMPANION, speaker=Speaker.PATIENT, acknowledgement=ACKED
        )
        assert decision.sensitive_delivery is SensitiveDelivery.TEXT_ONLY
        assert decision.safeguarding_asked is False

    def test_safeguarding_is_never_asked_of_a_proxy(self) -> None:
        decision = resolve_attribution(
            role=SubjectRole.COMPANION,
            speaker=Speaker.COMPANION,
            acknowledgement=ACKED,
            third_party_present=False,
        )
        assert decision.safeguarding_asked is False
        assert decision.sensitive_delivery is SensitiveDelivery.TEXT_ONLY


# --- the flow: consumes INT-223, never re-decides it --------------------------------


class TestProfileFlow:
    def test_a_verified_adult_alone_proceeds(self) -> None:
        outcome = resolve_profile_flow(ADULT, scope="core", on=ON)
        assert outcome.step is ProfileFlowStep.PROCEED
        assert outcome.permitted is True
        assert outcome.blocked_on == ()
        assert outcome.band is AgeBand.ADULT
        assert outcome.required_actor is RequiredActor.SELF
        assert outcome.minor_regime_asserted is True

    def test_an_absent_dob_proceeds_but_asserts_no_minor_regime(self) -> None:
        outcome = resolve_profile_flow(NO_DOB, scope="core", on=ON)
        assert outcome.permitted is True
        assert outcome.band is AgeBand.UNKNOWN
        # INT-223's no_dob_recorded row: the gate asserts nothing, the ledger
        # answers. The flow records the unassertability rather than inventing
        # an adult (the open dob_collection_mandatory question).
        assert outcome.minor_regime_asserted is False
        assert outcome.blocked_on == ()

    def test_a_child_fails_closed_on_the_two_linkage_questions(self) -> None:
        outcome = resolve_profile_flow(CHILD, scope="core", on=ON)
        assert outcome.step is ProfileFlowStep.BLOCKED_AWAITING_HUMAN
        assert outcome.permitted is False
        assert outcome.refusal_code == "guardian_consent_required"
        assert outcome.blocked_on == ("guardian_link_basis", "guardian_relationship_proof")

    def test_an_adolescent_additionally_names_the_two_relaxations_that_stay_refused(self) -> None:
        outcome = resolve_profile_flow(ADOLESCENT, scope="core", on=ON)
        assert outcome.step is ProfileFlowStep.BLOCKED_AWAITING_HUMAN
        assert outcome.refusal_code == "guardian_consent_required"
        assert outcome.blocked_on == (
            "adolescent_self_consent",
            "emancipation",
            "guardian_link_basis",
            "guardian_relationship_proof",
        )

    def test_an_unverified_dob_fails_closed_on_its_own_question(self) -> None:
        outcome = resolve_profile_flow(UNVERIFIED, scope="core", on=ON)
        assert outcome.refusal_code == "dob_unverified"
        assert outcome.blocked_on == ("unverified_dob",)

    def test_a_non_tr_subject_fails_closed_on_the_jurisdiction_question(self) -> None:
        outcome = resolve_profile_flow(NON_TR, scope="core", on=ON)
        assert outcome.refusal_code == "jurisdiction_unsupported"
        assert outcome.blocked_on == ("jurisdiction_tr_only",)

    def test_every_named_row_is_a_real_awaiting_human_policy_row(self) -> None:
        for context in (CHILD, ADOLESCENT, UNVERIFIED, NON_TR):
            outcome = resolve_profile_flow(context, scope="core", on=ON)
            assert outcome.blocked_on
            for row_id in outcome.blocked_on:
                entry = policy_entry(row_id)
                assert entry.status is PolicyStatus.AWAITING_HUMAN
                assert entry.fail_closed

    def test_blocking_rows_are_sorted_and_deduplicated(self) -> None:
        rows = blocking_policy_rows("guardian_consent_required", AgeBand.ADOLESCENT)
        assert list(rows) == sorted(set(rows))

    def test_no_refusal_blocks_on_nothing(self) -> None:
        # a permission is not a refusal with an empty reason list — the
        # mapping must not invent a blocker for a subject who may proceed
        assert blocking_policy_rows(None, AgeBand.ADULT) == ()

    def test_an_unmapped_refusal_names_no_row_rather_than_the_nearest_one(self) -> None:
        # a refusal code this layer does not know is reported with no
        # blocker, not with another refusal's questions borrowed
        assert blocking_policy_rows("consent_required", AgeBand.ADULT) == ()

    def test_a_permitted_subject_still_needs_the_proxy_acknowledgement(self) -> None:
        outcome = resolve_profile_flow(
            ADULT, scope="core", on=ON, role=SubjectRole.COMPANION, speaker=Speaker.COMPANION
        )
        assert outcome.step is ProfileFlowStep.NEEDS_PROXY_ACKNOWLEDGEMENT
        assert outcome.permitted is False
        assert outcome.refusal_code == "proxy_acknowledgement_required"
        # a product rule, not a legal one: nothing here is awaiting a human
        assert outcome.blocked_on == ()

    def test_an_acknowledged_companion_on_an_adult_proceeds_as_proxy(self) -> None:
        outcome = resolve_profile_flow(
            ADULT,
            scope="core",
            on=ON,
            role=SubjectRole.COMPANION,
            speaker=Speaker.COMPANION,
            acknowledgement=ACKED,
        )
        assert outcome.step is ProfileFlowStep.PROCEED
        assert outcome.attribution is not None
        assert outcome.attribution.attribution is Attribution.PROXY_REPORT
        assert outcome.attribution.proxy_reported is True


class TestNoRelaxationSurvives:
    """The four things INT-223 refused, pinned as still refused HERE."""

    def test_an_acknowledgement_is_not_proof_of_representation(self) -> None:
        # An adult companion who acknowledges speaking for a MINOR is still
        # refused: the acknowledgement never becomes velâyet evidence
        # (guardian_relationship_proof is awaiting-human).
        outcome = resolve_profile_flow(
            ADOLESCENT,
            scope="core",
            on=ON,
            role=SubjectRole.COMPANION,
            speaker=Speaker.COMPANION,
            acknowledgement=ACKED,
        )
        assert outcome.permitted is False
        assert outcome.refusal_code == "guardian_consent_required"
        assert "guardian_relationship_proof" in outcome.blocked_on
        # the age refusal outranks the acknowledgement step: the flow never
        # reaches an attribution for a subject it may not serve at all
        assert outcome.attribution is None

    def test_no_adolescent_self_consent_path_exists_in_the_flow(self) -> None:
        # There is no argument, no role and no acknowledgement that makes an
        # adolescent their own consent actor.
        for role, speaker, ack in (
            (SubjectRole.SELF, Speaker.PATIENT, None),
            (SubjectRole.COMPANION, Speaker.PATIENT, ACKED),
            (SubjectRole.COMPANION, Speaker.COMPANION, ACKED),
        ):
            outcome = resolve_profile_flow(
                ADOLESCENT, scope="core", on=ON, role=role, speaker=speaker, acknowledgement=ack
            )
            assert outcome.required_actor is RequiredActor.GUARDIAN
            assert outcome.permitted is False

    def test_the_flow_exposes_no_emancipation_input(self) -> None:
        import inspect

        signature = inspect.signature(resolve_profile_flow)
        assert not [name for name in signature.parameters if "emancip" in name.lower()]

    def test_the_guardian_link_gate_is_still_shut_for_the_flow(self) -> None:
        from intake_platform.consent.guardian import guardian_link_enabled

        assert guardian_link_enabled(InMemoryProvider()) is False


# --- the adolescent-private section (files/06 §6) -----------------------------------


class TestAdolescentPrivateSection:
    def test_the_clinician_always_receives_it(self) -> None:
        release = release_adolescent_private_section(audience=SectionAudience.CLINICIAN)
        assert release.section == ADOLESCENT_PRIVATE_SECTION
        assert release.released is True
        assert release.policy_entry == "adolescent_private_clinician_delivery"
        assert release.blocked_on == ()

    def test_no_recorded_clinic_policy_means_the_guardian_sees_nothing(self) -> None:
        release = release_adolescent_private_section(audience=SectionAudience.GUARDIAN)
        assert release.released is False
        assert release.applied_policy is None
        assert release.policy_entry == "adolescent_private_guardian_default"
        assert release.blocked_on == ("adolescent_private_guardian_default",)

    def test_a_recorded_permissive_policy_releases_and_is_named(self) -> None:
        policy = ClinicPolicy(policy_id="clinic:acibadem/adolescent-v3", guardian_may_view=True)
        release = release_adolescent_private_section(
            audience=SectionAudience.GUARDIAN, clinic_policy=policy
        )
        assert release.released is True
        # "the app records which policy applied" is the obligation
        assert release.applied_policy == "clinic:acibadem/adolescent-v3"
        assert release.blocked_on == ()

    def test_a_recorded_restrictive_policy_withholds_and_is_still_named(self) -> None:
        policy = ClinicPolicy(policy_id="clinic:acibadem/adolescent-v3", guardian_may_view=False)
        release = release_adolescent_private_section(
            audience=SectionAudience.GUARDIAN, clinic_policy=policy
        )
        assert release.released is False
        assert release.applied_policy == "clinic:acibadem/adolescent-v3"

    def test_a_third_party_in_the_room_stops_the_device_render_either_way(self) -> None:
        policy = ClinicPolicy(policy_id="clinic:acibadem/adolescent-v3", guardian_may_view=True)
        release = release_adolescent_private_section(
            audience=SectionAudience.GUARDIAN, clinic_policy=policy, third_party_present=True
        )
        assert release.released is True
        assert release.renderable_on_shared_device is False

    def test_alone_the_section_renders_on_the_device(self) -> None:
        release = release_adolescent_private_section(audience=SectionAudience.CLINICIAN)
        assert release.renderable_on_shared_device is True


# --- the API slice: the flag on every record, and no new leak -----------------------


def _visit_payload(**extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"hospital": "Acıbadem", "department": "Kardiyoloji"}
    payload.update(extra)
    return payload


class TestApiProxyFlag:
    def test_a_plain_visit_is_self_reported(self, harness: ApiHarness) -> None:
        created = harness.client.post(
            "/v1/visits", json=_visit_payload(), headers=harness.patient()
        )
        assert created.status_code == 201
        assert created.json()["proxy_reported"] is False
        assert created.json()["third_party_present"] is False

    def test_a_companion_visit_is_flagged_on_create_read_and_list(
        self, harness: ApiHarness
    ) -> None:
        created = harness.client.post(
            "/v1/visits",
            json=_visit_payload(
                attribution={"role": "companion", "speaker": "companion", "acknowledged": True}
            ),
            headers=harness.patient(),
        )
        assert created.status_code == 201, created.text
        visit_id = created.json()["id"]
        assert created.json()["proxy_reported"] is True

        read = harness.client.get(f"/v1/visits/{visit_id}", headers=harness.patient())
        assert read.json()["proxy_reported"] is True

        listed = harness.client.get("/v1/visits", headers=harness.patient())
        rows = [row for row in listed.json() if row["id"] == visit_id]
        assert rows and rows[0]["proxy_reported"] is True

    def test_assisted_self_report_is_third_party_present_but_not_proxy(
        self, harness: ApiHarness
    ) -> None:
        created = harness.client.post(
            "/v1/visits",
            json=_visit_payload(
                attribution={"role": "companion", "speaker": "patient", "acknowledged": True}
            ),
            headers=harness.patient(),
        )
        assert created.status_code == 201, created.text
        assert created.json()["proxy_reported"] is False
        assert created.json()["third_party_present"] is True

    def test_an_incoherent_declaration_is_refused_before_anything_is_stored(
        self, harness: ApiHarness
    ) -> None:
        # "I am doing this for myself" + "someone else is answering" is not a
        # session shape that exists; guessing which half was meant would be
        # guessing at the attribution of every answer that follows.
        created = harness.client.post(
            "/v1/visits",
            json=_visit_payload(
                attribution={"role": "self", "speaker": "companion", "acknowledged": True}
            ),
            headers=harness.patient(),
        )
        assert created.status_code == 422
        assert created.json() == {"error": "attribution_incoherent"}
        assert harness.client.get("/v1/visits", headers=harness.patient()).json() == []

    def test_a_companion_without_an_acknowledgement_is_refused(self, harness: ApiHarness) -> None:
        created = harness.client.post(
            "/v1/visits",
            json=_visit_payload(
                attribution={"role": "companion", "speaker": "companion", "acknowledged": False}
            ),
            headers=harness.patient(),
        )
        assert created.status_code == 422
        assert created.json() == {"error": "proxy_acknowledgement_required"}

    def test_every_visit_row_carries_the_flag(self, harness: ApiHarness) -> None:
        # a mixed ledger: the flag is on EVERY row, including the plain ones.
        # An absent flag would read as "unknown", and a clinician must be able
        # to tell self-reported from not-recorded (files/06 §6).
        for attribution in (
            None,
            {"role": "companion", "speaker": "companion", "acknowledged": True},
            {"role": "companion", "speaker": "patient", "acknowledged": True},
        ):
            payload = _visit_payload()
            if attribution is not None:
                payload["attribution"] = attribution
            assert (
                harness.client.post(
                    "/v1/visits", json=payload, headers=harness.patient()
                ).status_code
                == 201
            )
        listed = harness.client.get("/v1/visits", headers=harness.patient())
        assert listed.status_code == 200
        assert len(listed.json()) == 3
        for row in listed.json():
            assert isinstance(row["proxy_reported"], bool)
            assert isinstance(row["third_party_present"], bool)
        assert [row["proxy_reported"] for row in listed.json()].count(True) == 1

    def test_the_note_carries_the_session_flag(self, harness: ApiHarness) -> None:
        created = harness.client.post(
            "/v1/visits",
            json=_visit_payload(
                attribution={"role": "companion", "speaker": "companion", "acknowledged": True}
            ),
            headers=harness.patient(),
        )
        visit_id = created.json()["id"]
        put = harness.client.put(
            f"/v1/visits/{visit_id}/note",
            json={
                "status": "draft",
                "sections": [
                    {"id": "chief_complaint", "title": "Şikâyet", "lines": ["Göğüs ağrısı"]}
                ],
            },
            headers=harness.patient(),
        )
        assert put.status_code in (200, 201), put.text
        assert put.json()["proxy_reported"] is True
        got = harness.client.get(f"/v1/visits/{visit_id}/note", headers=harness.patient())
        assert got.json()["proxy_reported"] is True


class TestApiProfileRoute:
    def test_the_profile_route_reports_the_shut_guardian_gate(self, harness: ApiHarness) -> None:
        response = harness.client.get("/v1/me/profile", headers=harness.patient())
        assert response.status_code == 200
        body = response.json()
        assert body["guardian_flow_available"] is False
        assert body["proxy_acknowledgement_required"] is True
        assert body["attributions"] == ["self_report", "proxy_report", "assisted_self_report"]

    def test_the_profile_route_is_behind_the_one_enforcement_point(
        self, harness: ApiHarness
    ) -> None:
        api_state(harness).age_context = _FixedAgeSource(ADOLESCENT)
        response = harness.client.get("/v1/me/profile", headers=harness.patient())
        assert response.status_code == 403
        assert response.json() == {"error": "guardian_consent_required", "scope": "core"}

    def test_no_route_added_by_this_issue_is_undeclared(self, harness: ApiHarness) -> None:
        assert unguarded_data_routes(harness.client.app) == []  # type: ignore[arg-type]


class TestNoLeakOnTheWire:
    def test_a_minor_refusal_never_names_the_policy_row_or_the_band(
        self, harness: ApiHarness
    ) -> None:
        api_state(harness).age_context = _FixedAgeSource(ADOLESCENT)
        response = harness.client.post(
            "/v1/visits", json=_visit_payload(), headers=harness.patient()
        )
        assert response.status_code == 403
        body = response.text
        for leak in (
            "adolescent",
            "emancipation",
            "guardian_link_basis",
            "guardian_relationship_proof",
            "blocked_on",
            "band",
            "2012",
        ):
            assert leak not in body
        assert set(response.json()) == {"error", "scope"}

    def test_the_acknowledgement_refusal_body_is_a_bare_code(self, harness: ApiHarness) -> None:
        response = harness.client.post(
            "/v1/visits",
            json=_visit_payload(
                attribution={"role": "companion", "speaker": "companion", "acknowledged": False}
            ),
            headers=harness.patient(),
        )
        assert set(response.json()) == {"error"}


class TestDecisionShapes:
    """The decision objects are frozen data: a caller cannot mutate a
    refusal into a permission after the fact."""

    def test_attribution_decision_is_frozen(self) -> None:
        decision = resolve_attribution(role=SubjectRole.SELF, speaker=Speaker.PATIENT)
        assert isinstance(decision, AttributionDecision)
        with pytest.raises((AttributeError, TypeError)):
            decision.proxy_reported = True  # type: ignore[misc]

    def test_flow_outcome_is_frozen(self) -> None:
        outcome = resolve_profile_flow(CHILD, scope="core", on=ON)
        assert isinstance(outcome, ProfileFlowOutcome)
        with pytest.raises((AttributeError, TypeError)):
            outcome.permitted = True  # type: ignore[misc]
