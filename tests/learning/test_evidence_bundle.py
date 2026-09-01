"""INT-172 — evidence bundles, signing, and the open-not-merge PR request.

files/09 §4: a proposal is "a PR … + attached evidence bundle (aggregate
stats, de-identified exemplars, simulator run, triage goldens, latency
harness, shadow replay on de-identified transcripts, Langfuse experiment
link)". files/09 §7: "proposals and evidence bundles are signed" and the bot
identity "can open but not merge".

Two departures from that list are asserted here rather than left implicit:

- **No exemplars.** "De-identified exemplars" of Turkish clinical speech is
  the claim files/HUMAN_BLOCKERS.md HB-L6 records as one "Turkish NLP cannot
  support", and INT-171 built the whole analytics layer without narrative for
  that reason. A bundle carries counts and citations and nothing a person
  said. :func:`test_a_planted_turkish_symptom_sentence_never_reaches_a_bundle`
  is the adversarial proof.
- **The remaining artefacts fail closed rather than being faked.** Each is a
  required check starting at ``NOT_AVAILABLE`` and naming the issue that
  produces it; an incomplete bundle cannot open a pull request.

sec_row: `learning-loops`.  legal: KVKK-16, KSVY-16.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import pytest
from intake_learning.architect import EffectSizeFloor, PromotionThresholds, Proposal, propose
from intake_learning.evidence import CheckStatus, EvidenceBundle, EvidenceSource
from intake_learning.inspector import inspect_step_coverage
from intake_learning.publisher import (
    IncompleteEvidence,
    ProposalPublisher,
    PullRequestRequest,
    build_pull_request,
)
from intake_learning.signing import (
    SignedBundle,
    SigningKeyUnavailable,
    digest_of,
    sign_bundle,
    verify_bundle,
)
from intake_platform.analytics import (
    K_ANONYMITY_FLOOR,
    SESSION_OUTCOMES,
    STEP_COVERAGE,
    Cell,
    Cohort,
    KAnonymityRefusal,
    Measurement,
    RefusalReason,
    ThresholdBelowFloor,
    materialise,
)

#: The planted adversary, borrowed verbatim from
#: tests/observability/test_langfuse_gate.py (INT-175) the way
#: tests/infra/test_siem_feed.py (INT-205) borrows it, so every PHI gate in the
#: tree agrees on what patient narrative looks like: B1 Turkish, spaces,
#: Turkish letters, and no identifier pattern to key off — a redactor would
#: pass it through untouched, which is the point. The boundary must refuse a
#: carrier, not scrub a string.
TURKISH_SYMPTOM = "Göğsümde iki gündür şiddetli bir ağrı var ve nefes almakta zorlanıyorum."

#: A second adversary carrying a Turkish name in an oblique case — the exact
#: shape files/10 §3 records Turkish NER missing (*Ahmet'in*, *Ayşe'ye*).
TURKISH_WITH_NAME = "iki gündür göğsümde baskı var, Ahmet Bey aradı"

WEEK_1 = "2026-08-03"
WEEK_2 = "2026-08-10"

#: A 32-byte test key. Fixture credentials are the point of tests; no key
#: material for any real signer exists in this repository.
TEST_KEY = b"int-172-test-signing-key--32bytes"


def _blob(value: object) -> str:
    """The whole structure as one searchable string, diacritics intact.

    ``EvidenceBundle.to_json`` is ASCII-escaped (it is the digest's canonical
    form), so a substring sweep over it alone would pass on an escaped
    sentence. Round-tripping through ``ensure_ascii=False`` puts the Turkish
    letters back before the sweep looks for them.
    """
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def _cohort(description: str = STEP_COVERAGE.cohort_description) -> Cohort:
    return Cohort(
        description=description,
        window_start=datetime(2026, 8, 3, tzinfo=UTC),
        window_end=datetime(2026, 8, 17, tzinfo=UTC),
    )


def _step_cells(*weeks: str, slot_id: str = "medication_adherence") -> tuple[Cell, ...]:
    return tuple(
        Cell(
            dimensions={"protocol_id": "base.intake", "slot_id": slot_id, "week_start": week},
            subjects=40,
            tenants=3,
            measures={"sessions_answered": 10},
        )
        for week in weeks
    )


def _steps(*weeks: str, slot_id: str = "medication_adherence") -> Measurement:
    return materialise(
        STEP_COVERAGE,
        _step_cells(*weeks, slot_id=slot_id),
        cohort=_cohort(),
        k=K_ANONYMITY_FLOOR,
    )


def _sessions(*weeks: str) -> Measurement:
    return materialise(
        SESSION_OUTCOMES,
        [
            Cell(
                dimensions={
                    "protocol_id": "base.intake",
                    "protocol_version": "1.4.0",
                    "week_start": week,
                },
                subjects=40,
                tenants=3,
                measures={"sessions": 40, "completed": 38, "cancelled": 2},
            )
            for week in weeks
        ],
        cohort=_cohort(SESSION_OUTCOMES.cohort_description),
        k=K_ANONYMITY_FLOOR,
    )


def _bundle(measurement: Measurement | None = None) -> EvidenceBundle:
    return EvidenceBundle.build(
        view=STEP_COVERAGE,
        measurements=(measurement if measurement is not None else _steps(WEEK_1, WEEK_2),),
        citations=(EvidenceSource.FILES_09_S4, EvidenceSource.CLAUDE_INVARIANT_12),
        k=K_ANONYMITY_FLOOR,
    )


def _signed(bundle: EvidenceBundle | None = None) -> SignedBundle:
    return sign_bundle(bundle or _bundle(), key=TEST_KEY, key_id="learning-dev")


def _proposal() -> Proposal:
    findings = inspect_step_coverage(
        sessions=_sessions(WEEK_1, WEEK_2), steps=_steps(WEEK_1, WEEK_2)
    )
    thresholds = PromotionThresholds(
        effect_size_floor=EffectSizeFloor(value=0.5, recorded_in=EvidenceSource.TEST_FIXTURE)
    )
    return propose(findings, thresholds=thresholds)[0]


def _complete(bundle: EvidenceBundle) -> EvidenceBundle:
    """The same bundle with every required check passed.

    Nothing in the package can produce this today — every producer named in
    ``REQUIRED_CHECKS`` is a later issue — so the completed shape is built here
    to prove the publisher's happy path exists and is reachable the moment the
    artefacts are.
    """
    import dataclasses

    return dataclasses.replace(
        bundle,
        checks=tuple(
            dataclasses.replace(check, status=CheckStatus.PASSED) for check in bundle.checks
        ),
    )


# --- the bundle is counts and citations -------------------------------------------


def test_a_bundle_carries_the_measurement_provenance_sentence() -> None:
    """Invariant 20: a figure is a measurement of a named cohort over a stated
    window. The bundle carries INT-171's own provenance line rather than
    restating the number as a property of the product."""
    payload = json.loads(_bundle().to_json())
    provenance = payload["measurements"][0]["provenance"]
    assert "Measured learning.step_coverage for cohort" in provenance
    assert "suppressed below k=10" in provenance


def test_every_string_in_a_bundle_is_an_id_an_enum_or_committed_prose() -> None:
    """The structural half of invariant 6.

    Free text has no carrier: dimension values came through INT-171's id-shape
    gate, citations are enum members, and the only prose is the view registry's
    own committed description.
    """
    payload = json.loads(_bundle().to_json())
    committed = {STEP_COVERAGE.cohort_description, STEP_COVERAGE.narrative_exclusion}

    def walk(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [s for k, v in value.items() for s in (*walk(k), *walk(v))]
        if isinstance(value, list):
            return [s for item in value for s in walk(item)]
        return []

    for text in walk(payload):
        if text in committed or text.startswith("Measured "):
            continue
        # everything else is an id, an enum member, an ISO instant or a citation
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 §_.:/+-]{0,127}", text), (
            f"a bundle string is neither an id, an enum member nor committed "
            f"registry prose: {text!r}"
        )


def test_a_planted_turkish_symptom_sentence_never_reaches_a_bundle() -> None:
    """The adversarial proof (invariant 6), at every surface a bundle touches.

    1. In a **dimension value** — INT-171's gate refuses the whole view, and
       the bundle re-runs that gate rather than trusting a ``Measurement``
       handed to it (a ``Measurement`` is a plain dataclass anyone can build).
    2. In the **cohort description** — the bundle accepts only the committed
       ``cohort_description`` of the view it names, byte for byte.
    3. Neither refusal echoes what it refused.
    4. Nothing that does build carries the sentence, a word of it, or a Turkish
       letter — checked on the decoded blob, not the ASCII-escaped one.
    """
    for planted in (TURKISH_SYMPTOM, TURKISH_WITH_NAME):
        # 1 + 3 — the sentence as a slot id
        poisoned = Measurement(
            view=STEP_COVERAGE.name,
            cohort=_cohort(),
            k=K_ANONYMITY_FLOOR,
            cells=(
                Cell(
                    dimensions={
                        "protocol_id": "base.intake",
                        "slot_id": planted,
                        "week_start": WEEK_1,
                    },
                    subjects=40,
                    tenants=3,
                    measures={"sessions_answered": 10},
                ),
            ),
        )
        with pytest.raises(KAnonymityRefusal) as refusal:
            EvidenceBundle.build(
                view=STEP_COVERAGE,
                measurements=(poisoned,),
                citations=(EvidenceSource.FILES_09_S4,),
                k=K_ANONYMITY_FLOOR,
            )
        assert refusal.value.reason is RefusalReason.DIMENSION_NOT_ID_SHAPED
        assert planted not in f"{refusal.value!r} {refusal.value}"

        # 2 + 3 — the sentence as a cohort description
        with pytest.raises(ValueError) as mismatch:
            EvidenceBundle.build(
                view=STEP_COVERAGE,
                measurements=(
                    Measurement(
                        view=STEP_COVERAGE.name,
                        cohort=_cohort(planted),
                        k=K_ANONYMITY_FLOOR,
                        cells=_step_cells(WEEK_1),
                    ),
                ),
                citations=(EvidenceSource.FILES_09_S4,),
                k=K_ANONYMITY_FLOOR,
            )
        assert planted not in f"{mismatch.value!r} {mismatch.value}"

    # 4 — the whole artefact chain that a human actually receives
    signed = _signed(_complete(_bundle()))
    request = build_pull_request(proposal=_proposal(), evidence=signed)
    surfaces = _blob(
        [
            json.loads(signed.bundle.to_json()),
            signed.digest,
            signed.signature.value,
            request.branch,
            request.title,
            request.body,
            json.loads(request.attachment),
        ]
    )
    for fragment in (
        TURKISH_SYMPTOM,
        TURKISH_WITH_NAME,
        "Göğsümde",
        "ağrı",
        "baskı",
        "Ahmet",
    ):
        assert fragment not in surfaces
    for turkish_letter in "ğşıİöüçĞŞÖÜÇ":
        assert turkish_letter not in surfaces


def test_a_bundle_refuses_a_measurement_from_another_view() -> None:
    with pytest.raises(ValueError, match="learning.step_coverage"):
        EvidenceBundle.build(
            view=SESSION_OUTCOMES,
            measurements=(_steps(WEEK_1),),
            citations=(EvidenceSource.FILES_09_S4,),
            k=K_ANONYMITY_FLOOR,
        )


def test_a_bundle_needs_at_least_one_citation_and_one_measurement() -> None:
    with pytest.raises(ValueError, match="citation"):
        EvidenceBundle.build(
            view=STEP_COVERAGE,
            measurements=(_steps(WEEK_1),),
            citations=(),
            k=K_ANONYMITY_FLOOR,
        )
    with pytest.raises(ValueError, match="demonstrates nothing"):
        EvidenceBundle.build(
            view=STEP_COVERAGE,
            measurements=(),
            citations=(EvidenceSource.FILES_09_S4,),
            k=K_ANONYMITY_FLOOR,
        )


def test_a_bundle_inherits_the_k_floor_and_cannot_lower_it() -> None:
    with pytest.raises(ThresholdBelowFloor):
        EvidenceBundle.build(
            view=STEP_COVERAGE,
            measurements=(_steps(WEEK_1),),
            citations=(EvidenceSource.FILES_09_S4,),
            k=K_ANONYMITY_FLOOR - 1,
        )


def test_a_thin_cell_refuses_on_the_way_into_a_bundle() -> None:
    """A ``Measurement`` is a plain dataclass; the bundle re-gates it."""
    thin = Measurement(
        view=STEP_COVERAGE.name,
        cohort=_cohort(),
        k=K_ANONYMITY_FLOOR,
        cells=(
            Cell(
                dimensions={
                    "protocol_id": "base.intake",
                    "slot_id": "medication_adherence",
                    "week_start": WEEK_1,
                },
                subjects=3,
                tenants=1,
                measures={"sessions_answered": 3},
            ),
        ),
    )
    with pytest.raises(KAnonymityRefusal) as refusal:
        EvidenceBundle.build(
            view=STEP_COVERAGE,
            measurements=(thin,),
            citations=(EvidenceSource.FILES_09_S4,),
            k=K_ANONYMITY_FLOOR,
        )
    assert refusal.value.reason is RefusalReason.BELOW_K


# --- the required checks fail closed ----------------------------------------------


def test_the_required_checks_are_the_files_09_list_minus_the_exemplars() -> None:
    from intake_learning.evidence import REQUIRED_CHECKS

    assert {check.name for check in REQUIRED_CHECKS} == {
        "simulator_run",
        "triage_goldens",
        "latency_harness",
        "shadow_replay",
        "langfuse_experiment",
    }
    assert not any("exemplar" in check.name for check in REQUIRED_CHECKS)


def test_a_fresh_bundle_is_incomplete_because_no_check_can_pass_yet() -> None:
    bundle = _bundle()
    assert bundle.is_complete is False
    assert {check.status for check in bundle.checks} == {CheckStatus.NOT_AVAILABLE}
    assert set(bundle.unmet_checks) == {check.name for check in bundle.checks}


def test_every_unavailable_check_names_the_issue_that_supplies_it() -> None:
    """Invariant 17: a missing dependency is a named blocker, never a fake."""
    from intake_learning.evidence import REQUIRED_CHECKS

    for check in REQUIRED_CHECKS:
        assert re.fullmatch(r"INT-\d{3}", check.supplied_by), check.name


# --- signing ----------------------------------------------------------------------


def test_a_signed_bundle_verifies_against_its_key() -> None:
    signed = _signed()
    assert verify_bundle(signed, key=TEST_KEY) is True
    assert signed.signature.key_id == "learning-dev"
    assert signed.signature.algorithm == "hmac-sha256"
    assert len(signed.digest) == 64
    assert len(signed.signature.value) == 64


def test_a_tampered_digest_fails_verification() -> None:
    import dataclasses

    signed = _signed()
    assert verify_bundle(dataclasses.replace(signed, digest="0" * 64), key=TEST_KEY) is False


def test_a_swapped_bundle_under_a_valid_digest_fails_verification() -> None:
    """Both halves of the chain matter: MAC over digest, digest over bundle."""
    import dataclasses

    signed = _signed(_bundle(_steps(WEEK_1, WEEK_2)))
    swapped = dataclasses.replace(signed, bundle=_bundle(_steps(WEEK_1)))
    assert verify_bundle(swapped, key=TEST_KEY) is False


def test_a_different_key_fails_verification() -> None:
    assert verify_bundle(_signed(), key=b"another-key-of-exactly-32-bytes!!") is False


def test_an_unknown_algorithm_fails_verification() -> None:
    import dataclasses

    signed = _signed()
    forged = dataclasses.replace(
        signed, signature=dataclasses.replace(signed.signature, algorithm="none")
    )
    assert verify_bundle(forged, key=TEST_KEY) is False


def test_signing_fails_closed_without_a_usable_key() -> None:
    with pytest.raises(SigningKeyUnavailable, match="32 bytes"):
        sign_bundle(_bundle(), key=b"short", key_id="learning-dev")
    with pytest.raises(SigningKeyUnavailable, match="key id"):
        sign_bundle(_bundle(), key=TEST_KEY, key_id="  ")


def test_the_refusal_never_echoes_the_key() -> None:
    secret = b"a-secret-that-must-not-appear-in-a-message"
    with pytest.raises(SigningKeyUnavailable) as refusal:
        sign_bundle(_bundle(), key=secret, key_id="")
    assert "secret" not in f"{refusal.value!r} {refusal.value}"


def test_the_digest_is_over_a_canonical_serialisation() -> None:
    """The same measurement bundled twice hashes the same: key order and
    whitespace are not part of the claim being signed. Different cells do not.

    ``Measurement.measured_at`` is inside the digest on purpose, so two reads
    of the same view at different instants are two different claims — which is
    why this test bundles one measurement twice rather than reading twice.
    """
    measurement = _steps(WEEK_1, WEEK_2)
    assert digest_of(_bundle(measurement)) == digest_of(_bundle(measurement))
    assert digest_of(_bundle(measurement)) != digest_of(_bundle(_steps(WEEK_1)))


# --- the PR bot: open, never merge ------------------------------------------------


def test_the_publisher_refuses_a_bundle_whose_required_checks_are_unmet() -> None:
    with pytest.raises(IncompleteEvidence) as refusal:
        build_pull_request(proposal=_proposal(), evidence=_signed())
    message = str(refusal.value)
    for name in ("simulator_run", "triage_goldens", "langfuse_experiment"):
        assert name in message
    assert "invariant 17" in message


def test_a_pull_request_request_is_data_and_carries_no_merge_affordance() -> None:
    """files/09 §7: the bot "can open but not merge".

    The request type has no merge field, no merge method and no dispatcher in
    this repository: :class:`ProposalPublisher` is a Protocol with no concrete
    implementation, because the bot identity is not a value anyone has supplied
    (recorded in docs/evidence/INT-172.md).
    """
    from dataclasses import fields

    assert {f.name for f in fields(PullRequestRequest)} == {
        "branch",
        "title",
        "body",
        "attachment",
        "digest",
    }
    for surface in (PullRequestRequest, ProposalPublisher):
        assert not any(
            token in attr.lower()
            for attr in dir(surface)
            for token in ("merge", "approve", "push", "force")
        )


def test_no_concrete_publisher_ships_because_the_bot_identity_is_unset() -> None:
    from intake_learning import publisher

    concrete = [
        name
        for name in dir(publisher)
        if name.endswith("Publisher") and name != "ProposalPublisher"
    ]
    assert concrete == [], (
        "a concrete publisher needs a PR-bot identity nobody has issued, and an "
        "HTTP client this package's import closure forbids; the mechanism is "
        f"wired and the credential is empty: {concrete}"
    )


def test_a_complete_bundle_renders_an_open_not_merge_request() -> None:
    bundle = _complete(_bundle())
    request = build_pull_request(proposal=_proposal(), evidence=_signed(bundle))
    assert request.branch.startswith("int-172/learning-step-skip-rate-base-intake-")
    assert re.fullmatch(r"[A-Za-z0-9/_.-]+", request.branch)
    assert "QuestionWording" in request.title
    assert "This is a **proposal**" in request.body
    assert "cannot merge it" in request.body
    assert "invariant 12" in request.body
    # invariant 20: the figures arrive as measurements with their cohort
    assert "Measured learning.step_coverage for cohort" in request.body
    assert "files/09 §4" in request.body
    # the attachment is the canonical bundle, byte for byte
    assert request.attachment == bundle.to_json()


def test_the_pr_body_reports_counts_and_never_a_bare_rate() -> None:
    """Invariant 20 again, at the surface a human reads: numerator and
    denominator, never a percentage detached from its population."""
    body = build_pull_request(proposal=_proposal(), evidence=_signed(_complete(_bundle()))).body
    assert "| week | numerator | denominator | subjects | clinics |" in body
    assert "| `2026-08-03` | 30 | 40 | 40 | 3 |" in body
    assert "%" not in body


def test_the_pr_body_carries_no_turkish_letter() -> None:
    """The terminal surface. Whatever else a PR body holds, it cannot hold
    Turkish narrative — and the two non-ASCII characters it does hold are
    accounted for: the section mark from the blueprint's own citation form
    (``files/09 §4``) and the em-dash inside the analytics registry's
    committed ``narrative_exclusion`` prose."""
    body = build_pull_request(proposal=_proposal(), evidence=_signed(_complete(_bundle()))).body
    non_ascii = sorted({character for character in body if ord(character) > 127})
    assert non_ascii == sorted(("—", "§")), f"unexpected non-ASCII in a PR body: {non_ascii}"
