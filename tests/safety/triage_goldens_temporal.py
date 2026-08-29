"""INT-059 golden family 5: temporal boundaries (42 cases).

files/12 §2.4 — a tense-qualified rule cannot fire on an undated symptom,
and the window is a CALENDAR-day window computed against the session's
own reference time so replay is exact.

For every tense in merged content (`now`, `today`, `within_7d`,
`within_30d`) the corpus pins the exact boundary day, one day inside, one
day outside, and the four data defects that must read Unknown rather than
True or False: a future onset, a naive timestamp that cannot be placed on
the session clock, an unparseable string, and an anchor never asked at
all. Timezone-aware anchors are pinned in both directions, because the
conversion decides which calendar day the event lands on — 01:00+03 is the
previous UTC day, 22:30-03 the next.

No `ever`-tensed rule exists in merged content; see the headroom table in
docs/evidence/INT-059.md.
"""

from __future__ import annotations

from protocols.triage import SlotAnswer
from protocols.types import EK4Level
from triage_goldens_corpus import (
    ANCHOR,
    BK,
    BS,
    C1,
    C2,
    CD,
    CG,
    CP_ANCHOR,
    OE,
    GoldenCase,
    d,
    p,
)
from triage_goldens_fixtures import green, lt01p, lt02p, red, syn, yellow

# ---------------------------------------------------------------------------
# Family 5 — temporal boundaries (42): for every tense window in merged
# content, the exact boundary, one step inside, one step outside, plus the
# data defects that must read Unknown (future, naive, unparseable, missing —
# files/12 §2.4). No `ever`-tensed rule exists in merged content today.
# ---------------------------------------------------------------------------


def _now_rule_variants(
    prefix: str,
    rule_set: str,
    answers_for: dict[str, SlotAnswer],
    anchor_key: str,
    fire_fired: tuple[str, ...],
    fire_winner: str,
    fire_note: str,
) -> list[GoldenCase]:
    def with_anchor(anchor: SlotAnswer | None) -> dict[str, SlotAnswer]:
        answers = dict(answers_for)
        answers.pop(anchor_key, None)
        if anchor is not None:
            answers[anchor_key] = anchor
        return answers

    return [
        green(f"{prefix}-dun", rule_set, with_anchor(p(d(1))), "yesterday is outside `now`"),
        green(f"{prefix}-yarin", rule_set, with_anchor(p(d(-1))), "a future onset reads Unknown"),
        green(
            f"{prefix}-saf-saat",
            rule_set,
            with_anchor(p("2026-08-28T09:00:00")),
            "a naive timestamp cannot be placed on the session clock",
        ),
        green(
            f"{prefix}-bozuk",
            rule_set,
            with_anchor(p("bugun")),
            "an unparseable anchor reads Unknown, never today",
        ),
        green(f"{prefix}-yok", rule_set, with_anchor(None), "no anchor asked → cannot fire"),
        red(
            f"{prefix}-tzli-bugun",
            rule_set,
            with_anchor(p("2026-08-28T06:30:00+03:00")),
            fire_fired,
            fire_winner,
            fire_note,
        ),
    ]


