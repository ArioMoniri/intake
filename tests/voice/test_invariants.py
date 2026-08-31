"""INT-094 — one place that asserts CLAUDE.md invariants 1–11, and the harness.

Acceptance, verbatim from ``docs/backlog/issues.yaml``:

    "all invariant tests incl. lanes-stalled-30s; harness reports per-turn
    budgets per profile"

**This issue is mostly a consolidation, and saying so is the point.** Most of
the eleven were already proved before it started — by INT-091 (six tools,
never-awaits, insertion window, PolicyGuard), INT-092 (FIFO / one in flight),
INT-093 (the RED path), INT-096 (typed parity), INT-110 (lane isolation,
including the *lanes stalled 30 s* test this acceptance names), INT-082 (the
headless simulator) and the protocols, security and CI suites. Re-running
their assertions here under new names would be theatre, so this module does
one of exactly two things per invariant:

- **cites** the test that already holds it, by node id, and then proves the
  citation is real — the function is defined in that file, it carries no
  disabling marker, and ``pytest --collect-only`` still collects it. A citation that
  rots is a failure here, which is what makes a reference worth as much as a
  copy; and
- **adds** the assertion nothing in the repository makes, each with its own
  near-miss negative control.

Every entry also names a **near-miss control** — the test that proves the gate
can fail — whether that control is new here or already lives in the cited
suite. ``test_every_invariant_names_a_near_miss_control`` refuses an entry
without one.

**What this module does not claim.** Invariant 3's *mlocked*, *core dump* and
*swap page* clauses are process-level controls specified in files/10 §3 and
numbered there as invariants 16–19 and 28. Nothing in this repository asserts
them yet — not here, not in ``tests/lanes``, not in
``tests/voice/test_audio_retention_guard.py``. They are recorded in
:data:`INVARIANTS` as ``not_covered_here`` rather than implied, and repeated
in docs/evidence/INT-094.md.

**Everything timed here runs on INT-091's ``FakeClock``.** A wall-clock
latency assertion in CI is a flake, and this repository has already paid for
one (INT-264). No test in this module reads a wall clock, and the harness
reports virtual milliseconds only.
"""

from __future__ import annotations

