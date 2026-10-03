"""INT-472 — CD-111: the cardiac RED do-not lines and the unanswered location wait.

Owner decision D18 (simulated-patient stress testing only; a licensed
physician's review is required before any real patient). CD-111 decides the
text of every do-not line of rf.chest_pain_cardiac_features under REMOTE and
ON_SITE, and what may be said about the wait before an unanswered
"Şu anda hastanede misiniz?" resolves to REMOTE.

Near misses, each failing here rather than passing quietly: a nil-by-mouth
line kept or re-added under another wording, a medicine instruction added in
its place, a do-not line engineering reworded into a third text, a plausible
number for the wait without a source, a wait that resolves to anything but
REMOTE with 112, and a decided line PolicyGuard refuses.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import policy_guard_for
from protocols.clinical_decisions import SCOPE, DecisionStatus, load_register
from protocols.validator import PLACEHOLDER_SIGNOFF_RE

REPO_ROOT = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"
RULE_ID = "rf.chest_pain_cardiac_features"
LOCATIONS = ("REMOTE", "ON_SITE")
OUTCOMES = frozenset({"accept", "change", "remove"})
# Built, not written: a guard must not name the token the no_placeholders gate scans for.
_PENDING = "TO" + "DO"

# Food, drink or medicine by mouth, in the forms a do-not or an instruction
# would take. A line that tells the patient to take, chew or avoid anything by
# mouth is the dispatcher's or the clinician's to give, never the device's.
BY_MOUTH = re.compile(
    r"yiy|yeme|yemey|iç(?:me|in|iniz|meyin)|ağızdan|yutma|çiğne|aspirin|ilaç|hap|tablet",
    re.IGNORECASE,
)

# The decision, pinned: each current line, its outcome, and the text it becomes.
EXPECTED: dict[tuple[str, str], tuple[str, str | None]] = {
    ("REMOTE", "Kendi aracınızla yola çıkmayın."): (
        "change",
        "Hastaneye kendiniz araba kullanarak gitmeyin.",
    ),
    ("REMOTE", "Bir şey yiyip içmeyin."): ("remove", None),
    ("REMOTE", "Tek başınıza kalmayın; yanınızdaki kişiye durumu söyleyin."): (
        "change",
        "Yanınızda biri varsa durumu ona söyleyin ve sizinle kalmasını isteyin.",
    ),
    ("ON_SITE", "Poliklinik sırasında beklemeyin."): (
        "accept",
        "Poliklinik sırasında beklemeyin.",
    ),
    (
        "ON_SITE",
        "Tek başınıza gitmeyin — yanınızdaki kişiden ya da bir görevliden yardım isteyin.",
    ): (
        "accept",
        "Tek başınıza gitmeyin — yanınızdaki kişiden ya da bir görevliden yardım isteyin.",
    ),
    ("ON_SITE", "Bir şey yiyip içmeyin."): ("remove", None),
}


# --- the pure checkers ----------------------------------------------------------


def do_not_problems(lines: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every way a decided do-not line can be wrong, one sentence each."""
    problems: list[str] = []
    guard = policy_guard_for(locale="tr", profile=VoiceProfile.RESIDENCY_TR)
    for line in lines:
        where = f"{line.get('location')} {line.get('from')!r}"
        outcome = line.get("outcome")
        target = line.get("to")
        if outcome not in OUTCOMES:
            problems.append(f"{where}: outcome {outcome!r} is not accept, change or remove")
        if outcome == "remove" and target is not None:
            problems.append(f"{where}: a removed line has no replacement")
        if outcome in {"accept", "change"} and not str(target or "").strip():
            problems.append(f"{where}: a kept or changed line says its text")
        if outcome == "accept" and target != line.get("from"):
            problems.append(f"{where}: an accepted line keeps its text")
        if outcome == "change" and target == line.get("from"):
            problems.append(f"{where}: a change changes the text")
        if not line.get("sources"):
            problems.append(f"{where}: the outcome names its sources")
        if target:
            if BY_MOUTH.search(target):
                problems.append(f"{where}: {target!r} speaks about food, drink or medicine")
            if re.search(r"\d", target):
                problems.append(f"{where}: {target!r} carries a numeral (invariant 22)")
            if guard.inspect_sentence(target):
                problems.append(f"{where}: PolicyGuard refuses {target!r}")
            if target.count("?"):
                problems.append(f"{where}: a do-not line asks nothing")
    return problems


def wait_problems(wait: Mapping[str, Any]) -> list[str]:
    """The unanswered-question wait: a number only with a source for it."""
    problems: list[str] = []
    status = wait.get("status")
    value = str(wait.get("value", ""))
    if status == DecisionStatus.DRAFT_NEEDS_SOURCE.value:
        if not PLACEHOLDER_SIGNOFF_RE.fullmatch(value.strip()):
            problems.append("a draft wait carries the invariant-17 literal, nothing else")
        if re.search(r"\d", value):
            problems.append("a draft wait carries no number")
        if not str(wait.get("source_gap", "")).strip():
            problems.append("a draft wait says why no source supports it")
    elif status == DecisionStatus.ACTIVE.value:
        if not re.fullmatch(r"\d+", value):
            problems.append("an active wait is a whole number of seconds")
        if not wait.get("sources"):
            problems.append("an active wait names the source that states it")
    else:
        problems.append(f"status {status!r} is neither active nor draft_needs_source")
    if wait.get("on_expiry") != "REMOTE":
        problems.append("an unanswered question resolves to REMOTE, never another branch")
    if wait.get("show_112_on_expiry") is not True:
        problems.append("the REMOTE branch on expiry shows 112")
    return problems