def temporal_boundaries() -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    cases.extend(
        _now_rule_variants(
            "tense/bk",
            "base",
            syn(renk_tercihi=p("kirmizi")),
            ANCHOR,
            (BK,),
            BK,
            "an aware timestamp on the reference day fires the now-tensed RED",
        )
    )
    cases.extend(
        _now_rule_variants(
            "tense/cg",
            "child",
            syn(ek_soru=p(True), renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(False)),
            ANCHOR,
            (CD, CG),
            CG,
            "aware same-day timestamp fires both today- and now-tensed children",
        )
    )
    cases.extend(
        _now_rule_variants(
            "tense/c1",
            "life",
            lt01p(),
            CP_ANCHOR,
            (C1,),
            C1,
            "aware same-day timestamp fires the cardiac RED",
        )
    )
    cases.extend(
        [
            green(
                "tense/c1-tz-erken",
                "life",
                lt01p(anchor=p("2026-08-28T01:00:00+03:00")),
                "01:00 +03 is the PREVIOUS calendar day on the session's UTC"
                " clock — conversion happens before the window test",
            ),
            red(
                "tense/c1-tz-gec",
                "life",
                lt01p(anchor=p("2026-08-27T22:30:00-03:00")),
                (C1,),
                C1,
                "22:30 −03 the evening before IS the reference day in UTC",
            ),
        ]
    )
    lt02 = lt02p()
    for case_id, anchor, fires, note in (
        ("tense/c2-dun", p(d(1)), False, "yesterday is outside `today`"),
        ("tense/c2-yarin", p(d(-1)), False, "future onset reads Unknown"),
        ("tense/c2-saf-saat", p("2026-08-28T09:00:00"), False, "naive timestamp"),
        ("tense/c2-bozuk", p("dun aksam"), False, "unparseable anchor"),
        ("tense/c2-yok", None, False, "anchor never asked"),
        ("tense/c2-tzli", p("2026-08-28T07:15:00+03:00"), True, "aware same-day fires"),
    ):
        answers = dict(lt02)
        answers.pop(CP_ANCHOR)
        if anchor is not None:
            answers[CP_ANCHOR] = anchor
        if fires:
            cases.append(yellow(case_id, "life", answers, (C2,), EK4Level.SARI_K1, note))
        else:
            cases.append(green(case_id, "life", answers, note))
    for case_id, anchor, fires, note in (
        ("tense/bs-icinde", p(d(6)), True, "day 6 is inside within_7d"),
        ("tense/bs-sinir", p(d(7)), True, "day 7 is the inclusive boundary"),
        ("tense/bs-disi", p(d(8)), False, "day 8 is outside within_7d"),
        ("tense/bs-yarin", p(d(-1)), False, "future onset reads Unknown"),
        ("tense/bs-yok", None, False, "anchor never asked"),
        ("tense/bs-saf-saat", p("2026-08-21T09:00:00"), False, "naive timestamp"),
        ("tense/bs-bozuk", p("gecen hafta"), False, "unparseable anchor"),
        ("tense/bs-tz-sinir", p("2026-08-21T23:00:00+03:00"), True, "aware day-7 boundary"),
    ):
        answers: dict[str, SlotAnswer] = {"bekleme_suresi_gun_asimi": p(True)}
        if anchor is not None:
            answers[ANCHOR] = anchor
        if fires:
            cases.append(yellow(case_id, "base", answers, (BS,), EK4Level.SARI_K2, note))
        else:
            cases.append(green(case_id, "base", answers, note))
    for case_id, anchor, fires, note in (
        ("tense/oe-icinde", p(d(29)), True, "day 29 is inside within_30d"),
        ("tense/oe-sinir", p(d(30)), True, "day 30 is the inclusive boundary"),
        ("tense/oe-disi", p(d(31)), False, "day 31 is outside within_30d"),
        ("tense/oe-yarin", p(d(-1)), False, "future onset reads Unknown"),
        ("tense/oe-yok", None, False, "anchor never asked"),
        ("tense/oe-saf-saat", p("2026-07-29T09:00:00"), False, "naive timestamp"),
        ("tense/oe-bozuk", p("bir ay once"), False, "unparseable anchor"),
        ("tense/oe-tz-sinir", p("2026-07-29T23:30:00+03:00"), True, "aware day-30 boundary"),
    ):
        answers = {"ek_katman_bulgusu": p(True)}
        if anchor is not None:
            answers[ANCHOR] = anchor
        if fires:
            cases.append(yellow(case_id, "overlay", answers, (OE,), EK4Level.SARI_K2, note))
        else:
            cases.append(green(case_id, "overlay", answers, note))
    return cases
