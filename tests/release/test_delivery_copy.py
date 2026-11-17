"""INT-414 — every conversational delivery line through the canonical PolicyGuard.

Invariant 2 says patient-facing text passes PolicyGuard, and the guard is
Python. ``test_i18n_complete.py`` already runs the whole catalogue through
``inspect_sentence`` and pins the findings; this file holds the delivery lines
to the STRICTER bar they are spoken under:

- each line passes ``PolicyGuard.filter(..., scripted=False)`` — the DYNAMIC
  path, where a violation drops the sentence — with no violation, nothing
  dropped and no bridge. A delivery line is catalogue copy, but it is chosen at
  run time, so it is held to the rule for text the Talker chooses, not the
  report-only rule for authored scripts;
- it asks nothing: no ``?``, and no question by the guard's own count, because
  the question that follows it is the turn's one question;
- it carries no numeral (invariant 22) and no sentence over the B1 bound;
- an acknowledgement is at most five words (files/03 §4.2, the Talker's own
  bound for an empathic acknowledgement);
- the server's George allow-list (``intake_api.dev_voice_delivery``) is the
  Turkish catalogue, byte for byte, for every key it admits.

The lines are listed for clinician review in docs/evidence/INT-414.md under
HB-C1. Passing here is not that review and is not recorded as one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

import pytest
from intake_api.dev_voice_delivery import DELIVERY_TR, delivery_text_hashes
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.guard_lexicons.tr import B1_MAX_WORDS_PER_SENTENCE
from intake_voice_runtime.talker.policy_guard import (
    FormOfAddress,
    PolicyGuard,
    policy_guard_for,
)
from protocols.dsl import clip_text_hash

REPO = Path(__file__).resolve().parents[2]
I18N = REPO / "apps" / "mobile" / "src" / "lib" / "i18n"

#: The same entry reader test_i18n_complete.py uses: a value may wrap onto the
#: line after its key.
_ENTRY = re.compile(r'^  "([^"]+)":\s*\n?\s*("(?:[^"\\]|\\.)*"),?\s*$', re.M)

#: The delivery deck's own namespace, plus the one INT-293 line it reuses as
#: the first repair variant.
_DELIVERY_PREFIX: Final = "dialogue.delivery."
_REUSED: Final = frozenset({"dialogue.notUnderstood"})

#: Slots whose lines are acknowledgements (deliveryDeck.ts ACKNOWLEDGEMENT_SLOTS).
_ACK_SEGMENTS: Final = (".thanks.", ".hesitant.", ".revised.")
MAX_ACK_WORDS: Final = 5

#: The mı/mi/mu/mü clitic as a whole token, bare or with a person/tense tail.
_PARTICLE = re.compile(
    r"^m[ıiuü](?:s[ıiuü]n(?:[ıiuü]z)?|y[ıiuü][mz]|yd[ıiuü]|ym[ıiuü]ş|d[ıiuü]r)?$"
)


def _catalogue(locale: str) -> dict[str, str]:
    text = (I18N / f"{locale}.ts").read_text(encoding="utf-8")
    return {m.group(1): json.loads(m.group(2)) for m in _ENTRY.finditer(text)}


def _delivery(catalogue: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in catalogue.items()
        if key.startswith(_DELIVERY_PREFIX) or key in _REUSED
    }


TR: Final = _catalogue("tr")
DELIVERY: Final = _delivery(TR)


@pytest.fixture(scope="module")
def guard() -> PolicyGuard:
    return policy_guard_for(
        locale="tr", profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SIZ
    )


def test_the_deck_is_read_whole() -> None:
    # Non-vacuous: every slot has at least two variants, so a reader that
    # stopped matching would collapse this well below the deck's size.
    assert len(DELIVERY) > 40
    assert set(_delivery(_catalogue("en"))) == set(DELIVERY)


@pytest.mark.parametrize("key", sorted(DELIVERY))
def test_each_line_passes_policyguard_on_the_dynamic_path(key: str, guard: PolicyGuard) -> None:
    verdict = guard.filter(DELIVERY[key], scripted=False)
    assert verdict.violations == (), (key, verdict.violations)
    assert verdict.dropped == ()
    assert not verdict.bridge_required
    assert verdict.text_tr == " ".join(guard.sentences(DELIVERY[key]))


@pytest.mark.parametrize("key", sorted(DELIVERY))
def test_each_line_asks_nothing(key: str, guard: PolicyGuard) -> None:
    value = DELIVERY[key]
    assert "?" not in value
    tokens = [re.sub(r"^\W+|\W+$", "", token).casefold() for token in value.split()]
    assert not [token for token in tokens if _PARTICLE.match(token)], key
    for sentence in guard.sentences(value):
        assert not guard.inspect_sentence(sentence), key


@pytest.mark.parametrize("key", sorted(DELIVERY))
def test_each_line_is_short_and_numeral_free(key: str, guard: PolicyGuard) -> None:
    value = DELIVERY[key]
    assert not re.search(r"\d", value), key
    sentences = guard.sentences(value)
    assert 1 <= len(sentences) <= 2, key
    for sentence in sentences:
        assert len(sentence.split()) <= B1_MAX_WORDS_PER_SENTENCE, (key, sentence)
    if any(segment in key for segment in _ACK_SEGMENTS):
        assert len(value.split()) <= MAX_ACK_WORDS, key


def test_the_server_allow_list_is_the_turkish_catalogue_byte_for_byte() -> None:
    assert DELIVERY_TR, "the George delivery allow-list is empty"
    for key, text in DELIVERY_TR.items():
        assert key in DELIVERY, f"{key} is not a delivery key"
        assert text == TR[key], key


def test_the_server_admits_by_the_compiled_manifest_hash() -> None:
    assert delivery_text_hashes() == frozenset(clip_text_hash(t) for t in DELIVERY_TR.values())


def test_display_only_lines_are_not_admitted() -> None:
    # The typed orientation, the closing (review screen) and the measurement
    # topic (text-only steps) are never spoken, so the vendor never needs them.
    admitted = set(DELIVERY_TR)
    for key in DELIVERY:
        if ".orientTyped." in key or ".closing." in key or ".topic.measurements." in key:
            assert key not in admitted, key