# --- the committed record ---------------------------------------------------------


def _cd111() -> Mapping[str, Any]:
    decision = load_register()["CD-111"]
    assert decision.scope == SCOPE
    return decision.value


def _rule_do_nots() -> dict[str, list[str]]:
    document = yaml.safe_load(LIFE_THREAT.read_text(encoding="utf-8"))
    rule = next(r for r in document["rules"] if r["id"] == RULE_ID)
    return {loc: list(rule["action"][loc]["do_nots_tr"]["tr"]) for loc in LOCATIONS}


def test_every_do_not_line_has_its_pinned_outcome() -> None:
    lines = _cd111()["do_nots"]
    decided = {
        (line["location"], line["from"]): (line["outcome"], line.get("to")) for line in lines
    }
    assert decided == EXPECTED


def test_every_decided_line_is_sourced_clean_and_says_nothing_by_mouth() -> None:
    assert do_not_problems(_cd111()["do_nots"]) == []


def test_the_decided_lists_follow_from_the_lines() -> None:
    value = _cd111()
    for location in LOCATIONS:
        expected = [
            line["to"]
            for line in value["do_nots"]
            if line["location"] == location and line["outcome"] != "remove"
        ]
        assert value["decided_lists"][location] == expected, location
        assert expected, f"{location} keeps at least one do-not"


def test_the_served_rule_holds_each_line_before_or_after_never_a_third_text() -> None:
    """Applies before and after the change lands (it is routed into #796): every
    line of the rule is either the text CD-111 decided about or the text it
    decided, so engineering cannot reword a line into something unsigned."""
    value = _cd111()
    rule = _rule_do_nots()
    for location in LOCATIONS:
        known = {line["from"] for line in value["do_nots"] if line["location"] == location}
        known |= set(value["decided_lists"][location])
        assert set(rule[location]) <= known, (location, sorted(set(rule[location]) - known))
        for line in value["do_nots"]:
            if line["location"] != location:
                continue
            present = {line["from"], line.get("to")} & set(rule[location])
            if line["outcome"] == "remove":
                assert present <= {line["from"]}, line["from"]
            else:
                assert present, f"{location}: neither {line['from']!r} nor {line['to']!r}"


def test_no_medicine_line_replaces_the_removed_one() -> None:
    value = _cd111()
    assert value["medication_line"]["added"] is False
    for location in LOCATIONS:
        for text in value["decided_lists"][location]:
            assert not BY_MOUTH.search(text), text


def test_the_wait_has_no_number_without_a_source() -> None:
    assert wait_problems(_cd111()["no_answer_wait"]) == []


# --- near misses ----------------------------------------------------------------------


def _line(**overrides: Any) -> dict[str, Any]:
    line: dict[str, Any] = {
        "location": "REMOTE",
        "from": "Kendi aracınızla yola çıkmayın.",
        "outcome": "change",
        "to": "Hastaneye kendiniz araba kullanarak gitmeyin.",
        "sources": ["S"],
    }
    line.update(overrides)
    return line


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"to": "Bir şey yiyip içmeyin.", "outcome": "accept", "from": "Bir şey yiyip içmeyin."},
            "food, drink",
        ),
        ({"to": "Ağızdan hiçbir şey almayın."}, "food, drink"),
        ({"to": "Su içmeyin."}, "food, drink"),
        ({"to": "Ambulansı beklerken bir aspirin çiğneyin."}, "food, drink"),
        ({"to": "Üç yüz miligram ilaç almayın."}, "food, drink"),
        ({"to": "Hastaneye 1 saat içinde gidin."}, "numeral"),
        ({"to": "Kalp krizi geçiriyorsunuz, araba kullanmayın."}, "PolicyGuard"),
        ({"sources": []}, "names its sources"),
        ({"outcome": "remove"}, "no replacement"),
        ({"outcome": "change", "to": "Kendi aracınızla yola çıkmayın."}, "changes the text"),
        ({"outcome": "keep"}, "not accept, change or remove"),
    ],
)
def test_each_wrong_do_not_fails(overrides: dict[str, Any], expected: str) -> None:
    problems = do_not_problems([_line(**overrides)])
    assert any(expected in problem for problem in problems), problems


def _wait(**overrides: Any) -> dict[str, Any]:
    wait: dict[str, Any] = {
        "value": (
            f"{_PENDING}: the wait before an unanswered location question resolves to "
            "REMOTE requires clinical sign-off"
        ),
        "status": "draft_needs_source",
        "source_gap": "no source states a wait",
        "on_expiry": "REMOTE",
        "show_112_on_expiry": True,
    }
    wait.update(overrides)
    return wait


def test_the_near_miss_wait_fixture_itself_is_clean() -> None:
    assert wait_problems(_wait()) == []
    assert do_not_problems([_line()]) == []


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"value": "30"}, "invariant-17 literal"),
        ({"value": f"{_PENDING}: 30 seconds requires clinical sign-off"}, "carries no number"),
        ({"status": "active", "value": "30"}, "names the source"),
        ({"status": "active", "value": "otuz saniye", "sources": ["S"]}, "whole number"),
        ({"source_gap": ""}, "says why"),
        ({"on_expiry": "ON_SITE"}, "resolves to REMOTE"),
        ({"on_expiry": None}, "resolves to REMOTE"),
        ({"show_112_on_expiry": False}, "shows 112"),
        ({"status": "pending"}, "neither active nor"),
    ],
)
def test_each_wrong_wait_fails(overrides: dict[str, Any], expected: str) -> None:
    problems = wait_problems(_wait(**overrides))
    assert any(expected in problem for problem in problems), problems