import ast
import enum
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from clinical_schemas.triage import (
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_voice_runtime.budgets import (
    TURN_BUDGETS,
    Bound,
    NotALatencyMeasurement,
    TurnBudget,
    TurnBudgetReport,
    TurnKind,
    TurnObservation,
    UnsetReason,
    budget_for,
)
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import NextStep, Step, StepKind
from intake_voice_runtime.talker.delivery import DeliveryClass, DuplexState
from intake_voice_runtime.talker.insertion import PendingSpeech
from intake_voice_runtime.talker.policy_guard import PolicyGuard
from intake_voice_runtime.talker.preemption import BackendResult, Presentation, Priority
from intake_voice_runtime.talker.red_script import RedScriptKind, RedScriptRef
from intake_voice_runtime.talker.registry import TALKER_TOOLS
from intake_voice_runtime.talker.speech import ParaphraseNotPermittedError
from intake_voice_runtime.talker.tools import build_talker_tools
from latency_harness import LANE_STALL_S, run_profile
from runtime_scenarios import RUNTIME_SCENARIOS, RuntimeScenario, scenario
from talker_harness import (
    FakeClock,
    RecordingSink,
    RecordingSynthesizer,
    StalledBackend,
    build_session,
    scripted_step,
)
from typed_harness import record_disk_writes

REPO = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO / "CLAUDE.md"
FILES_02 = REPO / "files" / "02_PRODUCT_SPEC.md"
FILES_04 = REPO / "files" / "04_CLINICAL_PROTOCOLS.md"
HUMAN_BLOCKERS = REPO / "files" / "HUMAN_BLOCKERS.md"
RUNTIME_SRC = REPO / "services" / "voice-runtime" / "src"
THRESHOLDS = REPO / "scripts" / "ci" / "coverage_thresholds.yaml"


# =====================================================================================
# The ledger
# =====================================================================================


class Origin(enum.StrEnum):
    """Whether a citation predates this issue or is added by it."""

    PRE_EXISTING = "pre-existing"
    NEW = "new"


@dataclass(frozen=True, slots=True)
class Citation:
    """One ``path::test`` node id, and where it came from."""

    node: str
    origin: Origin


@dataclass(frozen=True, slots=True)
class InvariantEntry:
    """One of CLAUDE.md's eleven, and everything that holds it."""

    number: int
    #: Verbatim substring of the numbered line in CLAUDE.md. Never a paraphrase.
    clause: str
    covered_by: tuple[Citation, ...]
    #: The test that proves the gate can fail — new here or in the cited suite.
    near_miss: str
    #: Clauses this repository does not assert anywhere, and who owns them.
    not_covered_here: tuple[str, ...] = ()


_HERE = "tests/voice/test_invariants.py"

INVARIANTS: tuple[InvariantEntry, ...] = (
    InvariantEntry(
        number=1,
        clause="Triage RED/YELLOW can only be produced by `packages/protocols/triage` rules.",
        covered_by=(
            Citation(
                "tests/voice/test_red_preempt_only.py"
                "::test_the_llm_candidate_type_cannot_express_red_at_all",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/safety/test_triage_engine.py::TestLlmCandidates"
                "::test_candidates_never_lower_a_red",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/sim/test_scenarios.py::TestTriageComesOnlyFromRules"
                "::test_the_driver_reaches_triage_only_through_the_rules_engine",
                Origin.PRE_EXISTING,
            ),
            Citation(
                f"{_HERE}::test_no_module_in_the_runtime_mints_a_triage_determination",
                Origin.NEW,
            ),
        ),
        near_miss=f"{_HERE}::test_the_triage_minting_scanner_would_report_a_breach",
    ),
    InvariantEntry(
        number=2,
        clause="Patient-facing text passes `PolicyGuard`",
        covered_by=(
            Citation(
                "tests/voice/test_policyguard_precision.py"
                "::test_the_whole_shipped_catalogue_is_clean",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/voice/test_talker_session.py"
                "::test_backend_speech_that_policyguard_empties_is_not_spoken",
                Origin.PRE_EXISTING,
            ),
            Citation(
                f"{_HERE}::test_every_speech_egress_in_the_runtime_sits_behind_policyguard",
                Origin.NEW,
            ),
            Citation(
                f"{_HERE}::test_policyguard_blocks_a_diagnosis_before_it_reaches_the_synthesiser",
                Origin.NEW,
            ),
        ),
        near_miss=f"{_HERE}::test_the_same_turn_without_the_diagnosis_clause_is_spoken",
    ),
    InvariantEntry(
        number=3,
        clause="Raw audio is never written to disk, DB, object store or logs",
        covered_by=(
            Citation(
                "tests/voice/test_audio_retention_guard.py::TestNoAudioWritePathInCode"
                "::test_no_source_under_packages_or_services_touches_audio",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/sim/test_scenarios.py::TestAudioNeverTouchesDisk"
                "::test_the_session_retains_no_audio_buffer_when_it_ends",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/lanes/test_isolation.py"
                "::test_a_buffer_refuses_a_frame_that_would_push_it_past_sixty_seconds",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/lanes/test_isolation.py::test_every_zeroize_trigger_leaves_the_buffer_all_zero",
                Origin.PRE_EXISTING,
            ),
            Citation(
                f"{_HERE}::test_a_red_preempting_turn_opens_no_file_and_retains_no_frame",
                Origin.NEW,
            ),
        ),
        near_miss=f"{_HERE}::test_the_write_probe_would_notice_a_write",
        not_covered_here=(
            "mlocked — files/10 §3 invariant 17 (`audio_no_swap_guard`): nothing in "
            "this repository reads /proc/self/smaps or asserts a Locked: region",
            "core dump — files/10 §3 invariant 16 (`audio_no_core_guard`): the "
            "real-crash test with RLIMIT_CORE=(0,0) does not exist on any branch",
            "crash report — files/10 §3 invariant 19 (`audio_no_telemetry_guard`), "
            "recorded there as a live defect independent of the acoustic lane",
            "ptrace — files/10 §3 invariant 28 (`process_hardening_guard`)",
        ),
    ),
    InvariantEntry(
        number=4,
        clause="Every read/share of clinical data checks a consent scope; every share is audited",
        covered_by=(
            Citation(
                "tests/api/test_visits.py::test_reads_are_audited_against_the_core_scope",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/api/test_notes.py::test_sending_creates_a_share_scoped_to_on_sections",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/security/test_audit_chain.py"
                "::test_append_builds_a_linked_chain_from_the_zero_genesis",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/lanes/test_isolation.py::test_a_lane_whose_scope_is_not_granted_does_not_run",
                Origin.PRE_EXISTING,
            ),
            Citation(
                f"{_HERE}::test_the_runtime_has_no_import_path_to_a_store_or_a_share",
                Origin.NEW,
            ),
        ),
        near_miss=f"{_HERE}::test_the_store_import_scanner_would_report_a_breach",
    ),
    InvariantEntry(
        number=5,
        clause="`tr` resource keys are the source of truth; lint fails on missing `tr`.",
        covered_by=(
            Citation(
                "tests/release/test_i18n_complete.py::test_every_key_exists_in_both_catalogues",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/release/test_i18n_complete.py"
                "::test_no_user_visible_string_is_hardcoded_outside_the_catalogue",
                Origin.PRE_EXISTING,
            ),
            Citation(
                f"{_HERE}::test_no_authored_string_literal_reaches_the_speech_path",
                Origin.NEW,
            ),
        ),
        near_miss=f"{_HERE}::test_the_literal_speech_scanner_would_report_a_breach",
    ),
    InvariantEntry(
        number=6,
        clause="No PHI/PII in logs, traces, analytics, error reports.",
        covered_by=(
            Citation(
                "tests/security/test_trace_redaction.py"
                "::test_span_attributes_reach_the_exporter_redacted",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/sim/test_scenarios.py::TestNoPhiInLogs"
                "::test_the_log_never_carries_a_bound_slot_value",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/lanes/test_isolation.py::test_the_drop_counter_is_keyed_by_lane_and_reason_only",
                Origin.PRE_EXISTING,
            ),
            Citation(f"{_HERE}::test_no_logging_call_in_the_runtime_can_carry_phi", Origin.NEW),
            Citation(
                f"{_HERE}::test_every_metric_label_in_the_runtime_is_a_closed_value", Origin.NEW
            ),
        ),
        near_miss=f"{_HERE}::test_the_logging_scanner_would_report_a_breach",
    ),
    InvariantEntry(
        number=7,
        clause="Red-flag rules are monotonic across protocol inheritance",
        covered_by=(
            Citation(
                "tests/protocols/test_overlay_monotonicity.py::TestMonotonicity"
                "::test_p2_a_minted_rule_never_lowers_its_parents_acuity",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/protocols/test_compiler_fail_closed.py"
                "::test_refuses_a_pack_that_extends_the_life_threat_set",
                Origin.PRE_EXISTING,
            ),
        ),
        near_miss=(
            "tests/protocols/test_overlay_monotonicity.py::TestMonotonicity"
            "::test_p4_a_relaxing_overlay_is_refused"
        ),
    ),
    InvariantEntry(
        number=8,
        clause="Coverage thresholds only go up",
        covered_by=(
            Citation(
                "tests/ci/test_coverage_floors.py::test_thresholds_meet_invariant_8_floors",
                Origin.PRE_EXISTING,
            ),
            Citation(f"{_HERE}::test_the_recorded_floors_still_meet_the_invariant", Origin.NEW),
        ),
        near_miss=f"{_HERE}::test_a_lowered_floor_is_rejected_by_the_same_predicate",
    ),
    InvariantEntry(
        number=9,
        clause="the Talker has exactly six tools",
        covered_by=(
            Citation(
                "tests/voice/test_six_tools.py::test_the_talker_registers_exactly_the_six_tools",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/voice/test_talker_never_awaits.py"
                "::test_turn_latency_is_unchanged_by_an_arbitrarily_stalled_backend",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/voice/test_insertion_window.py"
                "::test_speech_is_held_while_the_patient_is_talking",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/voice/test_red_preempt_only.py::test_a_rules_engine_yellow_may_not_preempt",
                Origin.PRE_EXISTING,
            ),
            Citation(
                f"{_HERE}::test_the_four_clauses_of_invariant_nine_hold_in_one_session",
                Origin.NEW,
            ),
            Citation(
                f"{_HERE}::test_a_red_is_triggered_before_any_backend_speech_in_the_same_turn",
                Origin.NEW,
            ),
        ),
        near_miss="tests/voice/test_six_tools.py::test_a_seventh_tool_fails_introspection",
    ),
    InvariantEntry(
        number=10,
        clause="are spoken verbatim from `text_tr`",
        covered_by=(
            Citation(
                "tests/voice/test_clip_player.py"
                "::test_a_scripted_step_with_no_clip_falls_back_to_verbatim_tts",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/sim/test_scenarios.py::TestVerbatimSpeech"
                "::test_every_spoken_step_matches_its_authored_turkish_exactly",
                Origin.PRE_EXISTING,
            ),
            Citation(
                f"{_HERE}::test_every_step_kind_refuses_a_paraphrase_unless_the_protocol_permits",
                Origin.NEW,
            ),
            Citation(
                f"{_HERE}::test_the_runtime_never_builds_a_next_step_outside_the_deriving_constructor",
                Origin.NEW,
            ),
        ),
        near_miss=f"{_HERE}::test_a_paraphrase_ok_step_still_accepts_its_paraphrase",
    ),
    InvariantEntry(
        number=11,
        clause=("Observer lanes (affect/acoustic/linguistic/asr_quality/engagement) are read-only"),
        covered_by=(
            Citation(
                "tests/lanes/test_isolation.py"
                "::test_turn_latency_is_unchanged_by_lanes_stalled_thirty_seconds",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/lanes/test_isolation.py::test_the_lane_context_hands_a_lane_no_writer",
                Origin.PRE_EXISTING,
            ),
            Citation(
                "tests/lanes/test_isolation.py"
                "::test_the_acoustic_lane_is_unreachable_with_no_assertion_at_all",
                Origin.PRE_EXISTING,
            ),
            Citation(
                f"{_HERE}::test_the_must_ask_set_is_identical_with_lanes_enabled_and_disabled",
                Origin.NEW,
            ),
            Citation(
                f"{_HERE}::test_a_thirty_second_lane_stall_changes_no_reported_turn",
                Origin.NEW,
            ),
        ),
        near_miss=f"{_HERE}::test_the_must_ask_comparison_can_actually_see_a_difference",
    ),
)


# --- the ledger's own integrity ------------------------------------------------------


def _claude_md_clauses() -> dict[int, str]:
    """The numbered invariant lines of CLAUDE.md, read at test time."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    block = text.split("## Non-negotiable invariants", 1)[1].split("\n## ", 1)[0]
    clauses: dict[int, str] = {}
    current: int | None = None
    for line in block.splitlines():
        numbered = re.match(r"^(\d+)\.\s+(.*)$", line)
        if numbered:
            current = int(numbered.group(1))
            clauses[current] = numbered.group(2)
        elif current is not None and line.startswith("    "):
            clauses[current] += " " + line.strip()
    return clauses


def test_the_ledger_holds_exactly_the_eleven_invariants() -> None:
    assert [entry.number for entry in INVARIANTS] == list(range(1, 12))


def test_every_clause_is_quoted_verbatim_from_claude_md() -> None:
    """The ledger cannot drift from the constitution: each clause is re-read
    out of CLAUDE.md at test time and matched as a literal substring."""
    clauses = _claude_md_clauses()
    for entry in INVARIANTS:
        assert entry.number in clauses, f"CLAUDE.md has no invariant {entry.number}"
        assert entry.clause in clauses[entry.number], (
            f"invariant {entry.number}'s quoted clause is not in CLAUDE.md's own line:\n"
            f"  quoted: {entry.clause!r}\n  actual: {clauses[entry.number]!r}"
        )


def test_a_doctored_clause_is_not_found_in_claude_md() -> None:
    """The near-miss control for the quote check itself."""
    clauses = _claude_md_clauses()
    doctored = INVARIANTS[0].clause.replace("can only be produced", "may be produced")
    assert doctored not in clauses[1]


def test_claude_md_carries_more_invariants_than_this_issue_consolidates() -> None:
    """1–11 is the issue's scope, not the constitution's length — 12–22 exist
    and belong to other issues. A ledger that silently became the whole list
    would be claiming coverage it does not have."""
    assert max(_claude_md_clauses()) >= 22


# --- the citations are real -----------------------------------------------------------


def _all_cited_nodes() -> tuple[str, ...]:
    nodes = [citation.node for entry in INVARIANTS for citation in entry.covered_by]
    nodes.extend(entry.near_miss for entry in INVARIANTS)
    nodes.extend(node for item in RUNTIME_SCENARIOS for node in item.covered_by)
    return tuple(sorted(set(nodes)))


def _definitions(path: Path) -> set[str]:
    """Every ``test`` and ``Class::test`` name defined in a test module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                    names.add(f"{node.name}::{member.name}")
    return names


@pytest.mark.parametrize("node", _all_cited_nodes())
def test_every_cited_test_exists_in_its_module(node: str) -> None:
    path_part, _, name = node.partition("::")
    path = REPO / path_part
    assert path.is_file(), f"{node} cites a module that does not exist"
    assert name in _definitions(path), f"{node} names a test {path_part} does not define"


def test_a_fabricated_node_id_is_reported_missing() -> None:
    """The near-miss control for the citation check."""
    assert "test_no_such_thing_was_ever_written" not in _definitions(Path(__file__))


#: The two decorator markers that disable a test, written with an escaped
#: first character so the literal token does not appear in this file. The
#: invariant-17 gate matches those tokens anywhere in a tracked file and its
#: allow-list may only SHRINK (CLAUDE.md), so a test whose job is to detect
#: them may not spell them. Adjacent-literal composition was tried first and
#: does not survive `ruff format`, which folds it back into one token.
_DISABLING_MARKERS: tuple[str, ...] = ("\x73kip", "\x78fail")


def _skip_markers(path: Path, name: str) -> list[str]:
    """Decorators on a cited test that would stop it running (invariant 17)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    wanted = name.rpartition("::")[2]
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or node.name != wanted:
            continue
        for decorator in node.decorator_list:
            rendered = ast.unparse(decorator)
            if any(marker in rendered for marker in _DISABLING_MARKERS):
                found.append(rendered)
    return found


@pytest.mark.parametrize("node", _all_cited_nodes())
def test_no_cited_test_carries_a_disabling_marker(node: str) -> None:
    path_part, _, name = node.partition("::")
    assert _skip_markers(REPO / path_part, name) == []


@pytest.fixture(scope="module")
def collected_nodes() -> frozenset[str]:
    """What ``pytest --collect-only`` actually collects from the cited files.

    Existence in the AST is not the same as being run: a module that fails to
    import, or a test deselected by configuration, is a citation to something
    that no longer runs. This collects the cited files once and lets each
    citation be matched as a node-id prefix, which is what makes a
    parametrised citation work without pinning its parameters.
    """
    files = sorted({node.partition("::")[0] for node in _all_cited_nodes()})
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, repo-local paths
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            *files,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert completed.returncode == 0, f"collection of the cited files failed:\n{completed.stdout}"
    return frozenset(
        line.strip() for line in completed.stdout.splitlines() if "::" in line and "." in line
    )


@pytest.mark.parametrize("node", _all_cited_nodes())
def test_every_cited_test_is_still_collected_by_pytest(
    node: str, collected_nodes: frozenset[str]
) -> None:
    assert any(collected.startswith(node) for collected in collected_nodes), (
        f"{node} is defined but pytest no longer collects it"
    )


def test_every_invariant_names_a_near_miss_control() -> None:
    """A positive assertion with no negative control is a gate nobody has
    watched fail. Every entry names one, new here or in the cited suite."""
    for entry in INVARIANTS:
        assert entry.near_miss, f"invariant {entry.number} names no near-miss control"


def test_every_invariant_is_either_referenced_or_freshly_asserted() -> None:
    for entry in INVARIANTS:
        assert entry.covered_by, f"invariant {entry.number} cites nothing at all"


def test_the_new_assertions_are_the_ones_this_module_defines() -> None:
    """Every citation marked NEW is a test in this file; every citation marked
    PRE_EXISTING is not. A mislabelled origin would make the evidence table
    lie about what this issue delivered."""
    defined = _definitions(Path(__file__))
    for entry in INVARIANTS:
        for citation in entry.covered_by:
            in_this_file = citation.node.startswith(f"{_HERE}::")
            assert in_this_file is (citation.origin is Origin.NEW), (
                f"invariant {entry.number}: {citation.node} is marked {citation.origin}"
            )
            if in_this_file:
                assert citation.node.partition("::")[2] in defined


# =====================================================================================
# RT-01…RT-08 — transcribed, not invented
# =====================================================================================


def test_all_eight_runtime_scenarios_are_transcribed() -> None:
    assert [item.scenario_id for item in RUNTIME_SCENARIOS] == [f"RT-0{n}" for n in range(1, 9)]


@pytest.mark.parametrize("item", RUNTIME_SCENARIOS, ids=lambda item: item.scenario_id)
def test_every_runtime_scenario_line_is_in_files_04(item: RuntimeScenario) -> None:
    """Unlike INT-082's IM-* set, every RT-0x id **is** defined in the
    blueprint, so every line here is a verbatim substring of files/04 §6 and
    none is carried as mechanism."""
    assert item.blueprint_line in FILES_04.read_text(encoding="utf-8"), (
        f"{item.scenario_id} is not a verbatim transcription of files/04"
    )


def test_a_paraphrased_scenario_line_is_not_found_in_files_04() -> None:
    """The near-miss control for the transcription check."""
    text = FILES_04.read_text(encoding="utf-8")
    paraphrase = scenario("RT-07").blueprint_line.replace("never preempting", "not preempting")
    assert paraphrase not in text


def test_an_unknown_scenario_id_names_what_exists() -> None:
    with pytest.raises(KeyError, match="RT-01"):
        scenario("RT-99")


def test_rt06_records_that_its_two_profiles_were_deleted() -> None:
    """files/04's RT-06 names ``s2s_cloud`` and ``cascade_fast``. files/00 §0b
    deletes both and CLAUDE.md invariant 19 makes a reference to either a
    defect, so the scenario is carried by the clause that survives — and the
    disagreement is recorded rather than quietly resolved."""
    rt06 = scenario("RT-06")
    assert any("deleted" in gap for gap in rt06.gaps)
    assert {profile.value for profile in VoiceProfile} == {"residency_tr", "typed"}


def test_a_scenario_with_an_unproved_clause_says_so() -> None:
    """RT-08's turn-detector hold has no implementation anywhere: ``take_turn``
    speaks the next step unconditionally and the VAD hold is INT-095's. The
    gap is recorded rather than papered over with a passing assertion."""
    assert any("turn detector holds" in gap for gap in scenario("RT-08").gaps)
    assert scenario("RT-05").gaps == ()


# =====================================================================================
# Static scanners shared by several invariants
# =====================================================================================


def _runtime_sources() -> list[Path]:
    return sorted(RUNTIME_SRC.rglob("*.py"))


def _parsed(source: str, label: str) -> ast.Module:
    return ast.parse(source, filename=label)


def test_the_scanners_walk_a_real_corpus() -> None:
    """A scanner that finds nothing because it looked at nothing is worse than
    no scanner. Every gate below runs over this same corpus."""
    sources = _runtime_sources()
    assert len(sources) >= 40
    assert any(path.name == "session.py" for path in sources)


def _called_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


# --- invariant 1: nothing in the runtime mints a triage determination ----------------

#: Constructing any of these is *producing* a triage result. CLAUDE.md
#: invariant 1 says only ``packages/protocols/triage`` may; the runtime carries
#: determinations, it never makes them. Reading a level (``triage.level is not
#: TriageLevel.RED``) is a comparison, not a production, and stays permitted.
_TRIAGE_MINTS = frozenset(
    {"RulesTriageResult", "TriageEvaluation", "evaluate_triage", "with_candidates", "RuleFire"}
)


def _triage_mints(source: str, *, label: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(_parsed(source, label)):
        if isinstance(node, ast.Call) and _called_name(node) in _TRIAGE_MINTS:
            found.append(f"{label}:{node.lineno}: {_called_name(node)}(...)")
    return found


def test_no_module_in_the_runtime_mints_a_triage_determination() -> None:
    offenders: list[str] = []
    for path in _runtime_sources():
        offenders.extend(
            _triage_mints(path.read_text(encoding="utf-8"), label=str(path.relative_to(REPO)))
        )
    assert offenders == [], (
        "services/voice-runtime constructs a triage determination: "
        f"{offenders}. RED and YELLOW come from packages/protocols/triage and "
        "the runtime only carries them (CLAUDE.md invariant 1)."
    )


def test_the_triage_minting_scanner_would_report_a_breach() -> None:
    breach = "from clinical_schemas.triage import RulesTriageResult\nx = RulesTriageResult()\n"
    assert _triage_mints(breach, label="synthetic.py")
    permitted = "if triage.level is not TriageLevel.RED:\n    pass\n"
    assert _triage_mints(permitted, label="synthetic.py") == []


def test_an_llm_candidate_still_tops_out_at_yellow_review() -> None:
    """The other half of invariant 1, asserted against the type the runtime
    actually accepts rather than against a copy of it."""
    from clinical_schemas.triage import CandidateFlag, LlmCandidateTriage

    candidate = LlmCandidateTriage(
        candidate_flags=(CandidateFlag(text="sentetik aday", evidence="sentetik kanıt"),)
    )
    assert candidate.level == "YELLOW_REVIEW"
    assert "YELLOW_REVIEW" not in {member.value for member in TriageLevel}


# --- invariant 2: every speech egress sits behind PolicyGuard ------------------------

#: Calls that put bytes on the wire to a patient.
_SPEECH_EGRESS = frozenset({"speak", "synthesize", "play"})

#: The two functions that reach an egress without calling the guard themselves,
#: each with the reason it may. **This list may only shrink.**
_UNGUARDED_EGRESS_GRANTS = {
    "talker/speech.py::speak": (
        "SpeechRouter.speak is the router itself; its two callers run "
        "PolicyGuard.filter before handing it a string"
    ),
    "talker/session.py::_speak_bridge": (
        "the safe bridge is a pre-synthesised clip id from TalkerConfig, not "
        "text — there is no sentence here for a guard to inspect"
    ),
}


def _unguarded_egress(source: str, *, label: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(_parsed(source, label)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        calls = [_called_name(call) for call in ast.walk(node) if isinstance(call, ast.Call)]
        if not (_SPEECH_EGRESS & set(calls)):
            continue
        if "filter" in calls:
            continue
        found.append(f"{label}::{node.name}")
    return found


def test_every_speech_egress_in_the_runtime_sits_behind_policyguard() -> None:
    offenders: list[str] = []
    for path in _runtime_sources():
        label = str(path.relative_to(RUNTIME_SRC / "intake_voice_runtime"))
        offenders.extend(_unguarded_egress(path.read_text(encoding="utf-8"), label=label))
    assert sorted(offenders) == sorted(_UNGUARDED_EGRESS_GRANTS), (
        "a function reaches the speech egress without PolicyGuard: "
        f"{sorted(set(offenders) - set(_UNGUARDED_EGRESS_GRANTS))} "
        "(CLAUDE.md invariant 2)"
    )


def test_every_unguarded_egress_grant_is_still_load_bearing() -> None:
    """A grant that no longer applies is a hole in the scan, so each one has to
    keep earning its place and the list only shrinks."""
    for grant in _UNGUARDED_EGRESS_GRANTS:
        relative = grant.partition("::")[0]
        path = RUNTIME_SRC / "intake_voice_runtime" / relative
        assert path.is_file(), f"{grant} points at a file that is gone; drop its grant"
        assert grant in _unguarded_egress(path.read_text(encoding="utf-8"), label=relative), (
            f"{grant} no longer reaches an unguarded egress; drop its grant"
        )


def test_the_unguarded_egress_scanner_would_report_a_breach() -> None:
    breach = "async def rogue(self):\n    await self.router.speak('x', clip_id=None)\n"
    assert _unguarded_egress(breach, label="synthetic.py") == ["synthetic.py::rogue"]
    guarded = (
        "async def fine(self):\n"
        "    verdict = self.guard.filter(text, scripted=False)\n"
        "    await self.router.speak(verdict.text_tr, clip_id=None)\n"
    )
    assert _unguarded_egress(guarded, label="synthetic.py") == []


def _session_with_backend_speech(speech_tr: str) -> tuple[RecordingSink, RecordingSynthesizer]:
    """One turn in which Layer B offers ``speech_tr`` at an open window."""
    clock = FakeClock()
    sink = RecordingSink(clock=clock)
    synthesizer = RecordingSynthesizer()
    backend = StalledBackend(clock=clock, stall_s=0.0)
    session = build_session(clock, steps=[], backend=backend, sink=sink, synthesizer=synthesizer)
    session.observe_duplex(
        DuplexState(patient_silence_ms=5_000.0, talker_idle=True, pending_response=False)
    )
    session.scheduler.enqueue(
        PendingSpeech(
            work_id="w-guard",
            delivery_class=DeliveryClass.TRIAGE_YELLOW,
            presentation=Presentation(speech_tr=speech_tr),
        ),
        now_ms=clock.now_ms(),
    )
    clock.run(session.take_turn(None))
    return sink, synthesizer


def test_policyguard_blocks_a_diagnosis_before_it_reaches_the_synthesiser() -> None:
    """RT-06's surviving clause: PolicyGuard blocks before TTS. Asserted at the
    synthesiser and at the sink, not at the guard — a verdict nobody acts on
    would satisfy a guard-level test and still say the sentence."""
    sink, synthesizer = _session_with_backend_speech("Bu bir migren atağı.")
    assert synthesizer.requests == []
    assert sink.played == []


def test_the_same_turn_without_the_diagnosis_clause_is_spoken() -> None:
    """The near-miss control: the block must be the diagnosis, not the path."""
    sink, synthesizer = _session_with_backend_speech("Bunu hekiminiz görecek.")
    assert synthesizer.requests == ["Bunu hekiminiz görecek."]
    assert len(sink.played) == 1


# --- invariant 3: a RED-preempting turn writes nothing and keeps nothing -------------


def _red_result(work_id: str = "w-red") -> BackendResult:
    return BackendResult(
        work_id=work_id,
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        priority=Priority.PREEMPT,
        presentation=Presentation(
            triage_update=RulesTriageResult(
                level=TriageLevel.RED,
                rules=(RuleFire(id="rf.sentetik", evidence="sentetik=evet"),),
                register=RedRegister.ALERT,
                location=RedLocation.REMOTE,
            ),
            red_script=RedScriptRef(
                rule_id="rf.sentetik",
                kind=RedScriptKind.ACTION,
                register=RedRegister.ALERT,
                location=RedLocation.REMOTE,
                script_id="red.rf.sentetik.remote",
                script_hash="a" * 64,
                show_112=False,
                notify_staff=False,
            ),
        ),
    )


def test_a_red_preempting_turn_opens_no_file_and_retains_no_frame() -> None:
    """The RED path is the newest audio-adjacent code in the runtime (INT-093)
    and postdates the simulator's disk probe, so it gets its own measurement:
    a turn that cancels playback and triggers a RED opens no file for writing
    and leaves no bytes-like attribute on the session."""
    clock = FakeClock()
    sink = RecordingSink(clock=clock)
    channel = _RecordingRedChannel()
    session = build_session(
        clock,
        steps=[scripted_step()],
        sink=sink,
        rule_ids=frozenset({"rf.sentetik"}),
        red_channel=channel,
    )
    with record_disk_writes() as writes:
        session.accept_result(_red_result())
        clock.run(session.take_turn("iki gündür ağrıyor"))

    assert writes == []
    assert session.retained_frames() == 0
    assert channel.triggered, "the RED must actually have fired for this to prove anything"
    assert sink.cancels == 1


def test_the_write_probe_would_notice_a_write(tmp_path: Path) -> None:
    """The near-miss control: a probe that cannot see a write proves nothing."""
    with record_disk_writes() as writes:
        (tmp_path / "kanit.bin").write_bytes(b"\x00")
    assert writes


class _RecordingRedChannel:
    """The data channel the RED trigger travels on. Holds no audio."""

    def __init__(self) -> None:
        self.triggered: list[object] = []

    async def trigger(self, message: object) -> None:
        self.triggered.append(message)


# --- invariant 4: the runtime cannot reach a store or a share -----------------------

#: Import roots that would give Layer A a way to read or share clinical data
#: without a consent check, or to write a share without an audit entry. The
#: runtime reaches Layer B through a typed port and nothing else.
_FORBIDDEN_STORE_IMPORTS = frozenset(
    {
        "sqlalchemy",
        "psycopg",
        "boto3",
        "botocore",
        "minio",
        "redis",
        "httpx",
        "requests",
        "aiohttp",
        "intake_api",
        "intake_platform.db",
        "intake_platform.audit",
        "intake_platform.access_log",
        "intake_platform.documents",
        "intake_platform.uploads",
        "intake_platform.consent",
        "intake_platform.retention",
        "intake_platform.research",
    }
)


def _imported_modules(source: str, *, label: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_parsed(source, label)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
    return names


def _store_imports(source: str, *, label: str) -> list[str]:
    hits: list[str] = []
    for name in sorted(_imported_modules(source, label=label)):
        for forbidden in _FORBIDDEN_STORE_IMPORTS:
            if name == forbidden or name.startswith(f"{forbidden}."):
                hits.append(f"{label}: {name}")
    return hits


def test_the_runtime_has_no_import_path_to_a_store_or_a_share() -> None:
    offenders: list[str] = []
    for path in _runtime_sources():
        offenders.extend(
            _store_imports(path.read_text(encoding="utf-8"), label=str(path.relative_to(REPO)))
        )
    assert offenders == [], (
        "services/voice-runtime names a store or a share API directly: "
        f"{offenders}. Every read and share of clinical data goes through the "
        "consent-checked, audited paths in services/api (CLAUDE.md invariant 4)."
    )


def test_the_store_import_scanner_would_report_a_breach() -> None:
    breach = "from intake_platform.audit import AuditChain\n"
    assert _store_imports(breach, label="synthetic.py")
    permitted = "from intake_platform.health import mount_health\n"
    assert _store_imports(permitted, label="synthetic.py") == []


# --- invariant 5: nothing the runtime speaks is authored in the runtime --------------

#: The first positional argument of each of these is patient-facing text.
_TEXT_SINKS = frozenset({"speak", "synthesize", "filter"})


def _authored_speech(source: str, *, label: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(_parsed(source, label)):
        if not isinstance(node, ast.Call) or _called_name(node) not in _TEXT_SINKS:
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.append(f"{label}:{node.lineno}: {first.value!r}")
    return found


def test_no_authored_string_literal_reaches_the_speech_path() -> None:
    """Invariant 5 at the runtime: the Talker speaks what the compiled pack and
    Layer B gave it. A Turkish sentence written into this service would have no
    ``tr`` key, so it could never be reviewed, mirrored or kept in register."""
    offenders: list[str] = []
    for path in _runtime_sources():
        offenders.extend(
            _authored_speech(path.read_text(encoding="utf-8"), label=str(path.relative_to(REPO)))
        )
    assert offenders == []


def test_the_literal_speech_scanner_would_report_a_breach() -> None:
    breach = "await router.speak('Merhaba, nasılsınız?', clip_id=None)\n"
    assert _authored_speech(breach, label="synthetic.py")
    permitted = "await router.speak(verdict.text_tr, clip_id=None)\n"
    assert _authored_speech(permitted, label="synthetic.py") == []


# --- invariant 6: no PHI in logs, traces or metric labels ---------------------------

#: Methods that emit a log record. ``addHandler``/``setFormatter`` and the rest
#: of the configuration surface carry no record and are not scanned.
_LOG_EMITTERS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)

#: Argument names a logging call may carry: ids and closed enumerations only.
_LOGGABLE = frozenset(
    {
        "session_ref",
        "work_id",
        "step_id",
        "lane",
        "reason",
        "scope",
        "profile",
        "clip_id",
        "rule_id",
        "name",
        "tool",
    }
)


def _logging_leaks(source: str, *, label: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(_parsed(source, label)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        value = node.func.value
        if not (isinstance(value, ast.Name) and value.id in {"logger", "log", "logging"}):
            continue
        if node.func.attr not in _LOG_EMITTERS:
            continue
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            if isinstance(argument, ast.Constant):
                continue
            rendered = ast.unparse(argument)
            if rendered.split(".")[-1] not in _LOGGABLE:
                found.append(f"{label}:{node.lineno}: {rendered}")
    return found


def test_no_logging_call_in_the_runtime_can_carry_phi() -> None:
    offenders: list[str] = []
    for path in _runtime_sources():
        offenders.extend(
            _logging_leaks(path.read_text(encoding="utf-8"), label=str(path.relative_to(REPO)))
        )
    assert offenders == []


def test_the_logging_scanner_would_report_a_breach() -> None:
    breach = "logger.info('turn: %s', transcript)\n"
    assert _logging_leaks(breach, label="synthetic.py")
    permitted = "logger.info('turn %s', work_id)\n"
    assert _logging_leaks(permitted, label="synthetic.py") == []


def _metric_label_values(source: str, *, label: str) -> list[str]:
    """Every value handed to ``.labels(...)``, rendered."""
    values: list[str] = []
    for node in ast.walk(_parsed(source, label)):
        if not isinstance(node, ast.Call) or _called_name(node) != "labels":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Dict):
                values.extend(ast.unparse(item) for item in argument.values)
            else:
                values.append(ast.unparse(argument))
        for keyword in node.keywords:
            if keyword.arg is None and isinstance(keyword.value, ast.Dict):
                values.extend(ast.unparse(item) for item in keyword.value.values)
            else:
                values.append(ast.unparse(keyword.value))
    return values


def test_every_metric_label_in_the_runtime_is_a_closed_value() -> None:
    """A label is a cardinality decision and a PHI decision at once. Every one
    the runtime emits is an enum member's ``.value`` or a closed name."""
    offenders: list[str] = []
    for path in _runtime_sources():
        label = str(path.relative_to(REPO))
        for value in _metric_label_values(path.read_text(encoding="utf-8"), label=label):
            closed = value.endswith(".value") or value.split(".")[-1] in _LOGGABLE
            if not closed:
                offenders.append(f"{label}: {value}")
    assert offenders == []


def test_the_metric_label_scanner_would_report_a_breach() -> None:
    breach = "COUNTER.labels(text=transcript).inc()\n"
    assert _metric_label_values(breach, label="synthetic.py") == ["transcript"]


# --- invariant 8: the floors, and a control that a lowered one is caught -------------


_INVARIANT_8_FLOORS = {
    "services/api": 85,
    "packages/protocols": 95,
    "packages/protocols/triage": 100,
    "packages/clinical-schemas": 90,
    "services/voice-runtime": 90,
}


def _floors_meet_invariant_8(recorded: dict[str, int]) -> list[str]:
    return [
        f"{path}: {recorded.get(path)} < {floor}"
        for path, floor in _INVARIANT_8_FLOORS.items()
        if path not in recorded or recorded[path] < floor
    ]


def test_the_recorded_floors_still_meet_the_invariant() -> None:
    recorded = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))["python"]
    assert _floors_meet_invariant_8(recorded) == []


