"""INT-003 — ADRs 000..023 and the documentation index.

Acceptance (verbatim, with the count correction stated in issues.yaml):
  "docs/adr/ has ADR-000 template and 001..023 Accepted, one paragraph each
   (list in 07 §3.12)"
  "files/ contains files 01..11 verbatim; docs/index.md links everything"
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import yaml

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "adr"

# Anchors from 07 §3.12 — an ADR that exists but says the wrong thing is worse
# than a missing one, so each amended/high-stakes decision is content-checked.
CONTENT_ANCHORS = {
    2: ["FHIR R4", "openEHR", "P3", "archetype-path"],
    7: ["residency_tr_media", "residency_tr_models", "capacity contract"],
    9: ["six tools", "preemption", "qwen-audio-agent"],
    10: ["residency_tr", "typed", "cascade_fast"],
    12: ["read-only", "acoustic", "investigation"],
    20: ["device_functions", "Class IIb"],
    21: ["self-hosted", "LICENSE blob", "4.9.1"],
    22: ["No accuracy claims", "docs/evidence/"],
    23: ["route", "register", "location", "no default"],
}


def _adr_file(n: int) -> Path:
    matches = sorted(ADR.glob(f"ADR-{n:03d}-*.md"))
    assert matches, f"missing ADR-{n:03d}"
    return matches[0]


def test_template_exists() -> None:
    text = _adr_file(0).read_text(encoding="utf-8")
    for section in ("## Context", "## Decision", "## Consequences"):
        assert section in text, f"ADR-000 template missing {section}"


def test_all_23_adrs_accepted_with_three_sections() -> None:
    for n in range(1, 24):
        text = _adr_file(n).read_text(encoding="utf-8")
        assert re.search(r"^Status:\s+Accepted", text, re.M), f"ADR-{n:03d} not Accepted"
        for section in ("## Context", "## Decision", "## Consequences"):
            assert section in text, f"ADR-{n:03d} missing {section}"


def test_amended_adrs_carry_their_amendment() -> None:
    for n in (2, 7, 10, 20):
        text = _adr_file(n).read_text(encoding="utf-8")
        assert "amended" in text.lower(), f"ADR-{n:03d} lost its amendment note"


def test_content_anchors() -> None:
    for n, anchors in CONTENT_ANCHORS.items():
        text = _adr_file(n).read_text(encoding="utf-8")
        for needle in anchors:
            assert needle in text, f"ADR-{n:03d} missing anchor {needle!r}"


def test_blueprint_files_present() -> None:
    files = REPO / "files"
    expected = [
        "00_STATE.md",
        "01_MARKET_AND_STRATEGY.md",
        "02_PRODUCT_SPEC.md",
        "03_ARCHITECTURE.md",
        "04_CLINICAL_PROTOCOLS.md",
        "05_ROADMAP.md",
        "06_COMPLIANCE_TR.md",
        "07_CLAUDE_CODE_MASTER_PROMPT.md",
        "08_ADMIN_CONSOLE_AND_OBSERVABILITY.md",
        "09_SPECIALTY_COVERAGE_AND_LEARNING.md",
        "10_SECURITY_AND_TECHNICAL_MONITORING.md",
        "11_ISSUE_BACKLOG.md",
        "12_DSL_V2_AND_RUNTIME_SPEC.md",
        "13_QUESTION_FLOW.md",
        "HUMAN_BLOCKERS.md",
        "README.md",
    ]
    for name in expected:
        assert (files / name).is_file(), f"files/{name} missing"
    assert (files / "protocols" / "base.life_threat.yaml").is_file()


def test_index_links_everything() -> None:
    index = (REPO / "docs" / "index.md").read_text(encoding="utf-8")
    for n in range(0, 24):
        assert re.search(rf"ADR-{n:03d}", index), f"docs/index.md does not link ADR-{n:03d}"
    for name in (
        "00_STATE.md",
        "HUMAN_BLOCKERS.md",
        "07_CLAUDE_CODE_MASTER_PROMPT.md",
        "13_QUESTION_FLOW.md",
        "base.life_threat.yaml",
    ):
        assert name in index, f"docs/index.md does not link {name}"
    for gov in ("CLAUDE.md", "LOOP.md", "GOALS.md", "DoD.md", "TDD.md", "PROGRESS.md"):
        assert gov in index, f"docs/index.md does not link {gov}"


# INT-332 — ADR-033 ratifies the motion system as revised in
# docs/design/motion/motion-verification.md, with its 00_STATE row and the
# mobile-ui.md §Motion pointer. Its five open questions were recorded
# awaiting-human with their named owners, each failing closed; the owner
# answered all five in chat on 17 Nov 2026 (D44). Q2-Q4 are physician
# questions answered as owner decisions under D18 (synthetic host and simulated
# patients only, a licensed physician's signature before any real patient).
# These tests pin the answered state and the bound of each decision, so a row
# reverted to awaiting-human fails and a decision widened past the answer fails.
MOTION_ANCHORS = [
    "motion-verification.md",
    "opacity",
    "120 ms",
    '["red", "yellowPill", "workChip", "railCommit", "content", "ambient"]',
    "snap, never queue",
    "hold, never rest",
    "exits are instant",
    "root layer",
    "150 ms",
    "invariant 21",
    "the one permitted co-occurrence",
]

MOTION_ANSWERED = "answered (owner, 17 Nov 2026)"
MOTION_ORB_SCALE_MAX = 1.06


class MotionQuestion(NamedTuple):
    hb_id: str
    owner: str
    label: str  # the short name the answer is quoted under
    answer: str  # the owner's words, verbatim
    decision: str  # the ADR table's Decision cell, exactly


MOTION_QUESTIONS = {
    "Q1": MotionQuestion(
        "HB-O10",
        "owner",
        "root layer",
        "yes",
        '*"yes"*: the root layer paints first, the emergency route serves re-entry only, '
        "and no RED is ever drawn as a push or a modal",
    ),
    "Q2": MotionQuestion(
        "HB-C26",
        "Dr Efe Onganer",
        "ALERT haptic",
        "ok yes",
        '*"ok yes"*: an `ALERT` RED may fire one warning haptic, only when the microphone '
        "is cold; CALM, SILENT and DEFERRED_CLINICIAN never do",
    ),
    "Q3": MotionQuestion(
        "HB-C27",
        "Dr Efe Onganer",
        "SILENT announcement",
        "yes",
        '*"yes"*: VoiceOver or TalkBack may announce the SILENT guidance; '
        "the app plays no audio of its own",
    ),
    "Q4": MotionQuestion(
        "HB-C28",
        "Dr Efe Onganer",
        "112 under UNKNOWN",
        "yes hidden",
        '*"yes hidden"*: withheld until "Şu anda hastanede misiniz?" is answered; unchanged',
    ),
    "Q5": MotionQuestion(
        "HB-O11",
        "owner",
        "orb scale",
        "yes, grow and shrink",
        '*"yes, grow and shrink"*: the orb may breathe with a scale of at most 1.06',
    ),
}

# The widenings and the issue that builds each; app code is not in INT-332.
MOTION_WIDENINGS = {"Q2": "INT-609", "Q3": "INT-610", "Q5": "INT-611"}
RED_REGISTERS = ("ALERT", "CALM", "SILENT", "DEFERRED_CLINICIAN")


def _motion_adr() -> str:
    return _adr_file(33).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = text.find("\n## ", start + len(heading))
    return text[start:] if nxt == -1 else text[start:nxt]


def _hb_row(hb_id: str) -> str:
    text = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith(f"| **{hb_id}** |")]
    assert len(rows) == 1, f"{hb_id} must appear exactly once in HUMAN_BLOCKERS.md"
    return rows[0]


def _state_row(d: str) -> str:
    state = (REPO / "files" / "00_STATE.md").read_text(encoding="utf-8")
    rows = [line for line in state.splitlines() if line.startswith(f"| **{d}** |")]
    assert len(rows) == 1, f"files/00_STATE.md §3 must carry {d} exactly once"
    return rows[0]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _quoted(q: str) -> str:
    m = MOTION_QUESTIONS[q]
    return f'{q} ({m.label}): *"{m.answer}"*'


def test_motion_adr_is_accepted_with_three_sections_and_its_anchors() -> None:
    text = _motion_adr()
    assert re.search(r"^Status:\s+Accepted", text, re.M), "ADR-033 not Accepted"
    for section in ("## Context", "## Decision", "## Consequences"):
        assert section in text, f"ADR-033 missing {section}"
    for needle in MOTION_ANCHORS:
        assert needle in text, f"ADR-033 missing anchor {needle!r}"


def test_motion_adr_never_lets_motion_delay_red() -> None:
    red = _section(_motion_adr(), "### 5. RED")
    for needle in ("0 ms", "never a native-stack push", "never an RN `Modal`", "ON_SITE"):
        assert needle in red, f"ADR-033 §5 missing {needle!r}"


def _question_gaps(line: str, q: str) -> list[str]:
    """What an ADR question row lacks against its answered decision.

    The row must read answered, name its HB row and owner, and carry the
    decision cell exactly: a word added to the decision is a widening.
    """
    m = MOTION_QUESTIONS[q]
    cells = _cells(line)
    if len(cells) != 6:
        return ["six cells"]
    _, _, owner, status, hb_id, decision = cells
    gaps = []
    if status != MOTION_ANSWERED:
        gaps.append(MOTION_ANSWERED)
    if hb_id != m.hb_id:
        gaps.append(m.hb_id)
    if m.owner not in owner:
        gaps.append(m.owner)
    if decision != m.decision:
        gaps.append("decision")
    return gaps


def test_motion_questions_are_answered_with_owner_and_decision() -> None:
    questions = _section(_motion_adr(), "## Open questions")
    assert "awaiting-human" not in questions, "an ADR-033 question still reads awaiting-human"
    assert "D18" in questions and "real patient" in questions, "Q2-Q4 must carry the D18 scope"
    for q in MOTION_QUESTIONS:
        lines = [line for line in questions.splitlines() if line.startswith(f"| **{q}** |")]
        assert len(lines) == 1, f"ADR-033 must record {q} exactly once"
        gaps = _question_gaps(lines[0], q)
        assert not gaps, f"ADR-033 {q} missing {gaps}"
    for q, issue in MOTION_WIDENINGS.items():
        assert issue in questions, f"ADR-033 must name {issue} as the issue building {q}"


def test_motion_hb_rows_are_closed_with_the_verbatim_answer() -> None:
    for q, m in MOTION_QUESTIONS.items():
        row = _hb_row(m.hb_id)
        assert "awaiting-human" not in row, f"{m.hb_id} still reads awaiting-human"
        cells = _cells(row)
        assert cells[-2].startswith("**closed 17 Nov 2026**"), f"{m.hb_id} is not closed"
        assert cells[-1].endswith("closed 17 Nov 2026"), f"{m.hb_id} date cell lacks the close"
        for needle in ("ADR-033", m.owner, _quoted(q)):
            assert needle in row, f"{m.hb_id} missing {needle!r}"
        if m.hb_id.startswith("HB-C"):
            assert "D18" in row and "real patient" in row, f"{m.hb_id} must carry the D18 scope"
        if q in MOTION_WIDENINGS:
            assert MOTION_WIDENINGS[q] in row, f"{m.hb_id} must name {MOTION_WIDENINGS[q]}"


def test_motion_answers_are_verbatim_in_the_evidence() -> None:
    evidence = (REPO / "docs" / "evidence" / "INT-332.md").read_text(encoding="utf-8")
    answers = _section(evidence, "## Answers (owner, 17 Nov 2026, in chat)")
    for q in MOTION_QUESTIONS:
        assert _quoted(q) in answers, f"docs/evidence/INT-332.md missing {_quoted(q)!r}"
    assert "D18" in answers and "D44" in answers


def _haptic_registers(adr: str) -> set[str]:
    """The registers ADR-033 §5 lets fire a RED haptic: the backticked ones in
    the first sentence of its `One RED haptic` bullet."""
    red = _section(adr, "### 5. RED")
    bullets = [line for line in red.splitlines() if line.startswith("- **One RED haptic.**")]
    assert len(bullets) == 1, "ADR-033 §5 must carry the One RED haptic bullet once"
    first = bullets[0].removeprefix("- **One RED haptic.**").split(". ", 1)[0]
    return {r for r in re.findall(r"`([A-Z_]+)`", first) if r in RED_REGISTERS}


def _orb_scales(text: str) -> list[float]:
    return [float(v) for v in re.findall(r"scale of at most (\d+(?:\.\d+)?)", text)]


def _widening_gaps(adr: str) -> list[str]:
    gaps = []
    if _haptic_registers(adr) != {"ALERT"}:
        gaps.append("haptic registers")
    if "only while the microphone is cold" not in _section(adr, "### 5. RED"):
        gaps.append("cold microphone")
    scales = _orb_scales(adr)
    if not scales or max(scales) > MOTION_ORB_SCALE_MAX:
        gaps.append("orb scale")
    red = _section(adr, "### 5. RED")
    if "no takeover, colour change or app audio" not in red:
        gaps.append("SILENT app audio")
    if "UNKNOWN mounts no location action" not in red:
        gaps.append("112 under UNKNOWN")
    if "never a native-stack push" not in red:
        gaps.append("root layer")
    return gaps


def test_motion_widenings_stay_within_the_answers() -> None:
    assert _widening_gaps(_motion_adr()) == []


def test_near_miss_a_reverted_or_widened_question_is_refused() -> None:
    questions = _section(_motion_adr(), "## Open questions")
    rows = {
        q: next(line for line in questions.splitlines() if line.startswith(f"| **{q}** |"))
        for q in MOTION_QUESTIONS
    }
    for q, row in rows.items():
        reverted = row.replace(MOTION_ANSWERED, "awaiting-human")
        assert MOTION_ANSWERED in _question_gaps(reverted, q), f"{q} reverted was accepted"
    widened = {
        "Q1": ("no RED is ever drawn as a push or a modal", "a RED may be drawn as a push"),
        "Q2": ("an `ALERT` RED", "an `ALERT` or `CALM` RED"),
        "Q3": ("the app plays no audio of its own", "the app may play its own audio"),
        "Q4": ("withheld until", "shown before"),
        "Q5": ("at most 1.06", "at most 1.08"),
    }
    for q, (old, new) in widened.items():
        assert old in rows[q], f"{q} near miss no longer applies"
        assert "decision" in _question_gaps(rows[q].replace(old, new), q), f"{q} widened"


def test_near_miss_a_widened_adr_body_is_refused() -> None:
    adr = _motion_adr()
    mutants = {
        "haptic registers": ("An `ALERT` RED may", "An `ALERT` or `CALM` RED may"),
        "cold microphone": ("only while the microphone is cold", "whatever the microphone"),
        "orb scale": ("a scale of at most 1.06 (Q5)", "a scale of at most 1.08 (Q5)"),
        "SILENT app audio": ("no takeover, colour change or app audio", "no takeover"),
        "112 under UNKNOWN": ("UNKNOWN mounts no location action", "UNKNOWN mounts 112"),
        "root layer": ("never a native-stack push", "sometimes a native-stack push"),
    }
    red = _section(adr, "### 5. RED")
    for gap, (old, new) in mutants.items():
        # Mutate the one place the rule lives: §5 for RED rules, else the whole ADR.
        scope = red if old in red else adr
        assert scope.count(old) == 1, f"near miss {gap!r} no longer applies"
        mutant = adr.replace(scope, scope.replace(old, new))
        assert gap in _widening_gaps(mutant), f"widened {gap!r} was accepted"


def test_motion_state_rows_and_mobile_ui_pointer() -> None:
    d40 = _state_row("D40")
    for needle in ("ADR-033", "INT-332", "D44", *(m.hb_id for m in MOTION_QUESTIONS.values())):
        assert needle in d40, f"D40 missing {needle!r}"
    d44 = _state_row("D44")
    for needle in (
        "ADR-033",
        "INT-332",
        "17 Nov 2026",
        "D18",
        "simulated patients only",
        "licensed physician",
        *(_quoted(q) for q in MOTION_QUESTIONS),
        *MOTION_WIDENINGS.values(),
        *(m.hb_id for m in MOTION_QUESTIONS.values()),
    ):
        assert needle in d44, f"D44 missing {needle!r}"
    assert "awaiting-human" not in d44
    state = (REPO / "files" / "00_STATE.md").read_text(encoding="utf-8")
    changelog = _section(state, "## 8. Changelog")
    assert any(line.startswith("| 17 Nov 2026 | **D44") for line in changelog.splitlines()), (
        "files/00_STATE.md §8 must log D44"
    )
    mobile = (REPO / "docs" / "design" / "mobile-ui.md").read_text(encoding="utf-8")
    motion = _section(mobile, "## Motion")
    assert "adr/ADR-033-motion-system-v1.md" in motion, "mobile-ui.md §Motion must point to ADR-033"
    index = (REPO / "docs" / "index.md").read_text(encoding="utf-8")
    assert "adr/ADR-033-motion-system-v1.md" in index, "docs/index.md must link ADR-033"


def test_motion_widenings_are_backlog_rows_not_app_code() -> None:
    issues = {
        i["id"]: i
        for i in yaml.safe_load(
            (REPO / "docs" / "backlog" / "issues.yaml").read_text(encoding="utf-8")
        )
    }
    for issue in MOTION_WIDENINGS.values():
        row = issues[issue]
        assert row["status"] == "todo", f"{issue} must be todo"
        assert "INT-332" in row["depends_on"], f"{issue} must depend on INT-332"
        assert row["acceptance"], f"{issue} needs acceptance lines"
    assert "1.06" in " ".join(issues["INT-611"]["acceptance"])
