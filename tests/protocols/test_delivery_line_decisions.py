"""INT-447 — INT-414's 48 delivery lines, each a verified entry in CD-19..CD-23.

Owner decision D18 (INT-432): a medical-author agent and an independent
verifier agent sign patient-facing clinical copy for simulated-patient testing
only; a licensed physician reviews before any real patient. INT-414 (#726)
wraps each verbatim question in a welcome, lead-ins, transitions,
acknowledgements and a closing, and listed the 48 lines for review in
docs/evidence/INT-414.md. CD-19..CD-23 hold one entry per line.

This file pins what those records claim, and holds the recorded Turkish to
the same bar the delivery deck is spoken under:

- every row of the INT-414 table has exactly one entry, under one key;
- every entry records all six checks as passed, the author's verdict and
  the independent verifier's verdict, and a changed line names what it
  replaced;
- every recorded line passes PolicyGuard on the dynamic path, asks nothing
  (no ``?``, no mı/mi/mu/mü, no interrogative opening), carries no numeral,
  stays inside the B1 sentence bound and the siz register, and an
  acknowledgement is at most five words.

Each rule has a near-miss twin that the same checker refuses, so a checker
that stopped looking would fail here rather than pass everything.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

import pytest
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.guard_lexicons.tr import B1_MAX_WORDS_PER_SENTENCE
from intake_voice_runtime.talker.policy_guard import (
    FormOfAddress,
    PolicyGuard,
    policy_guard_for,
)
from protocols.clinical_decisions import (
    ClinicalDecision,
    DecisionStatus,
    VerifierVerdict,
    load_register,
)

DELIVERY_RECORDS: Final = ("CD-19", "CD-20", "CD-21", "CD-22", "CD-23")
TABLE_ROWS: Final = 48
CHECKS: Final = (
    "policyguard",
    "b1_plain_language",
    "siz_register",
    "not_a_question",
    "no_numerals",
    "fits_context",
)
ACK_SEGMENTS: Final = (".thanks.", ".hesitant.", ".revised.")
MAX_ACK_WORDS: Final = 5
SIGNED: Final = frozenset({VerifierVerdict.AGREE, VerifierVerdict.AGREE_WITH_CHANGES})

#: The mı/mi/mu/mü clitic as a whole token, bare or with a person/tense tail
#: (the same reader tests/release/test_delivery_copy.py uses).
_PARTICLE: Final = re.compile(
    r"^m[ıiuü](?:s[ıiuü]n(?:[ıiuü]z)?|y[ıiuü][mz]|yd[ıiuü]|ym[ıiuü]ş|d[ıiuü]r)?$"
)
#: Interrogative words that, opening a line, make a listener hear a question
#: before the sentence resolves (CD-22, sensitiveLead.b).
_INTERROGATIVE_OPENERS: Final = frozenset(
    {"nasıl", "ne", "neden", "niçin", "niye", "kim", "hangi", "nerede", "nereye", "kaç"}
)
#: The second person singular pronoun in its common case forms.
_SEN_FORMS: Final = frozenset({"sen", "senin", "sana", "seni", "sende", "senden", "seninle"})


@pytest.fixture(scope="module")
def guard() -> PolicyGuard:
    return policy_guard_for(
        locale="tr", profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SIZ
    )


def _records() -> Mapping[str, ClinicalDecision]:
    register = load_register()
    return {cd: register[cd] for cd in DELIVERY_RECORDS}


RECORDS: Final = _records()
LINES: Final[tuple[tuple[str, Mapping[str, Any]], ...]] = tuple(
    (cd, line) for cd, record in RECORDS.items() for line in record.value["lines"]
)


def _tokens(text: str) -> list[str]:
    return [re.sub(r"^\W+|\W+$", "", token).casefold() for token in text.split()]


def line_defects(key: str, tr: str, en: str, guard: PolicyGuard) -> list[str]:
    """Every rule a delivery line breaks; empty when it passes all of them."""
    defects: list[str] = []
    verdict = guard.filter(tr, scripted=False)
    if verdict.violations or verdict.dropped or verdict.bridge_required:
        defects.append("policyguard")
    tokens = _tokens(tr)
    if "?" in tr or any(_PARTICLE.match(token) for token in tokens):
        defects.append("question")
    if tokens and tokens[0] in _INTERROGATIVE_OPENERS:
        defects.append("interrogative_opening")
    if any(guard.inspect_sentence(sentence) for sentence in guard.sentences(tr)):
        defects.append("guard_sentence")
    if re.search(r"\d", tr) or re.search(r"\d", en):
        defects.append("numeral")
    sentences = guard.sentences(tr)
    if not 1 <= len(sentences) <= 2 or any(
        len(sentence.split()) > B1_MAX_WORDS_PER_SENTENCE for sentence in sentences
    ):
        defects.append("b1_length")
    if any(segment in key for segment in ACK_SEGMENTS) and len(tr.split()) > MAX_ACK_WORDS:
        defects.append("acknowledgement_length")
    if any(token in _SEN_FORMS for token in tokens):
        defects.append("sen_register")
    return defects


def test_every_row_of_the_int414_table_has_exactly_one_entry() -> None:
    rows = sorted(line["row"] for _, line in LINES)
    assert rows == list(range(1, TABLE_ROWS + 1))
    keys = [line["key"] for _, line in LINES]
    assert len(set(keys)) == TABLE_ROWS
    for cd, record in RECORDS.items():
        assert record.value["line_count"] == len(record.value["lines"]), cd


def test_each_record_is_active_sourced_and_independently_signed() -> None:
    for cd, record in RECORDS.items():
        assert record.status is DecisionStatus.ACTIVE, cd
        assert record.sources, cd
        assert record.verifier.verdict in SIGNED, cd
        assert record.verifier.role and "independent" in record.verifier.role, cd
        assert record.author_role != record.verifier.role, cd


def test_each_entry_records_six_passed_checks_and_both_verdicts() -> None:
    for cd, line in LINES:
        assert line["checks"] == dict.fromkeys(CHECKS, "pass"), (cd, line["key"])
        assert line["author_verdict"] in {"approve", "change"}, (cd, line["key"])
        assert line["verifier_verdict"] in {"agree", "agree_with_changes"}, (cd, line["key"])


def test_a_changed_line_names_what_it_replaced_and_an_approved_one_does_not() -> None:
    changed = {key for record in RECORDS.values() for key in record.value["changed"]}
    for cd, line in LINES:
        if line["author_verdict"] == "change":
            assert line["key"] in changed, (cd, line["key"])
            assert line["previous_tr"] and line["previous_tr"] != line["tr"], (cd, line["key"])
        else:
            assert line["key"] not in changed, (cd, line["key"])
            assert "previous_tr" not in line, (cd, line["key"])
    # Non-vacuous: CD-22 rewords exactly one line, so the branch above is taken.
    assert changed


@pytest.mark.parametrize(("cd", "line"), LINES, ids=[line["key"] for _, line in LINES])
def test_each_recorded_line_passes_every_rule(
    cd: str, line: Mapping[str, Any], guard: PolicyGuard
) -> None:
    assert line_defects(line["key"], line["tr"], line["en"], guard) == [], (cd, line["key"])


@pytest.mark.parametrize(
    ("key", "tr", "defect"),
    [
        ("dialogue.delivery.lead.a", "Devam edelim mi?", "question"),
        ("dialogue.delivery.lead.a", "Devam edelim mi.", "question"),
        ("dialogue.delivery.hesitant.a", "Merak etmeyin, geçer.", "policyguard"),
        ("dialogue.delivery.pain.b", "Ağrınızla ilgili 3 ayrıntı soralım.", "numeral"),
        (
            "dialogue.delivery.sensitiveLead.b",
            "Nasıl rahat ediyorsanız öyle yanıtlayabilirsiniz.",
            "interrogative_opening",
        ),
        (
            "dialogue.delivery.thanks.c",
            "Not aldım, size çok teşekkür ederim.",
            "acknowledgement_length",
        ),
        (
            "dialogue.delivery.lead.d",
            "Bir de şunu öğrenmek istiyorum çünkü bu bilgi muayeneniz sırasında "
            "hekimin önünde hazır duran notun önemli bir parçası.",
            "b1_length",
        ),
        (
            "dialogue.delivery.orientTyped.a",
            "Sen soruları kendi hızında yanıtlayabilirsin.",
            "sen_register",
        ),
    ],
)
def test_the_checker_refuses_each_near_miss(
    key: str, tr: str, defect: str, guard: PolicyGuard
) -> None:
    assert defect in line_defects(key, tr, "", guard)


def test_the_line_cd22_replaced_is_refused_and_its_replacement_admitted(
    guard: PolicyGuard,
) -> None:
    (entry,) = [line for _, line in LINES if line["key"] == "dialogue.delivery.sensitiveLead.b"]
    assert line_defects(entry["key"], entry["previous_tr"], entry["en"], guard)
    assert line_defects(entry["key"], entry["tr"], entry["en"], guard) == []