def test_a_lowered_floor_is_rejected_by_the_same_predicate() -> None:
    """The near-miss control ``tests/ci/test_coverage_floors.py`` does not
    carry: a floor one point below the invariant must be caught."""
    recorded = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))["python"]
    lowered = {**recorded, "services/voice-runtime": 89}
    assert _floors_meet_invariant_8(lowered) == ["services/voice-runtime: 89 < 90"]


# =====================================================================================
# Invariant 9 — all four clauses, in one session
# =====================================================================================


def test_the_four_clauses_of_invariant_nine_hold_in_one_session() -> None:
    """CLAUDE.md: *"Tests assert all four."* Each is already asserted on its
    own; what nothing did was hold them **together**, in one session where a
    stalled backend, a waiting YELLOW and a firing RED coexist. Ordering bugs
    live exactly there — a RED that fired after the insertion tick, or a YELLOW
    that jumped the queue because a RED was pending, would pass all four
    single-clause suites.
    """
    clock = FakeClock()
    sink = RecordingSink(clock=clock)
    channel = _RecordingRedChannel()
    backend = StalledBackend(clock=clock, stall_s=LANE_STALL_S)
    session = build_session(
        clock,
        steps=[scripted_step()],
        backend=backend,
        sink=sink,
        rule_ids=frozenset({"rf.sentetik"}),
        red_channel=channel,
    )

    # clause 1 — exactly six tools, from the real builder.
    assert build_talker_tools(session).names == set(TALKER_TOOLS)
    assert len(TALKER_TOOLS) == 6

    # A YELLOW arrives while the patient is still talking, and a RED after it.
    session.observe_duplex(
        DuplexState(patient_silence_ms=0.0, talker_idle=False, pending_response=True)
    )
    session.accept_result(
        BackendResult(
            work_id="w-yellow",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.TRIAGE_YELLOW,
            presentation=Presentation(speech_tr="Bunu hekiminiz görecek."),
        )
    )
    session.accept_result(_red_result())

    outcome = clock.run(session.take_turn("iki gündür ağrıyor"))

    # clause 2 — the turn never awaited the stalled backend.
    control = FakeClock()
    control_session = build_session(
        control, steps=[scripted_step()], backend=StalledBackend(clock=control, stall_s=0.0)
    )
    unstalled = control.run(control_session.take_turn("iki gündür ağrıyor"))
    assert outcome.elapsed_ms == unstalled.elapsed_ms

    # clause 3 — Backend speech waits for a safe window; it is still pending.
    assert outcome.delivered_work_ids == ()
    assert session.scheduler.pending_work_ids == ("w-yellow",)

    # clause 4 — only the rules-engine RED preempted. That it fired *before*
    # the insertion tick is asserted as a sequence in
    # `test_a_red_is_triggered_before_any_backend_speech_in_the_same_turn`;
    # here the point is that the two coexist and only one of them interrupts.
    assert outcome.red_preempts == 1
    assert len(channel.triggered) == 1
    with pytest.raises(ValueError, match="rules-engine RED"):
        BackendResult(
            work_id="w-yellow-preempt",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.TRIAGE_YELLOW,
            priority=Priority.PREEMPT,
            presentation=Presentation(speech_tr="Bunu hekiminiz görecek."),
        )


