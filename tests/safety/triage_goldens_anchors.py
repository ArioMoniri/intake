"""Golden families 15 and 16: the onset anchor as CD-05 and CD-04 resolve it.

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

Family 16 (INT-540, 13 cases; INT-547, 14): a hedged onset answer, read by
CD-04. Each active UNCLEAR entry of CD-04's table, said to the onset question,
reads UNCLEAR on the anchor (``protocols.answer_states``, the table read from the
decision); once CD-04's one follow-up is spent, CD-05 resolves it to the
reference day and both rules fire — so a hedge dropped from the table, or
read as anything but UNCLEAR on the anchor, fails the golden suite. Two near
misses sit one attribute away: the same hedge before its follow-up is spent
(the anchor still pending, Unknown: CD-04's "reads Unknown and triggers the
slot's follow_up_tr once"), and — for the SARI sibling, whose gate turns on
the character — the hedge said to the character instead, which is not an
anchor, resolves to no value and leaves the sibling Unknown.

That last state is the one CD-04 says must reach the clinic (INT-547):
the character still UNCLEAR after its follow-up leaves both chest-pain arms
Unknown, so the session is GREEN on a pain nobody could characterise, and
CD-04 ``unresolved_after_follow_up`` raises the CD-08 clinic-inbox item
``chest_pain_arms_unresolved``. ``hedge/c2-karakter-belirsiz`` pins the item
beside the GREEN; its near miss ``hedge/c2-karakter-takipte-netlesti`` answers
the same follow-up with a choice, so the arm resolves (SARI_K1) and nothing is
raised.
"""

from __future__ import annotations

from dataclasses import replace

from clinical_schemas.session import AnswerState
from protocols.anchor_choices import load_anchor_choice_table
from protocols.answer_states import HedgeBasis, HedgeState, load_answer_state_table
from protocols.clinic_items import ClinicItemKind
from protocols.triage import SlotAnswer
from protocols.types import EK4Level
from triage_goldens_corpus import C1, C2, CP_ANCHOR, REF_TIME, GoldenCase, p, st
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
    """The anchor once CD-04's one follow-up is spent on a hedge: UNCLEAR, read
    as CD-05's unresolved day. Refuses a hedge the table does not read UNCLEAR."""
    reading = load_answer_state_table().read(CP_ANCHOR, said)
    assert reading is not None, said
    assert (reading.state, reading.basis) == (HedgeState.UNCLEAR, HedgeBasis.DECIDED), said
    return _unclear()


def anchor_hedges() -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for suffix, said in HEDGED_ONSET:
        note = f"CD-04 '{suffix}' on the onset: UNCLEAR, the follow-up spent → the reference day"
        anchor = _hedged(said)
        cases.append(red(f"hedge/c1-{suffix}", "life", lt01p(anchor=anchor), (C1,), C1, note))
        cases.append(
            yellow(
                f"hedge/c2-{suffix}", "life", lt02p(anchor=anchor), (C2,), EK4Level.SARI_K1, note
            )
        )
    pending = st(AnswerState.ASKED_PENDING)
    note = "near miss: the hedge before its one follow-up is spent reads Unknown (CD-04)"
    cases.append(green("hedge/c1-takip-bekliyor", "life", lt01p(anchor=pending), note))
    cases.append(green("hedge/c2-takip-bekliyor", "life", lt02p(anchor=pending), note))
    cases.extend(_character_hedges())
    return cases


#: CD-04's "asked once", for the character in the two cases below.
_CHARACTER_FOLLOWED_UP = {"chest_pain.character": 1}


def _character_hedges() -> list[GoldenCase]:
    """INT-547: the character's hedge, and the clinic item it raises."""
    anchor = _hedged("Bilmiyorum.")
    unresolved = green(
        "hedge/c2-karakter-belirsiz",
        "life",
        lt02p(anchor=anchor, **{"chest_pain.character": st(AnswerState.UNCLEAR)}),
        "near miss: 'bilmiyorum' to the character is not an anchor and resolves to no "
        "value; still UNCLEAR after its follow-up it leaves both arms Unknown, so CD-04 "
        "raises the CD-08 clinic-inbox item chest_pain_arms_unresolved (INT-547)",
    )
    resolved = yellow(
        "hedge/c2-karakter-takipte-netlesti",
        "life",
        lt02p(anchor=anchor, **{"chest_pain.character": p("başka bir his")}),
        (C2,),
        EK4Level.SARI_K1,
        "near miss of the clinic item: the character's follow-up answered with a choice, "
        "the arm resolves to SARI_K1 and CD-04 raises nothing (INT-547)",
    )
    return [
        replace(
            unresolved,
            follow_ups_asked=_CHARACTER_FOLLOWED_UP,
            clinic_items=(ClinicItemKind.CHEST_PAIN_ARMS_UNRESOLVED.value,),
        ),
        replace(resolved, follow_ups_asked=_CHARACTER_FOLLOWED_UP, clinic_items=()),
    ]
