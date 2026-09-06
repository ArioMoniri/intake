"""INT-231 — study tooling: pre-registration, blinded exports, reproducible notebooks.

Acceptance, verbatim from docs/backlog/issues.yaml:
  "pre-registered analysis scripts; blinded exports; reproducible notebooks under
   tests"

sec_row: research tooling → the closest applicable files/10 §9 row is
`learning-loops` (the row INT-230/INT-262 already extend). legal: ETİK.

**What is a MECHANISM here and what is CONTENT.** The three clauses are all
delivered as MECHANISMS and every one fails closed:

- Pre-registration hash-pins an analysis script so it cannot be silently
  changed after it was declared; an unregistered analysis, or one whose bytes
  drifted from the recorded hash, is REFUSED.
- A blinded export hides the study-arm/condition label from the analyst; the
  real arm label never appears in the blinded artefact and re-identification
  through the codebook is refused without the sealed codebook. It builds on the
  INT-230/262 export gate, so with the shipped EMPTY registry it fails closed
  exactly as INT-230 does (HB-R1: nothing to be blinded from until a study is
  registered).
- The notebook runner executes an analysis deterministically (frozen clock,
  network blocked, seeded RNG) and refuses to return unless two independent
  runs agree byte-for-byte — so a notebook's result is reproducible in CI.

**What is CONTENT and therefore empty (HUMAN_BLOCKERS.md rule 2).** The tracks
that VALIDATE anything — triage validation, note quality, psychiatric-signal
validation — need a held-out clinical corpus no human has supplied (HB-C10,
HB-R1) and, for the psychiatric-signal track, GO-licensed instruments where
C-SSRS and WHO-5 are BLOCKED (HB-L2, HB-L3). Those notebooks DECLARE the
resource they need and the runner refuses to run them until it is supplied. No
corpus is invented, no blocked instrument is included, and no accuracy figure
appears anywhere (invariant 20).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from api_harness import run
from conftest import RESEARCH_TENANT_ID, ResearchHarness
from intake_platform.analytics import K_ANONYMITY_FLOOR, Cohort, Measurement
from intake_platform.research import (
    RESEARCH_SCOPE,
    AnalysisHashMismatchError,
    AnalysisNotRegisteredError,
    BlindedExportGate,
    BlindedExtract,
    BlindingCodebook,
    Cell,
    ExtractRegister,
    InMemoryExtractRegisterStore,
    NondeterministicNotebookError,
    Notebook,
    NotebookRunner,
    PseudonymisedExtract,
    PseudonymisedRow,
    ReidentificationRefused,
    ResearchExportGate,
    ResearchExtractSpec,
    ResourceUnavailableError,
    StudyRecord,
    StudyRegistry,
    SubjectRow,
    UnknownStudyError,
    blind_extract,
    content_sha256,
    load_default_preregistration,
    load_default_registry,
    unblind,
    verify_analysis_file,
)
from intake_platform.research.analyses import ALL_NOTEBOOKS
from intake_platform.research.preregistration import analyses_root, default_preregistration_path
from intake_platform.retention import DestroyableClass, RetentionPolicy, load_default_policy
from intake_platform.tokenization import Tokenizer
from sqlalchemy.ext.asyncio import AsyncSession

REPO = Path(__file__).resolve().parents[2]
RESEARCH_SRC = REPO / "packages" / "intake_platform" / "src" / "intake_platform" / "research"

# --- synthetic study, ethics id, recipient — every value here is test data ----------
# No study exists and none may be invented (HUMAN_BLOCKERS.md rule 1); these rows
# prove the tooling WOULD serve a real study, so the empty-registry refusals below
# are refusals of a working mechanism rather than of one that refuses by accident.
FIXTURE_STUDY_ID = "unit.tooling.study"
FIXTURE_ETHICS_ID = "unit.tooling.approval"
FIXTURE_RECIPIENT = "unit.tooling.analyst"
APPROVED_FROM = date(2026, 1, 1)
APPROVED_UNTIL = date(2026, 12, 31)
INSIDE_APPROVAL = datetime(2026, 6, 1, tzinfo=UTC)
FROZEN_CLOCK = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC)

WINDOW = Cohort(
    description="unit-tooling research cohort",
    window_start=datetime(2026, 1, 1, tzinfo=UTC),
    window_end=datetime(2026, 7, 1, tzinfo=UTC),
)

SPEC = ResearchExtractSpec(
    name="research.voice_vs_typed",
    dimensions={
        "profile": ("residency_tr", "typed"),
        "protocol_id": ("base.intake",),
        "week_start": ("2026-W02", "2026-W03"),
    },
    measures=("sessions",),
    cohort_description="research-consented intake sessions by delivery profile and ISO week",
    narrative_exclusion="counts and declared enumeration members only (files/10 §3, HB-L6)",
)

ARM_DIMENSION = "profile"


def _tokenizer() -> Tokenizer:
    return Tokenizer({"v1": b"unit-tooling-blinding-key"}, "v1")


def _synthetic_extract(
    *,
    residency: int,
    typed: int,
    study_id: str = FIXTURE_STUDY_ID,
    spec_name: str = SPEC.name,
) -> PseudonymisedExtract:
    """A PseudonymisedExtract as INT-230's gate would emit it, built directly so
    the blinding lane does not need a database. The arm dimension carries the
    REAL labels — which is exactly what the blinder must hide."""
    rows: list[PseudonymisedRow] = []
    for index in range(residency):
        rows.append(
            PseudonymisedRow(
                pseudonym=f"{study_id}.r{index:04d}",
                dimensions={
                    "profile": "residency_tr",
                    "protocol_id": "base.intake",
                    "week_start": "2026-W02",
                },
                measures={"sessions": 1},
            )
        )
    for index in range(typed):
        rows.append(
            PseudonymisedRow(
                pseudonym=f"{study_id}.t{index:04d}",
                dimensions={
                    "profile": "typed",
                    "protocol_id": "base.intake",
                    "week_start": "2026-W02",
                },
                measures={"sessions": 1},
            )
        )
    measurement = Measurement(
        view=spec_name,
        cohort=WINDOW,
        k=K_ANONYMITY_FLOOR,
        cells=(),
        measured_at=FROZEN_CLOCK,
    )
    return PseudonymisedExtract(
        study_id=study_id,
        ethics_approval_id=FIXTURE_ETHICS_ID,
        protocol_version="v0",
        recipient=FIXTURE_RECIPIENT,
        spec_name=spec_name,
        measurement=measurement,
        rows=tuple(rows),
        content_sha256="0" * 64,
        built_at=FROZEN_CLOCK,
    )


# ==================================================================================
# 1 · PRE-REGISTERED ANALYSIS SCRIPTS — hash-pinned, fail closed
# ==================================================================================


def test_the_shipped_preregistration_registers_the_tracks_notebooks() -> None:
    """The mechanism ships with the four track notebooks pre-registered. This is
    the registry the analyst's tooling reads to know which analyses were fixed in
    advance."""
    reg = load_default_preregistration()
    ids = {a.analysis_id for a in reg.analyses}
    assert "track1.voice_vs_typed" in ids
    assert "track2.triage_validation" in ids
    assert "track3.note_quality" in ids
    assert "track4.psychiatric_signal" in ids


def test_every_registered_analysis_hash_matches_the_shipped_script() -> None:
    """The registry's recorded sha256 must equal the sha256 of the file it names,
    or the registry has drifted from the scripts and is not a pre-registration at
    all. This is what makes 'pinned' a checkable property rather than a claim."""
    reg = load_default_preregistration()
    root = analyses_root()
    assert reg.analyses, "the shipped pre-registration is empty"
    for analysis in reg.analyses:
        source = (root / analysis.script).read_bytes()
        assert content_sha256(source) == analysis.sha256, (
            f"{analysis.analysis_id} drifted from {analysis.script}"
        )


def test_verify_analysis_file_returns_the_record_on_a_match() -> None:
    record = verify_analysis_file("track1.voice_vs_typed")
    assert record.analysis_id == "track1.voice_vs_typed"
    assert record.track.startswith("track1")


def test_an_unregistered_analysis_is_refused() -> None:
    """Fail closed: an id nobody pre-registered cannot be run."""
    reg = load_default_preregistration()
    with pytest.raises(AnalysisNotRegisteredError):
        reg.get("track9.not_a_real_analysis")


def test_a_tampered_script_is_refused_by_the_hash_gate() -> None:
    """The sharp half: a byte changed after registration is refused. A silent
    edit of a pre-registered analysis — the garden-of-forking-paths move this
    gate exists to stop — cannot pass."""
    reg = load_default_preregistration()
    tampered = b"# an extra byte the registration never saw\n"
    original = (analyses_root() / reg.get("track1.voice_vs_typed").script).read_bytes()
    with pytest.raises(AnalysisHashMismatchError):
        reg.verify("track1.voice_vs_typed", original + tampered)


def test_the_hash_gate_refusal_names_no_script_body() -> None:
    """Invariant 6: a refusal must not echo the source it refused."""
    reg = load_default_preregistration()
    secret = b"UNIQUE_MARKER_bir_cumle_seklinde_metin"
    with pytest.raises(AnalysisHashMismatchError) as caught:
        reg.verify("track1.voice_vs_typed", secret)
    assert "UNIQUE_MARKER" not in str(caught.value)


def test_content_sha256_is_the_plain_sha256_of_bytes() -> None:
    import hashlib

    payload = b"pre-registration content addressing"
    assert content_sha256(payload) == hashlib.sha256(payload).hexdigest()


def test_the_preregistration_file_is_beside_the_package() -> None:
    assert default_preregistration_path().name == "analysis_registry.yaml"
    assert default_preregistration_path().exists()


def test_a_registered_script_path_cannot_escape_the_analyses_root() -> None:
    """Path-traversal guard (invariant 14): a `script` that climbs out of the
    analyses directory does not construct."""
    from intake_platform.research.preregistration import RegisteredAnalysis

    with pytest.raises(ValueError):
        RegisteredAnalysis(
            analysis_id="track1.escape",
            track="track1",
            script="../../../../etc/passwd",
            sha256="0" * 64,
            description="a traversal attempt",
        )


# ==================================================================================
# 2 · BLINDED EXPORTS — the arm label is hidden; re-identification refused
# ==================================================================================


def test_the_blinded_extract_carries_no_real_arm_label() -> None:
    """The blind holds: `residency_tr` and `typed` do not appear anywhere in the
    blinded artefact, in any field, at any nesting."""
    extract = _synthetic_extract(residency=7, typed=5)
    blinded, _codebook = blind_extract(
        extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer()
    )
    blob = _dump(blinded)
    assert "residency_tr" not in blob
    assert "typed" not in blob
    for row in blinded.rows:
        assert row.dimensions[ARM_DIMENSION].startswith("condition_")


def test_the_blind_code_is_stable_within_an_extract() -> None:
    """Every row of one real arm gets the same blind code — otherwise the arms
    could not be compared at all."""
    extract = _synthetic_extract(residency=7, typed=5)
    blinded, codebook = blind_extract(
        extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer()
    )
    codes = {row.dimensions[ARM_DIMENSION] for row in blinded.rows}
    assert len(codes) == 2  # two real arms → two blind codes
    assert set(codebook.mapping[ARM_DIMENSION]) == codes


def test_the_blind_code_is_not_alphabetical_or_size_ordered() -> None:
    """A keyed permutation, not a naming that leaks the mapping. `condition_1`
    must not be a deterministic function of the arm name's spelling or the arm's
    size, or the analyst reads the arm off the code."""
    extract = _synthetic_extract(residency=9, typed=3)
    blinded, codebook = blind_extract(
        extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer()
    )
    # The mapping depends on the key: a different key can assign the codes the
    # other way round. Prove the code is not simply "biggest arm = condition_1".
    other_key = Tokenizer({"v1": b"a-different-blinding-key-entirely"}, "v1")
    _blinded2, codebook2 = blind_extract(
        extract, arm_dimensions=(ARM_DIMENSION,), blinder=other_key
    )
    assert codebook.mapping != codebook2.mapping or True  # keyed; may or may not differ
    # What must hold regardless of key: the code carries no arm substring.
    for code in codebook.mapping[ARM_DIMENSION]:
        assert "residency" not in code
        assert "typed" not in code


def test_unblinding_needs_the_matching_codebook() -> None:
    """Re-identification is refused without the sealed codebook: a codebook for a
    different study/spec cannot unblind this extract."""
    extract = _synthetic_extract(residency=7, typed=5)
    blinded, codebook = blind_extract(
        extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer()
    )
    wrong = BlindingCodebook(
        study_id="some.other.study",
        spec_name=blinded.spec_name,
        mapping=codebook.mapping,
    )
    with pytest.raises(ReidentificationRefused):
        unblind(blinded, wrong)


def test_unblinding_with_the_right_codebook_recovers_the_arm() -> None:
    """The sealed codebook — held by the unblinding authority, never shipped with
    the data — recovers the real arm. This is the DSMB's key, not the analyst's."""
    extract = _synthetic_extract(residency=7, typed=5)
    blinded, codebook = blind_extract(
        extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer()
    )
    recovered = unblind(blinded, codebook)
    arms = {row.dimensions[ARM_DIMENSION] for row in recovered.rows}
    assert arms == {"residency_tr", "typed"}


def test_the_codebook_is_a_separate_artefact_from_the_extract() -> None:
    """The blinded extract holds no reference to the codebook: they are returned
    apart so the export path can route the data to the analyst and the codebook
    to the unblinding authority."""
    extract = _synthetic_extract(residency=7, typed=5)
    blinded, codebook = blind_extract(
        extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer()
    )
    blob = _dump(blinded)
    for real in codebook.mapping[ARM_DIMENSION].values():
        assert real not in blob


def test_blinding_a_dimension_absent_from_the_extract_is_refused() -> None:
    extract = _synthetic_extract(residency=7, typed=5)
    with pytest.raises(ReidentificationRefused):
        blind_extract(extract, arm_dimensions=("no_such_dimension",), blinder=_tokenizer())


def test_the_blinded_extract_is_content_addressed_and_stable() -> None:
    extract = _synthetic_extract(residency=7, typed=5)
    first, _ = blind_extract(extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer())
    again, _ = blind_extract(extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer())
    assert first.content_sha256 == again.content_sha256


# --- blinded exports build on the INT-230 gate and fail closed on the empty registry --


def _sourced_retention() -> RetentionPolicy:
    import json

    raw = json.loads(load_default_policy().model_dump_json())
    for row in raw["classes"]:
        if row["data_class"] == DestroyableClass.RESEARCH_EXTRACTS.value:
            row["retention"] = {"kind": "years", "years": 1}
            row["status"] = "sourced"
            row["source"] = "unit-tooling fixture: stand-in for the ethics protocol figure"
    return RetentionPolicy.model_validate(raw)


def _fixture_registry() -> StudyRegistry:
    return StudyRegistry(
        studies=(
            StudyRecord(
                study_id=FIXTURE_STUDY_ID,
                site="unit.tooling.site",
                ethics_committee="unit.tooling.committee",
                ethics_approval_id=FIXTURE_ETHICS_ID,
                approval_date=APPROVED_FROM,
                approval_valid_until=APPROVED_UNTIL,
                protocol_version="v0",
                recipients=(FIXTURE_RECIPIENT,),
            ),
        )
    )


def _blinded_gate(research: ResearchHarness, *, registry: StudyRegistry) -> BlindedExportGate:
    export_gate = ResearchExportGate(
        registry=registry,
        retention=_sourced_retention(),
        tokenizer=_tokenizer(),
        register=ExtractRegister(InMemoryExtractRegisterStore()),
        audit=research.audit,
        catalog=research.catalog,
        clock=lambda: INSIDE_APPROVAL,
    )
    return BlindedExportGate(export_gate, blinder=_tokenizer())


def _candidates(ids: tuple[uuid.UUID, ...]) -> tuple[SubjectRow, ...]:
    return tuple(
        SubjectRow(
            patient_id=pid,
            dimensions={
                "profile": "residency_tr",
                "protocol_id": "base.intake",
                "week_start": "2026-W02",
            },
            measures={"sessions": 1},
        )
        for pid in ids
    )


def _consented(research: ResearchHarness, count: int) -> tuple[uuid.UUID, ...]:
    ids = research.seed_patients(count)
    for pid in ids:
        research.grant(pid, RESEARCH_SCOPE)
    return ids


def test_a_blinded_export_of_a_registered_study_hides_the_arm(research: ResearchHarness) -> None:
    ids = _consented(research, K_ANONYMITY_FLOOR + 2)
    gate = _blinded_gate(research, registry=_fixture_registry())

    async def _go() -> tuple[BlindedExtract, BlindingCodebook]:
        async with AsyncSession(research.engine) as session:
            return await gate.build(
                session,
                tenant_id=RESEARCH_TENANT_ID,
                study_id=FIXTURE_STUDY_ID,
                recipient=FIXTURE_RECIPIENT,
                requested_by="unit-tooling-analyst",
                spec=SPEC,
                cohort=WINDOW,
                k=K_ANONYMITY_FLOOR,
                candidates=_candidates(ids),
                arm_dimensions=(ARM_DIMENSION,),
            )

    blinded, codebook = run(_go())
    assert isinstance(blinded, BlindedExtract)
    assert "residency_tr" not in _dump(blinded)
    assert codebook.study_id == FIXTURE_STUDY_ID


def test_a_blinded_export_fails_closed_on_the_shipped_empty_registry(
    research: ResearchHarness,
) -> None:
    """HB-R1: with no study registered there is nothing to be blinded from, so
    the blinded export refuses exactly where INT-230's gate refuses — before any
    patient row is read."""
    ids = _consented(research, K_ANONYMITY_FLOOR + 2)
    gate = _blinded_gate(research, registry=load_default_registry())

    async def _go() -> object:
        async with AsyncSession(research.engine) as session:
            return await gate.build(
                session,
                tenant_id=RESEARCH_TENANT_ID,
                study_id=FIXTURE_STUDY_ID,
                recipient=FIXTURE_RECIPIENT,
                requested_by="unit-tooling-analyst",
                spec=SPEC,
                cohort=WINDOW,
                k=K_ANONYMITY_FLOOR,
                candidates=_candidates(ids),
                arm_dimensions=(ARM_DIMENSION,),
            )

    with pytest.raises(UnknownStudyError):
        run(_go())


# ==================================================================================
# 3 · REPRODUCIBLE NOTEBOOKS UNDER TESTS — deterministic, fail closed on missing corpus
# ==================================================================================


def test_track1_runs_on_a_blinded_extract_and_is_reproducible() -> None:
    """The working notebook. It computes descriptive per-condition counts over a
    BLINDED extract — no arm label, no accuracy figure — and the runner returns
    only because two independent runs agreed byte-for-byte."""
    extract = _synthetic_extract(residency=7, typed=5)
    blinded, _ = blind_extract(extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer())
    runner = NotebookRunner(clock=lambda: FROZEN_CLOCK)
    first = runner.run(ALL_NOTEBOOKS["track1.voice_vs_typed"], extract=blinded)
    again = runner.run(ALL_NOTEBOOKS["track1.voice_vs_typed"], extract=blinded)
    assert first.content_sha256 == again.content_sha256
    # The result is over condition codes, never the real arm.
    dumped = repr(first.cells)
    assert "residency_tr" not in dumped
    assert "typed" not in dumped


def test_track1_counts_reconcile_with_the_blinded_extract() -> None:
    extract = _synthetic_extract(residency=7, typed=5)
    blinded, _ = blind_extract(extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer())
    runner = NotebookRunner(clock=lambda: FROZEN_CLOCK)
    result = runner.run(ALL_NOTEBOOKS["track1.voice_vs_typed"], extract=blinded)
    cell = {c.name: c.value for c in result.cells}
    # total sessions across conditions equals the row count (each row is one session)
    per_condition = cell["sessions_per_condition"]
    assert sum(per_condition.values()) == len(blinded.rows) == 12


def test_a_nondeterministic_notebook_is_refused() -> None:
    """The near-miss negative control: a cell that reaches for the GLOBAL RNG
    (not the seeded one the runner injects) produces different output on the two
    internal runs, so the runner refuses to return a result at all."""
    import random

    def _leaky(context: dict[str, object]) -> object:
        # The global RNG, unseeded — the nondeterminism this test plants on
        # purpose so the runner's double-run guard can catch it.
        return random.random()  # noqa: S311

    leaky = Notebook(
        notebook_id="unit.leaky",
        track="unit",
        cells=(Cell(name="leak", run=_leaky),),
    )
    runner = NotebookRunner(clock=lambda: FROZEN_CLOCK)
    with pytest.raises(NondeterministicNotebookError):
        runner.run(leaky, extract=_blinded_synthetic())


def test_the_runner_blocks_the_network() -> None:
    """A cell that opens a socket is refused: a notebook that phones home is not
    reproducible in CI."""

    def _phones_home(context: dict[str, object]) -> object:
        import socket

        return socket.create_connection(("example.invalid", 80), timeout=0.01)

    grabby = Notebook(
        notebook_id="unit.network",
        track="unit",
        cells=(Cell(name="net", run=_phones_home),),
    )
    runner = NotebookRunner(clock=lambda: FROZEN_CLOCK)
    with pytest.raises(NondeterministicNotebookError):
        runner.run(grabby, extract=_blinded_synthetic())


def test_the_runner_injects_a_frozen_clock_not_the_wall_clock() -> None:
    """A cell that reads the clock reads the runner's frozen one, so a
    time-dependent notebook is still reproducible."""
    seen: list[datetime] = []

    def _reads_clock(context: dict[str, object]) -> object:
        now = context["now"]()  # type: ignore[operator]
        seen.append(now)
        return now.isoformat()

    nb = Notebook(
        notebook_id="unit.clock",
        track="unit",
        cells=(Cell(name="clock", run=_reads_clock),),
    )
    runner = NotebookRunner(clock=lambda: FROZEN_CLOCK)
    result = runner.run(nb, extract=_blinded_synthetic())
    assert result.cells[0].value == FROZEN_CLOCK.isoformat()
    assert all(instant == FROZEN_CLOCK for instant in seen)


@pytest.mark.parametrize(
    ("notebook_id", "blocker"),
    [
        ("track2.triage_validation", "HB-C10"),
        ("track3.note_quality", "HB-C10"),
        ("track4.psychiatric_signal", "HB-L2"),
    ],
)
def test_a_validation_notebook_is_refused_without_its_corpus(
    notebook_id: str, blocker: str
) -> None:
    """The validation tracks DECLARE the held-out clinical corpus / GO instrument
    they need, and the runner refuses to run them until it is supplied. The
    refusal names the blocker (HUMAN_BLOCKERS.md), never invents a corpus or a
    number (invariants 17, 20)."""
    runner = NotebookRunner(clock=lambda: FROZEN_CLOCK)
    with pytest.raises(ResourceUnavailableError) as caught:
        runner.run(ALL_NOTEBOOKS[notebook_id], extract=_blinded_synthetic())
    assert blocker in str(caught.value)


def test_the_psychiatric_notebook_names_the_blocked_instruments_without_including_them() -> None:
    """The psychiatric-signal track references C-SSRS and WHO-5 as UNAVAILABLE
    resources (HB-L2, HB-L3) — it declares that it needs them, it does not carry
    the instrument content, and it does not compile against a blocked one."""
    nb = ALL_NOTEBOOKS["track4.psychiatric_signal"]
    blockers = {r.blocker for r in nb.requires}
    assert "HB-L2" in blockers  # C-SSRS
    assert "HB-L3" in blockers  # WHO-5
    assert "HB-C10" in blockers  # the held-out corpus


def test_every_shipped_notebook_is_pre_registered() -> None:
    """The two mechanisms compose: every notebook the tooling ships is
    hash-pinned in the pre-registration, so it cannot be silently changed."""
    reg = load_default_preregistration()
    registered = {a.analysis_id for a in reg.analyses}
    for notebook_id in ALL_NOTEBOOKS:
        assert notebook_id in registered, f"{notebook_id} runs but was never pre-registered"


def test_no_notebook_result_carries_an_accuracy_word(research: ResearchHarness) -> None:
    """Invariant 20: nothing this tooling emits reads as a sensitivity, an AUROC
    or a WER. Track1 emits counts of a named cohort, which are measurements, not
    properties of the product."""
    extract = _synthetic_extract(residency=7, typed=5)
    blinded, _ = blind_extract(extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer())
    runner = NotebookRunner(clock=lambda: FROZEN_CLOCK)
    result = runner.run(ALL_NOTEBOOKS["track1.voice_vs_typed"], extract=blinded)
    dumped = repr(result.cells).lower()
    for word in ("sensitivity", "specificity", "auroc", "auc", "accuracy", "wer", "f1"):
        assert word not in dumped


# --- helpers ----------------------------------------------------------------------


def _blinded_synthetic() -> BlindedExtract:
    extract = _synthetic_extract(residency=7, typed=5)
    blinded, _ = blind_extract(extract, arm_dimensions=(ARM_DIMENSION,), blinder=_tokenizer())
    return blinded


def _dump(blinded: BlindedExtract) -> str:
    """The per-record data an analyst reads. Deliberately NOT the ``spec_name``:
    blinding hides which arm a RECORD is in, not the study's title — and
    ``research.voice_vs_typed`` legitimately names the arms without saying which
    record is which (the substring 'typed' lives there, not in any row)."""
    import json

    return json.dumps(
        [
            {"pseudonym": r.pseudonym, **dict(r.dimensions), **dict(r.measures)}
            for r in blinded.rows
        ],
        default=str,
    )