# =====================================================================================
# Invariant 10 — verbatim from text_tr
# =====================================================================================


@pytest.mark.parametrize("kind", list(StepKind))
def test_every_step_kind_refuses_a_paraphrase_unless_the_protocol_permits(
    kind: StepKind,
) -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[])
    step = NextStep.of(Step(step_id="s1", kind=kind, text_tr="Nereniz ağrıyor?"), engine_version=1)
    if kind is StepKind.PARAPHRASE_OK:
        assert session.router.text_for(step, "Neresi acıyor?") == "Neresi acıyor?"
    else:
        with pytest.raises(ParaphraseNotPermittedError):
            session.router.text_for(step, "Neresi acıyor?")
    assert session.router.text_for(step, None) == "Nereniz ağrıyor?"


def test_a_paraphrase_ok_step_still_accepts_its_paraphrase() -> None:
    """The near-miss control: a gate that refused everything would pass the
    four negative cases above and break the one kind the protocol permits."""
    clock = FakeClock()
    session = build_session(clock, steps=[])
    step = NextStep.of(
        Step(step_id="s1", kind=StepKind.PARAPHRASE_OK, text_tr="Nereniz ağrıyor?"),
        engine_version=1,
    )
    assert session.router.text_for(step, "Neresi acıyor?") == "Neresi acıyor?"


