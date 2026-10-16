"""Golden families 15 to 17: the onset anchor as CD-05 and CD-04 resolve it.

Family 15 (INT-522, 10 cases): the closed onset choice, resolved by CD-05.

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

Family 16 (INT-540, 13 cases; INT-546): a hedged onset answer, read by
CD-04. Each active UNCLEAR entry of CD-04's table, said to the onset question,
reads UNCLEAR on the anchor (``protocols.answer_states``, the table read from
the decision); since CD-04 round 3 (INT-519 item 5) a hedge takes no
follow-up, so CD-05 resolves it at once to the reference day and both rules
fire — a hedge dropped from the table, read as anything but UNCLEAR on the
anchor, or given a follow-up, fails the golden suite. Two near misses sit one
attribute away: an answer that binds no choice, before its one follow-up is
spent (the anchor still pending, Unknown: CD-04's "reads Unknown and triggers
the slot's follow_up_tr once"), and — for the SARI sibling, whose gate turns
on the character — the hedge said to the character instead, which is not an
anchor, resolves to no value and leaves the sibling Unknown.

Family 17 (INT-546, 6 cases): the anchor at the session's close (CD-05 round
3, INT-519 items 10 and 11). An anchor never asked when the session closes,
while ``chest_pain.present`` reads true, is evaluated once as the reference
day (``never_asked_at_close``), and an anchor asked and never answered is
UNCLEAR with the ``session_closed`` label, the same day: both rules fire on
each. The near misses: chest pain denied (``chest_pain.present = hayır``,
the anchor NOT_ASKED and not read), and chest pain never answered (both
NOT_ASKED) — nothing fires, because the runtime reads the never-asked anchor
only when its gate is open.
"""

from __future__ import annotations

from clinical_schemas.session import AnswerState
from protocols.anchor_choices import load_anchor_choice_table
from protocols.answer_states import HedgeBasis, HedgeState, load_answer_state_table
from protocols.triage import SlotAnswer
from protocols.types import EK4Level
from triage_goldens_corpus import C1, C2, CP_ANCHOR, REF_TIME, GoldenCase, ab, p, st
from triage_goldens_fixtures import green, lt01p, lt02p, red, yellow

NOW_CHOICE = "şu anda var"
TWELVE_HOURS = "son on iki saat içinde"
TWELVE_TO_72 = "on iki saatten önce ama son üç gün içinde"
OLDER = "üç günden daha önce"


def _chosen(choice: str) -> SlotAnswer:
    """The anchor as the runtime binds it from a spoken choice."""
    table = load_anchor_choice_table()
    return p(table.resolve(CP_ANCHOR, choice, REF_TIME).resolved_on)


def _unclear(cause: str | None = None) -> SlotAnswer:
    """The anchor as the runtime reads an answer that fit no choice."""
    table = load_anchor_choice_table()
    return p(table.resolve_unresolved(CP_ANCHOR, REF_TIME, cause=cause).resolved_on)


def _never_asked() -> SlotAnswer:
    """The anchor as the runtime reads it at close, never asked, pain affirmed."""
    table = load_anchor_choice_table()
    return p(table.resolve_never_asked(CP_ANCHOR, REF_TIME).resolved_on)


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


#: CD-04's active UNCLEAR entries, as a patient says each to the onset
#: question, keyed by a golden id suffix. Synthetic (files/04 §7).
HEDGED_ONSET: tuple[tuple[str, str], ...] = (
    ("bilmiyorum", "Bilmiyorum."),
    ("emin-degilim", "Emin değilim."),
    ("sanmiyorum", "Sanmıyorum."),
    ("pek-sayilmaz", "Pek sayılmaz."),
    ("yok-gibi", "Yok gibi."),
)


def _hedged(said: str) -> SlotAnswer:
    """The anchor on the Work that read a hedge: UNCLEAR at once (CD-04 round 3:
    no follow-up for a hedge), read as CD-05's unresolved day. Refuses a hedge
    the table does not read UNCLEAR, and a table that gives a hedge a follow-up."""
    table = load_answer_state_table()
    assert table.tense_anchor_follow_up_tr_asks["hedge"] == 0
    reading = table.read(CP_ANCHOR, said)
    assert reading is not None, said
    assert (reading.state, reading.basis) == (HedgeState.UNCLEAR, HedgeBasis.DECIDED), said
    return _unclear("hedge")


def anchor_hedges() -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for suffix, said in HEDGED_ONSET:
        note = f"CD-04 '{suffix}' on the onset: UNCLEAR at once, no follow-up → the reference day"
        anchor = _hedged(said)
        cases.append(red(f"hedge/c1-{suffix}", "life", lt01p(anchor=anchor), (C1,), C1, note))
        cases.append(
            yellow(
                f"hedge/c2-{suffix}", "life", lt02p(anchor=anchor), (C2,), EK4Level.SARI_K1, note
            )
        )
    pending = st(AnswerState.ASKED_PENDING)
    note = "near miss: an answer binding no choice, before its one follow-up, reads Unknown"
    cases.append(green("hedge/c1-takip-bekliyor", "life", lt01p(anchor=pending), note))
    cases.append(green("hedge/c2-takip-bekliyor", "life", lt02p(anchor=pending), note))
    unclear_character = st(AnswerState.UNCLEAR)
    cases.append(
        green(
            "hedge/c2-karakter-belirsiz",
            "life",
            lt02p(anchor=_hedged("Bilmiyorum."), **{"chest_pain.character": unclear_character}),
            "near miss: 'bilmiyorum' to the character is not an anchor and resolves to no value",
        )
    )
    return cases


def anchor_close() -> list[GoldenCase]:
    """Family 17 (INT-546): the anchor at the session's close."""
    never = "CD-05 never_asked_at_close: chest pain affirmed, the anchor read as the reference day"
    closed = "CD-05 session_closed: asked, never answered → UNCLEAR → the reference day"
    denied = "near miss: chest pain denied, the never-asked anchor is not read and nothing fires"
    unanswered = "near miss: chest pain never answered, the anchor is not read and nothing fires"
    not_asked = st(AnswerState.NOT_ASKED)
    return [
        red("close/c1-sorulmadi", "life", lt01p(anchor=_never_asked()), (C1,), C1, never),
        yellow(
            "close/c2-sorulmadi",
            "life",
            lt02p(anchor=_never_asked()),
            (C2,),
            EK4Level.SARI_K1,
            never,
        ),
        red(
            "close/c1-oturum-kapandi",
            "life",
            lt01p(anchor=_unclear("session_closed")),
            (C1,),
            C1,
            closed,
        ),
        yellow(
            "close/c2-oturum-kapandi",
            "life",
            lt02p(anchor=_unclear("session_closed")),
            (C2,),
            EK4Level.SARI_K1,
            closed,
        ),
        green(
            "close/c1-gogus-agrisi-yok",
            "life",
            {**lt01p(anchor=not_asked), "chest_pain.present": ab(False)},
            denied,
        ),
        green(
            "close/c1-gogus-agrisi-sorulmadi",
            "life",
            {**lt01p(anchor=not_asked), "chest_pain.present": not_asked},
            unanswered,
        ),
    ]
