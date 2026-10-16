"""INT-522 golden family 15: the closed onset choice, resolved by CD-05 (10 cases).

``chest_pain.onset_at`` is answered by one of four closed choices, never by a
date, and CD-05 decided which calendar day each resolves to against the
session's reference time (``protocols.anchor_choices``). Family 5 pins the
tense windows over hand-written ISO dates; this family pins the same two
active chest-pain rules over the days the *choices* resolve to, so a change to
the resolution — a band moved by a day, the unresolved answer made less acute —
fails the golden suite and not only the resolver's own tests.

For each rule, every choice and the unresolved answer (UNCLEAR → the reference
day): the three bands on the reference day fire, and 'üç günden daha önce' is
the near-miss negative — one attribute off, the anchor three days back — that
must not (``NEAR_MISS_BY_RULE``). The twelve-to-seventy-two-hour band fires on
CD-05's while-draft resolution; its final resolution is the D18 lane's.
"""

from __future__ import annotations

from protocols.anchor_choices import load_anchor_choice_table
from protocols.triage import SlotAnswer
from protocols.types import EK4Level
from triage_goldens_corpus import C1, C2, CP_ANCHOR, REF_TIME, GoldenCase, p
from triage_goldens_fixtures import green, lt01p, lt02p, red, yellow

NOW_CHOICE = "şu anda var"
TWELVE_HOURS = "son on iki saat içinde"
TWELVE_TO_72 = "on iki saatten önce ama son üç gün içinde"
OLDER = "üç günden daha önce"


def _chosen(choice: str) -> SlotAnswer:
    """The anchor as the runtime binds it from a spoken choice."""
    table = load_anchor_choice_table()
    return p(table.resolve(CP_ANCHOR, choice, REF_TIME).resolved_on)


def _unclear() -> SlotAnswer:
    """The anchor as the runtime reads an answer that fit no choice."""
    table = load_anchor_choice_table()
    return p(table.resolve_unresolved(CP_ANCHOR, REF_TIME).resolved_on)


def anchor_choices() -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for suffix, anchor, fires, note in (
        ("su-anda", _chosen(NOW_CHOICE), True, "'şu anda var' is the reference day"),
        ("on-iki-saat", _chosen(TWELVE_HOURS), True, "the twelve-hour band is the reference day"),
        (
            "uc-gune-kadar-taslak",
            _chosen(TWELVE_TO_72),
            True,
            "twelve to seventy-two hours: CD-05's while-draft resolution, the reference day",
        ),
        (
            "uc-gunden-once",
            _chosen(OLDER),
            False,
            "near miss: 'üç günden daha önce' is the reference day minus three",
        ),
        ("belirsiz", _unclear(), True, "an answer fitting no choice: UNCLEAR → the reference day"),
    ):
        k2_id, sari_id = f"anchor/c1-{suffix}", f"anchor/c2-{suffix}"
        if fires:
            cases.append(red(k2_id, "life", lt01p(anchor=anchor), (C1,), C1, note))
            cases.append(
                yellow(sari_id, "life", lt02p(anchor=anchor), (C2,), EK4Level.SARI_K1, note)
            )
        else:
            cases.append(green(k2_id, "life", lt01p(anchor=anchor), note))
            cases.append(green(sari_id, "life", lt02p(anchor=anchor), note))
    return cases