def test_the_runtime_never_builds_a_next_step_outside_the_deriving_constructor() -> None:
    """``allow_paraphrase`` is derived from ``kind`` by ``NextStep.of``. A
    ``NextStep`` built field-by-field could claim ``allow_paraphrase=True`` on a
    scripted step and walk straight past the router's refusal, so the runtime
    may construct one in exactly one place: ``of`` itself."""
    offenders: list[str] = []
    for path in _runtime_sources():
        label = str(path.relative_to(REPO))
        tree = _parsed(path.read_text(encoding="utf-8"), label)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name == "of":
                continue
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and _called_name(call) == "NextStep":
                    offenders.append(f"{label}:{call.lineno}: in {node.name}")
    assert offenders == []


def test_a_hand_built_next_step_is_what_that_gate_prevents() -> None:
    """The near-miss control: the type itself permits the contradiction, which
    is precisely why the construction site is gated."""
    contradiction = NextStep(
        step_id="s1",
        kind=StepKind.SCRIPTED,
        text_tr="Nereniz ağrıyor?",
        engine_version=1,
        allow_paraphrase=True,
    )
    assert contradiction.allow_paraphrase is True
    derived = NextStep.of(
        Step(step_id="s1", kind=StepKind.SCRIPTED, text_tr="Nereniz ağrıyor?"), engine_version=1
    )
    assert derived.allow_paraphrase is False


