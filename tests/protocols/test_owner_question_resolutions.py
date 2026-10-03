"""INT-470 — every INT-448 owner question is resolved exactly once.

INT-448 (CD-100..CD-106) recorded 31 sign-off packet items as
``owner_question`` because a packet listed the owner or the base owner as
their decider. Two things resolve them, and nothing else may:

- **CD-110** (owner decision D18, restated 3 Oct 2026): the clinical and
  interview-design questions are decided by sourced medical agents with an
  independent verifier, never sent back to the owner. CD-110 also decides the
  base-owner parts of five clinically decided rows.
- **D24** (files/00_STATE.md §3): the owner's 3 Oct 2026 answer to the
  product and data questions. Its legal and data follow-through is routed to
  the legal lane, never decided here.

The INT-448 rows keep their history: the outcome stays ``owner_question``
and the question text stays; the row gains a pointer to what resolved it,
and the resolver points back. Near misses: a pointer that dangles, an item
resolved twice, a resolution of an item already decided elsewhere, a missing
back-pointer, an owner answer the state file does not carry, and a
resolution that hands a part back to the owner all fail here.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from protocols.clinical_decisions import SCOPE, DecisionStatus, load_register

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "clinical" / "int448_signoff_items.json"
STATE = REPO_ROOT / "files" / "00_STATE.md"
CLINICAL_OUTCOMES = frozenset({"accept", "change", "reject", "draft_needs_source"})
RECORD_ID = re.compile(r"^CD-\d{2,3}$")
OWNER_DECISION_ID = re.compile(r"^D\d+$")
STATE_ROW = re.compile(r"^\|\s*\**(D\d+)\**\s*\|(.*)$")

_NT = "docs/evidence/verification/near-twin-sweep-582.md#L"
_WB = "docs/evidence/verification/cluster-wave-b.md#L"
_WA = "docs/evidence/verification/cluster-wave-a.md#L"
_353 = "docs/evidence/INT-353.md#L"
_W6 = "docs/evidence/verification/specialty-wave6-internal-mental.md#L"
_W7 = "docs/evidence/verification/specialty-wave7-onc-women-peds.md#L"
_W8 = "docs/evidence/verification/specialty-wave8-geriatric-dental.md#L"
_W9 = "docs/evidence/verification/specialty-wave9-occupational-public.md#L"
_SR = "docs/evidence/verification/sibling-rebinds-582.md#L"

# GitHub #798 scope: the clinical owner questions CD-110 decides.
CD110_OWNER_QUESTIONS = frozenset(
    {
        f"{_NT}95",  # T2 basvuru_nedeni against chief_complaint_text
        f"{_NT}96",  # T3 sikayet_suresi against duration
        f"{_NT}110",  # T17 onset_date against duration
        f"{_NT}185",  # T92 sikayet_suresi against onset_date
        f"{_WB}103",  # dental airway posture
        f"{_WB}104",  # pedodonti airway re-declaration
        f"{_WB}116",  # report-only visits and the base HPI
        f"{_353}314",  # radyoloji airway item, one question
        f"{_353}316",  # saglik_kurulu Q8
        f"{_353}432",  # FTR ates_var_mi routing
        f"{_W8}96",  # one dental airway posture
        f"{_SR}61",  # FTR ates_var_mi routing
        f"{_SR}118",  # ungated airway re-declarations
    }
)
# Base-owner parts of rows INT-448 already decided clinically.
CD110_OWNER_PARTS = frozenset(
    {
        f"{_NT}94",  # T1 lmp_date gate
        f"{_NT}97",  # T4 pregnancy_status as the gate of record
        f"{_353}315",  # pedodonti airway: is the item asked at all
        f"{_W7}93",  # no-complaint visits: base timing ask
        f"{_W8}94",  # recall visits: base timing ask
    }
)
# files/00_STATE.md D24: the owner's reply "1Y 2Y 3Y 4Y 5Y 6A", read per item.
D24_QUOTE = "1Y 2Y 3Y 4Y 5Y 6A"
D24_ANSWERS = {
    f"{_NT}104": "1Y",
    f"{_NT}105": "1Y",
    f"{_NT}106": "1Y",
    f"{_NT}107": "1Y",
    f"{_NT}108": "1Y",
    f"{_WB}77": "1Y",
    f"{_WB}105": "1Y",
    f"{_WB}117": "1Y",
    f"{_353}310": "1Y",
    f"{_W7}84": "2Y",
    f"{_W8}84": "2Y",
    f"{_W8}113": "2Y",
    f"{_WB}90": "3Y",
    f"{_W9}88": "4Y",
    f"{_WB}115": "4Y",
    f"{_W9}71": "5Y",
    f"{_W6}61": "6A",
}
# Every D24 item has a legal or data follow-through except the TRD/TTD one,
# which 6A answers by not taking a snapshot at all.
D24_WITHOUT_LEGAL_PART = frozenset({f"{_W6}61"})
# No owner answer covers cluster-wave-a #L128 (text_first before the INT-349
# rows): it is routed to the legal lane, not resolved (review of #804, finding 10).
LEGAL_LANE = "the legal lane (INT-471, GitHub #800)"
LEGAL_PART_PREFIX = "routed to the legal lane (INT-471, GitHub #800)"
ROUTED_TO_LEGAL_LANE = frozenset({f"{_WA}128"})
DECISION_NUMBER = re.compile(r"\bD\d+\b")
# The six questions as put to the owner on 3 Oct 2026, committed verbatim in
# docs/evidence/INT-470.md (review of #804, finding 11).
EVIDENCE = REPO_ROOT / "docs" / "evidence" / "INT-470.md"
OWNER_QUESTION_OPENINGS = (
    "1. Proxy answers (parent/carer answering for the patient):",
    "2. Family history, relatives' health and consanguinity = one sensitive section:",
    '3. "Do you hear voices others don\'t?" (mental-health Q16):',
    "4. Purpose scope: occupational clinics may ask sick leave, job tenure and household TB",
    "5. The read-aloud accommodation question (nursing-education Q10) may be spoken",
    "6. Turkish society guideline texts (TRD, TTD): A = cite international guidelines only,",
)

type Rows = Mapping[str, tuple[str, Mapping[str, Any]]]
type Resolutions = Mapping[str, list[Mapping[str, Any]]]


def resolution_problems(
    rows: Rows, resolutions: Resolutions, owner_rows: Mapping[str, str]
) -> list[str]:
    """Every way a resolution can be wrong, as one sentence each.

    ``rows`` maps an item to (the record that holds its INT-448 row, the
    row); ``resolutions`` maps a record id to its ``value.resolutions``;
    ``owner_rows`` maps an owner decision id (``D24``) to its row in
    files/00_STATE.md §3.
    """
    problems: list[str] = []
    counts: Counter[str] = Counter()
    for record, entries in resolutions.items():
        for resolution in entries:
            item = str(resolution.get("item", ""))
            counts[item] += 1
            problems.extend(_resolution_problems(record, item, resolution, rows))
    for item, (_record, row) in rows.items():
        resolver = row.get("resolved_by")
        part_resolver = row.get("owner_part_resolved_by")
        routed = row.get("routed_to")
        if resolver is not None and part_resolver is not None:
            problems.append(f"{item}: resolved as a whole and in part")
        if routed is not None:
            problems.extend(_routing_problems(item, row, str(routed)))
        if resolver is not None:
            if OWNER_DECISION_ID.match(str(resolver)):
                counts[item] += 1
            problems.extend(_pointer_problems(item, row, str(resolver), resolutions, owner_rows))
        if part_resolver is not None:
            if not str(row.get("owner_part", "")).strip():
                problems.append(f"{item}: owner_part_resolved_by on a row with no owner_part")
            problems.extend(_dangling(item, str(part_resolver), "owner_part", resolutions))
    problems.extend(f"{item}: resolved {n} times" for item, n in counts.items() if n > 1)
    return problems


def _resolution_problems(
    record: str, item: str, resolution: Mapping[str, Any], rows: Rows
) -> list[str]:
    problems: list[str] = []
    if item not in rows:
        return [f"{record}: resolves {item!r}, which no INT-448 row records"]
    home, row = rows[item]
    part = resolution.get("resolves")
    if resolution.get("record") != home:
        problems.append(f"{record} {item}: names record {resolution.get('record')!r}, not {home}")
    if part == "owner_question":
        if row.get("outcome") != "owner_question":
            problems.append(f"{record} {item}: already decided in {home}, not an owner question")
        if row.get("resolved_by") != record:
            problems.append(f"{record} {item}: {home} does not point back (resolved_by)")
    elif part == "owner_part":
        if row.get("outcome") == "owner_question" or not str(row.get("owner_part", "")).strip():
            problems.append(f"{record} {item}: {home} carries no owner part beside a decision")
        if row.get("owner_part_resolved_by") != record:
            problems.append(f"{record} {item}: {home} does not point back (owner_part_resolved_by)")
    else:
        problems.append(
            f"{record} {item}: resolves {part!r}, neither owner_question nor owner_part"
        )
    outcome = resolution.get("outcome")
    if outcome not in CLINICAL_OUTCOMES:
        problems.append(f"{record} {item}: outcome {outcome!r} is not a clinical decision")
    if outcome == "change" and not str(resolution.get("change", "")).strip():
        problems.append(f"{record} {item}: a change says what changes")
    if outcome in {"accept", "change", "reject"} and not resolution.get("sources"):
        problems.append(f"{record} {item}: a clinical outcome names its sources")
    if (outcome == "draft_needs_source") != (resolution.get("status") == "draft_needs_source"):
        problems.append(f"{record} {item}: outcome and status disagree on draft_needs_source")
    if "owner_part" in resolution:
        problems.append(f"{record} {item}: hands a part back to the owner (D18 restated)")
    return problems


def _pointer_problems(
    item: str,
    row: Mapping[str, Any],
    resolver: str,
    resolutions: Resolutions,
    owner_rows: Mapping[str, str],
) -> list[str]:
    problems: list[str] = []
    if row.get("outcome") != "owner_question":
        problems.append(f"{item}: resolved_by on a row decided as {row.get('outcome')!r}")
    if not str(row.get("owner_part", "")).strip():
        problems.append(f"{item}: a resolved owner question keeps its question (owner_part)")
    if RECORD_ID.match(resolver):
        problems.extend(_dangling(item, resolver, "owner_question", resolutions))
    elif OWNER_DECISION_ID.match(resolver):
        state_row = owner_rows.get(resolver)
        answer = row.get("owner_answer") or {}
        if state_row is None:
            problems.append(f"{item}: resolved_by {resolver}, which files/00_STATE.md §3 lacks")
        elif str(answer.get("quote", "")) not in state_row or not answer.get("quote"):
            problems.append(f"{item}: the owner's quote is not verbatim in {resolver}")
        elif not answer.get("answer") or str(answer["answer"]) not in state_row:
            problems.append(f"{item}: answer {answer.get('answer')!r} is not in {resolver}")
    else:
        problems.append(f"{item}: resolved_by {resolver!r} is neither a record nor a decision")
    return problems


def _routing_problems(item: str, row: Mapping[str, Any], routed: str) -> list[str]:
    problems: list[str] = []
    if routed != LEGAL_LANE:
        problems.append(f"{item}: routed_to {routed!r} is not {LEGAL_LANE}")
    if row.get("resolved_by") is not None:
        problems.append(f"{item}: routed and resolved at once")
    if row.get("outcome") != "owner_question":
        problems.append(f"{item}: routed_to on a row decided as {row.get('outcome')!r}")
    if not str(row.get("owner_part", "")).strip():
        problems.append(f"{item}: a routed owner question keeps its question (owner_part)")
    if not str(row.get("routing_note", "")).strip():
        problems.append(f"{item}: a routing says why it is not an owner answer")
    return problems


def legal_part_problems(texts: list[str], owner_rows: Mapping[str, str]) -> list[str]:
    """A legal part routes to the legal lane by issue, and any owner decision it
    names exists in files/00_STATE.md §3 (a D-number from another PR dangles)."""
    problems: list[str] = []
    for text in texts:
        if not text.startswith(LEGAL_PART_PREFIX):
            problems.append(f"{text[:60]!r}: does not route to {LEGAL_LANE}")
        for number in DECISION_NUMBER.findall(text):
            if number not in owner_rows:
                problems.append(f"{text[:60]!r}: names {number}, which files/00_STATE.md lacks")
    return problems


def _dangling(item: str, resolver: str, part: str, resolutions: Resolutions) -> list[str]:
    matches = [
        entry
        for entry in resolutions.get(resolver, ())
        if entry.get("item") == item and entry.get("resolves") == part
    ]
    if len(matches) != 1:
        return [f"{item}: {resolver} holds {len(matches)} {part} resolutions for it (dangling)"]
    return []


# --- the committed register ---------------------------------------------------


def _committed() -> tuple[Rows, Resolutions, dict[str, str]]:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    keys = {entry["key"] for entry in document["items"]}
    rows: dict[str, tuple[str, Mapping[str, Any]]] = {}
    resolutions: dict[str, list[Mapping[str, Any]]] = {}
    for record, decision in load_register().items():
        for entry in decision.value.get("items", ()):
            if entry["item"] in keys:
                rows[entry["item"]] = (record, entry)
        if decision.value.get("resolutions"):
            resolutions[record] = list(decision.value["resolutions"])
    return rows, resolutions, _owner_rows(STATE.read_text(encoding="utf-8"))


def _owner_rows(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        match = STATE_ROW.match(line)
        if match:
            rows[match.group(1)] = line
    return rows


def test_the_committed_register_resolves_without_a_problem() -> None:
    assert resolution_problems(*_committed()) == []


def test_every_int448_owner_question_is_resolved_and_keeps_its_history() -> None:
    rows, _, _ = _committed()
    open_questions = [
        item
        for item, (_, row) in rows.items()
        if row["outcome"] == "owner_question"
        and not row.get("resolved_by")
        and not row.get("routed_to")
    ]
    assert open_questions == []
    routed = {item for item, (_, row) in rows.items() if row.get("routed_to")}
    assert routed == ROUTED_TO_LEGAL_LANE
    assert sum(1 for _, row in rows.values() if row["outcome"] == "owner_question") == 31


def test_cd110_resolves_exactly_the_int470_scope() -> None:
    _, resolutions, _ = _committed()
    entries = resolutions["CD-110"]
    by_part: dict[str, set[str]] = {"owner_question": set(), "owner_part": set()}
    for entry in entries:
        by_part[entry["resolves"]].add(entry["item"])
    assert by_part["owner_question"] == CD110_OWNER_QUESTIONS
    assert by_part["owner_part"] == CD110_OWNER_PARTS
    assert set(resolutions) == {"CD-110"}, "only CD-110 resolves INT-448 items"


def test_d24_resolves_exactly_the_owner_reply_items() -> None:
    rows, _, owner_rows = _committed()
    resolved = {
        item: row["owner_answer"]["answer"]
        for item, (_, row) in rows.items()
        if row.get("resolved_by") == "D24"
    }
    assert resolved == D24_ANSWERS
    assert {
        row["owner_answer"]["quote"] for item, (_, row) in rows.items() if item in resolved
    } == {D24_QUOTE}
    assert D24_QUOTE in owner_rows["D24"]
    assert "17" in owner_rows["D24"] and "#L128" not in owner_rows["D24"]


def test_the_six_owner_questions_are_committed_with_channel_and_date() -> None:
    text = EVIDENCE.read_text(encoding="utf-8")
    for opening in OWNER_QUESTION_OPENINGS:
        assert opening in text, opening
    assert "orchestrator → main conversation → owner in chat, 3 Oct 2026" in text


def _legal_texts() -> list[str]:
    rows, resolutions, _ = _committed()
    texts = [str(row["legal_part"]) for _, row in rows.values() if row.get("legal_part")]
    texts += [str(e["legal_part"]) for e in resolutions["CD-110"] if e.get("legal_part")]
    return texts


def test_every_legal_part_routes_by_issue_and_names_no_missing_decision() -> None:
    _, _, owner_rows = _committed()
    texts = _legal_texts()
    assert len(texts) == 17
    assert legal_part_problems(texts, owner_rows) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("routed to the legal lane (D25, INT-471 #800): rows", "does not route"),
        (f"{LEGAL_PART_PREFIX}: as D25 decides", "names D25"),
        ("routed to counsel: rows", "does not route"),
    ],
)
def test_a_legal_part_naming_a_missing_decision_or_no_issue_fails(text: str, expected: str) -> None:
    problems = legal_part_problems([text], {"D24": "| **D24** |"})
    assert any(expected in problem for problem in problems), problems


def test_legal_and_data_follow_through_is_routed_not_decided() -> None:
    rows, resolutions, _ = _committed()
    for item in D24_ANSWERS:
        legal = str(rows[item][1].get("legal_part", "")).strip()
        assert bool(legal) is (item not in D24_WITHOUT_LEGAL_PART), item
    pedodonti = next(e for e in resolutions["CD-110"] if e["item"] == f"{_WB}104")
    assert str(pedodonti.get("legal_part", "")).strip(), "HB-L20 minors go to the legal lane"


def test_cd110_is_a_d18_record_and_never_a_signoff() -> None:
    decision = load_register()["CD-110"]
    assert decision.scope == SCOPE
    assert decision.status is DecisionStatus.ACTIVE
    assert "items" not in decision.value, "CD-110 resolves rows; it records no packet item"


# --- near misses: each wrong shape fails ----------------------------------------


def _fixture() -> tuple[
    dict[str, tuple[str, dict[str, Any]]], dict[str, list[dict[str, Any]]], dict[str, str]
]:
    rows: dict[str, tuple[str, dict[str, Any]]] = {
        "a": ("CD-100", {"outcome": "owner_question", "owner_part": "q", "resolved_by": "CD-110"}),
        "b": (
            "CD-101",
            {"outcome": "change", "owner_part": "q", "owner_part_resolved_by": "CD-110"},
        ),
        "c": (
            "CD-102",
            {
                "outcome": "owner_question",
                "owner_part": "q",
                "resolved_by": "D24",
                "owner_answer": {"quote": "1Y 2Y", "answer": "1Y"},
            },
        ),
        "d": ("CD-103", {"outcome": "accept"}),
        "e": (
            "CD-102",
            {
                "outcome": "owner_question",
                "owner_part": "q",
                "routed_to": LEGAL_LANE,
                "routing_note": "no owner answer covers it",
            },
        ),
    }
    resolutions = {
        "CD-110": [
            _resolution("a", "CD-100", "owner_question"),
            _resolution("b", "CD-101", "owner_part"),
        ]
    }
    return rows, resolutions, {"D24": '| **D24** | owner: *"1Y 2Y"* |'}


def _resolution(item: str, record: str, part: str) -> dict[str, Any]:
    return {
        "item": item,
        "record": record,
        "resolves": part,
        "outcome": "change",
        "change": "x",
        "sources": ["S"],
        "status": "active",
    }


def test_the_near_miss_fixture_itself_is_clean() -> None:
    assert resolution_problems(*_fixture()) == []


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("dangling_record", "dangling"),
        ("dangling_owner_decision", "lacks"),
        ("resolved_twice", "resolved 2 times"),
        ("decided_elsewhere", "already decided"),
        ("no_back_pointer", "does not point back"),
        ("quote_not_verbatim", "not verbatim"),
        ("answer_not_in_decision", "is not in D24"),
        ("hands_back_to_owner", "hands a part back"),
        ("history_erased", "keeps its question"),
        ("owner_question_and_decision_disagree", "resolved_by on a row decided"),
        ("part_on_a_row_without_one", "no owner_part"),
        ("unknown_item", "no INT-448 row"),
        ("wrong_home_record", "names record"),
        ("routed_elsewhere", "is not the legal lane"),
        ("routed_and_resolved", "routed and resolved"),
        ("routed_without_reason", "says why"),
    ],
)
def test_each_wrong_resolution_fails(case: str, expected: str) -> None:
    rows, resolutions, owner_rows = _fixture()
    if case == "dangling_record":
        rows["a"][1]["resolved_by"] = "CD-111"
    elif case == "dangling_owner_decision":
        rows["c"][1]["resolved_by"] = "D25"
    elif case == "resolved_twice":
        resolutions["CD-112"] = [_resolution("a", "CD-100", "owner_question")]
    elif case == "decided_elsewhere":
        resolutions["CD-110"].append(_resolution("d", "CD-103", "owner_question"))
    elif case == "no_back_pointer":
        del rows["a"][1]["resolved_by"]
    elif case == "quote_not_verbatim":
        rows["c"][1]["owner_answer"] = {"quote": "1Y 2N", "answer": "1Y"}
    elif case == "answer_not_in_decision":
        rows["c"][1]["owner_answer"] = {"quote": "1Y 2Y", "answer": "7Y"}
    elif case == "hands_back_to_owner":
        resolutions["CD-110"][0]["owner_part"] = "Owner: decide."
    elif case == "history_erased":
        del rows["a"][1]["owner_part"]
    elif case == "owner_question_and_decision_disagree":
        rows["a"][1]["outcome"] = "change"
    elif case == "part_on_a_row_without_one":
        rows["d"][1]["owner_part_resolved_by"] = "CD-110"
    elif case == "unknown_item":
        resolutions["CD-110"].append(_resolution("zz", "CD-100", "owner_question"))
    elif case == "wrong_home_record":
        resolutions["CD-110"][0]["record"] = "CD-101"
    elif case == "routed_elsewhere":
        rows["e"][1]["routed_to"] = "D25"
    elif case == "routed_and_resolved":
        rows["e"][1]["resolved_by"] = "D24"
        rows["e"][1]["owner_answer"] = {"quote": "1Y 2Y", "answer": "1Y"}
    elif case == "routed_without_reason":
        del rows["e"][1]["routing_note"]
    problems = resolution_problems(rows, resolutions, owner_rows)
    assert any(expected in problem for problem in problems), problems
