"""INT-102 — RT-12…RT-14: attribution, a spoken identifier, and failover.

The other half of files/04 §6 line 206. Same discipline as
``test_adversarial_rt09_14.py``: every attack carries the benign case one field
away, and the control must pass clean, because a gate that refused every
companion session, shredded every eleven-digit number or denied every host
would satisfy each refusal here while shipping nothing.

One of these scenarios does not close, and this suite says so rather than
working around it. RT-13's blueprint sentence is about a TC Kimlik number
**spoken aloud**; both pattern tiers in this repository match a contiguous
eleven-digit run, so the spoken forms are not masked. That is asserted as a
fact, together with the two controls that actually hold the line today, and it
is recorded on the scenario and in docs/evidence/INT-102.md. Closing it is a
change to :mod:`intake_platform.deid` plus an ASR-side digit-run
normalisation — two packages, and a defect for the coordinator to file.

Nothing here calls a model, a vendor or a network. Vendor hosts are never
written down: they are composed from ``intake_platform.egress.VENDOR_LLM_DOMAINS``,
which is that module's own documented convention and what
``scripts/ci/assert_no_vendor_calls.sh`` exists to keep true.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from adversarial_corpus import (
    ACCESSION_NUMBER_11_DIGITS,
    SECOND_SYNTHETIC_TCKN,
    SPOKEN_ACCESSION_FORMS,
    SPOKEN_DURATION_UTTERANCE,
    SPOKEN_TCKN_FORMS,
    SYNTHETIC_TCKN,
    FixedClock,
    KilledAdapter,
    SpokenForm,
    spoken_forms,
    utterance_with,
    utterance_with_duration,
    utterance_with_two,
)
from adversarial_scenarios import ADVERSARIAL_SCENARIOS
from intake_platform.chaos import (
    FALLBACK_DEADLINE_S,
    DegradationRouter,
    MockVendorAdapter,
    RouteMode,
    VendorKilled,
)
from intake_platform.deid import Deidentifier
from intake_platform.egress import (
    VENDOR_LLM_DOMAINS,
    AllowlistEntry,
    EgressAllowlist,
    EgressConfigError,
    EgressPurpose,
    assert_dev_only_vendors,
    load_allowlist,
)
from intake_platform.observability.spans import (
    LLM_SPAN_FIELDS,
    SpanFieldRefused,
    refuse_unless_ref_shaped,
)
from intake_platform.profiles.attribution import (
    PROXY_ACK_REQUIRED,
    Attribution,
    ProxyAcknowledgement,
    SensitiveDelivery,
    Speaker,
    SubjectRole,
    resolve_attribution,
)
from intake_platform.redaction import is_valid_tckn, redact_text
from intake_voice_runtime.extraction.errors import (
    ExtractionUnavailable,
    VendorEndpointRefused,
)
from intake_voice_runtime.extraction.gateway import (
    ENV_EXTRACTION_ENDPOINT,
    HttpExtractionGateway,
    extraction_gateway_from_env,
)

REPO = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = REPO / "infra" / "security" / "egress-allowlist.yaml"
ACKNOWLEDGED = ProxyAcknowledgement(
    acknowledged=True, at=datetime.datetime(2026, 9, 3, 9, 0, tzinfo=datetime.UTC)
)
UNACKNOWLEDGED = ProxyAcknowledgement(acknowledged=False)


# ---------------------------------------------------------------------------
# RT-12 — a companion answering for an adult without acknowledgement.
# ---------------------------------------------------------------------------


class TestRT12ProxyImpersonation:
    """*"engine requires `subject_role` confirmation and flags proxy-reported"*.

    The attack is not a forged field — it is the *absence* of one. A companion
    who simply starts answering is indistinguishable from the patient unless
    the role is declared and the acknowledgement given, so the refusal has to
    be the default and it has to be the *expensive* branch: a refusal that
    dropped the session into a laxer regime would make impersonation the
    cheaper path.
    """

    def test_an_unacknowledged_companion_is_refused_into_the_protective_regime(
        self,
    ) -> None:
        decision = resolve_attribution(
            role=SubjectRole.COMPANION,
            speaker=Speaker.COMPANION,
            acknowledgement=UNACKNOWLEDGED,
        )
        assert decision.permitted is False
        assert decision.refusal_code == PROXY_ACK_REQUIRED
        # The refusal is not a shortcut: most protective delivery, safeguarding
        # not asked, proxy_reported set.
        assert decision.sensitive_delivery is SensitiveDelivery.TEXT_ONLY
        assert decision.safeguarding_asked is False
        assert decision.proxy_reported is True

    def test_a_missing_acknowledgement_object_is_the_same_refusal(self) -> None:
        assert (
            resolve_attribution(
                role=SubjectRole.COMPANION, speaker=Speaker.COMPANION, acknowledgement=None
            ).refusal_code
            == PROXY_ACK_REQUIRED
        )

    def test_no_companion_session_can_ever_become_a_self_report(self) -> None:
        """The whole attack surface, enumerated rather than sampled."""
        for speaker in Speaker:
            for acknowledgement in (None, UNACKNOWLEDGED, ACKNOWLEDGED):
                for third_party in (False, True):
                    decision = resolve_attribution(
                        role=SubjectRole.COMPANION,
                        speaker=speaker,
                        acknowledgement=acknowledgement,
                        third_party_present=third_party,
                    )
                    assert decision.attribution is not Attribution.SELF_REPORT
                    assert decision.sensitive_delivery is SensitiveDelivery.TEXT_ONLY

    def test_a_self_role_cannot_declare_a_companion_speaker(self) -> None:
        with pytest.raises(ValueError, match="companion speaker"):
            resolve_attribution(role=SubjectRole.SELF, speaker=Speaker.COMPANION)

    def test_an_acknowledgement_without_its_instant_cannot_exist(self) -> None:
        with pytest.raises(ValueError, match="instant"):
            ProxyAcknowledgement(acknowledged=True)

    def test_the_near_miss_control_an_acknowledged_proxy_is_permitted(self) -> None:
        """A gate that refused every companion would pass every test above and
        would make the product unusable for the case it was designed around."""
        decision = resolve_attribution(
            role=SubjectRole.COMPANION,
            speaker=Speaker.COMPANION,
            acknowledgement=ACKNOWLEDGED,
        )
        assert decision.permitted is True
        assert decision.attribution is Attribution.PROXY_REPORT
        assert decision.proxy_reported is True

    def test_the_near_miss_control_a_genuine_self_session_is_untouched(self) -> None:
        decision = resolve_attribution(role=SubjectRole.SELF, speaker=Speaker.PATIENT)
        assert decision.attribution is Attribution.SELF_REPORT
        assert decision.proxy_reported is False
        assert decision.safeguarding_asked is True
        assert decision.sensitive_delivery is SensitiveDelivery.PROTOCOL

    def test_the_near_miss_control_the_assisted_case_is_neither_lie(self) -> None:
        decision = resolve_attribution(
            role=SubjectRole.COMPANION,
            speaker=Speaker.PATIENT,
            acknowledgement=ACKNOWLEDGED,
        )
        assert decision.attribution is Attribution.ASSISTED_SELF_REPORT
        assert decision.proxy_reported is False
        assert decision.third_party_present is True


# ---------------------------------------------------------------------------
# RT-13 — a TC Kimlik number spoken aloud.
# ---------------------------------------------------------------------------


class TestRT13SpokenIdentifier:
    """*"de-identification masks it before any cloud call and in logs"*.

    INT-102 asserted that this did **not** hold for a number said out loud, and
    committed the reproduction instead of normalising its own input to go green.
    INT-312 closes it. The corpus is still the input: ``SPOKEN_TCKN_FORMS`` is
    read as it stands, not pre-joined, and the same four shapes over a
    checksum-failing accession number are the control.

    The discriminator did not change. It is still the published checksum, so a
    lab accession number in any of these shapes survives untouched and a spoken
    duration — *"on beş gündür"* — is not an identifier. Over-masking a duration
    is a clinical harm, not a nuisance: a redacted duration is a lost history.
    """

    @staticmethod
    def _engine() -> Deidentifier:
        return Deidentifier(None, subject_key="rt-13")

    def test_the_written_form_is_masked_in_logs_and_by_the_pattern_tier(self) -> None:
        assert is_valid_tckn(SYNTHETIC_TCKN)
        text = utterance_with(SYNTHETIC_TCKN)
        assert redact_text(text) == text.replace(SYNTHETIC_TCKN, "[TCKN]")
        assert SYNTHETIC_TCKN not in self._engine().deidentify(text)

    @pytest.mark.parametrize("spoken", SPOKEN_TCKN_FORMS, ids=lambda form: form.id)
    def test_the_spoken_forms_are_masked_whole_by_both_tiers(self, spoken: SpokenForm) -> None:
        """Every shape, masked as one span — separators and all.

        Masking the digits and leaving ``100 - 78`` behind would be a partial
        leak dressed as a redaction, so the assertion is equality against the
        sentence with the whole spoken run replaced, not an ``in`` check.
        """
        text = utterance_with(spoken.transcript)
        assert spoken.why
        assert redact_text(text) == utterance_with("[TCKN]")
        assert self._engine().deidentify(text) == utterance_with("[TCKN]")

    def test_the_corpus_still_carries_the_shapes_the_finding_was_written_about(self) -> None:
        """The two shapes INT-102 committed are still in the corpus by id.

        A fix that quietly narrowed the corpus to the shapes it happens to
        handle would pass every test above.
        """
        ids = {form.id for form in SPOKEN_TCKN_FORMS}
        assert {"spaced-groups", "digit-words"} <= ids
        assert {"hyphenated-groups", "mixed-words-and-groups"} <= ids
        assert {form.id for form in SPOKEN_ACCESSION_FORMS} == ids

    def test_two_identifiers_in_one_utterance_are_both_masked(self) -> None:
        """Nothing here may depend on there being one number in a sentence.

        Two different values in two different shapes, and the ordinary words
        between them survive: a candidate that ran from the first identifier to
        the last would take ``eşiminki`` with it.
        """
        first, second = SPOKEN_TCKN_FORMS[0], spoken_forms(SECOND_SYNTHETIC_TCKN)[2]
        assert is_valid_tckn(SECOND_SYNTHETIC_TCKN)
        text = utterance_with_two(first.transcript, second.transcript)
        for masked in (redact_text(text), self._engine().deidentify(text)):
            assert masked == utterance_with_two("[TCKN]", "[TCKN]")
            assert "eşiminki" in masked

    @pytest.mark.parametrize("spoken", SPOKEN_ACCESSION_FORMS, ids=lambda form: form.id)
    def test_the_near_miss_control_the_same_shapes_with_a_failing_checksum_survive(
        self, spoken: SpokenForm
    ) -> None:
        """The control that stops the new tier being a number shredder.

        Identical shapes to the masked forms above, one field away: the
        checksum. A lab accession number said aloud is exactly as groupable as
        an identity number, and destroying it would take the provenance of a
        result with it.
        """
        text = utterance_with(spoken.transcript)
        assert redact_text(text) == text
        assert self._engine().deidentify(text) == text

    def test_the_near_miss_control_a_spoken_duration_is_not_an_identifier(self) -> None:
        """*"On beş gündür ağrım var"* is fifteen days of pain.

        Turkish digit words are ordinary clinical speech. A normaliser that
        treated any run of them as an identifier would delete the history the
        note exists to carry.
        """
        assert redact_text(SPOKEN_DURATION_UTTERANCE) == SPOKEN_DURATION_UTTERANCE
        assert self._engine().deidentify(SPOKEN_DURATION_UTTERANCE) == SPOKEN_DURATION_UTTERANCE

    def test_a_duration_touching_the_identifier_survives_the_mask(self) -> None:
        """The adjacency case, which is where a loose window actually bites.

        ``… yedi sekiz beş gündür`` — the duration's first word is one space
        from the identifier's last digit, inside the same run of digit-bearing
        tokens. The identifier goes; ``beş gündür`` stays.
        """
        spoken = SPOKEN_TCKN_FORMS[2]
        text = utterance_with_duration(spoken.transcript)
        for masked in (redact_text(text), self._engine().deidentify(text)):
            assert masked == utterance_with_duration("[TCKN]")
            assert "beş gündür ağrım var" in masked

    def test_what_actually_holds_the_line_the_egress_tier_fails_closed(self) -> None:
        """Asserted before the fix and after it, unchanged.

        ``deidentify_for_egress`` refuses **entirely** without the names/
        addresses tier, so pattern-only output is never mistaken for
        de-identified text on that boundary. A masking improvement is not a
        reason to soften it — the spoken forms are now masked *and* the egress
        boundary still refuses.
        """
        pattern_only = self._engine()
        assert pattern_only.ner_enabled is False
        with pytest.raises(RuntimeError, match="NER tier"):
            pattern_only.deidentify_for_egress(utterance_with(SYNTHETIC_TCKN))
        with pytest.raises(RuntimeError, match="NER tier"):
            pattern_only.deidentify_for_egress(utterance_with(SPOKEN_TCKN_FORMS[0].transcript))

    def test_what_actually_holds_the_line_the_trace_boundary_has_no_text_field(
        self,
    ) -> None:
        """There is no span field an utterance could occupy.

        Every string field is ref-shaped (no spaces, ASCII, ≤128 chars), so a
        sentence carrying an identifier is refused by field name with the value
        never echoed — and the closed field set has no free-text member at all.
        Asserted before the fix and after it, unchanged, and now over a spoken
        form as well as the written one.
        """
        assert not {"transcript", "text", "prompt", "utterance"} & set(LLM_SPAN_FIELDS)
        for value in (SYNTHETIC_TCKN, SPOKEN_TCKN_FORMS[1].transcript):
            with pytest.raises(SpanFieldRefused) as excinfo:
                refuse_unless_ref_shaped("work_id", utterance_with(value))
            assert value not in str(excinfo.value)

    def test_the_near_miss_control_a_checksum_failing_number_survives(self) -> None:
        """The checksum is what makes this a TCKN redactor rather than a number
        shredder. A lab accession number is eleven digits too, and destroying
        it would take the provenance of a result with it."""
        assert not is_valid_tckn(ACCESSION_NUMBER_11_DIGITS)
        text = utterance_with(ACCESSION_NUMBER_11_DIGITS)
        assert redact_text(text) == text
        assert Deidentifier(None, subject_key="rt-13").deidentify(text) == text

    def test_the_near_miss_control_an_ordinary_id_still_reaches_a_span(self) -> None:
        """A refuser that refused every value would pass the trace test above."""
        assert refuse_unless_ref_shaped("work_id", "work_01JABCDEF") == "work_01JABCDEF"

    def test_the_measured_leak_over_the_committed_corpus_is_zero(self) -> None:
        """The figure docs/evidence/INT-312.md records, as an assertion.

        Invariant 20: it is a measurement of *this* corpus on the day it ran,
        never a property of the product, so the corpus is named and counted here
        and the date lives with the run in the evidence file.
        """
        engine = self._engine()
        cases = [utterance_with(form.transcript) for form in SPOKEN_TCKN_FORMS]
        leaked = [
            form.id
            for form, text in zip(SPOKEN_TCKN_FORMS, cases, strict=True)
            if form.transcript in redact_text(text) or form.transcript in engine.deidentify(text)
        ]
        assert len(cases) == 4
        assert leaked == []

    def test_the_gap_recorded_on_the_scenario_is_closed(self) -> None:
        """RT-13 carried the only open gap that was a hole rather than a note.

        It is emptied here rather than left standing with a fix behind it: a
        gaps tuple that outlives its gap is how the next reader learns to
        ignore the field.
        """
        assert ADVERSARIAL_SCENARIOS["RT-13"].gaps == ()


# ---------------------------------------------------------------------------
# RT-14 — the ASR vendor fails mid-session.
# ---------------------------------------------------------------------------


class TestRT14VendorFailover:
    """*"fails over to the fallback adapter or typed mode within 2 s;
    session resumes; metrics show the switch"*.

    The adversarial reading of a failover clause is the interesting one:
    **failover must not become a route around the allow-list**. A degradation
    path that could reach "the next vendor" would be a policy hole that only
    opens when something is already going wrong, which is the worst possible
    time for it to open.
    """

    def test_the_next_vendor_is_not_a_value_the_router_can_return(self) -> None:
        assert set(RouteMode.__args__) == {"vendor", "typed"}

    def test_a_dead_adapter_degrades_to_typed_inside_the_bound(self) -> None:
        clock = FixedClock(readings=[0.0, 0.75])
        router = DegradationRouter(adapter=KilledAdapter(), clock=clock)
        result = router.route("payload")
        assert result.mode == "typed"
        assert result.response is None
        assert result.fallback_latency_s is not None
        assert result.fallback_latency_s <= FALLBACK_DEADLINE_S
        # The reason is a class name, never message text that could quote a
        # payload (invariant 6).
        assert result.reason == VendorKilled.__name__
        assert "payload" not in str(result.reason)

    def test_the_near_miss_control_a_healthy_adapter_still_routes(self) -> None:
        """A router that always degraded would pass the test above and would
        never serve a session."""
        router = DegradationRouter(adapter=MockVendorAdapter(name="probe"))
        result = router.route("payload")
        assert result.mode == "vendor"
        assert result.fallback_latency_s is None
        assert result.reason is None

    @pytest.mark.parametrize("domain", sorted(VENDOR_LLM_DOMAINS))
    def test_no_failover_can_be_configured_at_a_vendor_host(self, domain: str) -> None:
        """Composed from ``VENDOR_LLM_DOMAINS``, never written down: the gate in
        ``scripts/ci/assert_no_vendor_calls.sh`` exists because the deleted
        vendor list recirculates, and a test that restated it would be the
        recirculation."""
        env = {ENV_EXTRACTION_ENDPOINT: f"https://{domain}/v1"}
        with pytest.raises(VendorEndpointRefused):
            extraction_gateway_from_env(env)

    def test_a_policy_refusal_is_not_an_availability_error(self) -> None:
        """The distinction that stops a retry loop treating a policy block as a
        flaky endpoint, and eventually treating it as a reason to widen the
        allow-list."""
        assert not issubclass(VendorEndpointRefused, ExtractionUnavailable)
        assert not issubclass(ExtractionUnavailable, VendorEndpointRefused)

    def test_the_near_miss_control_a_self_hosted_endpoint_is_accepted(self) -> None:
        """A refuser that refused every host would pass the two tests above."""
        gateway = extraction_gateway_from_env(
            {ENV_EXTRACTION_ENDPOINT: "https://asr.intake.svc.cluster.local:8000"}
        )
        assert isinstance(gateway, HttpExtractionGateway)

    def test_the_shipped_allowlist_keeps_vendors_off_the_phi_path(self) -> None:
        assert_dev_only_vendors(load_allowlist(ALLOWLIST_PATH))

    def test_the_allowlist_gate_can_fail_when_a_vendor_family_moves(self) -> None:
        """The same gate, given a list that puts a vendor family on the PHI
        path, refuses — otherwise the test above asserts nothing.

        The shipped file carries no vendor entry at all, which is why the
        failing case has to be constructed here. The host is taken from
        ``VENDOR_LLM_DOMAINS`` rather than written down.
        """
        with pytest.raises(EgressConfigError, match="PHI path"):
            assert_dev_only_vendors(_allowlist_with(_vendor_entry(), tier="phi_path"))

    def test_the_near_miss_control_the_same_entry_on_the_dev_tier_is_allowed(self) -> None:
        """Invariant 19: those adapters exist as the mock/dev path. A gate that
        refused them everywhere would delete the dev lane rather than protect
        the PHI one."""
        assert_dev_only_vendors(_allowlist_with(_vendor_entry(), tier="dev"))


def _vendor_entry() -> AllowlistEntry:
    return AllowlistEntry(
        name="vendor-family-under-test",
        host=sorted(VENDOR_LLM_DOMAINS)[0],
        port=443,
        protocol="https",
        purpose_id=EgressPurpose.MODEL_WEIGHTS,
        purpose="the mock/dev LLM adapter lane (CLAUDE.md invariant 19)",
        basis="dev tier only; never on the PHI path",
    )


def _allowlist_with(entry: AllowlistEntry, *, tier: str) -> EgressAllowlist:
    tiers: dict[str, list[dict[str, object]]] = {"dev": [], "phi_path": []}
    tiers[tier] = [entry.model_dump()]
    return EgressAllowlist.model_validate({"version": 1, "tiers": tiers})