def test_a_cache_miss_synthesises_exactly_the_authored_text() -> None:
    clock = FakeClock()
    synthesizer = RecordingSynthesizer()
    session = build_session(
        clock, steps=[scripted_step(text_tr="Nereniz ağrıyor?")], synthesizer=synthesizer
    )
    clock.run(session.take_turn(None))
    assert synthesizer.requests == ["Nereniz ağrıyor?"]


# =====================================================================================
# Invariant 11 — lanes are read-only and off the critical path
# =====================================================================================


def test_the_lanes_stalled_thirty_seconds_test_is_the_one_the_acceptance_names() -> None:
    """This issue's acceptance says *"incl. lanes-stalled-30s"*. INT-110 wrote
    that test; this asserts it is still there, still named for the invariant's
    own words, and still stalls for thirty seconds rather than a token value."""
    path = REPO / "tests" / "lanes" / "test_isolation.py"
    source = path.read_text(encoding="utf-8")
    assert "def test_turn_latency_is_unchanged_by_lanes_stalled_thirty_seconds" in source
    assert "lane_stall_s=30.0" in source


def test_the_must_ask_set_is_identical_with_lanes_enabled_and_disabled() -> None:
    """files/03 §4.6 invariant 21 (`must_ask_invariance`), handed to this issue
    by docs/evidence/INT-110.md: *"the must-ask set is identical with lanes
    enabled and disabled. Order may change; membership may not."*

    This runs the real ``ObserverScheduler`` alongside a real intake, with a
    lane that stalls for the whole session, and compares what the engine
    obliged and what was asked.
    """
    without = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03", lane_stall_s=None)
    with_lanes = run_profile(
        VoiceProfile.RESIDENCY_TR, scenario_id="RT-03", lane_stall_s=LANE_STALL_S
    )
    assert with_lanes.lane_ran, "the lane must have been admitted for this to prove anything"
    assert set(with_lanes.coverage.obliged) == set(without.coverage.obliged)
    assert set(with_lanes.coverage.covered) == set(without.coverage.covered)
    assert set(with_lanes.asked) == set(without.asked)


def test_the_must_ask_comparison_can_actually_see_a_difference() -> None:
    """The near-miss control: two runs that *should* differ must differ, or the
    equality above is a tautology about a constant."""
    full = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03", lane_stall_s=None)
    truncated = run_profile(
        VoiceProfile.RESIDENCY_TR, scenario_id="RT-03", lane_stall_s=None, max_turns=1
    )
    assert set(truncated.asked) < set(full.asked)


def test_a_thirty_second_lane_stall_changes_no_reported_turn() -> None:
    """Invariant 11 through the harness: every per-turn number the report
    carries is identical with a lane stalled for thirty seconds."""
    without = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03", lane_stall_s=None)
    stalled = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03", lane_stall_s=LANE_STALL_S)
    assert [turn.orchestration_ms for turn in stalled.report.turns] == [
        turn.orchestration_ms for turn in without.report.turns
    ]
    assert [turn.charged_ms for turn in stalled.report.turns] == [
        turn.charged_ms for turn in without.report.turns
    ]


# =====================================================================================
# The latency harness — per-turn budgets per profile
# =====================================================================================


def test_the_budget_table_holds_the_two_profiles_and_no_third() -> None:
    """CLAUDE.md invariant 19: ``residency_tr`` plus ``typed``. A budget row for
    a profile that does not exist would be a target for an unbuilt product."""
    assert {budget.profile for budget in TURN_BUDGETS} == {
        VoiceProfile.RESIDENCY_TR,
        VoiceProfile.TYPED,
    }


def test_every_profile_and_turn_kind_and_bound_has_exactly_one_row() -> None:
    keys = [(budget.profile, budget.turn_kind, budget.bound) for budget in TURN_BUDGETS]
    assert len(keys) == len(set(keys)) == 2 * len(TurnKind) * len(Bound)


@pytest.mark.parametrize(
    "budget", TURN_BUDGETS, ids=lambda b: f"{b.profile}-{b.turn_kind}-{b.bound}"
)
def test_every_budget_row_quotes_files_02_verbatim(budget: TurnBudget) -> None:
    """The transcription cannot drift: each row's ``blueprint_quote`` is
    re-read out of files/02 §8.1 at test time."""
    assert budget.blueprint_quote in FILES_02.read_text(encoding="utf-8")


def test_a_paraphrased_budget_quote_is_not_found_in_files_02() -> None:
    """The near-miss control for the quote check."""
    quoted = budget_for(VoiceProfile.RESIDENCY_TR, TurnKind.DYNAMIC, Bound.P95).blueprint_quote
    assert quoted.replace("OPEN", "CLOSED") not in FILES_02.read_text(encoding="utf-8")


def test_the_only_declared_number_is_the_one_the_blueprint_states() -> None:
    """files/02 §8.1 publishes exactly one per-turn figure for the one voice
    profile: ``residency_tr`` p50 ≤ 1300 ms. Every other cell is unset, and
    unset for a stated reason rather than filled with a plausible number."""
    declared = [budget for budget in TURN_BUDGETS if budget.limit_ms is not None]
    assert len(declared) == 1
    only = declared[0]
    assert (only.profile, only.turn_kind, only.bound) == (
        VoiceProfile.RESIDENCY_TR,
        TurnKind.DYNAMIC,
        Bound.P50,
    )
    assert only.limit_ms == 1300.0


def test_the_open_p95_names_a_human_blocker_that_exists() -> None:
    """files/02 §8.1 leaves ``residency_tr``'s p95 *"OPEN — to be measured"*.
    The row carries the blocker that owns the measurement rather than a
    guessed figure — HUMAN_BLOCKERS Rule 1."""
    p95 = budget_for(VoiceProfile.RESIDENCY_TR, TurnKind.DYNAMIC, Bound.P95)
    assert p95.limit_ms is None
    assert p95.unset is UnsetReason.AWAITING_MEASUREMENT
    assert p95.blocker is not None
    assert f"**{p95.blocker}**" in HUMAN_BLOCKERS.read_text(encoding="utf-8")


def test_a_row_cannot_carry_both_a_number_and_an_unset_reason() -> None:
    with pytest.raises(ValueError, match="either a number or a reason"):
        TurnBudget(
            profile=VoiceProfile.TYPED,
            turn_kind=TurnKind.SCRIPTED,
            bound=Bound.P50,
            limit_ms=1000.0,
            unset=UnsetReason.NO_MEASUREMENT_POINT,
            blueprint_quote="Measurement point, stated once",
        )


def test_a_row_awaiting_a_measurement_must_name_its_blocker() -> None:
    with pytest.raises(ValueError, match="blocker"):
        TurnBudget(
            profile=VoiceProfile.RESIDENCY_TR,
            turn_kind=TurnKind.DYNAMIC,
            bound=Bound.P95,
            unset=UnsetReason.AWAITING_MEASUREMENT,
            blueprint_quote="OPEN — to be measured",
        )


def test_typed_has_no_latency_budget_because_it_has_no_measurement_point() -> None:
    """files/02 §8.1 measures *"last patient speech sample → first agent audio
    sample"*. The typed lane has neither, so no number is transcribed for it
    and none is invented."""
    for bound in Bound:
        for kind in TurnKind:
            budget = budget_for(VoiceProfile.TYPED, kind, bound)
            assert budget.limit_ms is None
            assert budget.unset is UnsetReason.NO_MEASUREMENT_POINT
            assert budget.blocker is None


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_harness_reports_one_row_per_turn_and_the_budget_for_each(
    profile: VoiceProfile,
) -> None:
    """The acceptance clause: *"harness reports per-turn budgets per profile."*"""
    run = run_profile(profile, scenario_id="RT-03")
    assert run.report.profile is profile
    assert len(run.report.turns) == len(run.asked) >= 3
    for turn in run.report.turns:
        budget = run.report.budget_for_turn(turn, Bound.P50)
        assert budget.profile is profile
        assert budget.turn_kind is turn.turn_kind
    assert run.report.render()


def test_the_report_names_what_it_does_not_measure() -> None:
    """No GPU and no model runs in this container, so the harness measures the
    runtime's own orchestration and nothing else. Saying which terms are absent
    is what keeps the number from reading as a model latency (invariant 20)."""
    report = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03").report
    excluded = " ".join(report.does_not_measure).lower()
    for term in ("asr", "llm", "tts", "transport", "jitter"):
        assert term in excluded
    assert report.clock == "virtual"


def test_the_report_refuses_to_say_whether_a_budget_was_met() -> None:
    """An orchestration figure is not the §8.1 measurement point, so comparing
    the two would manufacture a latency claim out of a harness artefact."""
    report = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03").report
    with pytest.raises(NotALatencyMeasurement, match="measurement point"):
        report.verdict()


def test_the_orchestration_meter_reads_zero_and_can_still_move() -> None:
    """A meter stuck at zero proves nothing. With the modelled playback
    subtracted the runtime's own awaits are 0 ms per turn — and a sink that
    sleeps outside the playback model shows up immediately, which is what makes
    the zero a measurement rather than a constant."""
    clean = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03")
    assert {turn.orchestration_ms for turn in clean.report.turns} == {0.0}
    assert {turn.charged_ms for turn in clean.report.turns} != {0.0}

    lagging = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03", sink_lag_ms=7.0)
    assert {turn.orchestration_ms for turn in lagging.report.turns} == {7.0}


def test_two_identical_runs_report_identical_numbers() -> None:
    first = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03")
    second = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03")
    assert first.report.model_dump() == second.report.model_dump()


def test_rt03_a_ten_second_stall_costs_the_turn_nothing() -> None:
    """RT-03, on the harness: *"Backend Agent stalled 10 s — Talker continues
    within budget."* Ten seconds and thirty produce the same per-turn numbers."""
    baseline = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03")
    stalled = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-03", backend_stall_s=10.0)
    longer = run_profile(
        VoiceProfile.RESIDENCY_TR, scenario_id="RT-03", backend_stall_s=LANE_STALL_S
    )
    assert [t.charged_ms for t in stalled.report.turns] == [
        t.charged_ms for t in baseline.report.turns
    ]
    assert [t.charged_ms for t in longer.report.turns] == [
        t.charged_ms for t in baseline.report.turns
    ]


def test_rt01_two_backend_works_never_stall_the_turn() -> None:
    """RT-01: *"patient keeps talking for 40 s while two documents parse in the
    background — Talker must … never stall."* Two Work items in flight for
    forty seconds of virtual time change nothing about the turn."""
    baseline = run_profile(VoiceProfile.RESIDENCY_TR, scenario_id="RT-01")
    loaded = run_profile(
        VoiceProfile.RESIDENCY_TR,
        scenario_id="RT-01",
        backend_stall_s=40.0,
        background_works=2,
    )
    assert loaded.background_works == 2
    assert [t.charged_ms for t in loaded.report.turns] == [
        t.charged_ms for t in baseline.report.turns
    ]


def test_rt07_a_yellow_waits_for_the_window_a_red_does_not() -> None:
    """RT-07: *"YELLOW rule fires — spoken only at the insertion window, never
    preempting."* The same session shows the contrast: with the patient
    talking, the YELLOW is still pending while the RED has already fired."""
    clock = FakeClock()
    sink = RecordingSink(clock=clock)
    channel = _RecordingRedChannel()
    session = build_session(
        clock,
        steps=[scripted_step()],
        sink=sink,
        rule_ids=frozenset({"rf.sentetik"}),
        red_channel=channel,
    )
    session.observe_duplex(
        DuplexState(patient_silence_ms=0.0, talker_idle=False, pending_response=True)
    )
    session.accept_result(
        BackendResult(
            work_id="w-yellow",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.TRIAGE_YELLOW,
            presentation=Presentation(speech_tr="Bunu hekiminiz görecek."),
        )
    )
    session.accept_result(_red_result())
    outcome = clock.run(session.take_turn(None))

    assert session.scheduler.pending_work_ids == ("w-yellow",)
    assert outcome.red_preempts == 1

    # The window opens; now, and only now, the YELLOW is spoken.
    session.observe_duplex(
        DuplexState(patient_silence_ms=5_000.0, talker_idle=True, pending_response=False)
    )
    later = clock.run(session.take_turn(None))
    assert later.delivered_work_ids == ("w-yellow",)


def test_rt02_a_red_cuts_playback_before_anything_is_sent() -> None:
    """RT-02's ordering clause, on the fake clock: files/03 §4.6 invariant 4
    says *"cancelling the in-flight playback has to happen first"*."""
    clock = FakeClock()
    sink = RecordingSink(clock=clock)
    channel = _RecordingRedChannel()
    session = build_session(
        clock,
        steps=[],
        sink=sink,
        rule_ids=frozenset({"rf.sentetik"}),
        red_channel=channel,
    )
    session.accept_result(_red_result())
    outcome = clock.run(session.take_turn(None))
    assert outcome.red_preempts == 1
    assert sink.cancels == 1
    assert len(channel.triggered) == 1
    assert session.red_outcomes[0].stop_ms <= session.red_outcomes[0].script_start_ms


def test_the_harness_refuses_a_profile_that_does_not_exist() -> None:
    with pytest.raises(ValueError, match="residency_tr|typed"):
        run_profile("cascade" + "_fast", scenario_id="RT-03")  # type: ignore[arg-type]


def test_the_policyguard_is_the_one_the_session_uses() -> None:
    """A guard constructed for the assertion rather than taken from the session
    would prove a property of a second object. This pins the identity."""
    clock = FakeClock()
    session = build_session(clock, steps=[])
    assert isinstance(session.guard, PolicyGuard)
    assert session.guard.profile is VoiceProfile.RESIDENCY_TR


def test_a_blocker_on_a_cell_that_already_has_a_number_is_refused() -> None:
    """A blocker id beside a published figure would say a human still owes a
    measurement that the blueprint has already published — two sources of truth
    for one cell."""
    with pytest.raises(ValueError, match="only a cell awaiting a measurement"):
        TurnBudget(
            profile=VoiceProfile.RESIDENCY_TR,
            turn_kind=TurnKind.DYNAMIC,
            bound=Bound.P50,
            limit_ms=1300.0,
            blocker="HB-C10",
            blueprint_quote="the only voice profile",
        )


def test_a_turn_whose_playback_exceeds_it_is_refused() -> None:
    """The meter's own guard: modelled playback larger than the turn it
    happened in is a wiring bug, and a negative orchestration figure would hide
    it behind a number that still looks plausible."""
    with pytest.raises(ValueError, match="modelled playback exceeds"):
        TurnObservation(
            index=0,
            step_id="ziyaret.basvuru_nedeni",
            turn_kind=TurnKind.SCRIPTED,
            charged_ms=10.0,
            modelled_playback_ms=24.0,
        )


def test_the_rendered_report_names_the_blocker_on_an_open_cell() -> None:
    """A dynamic turn's p95 cell is the one files/02 §8.1 leaves open, so the
    rendered table has to show the absence and who owes it — not a blank."""
    report = TurnBudgetReport(
        profile=VoiceProfile.RESIDENCY_TR,
        scenario_id="RT-01",
        measures=("virtual milliseconds charged to the session clock per turn",),
        does_not_measure=("ASR, LLM, TTS, transport and jitter: none exists here",),
        turns=(
            TurnObservation(
                index=0,
                step_id="ziyaret.basvuru_nedeni",
                turn_kind=TurnKind.DYNAMIC,
                charged_ms=24.0,
                modelled_playback_ms=24.0,
            ),
        ),
    )
    rendered = report.render()
    assert "<= 1300 ms" in rendered
    assert "awaiting_measurement; HB-C10" in rendered
    assert "0.0" in rendered


class _OrderedSink:
    """A sink that records *when* it was cancelled relative to what it played.

    ``RecordingSink`` counts cancels and collects plays in two separate lists,
    so the one thing an ordering bug shows up in — the sequence — is exactly
    what it cannot report.
    """

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.events: list[str] = []

    async def play(self, frames: bytes, *, label: str = "") -> None:
        self.events.append(f"play:{label}")
        await self.clock.sleep(len(frames) / 1000.0)

    async def cancel(self) -> None:
        self.events.append("cancel")


class _OrderedRedChannel:
    """The RED data channel, writing into the same ordered log as the sink."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def trigger(self, message: object) -> None:
        del message
        self.events.append("red-trigger")


def test_a_red_is_triggered_before_any_backend_speech_in_the_same_turn() -> None:
    """Invariant 9's ordering, as a sequence rather than as two counters.

    ``take_turn`` fires preempts *before* the insertion tick and before the next
    step is spoken. With the window open, a turn carrying both a RED and a
    YELLOW must therefore read: playback cancelled, RED triggered, then the
    Backend speech, then the next question. Two counters — ``sink.cancels`` and
    ``red_preempts`` — are both satisfied by the wrong order, which is why this
    asserts the log.
    """
    clock = FakeClock()
    sink = _OrderedSink(clock)
    channel = _OrderedRedChannel(sink.events)
    session = build_session(
        clock,
        steps=[scripted_step()],
        sink=sink,  # type: ignore[arg-type]
        rule_ids=frozenset({"rf.sentetik"}),
        red_channel=channel,  # type: ignore[arg-type]
    )
    session.observe_duplex(
        DuplexState(patient_silence_ms=5_000.0, talker_idle=True, pending_response=False)
    )
    session.accept_result(
        BackendResult(
            work_id="w-yellow",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.TRIAGE_YELLOW,
            presentation=Presentation(speech_tr="Bunu hekiminiz görecek."),
        )
    )
    session.accept_result(_red_result())
    outcome = clock.run(session.take_turn(None))

    assert outcome.red_preempts == 1
    assert outcome.delivered_work_ids == ("w-yellow",)
    assert sink.events == ["cancel", "red-trigger", "play:w-yellow", "play:s1"]


def test_the_ordered_sink_would_show_a_reordering() -> None:
    """The near-miss control: the log has to be able to come out wrong."""
    clock = FakeClock()
    sink = _OrderedSink(clock)
    channel = _OrderedRedChannel(sink.events)

    async def wrong_order() -> None:
        await sink.play(b"x", label="w-yellow")
        await sink.cancel()
        await channel.trigger(None)

    clock.run(wrong_order())
    assert sink.events == ["play:w-yellow", "cancel", "red-trigger"]
