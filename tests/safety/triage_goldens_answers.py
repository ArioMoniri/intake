"""INT-059 golden families 3-6: how the engine reads answer state.

- ``valueless_states`` (35): files/12 §1.1 — not_asked / asked_pending /
  unclear / declined all read Unknown, and Unknown never fires. A decline
  rendered as an elicited negative is the exact defect that section names.
- ``explicit_absent`` (7): ``asked_absent`` DOES carry its value, in both
  directions — the negated-feature rule needs it to fire at all.
- ``temporal_boundaries`` (42): every tense window in merged content at its
  boundary, one day inside, one day outside, plus the data defects that
  must read Unknown (future, naive, unparseable, missing) and the
  timezone conversions that decide which calendar day an event lands on.
- ``contested_values`` (13): files/12 §7.3 — evaluation per world, joined
  escalating-only, with no cross-world mixing.
"""

from __future__ import annotations

from decimal import Decimal

from clinical_schemas.session import AnswerState
from protocols.types import EK4Level
from triage_goldens_corpus import (
    ANCHOR,
    BK,
    BS,
    C1,
    C2,
    CD,
    CG,
    OE,
    TODAY,
    VALUELESS_STATES,
    GoldenCase,
    ab,
    con,
    d,
    p,
    st,
)
from triage_goldens_fixtures import (
    chest,
    green,
    lt01p,
    lt02p,
    red,
    syn,
    yellow,
)

# ---------------------------------------------------------------------------
# Family 3 — valueless answer states read Unknown and never fire (35):
# 4 states × 7 rules on the gate slot, declined-on-a-negated-conjunct ×2,
# and 5 anchor-state cases (files/12 §1.1: a decline rendered as an elicited
# negative is the exact defect the section names).
# ---------------------------------------------------------------------------


def valueless_states() -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for state in VALUELESS_STATES:
        tag = state.value.lower()
        cases.extend(
            [
                green(
                    f"state/bk-{tag}",
                    "base",
                    syn(renk_tercihi=st(state)),
                    f"{state.value} on the gate slot reads Unknown — no fire",
                ),
                green(
                    f"state/bs-{tag}",
                    "base",
                    syn(bekleme_suresi_gun_asimi=st(state)),
                    f"{state.value} never fires the SARI rule",
                ),
                green(
                    f"state/cd-{tag}",
                    "child",
                    syn(
                        ek_soru=st(state),
                        renk_tercihi=p("mavi"),
                        bekleme_suresi_asildi=p(False),
                    ),
                    f"{state.value} on the child SARI slot — parent arms false",
                ),
                green(
                    f"state/cg-{tag}",
                    "child",
                    syn(
                        renk_tercihi=st(state),
                        ek_soru=p(False),
                        bekleme_suresi_asildi=p(False),
                    ),
                    f"{state.value} on the tightened rule's inherited arm",
                ),
                green(
                    f"state/oe-{tag}",
                    "overlay",
                    syn(ek_katman_bulgusu=st(state)),
                    f"{state.value} never fires the overlay rule",
                ),
                green(
                    f"state/c1-{tag}",
                    "life",
                    chest(
                        p(TODAY),
                        present=st(state),
                        character=p("baskı"),
                        radiation=p("kol"),
                        diaphoresis=p(True),
                        dyspnoea=p(True),
                    ),
                    f"every arm screams but presence is {state.value} — U ∧ T = U,"
                    " no fire and no false reassurance",
                ),
                green(
                    f"state/c2-{tag}",
                    "life",
                    lt02p(**{"chest_pain.present": st(state)}),
                    f"presence {state.value} keeps the SARI conjunction Unknown",
                ),
            ]
        )
    cases.extend(
        [
            green(
                "state/c2-dispne-declined",
                "life",
                lt02p(**{"associated.dyspnoea": st(AnswerState.DECLINED)}),
                "a declined dyspnoea question is NOT an elicited negative —"
                " the `== false` conjunct reads Unknown (files/12 §1.1)",
            ),
            green(
                "state/c2-terleme-declined",
                "life",
                lt02p(**{"associated.diaphoresis": st(AnswerState.DECLINED)}),
                "a declined diaphoresis question is not a 'no'",
            ),
            green(
                "state/c1-anchor-declined",
                "life",
                lt01p(anchor=st(AnswerState.DECLINED)),
                "an undated (declined) onset cannot satisfy a tensed rule (files/12 §2.4)",
            ),
        ]
    )
    for state in VALUELESS_STATES:
        cases.append(
            green(
                f"state/bk-anchor-{state.value.lower()}",
                "base",
                {ANCHOR: st(state), "renk_tercihi": p("kirmizi")},
                f"anchor in {state.value}: a now-tensed rule cannot fire on an undated event",
            )
        )
    return cases


# ---------------------------------------------------------------------------
# Family 4 — asked_absent carries its value, in both directions (7).
# ---------------------------------------------------------------------------


def explicit_absent() -> list[GoldenCase]:
    return [
        green(
            "absent/bk",
            "base",
            syn(renk_tercihi=p("mavi"), bekleme_suresi_asildi=ab(False)),
            "an elicited negative is a real False, and False does not fire",
        ),
        green(
            "absent/bs",
            "base",
            syn(bekleme_suresi_gun_asimi=ab(False)),
            "elicited negative on the SARI gate",
        ),
        green(
            "absent/child",
            "child",
            syn(ek_soru=ab(False), renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(False)),
            "elicited negative on the child slot",
        ),
        green(
            "absent/oe",
            "overlay",
            syn(p(d(30)), ek_katman_bulgusu=ab(False)),
            "elicited negative on the overlay slot",
        ),
        green(
            "absent/c1",
            "life",
            chest(
                p(TODAY),
                present=p(True),
                character=p("batıcı"),
                radiation=p("yok"),
                diaphoresis=ab(False),
                dyspnoea=ab(False),
                trauma=p(True),
            ),
            "elicited negatives on both associated symptoms — clean no-fire",
        ),
        yellow(
            "absent/c2-fires",
            "life",
            lt02p(
                **{
                    "associated.diaphoresis": ab(False),
                    "associated.dyspnoea": ab(False),
                    "trauma.recent": ab(False),
                }
            ),
            (C2,),
            EK4Level.SARI_K1,
            "the negated-feature rule NEEDS elicited negatives — asked_absent"
            " supplies its value and the SARI fires",
        ),
        green(
            "absent/c1-kill",
            "life",
            chest(
                p(TODAY),
                present=ab(False),
                character=p("baskı"),
                radiation=p("kol"),
                diaphoresis=p(True),
                dyspnoea=p(False),
                trauma=p(True),
            ),
            "presence elicited-absent kills the rule despite true arms",
        ),
    ]


# ---------------------------------------------------------------------------
# Family 6 — contested values evaluate per world and join escalating-only
# (13; files/12 §7.3).
# ---------------------------------------------------------------------------


def contested_values() -> list[GoldenCase]:
    return [
        red(
            "cont/bk-escalates",
            "base",
            syn(renk_tercihi=con("mavi", "kirmizi")),
            (BK,),
            BK,
            "any contested world that fires, fires",
            evidence_contains=((BK, '"mavi"|"kirmizi"'),),
        ),
        green(
            "cont/bk-both-safe",
            "base",
            syn(renk_tercihi=con("mavi", "yesil"), bekleme_suresi_asildi=p(False)),
            "no contested world fires → no fire",
        ),
        red(
            "cont/bk-anchor",
            "base",
            {ANCHOR: con(d(1), TODAY), "renk_tercihi": p("kirmizi")},
            (BK,),
            BK,
            "a contested anchor takes the escalating (in-window) world",
        ),
        red(
            "cont/bk-uc-deger",
            "base",
            syn(renk_tercihi=con("mavi", "yesil", "kirmizi")),
            (BK,),
            BK,
            "three contested worlds — one firing world is enough",
        ),
        yellow(
            "cont/bs-deger",
            "base",
            syn(bekleme_suresi_gun_asimi=con(False, True)),
            (BS,),
            EK4Level.SARI_K2,
            "contested boolean escalates to the firing world",
        ),
        yellow(
            "cont/bs-anchor",
            "base",
            {ANCHOR: con(d(8), d(7)), "bekleme_suresi_gun_asimi": p(True)},
            (BS,),
            EK4Level.SARI_K2,
            "contested anchor straddling the 7-day boundary fires",
        ),
        red(
            "cont/c1-karakter",
            "life",
            chest(
                p(TODAY),
                present=p(True),
                character=con("batıcı", "baskı"),
                radiation=p("yok"),
                diaphoresis=p(False),
                dyspnoea=p(False),
                trauma=p(True),
            ),
            (C1,),
            C1,
            "the 'baskı' world fires the cardiac arm; trauma keeps SARI out",
        ),
        red(
            "cont/c1c2-union",
            "life",
            lt02p(**{"chest_pain.character": con("batıcı", "baskı")}),
            (C1, C2),
            C1,
            "one world satisfies each sibling — the union fires BOTH and the"
            " KIRMIZI winner supplies register and script",
        ),
        red(
            "cont/c2-exact-worlds",
            "life",
            lt02p(**{"chest_pain.character": con("baskı", "sıkışma")}),
            (C1,),
            C1,
            "both worlds sit in the cardiac set: SARI is false in EVERY world"
            " (no cross-world mixing), KIRMIZI fires in every world",
        ),
        red(
            "cont/c1-dispne",
            "life",
            chest(
                p(TODAY),
                present=p(True),
                character=p("batıcı"),
                radiation=p("yok"),
                diaphoresis=p(False),
                dyspnoea=con(False, True),
                trauma=p(True),
            ),
            (C1,),
            C1,
            "contested dyspnoea escalates into the cardiac arm",
        ),
        yellow(
            "cont/oe",
            "overlay",
            syn(p(d(30)), ek_katman_bulgusu=con(False, True)),
            (OE,),
            EK4Level.SARI_K2,
            "contested overlay slot on the boundary day fires",
        ),
        red(
            "cont/cg-iki-slot",
            "child",
            syn(renk_tercihi=con("mavi", "kirmizi"), ek_soru=con(False, True)),
            (BK, CD, CG),
            BK,
            "two contested slots: each rule fires from its own escalating world",
        ),
        green(
            "cont/cd-safe",
            "child",
            syn(
                ek_soru=con(False, False),
                renk_tercihi=p("mavi"),
                bekleme_suresi_asildi=p(False),
            ),
            "contested with only safe values does not escalate",
        ),
    ]


# ---------------------------------------------------------------------------
# Family 14 — a cross-type comparison is Unknown, never False (4). A data
# defect can suppress a firing only into review, never into false
# reassurance (files/13 §9.5; triage/expr.py `_equal`).
# ---------------------------------------------------------------------------


def type_mismatch_unknown() -> list[GoldenCase]:
    return [
        green(
            "type/bk-sayi",
            "base",
            syn(renk_tercihi=p(3)),
            "a number where the rule compares a string reads Unknown, never False and never True",
        ),
        green(
            "type/bs-metin",
            "base",
            syn(bekleme_suresi_gun_asimi=p("evet")),
            "a string where the rule compares a boolean reads Unknown",
        ),
        green(
            "type/c1-sayi",
            "life",
            chest(
                p(TODAY),
                present=p(True),
                character=p(7),
                radiation=p("yok"),
                diaphoresis=p(False),
                dyspnoea=p(False),
                trauma=p(True),
            ),
            "a numeric character makes the set test Unknown — U, not a fire and not a clean pass",
        ),
        green(
            "type/bk-anchor-sayi",
            "base",
            {ANCHOR: p(5), "renk_tercihi": p("kirmizi")},
            "a non-string anchor is undated — the tensed rule cannot fire",
        ),
        green(
            "type/bk-ondalik",
            "base",
            syn(renk_tercihi=p(Decimal("38.50"))),
            "INT-303: a Decimal is inside the carrier — it reads Unknown against "
            "a string comparison, and reading it as Unknown is a CHOICE the "
            "grammar makes rather than the engine failing to recognise the type",
        ),
        green(
            "type/bs-ondalik",
            "base",
            syn(bekleme_suresi_gun_asimi=p(Decimal("1"))),
            "INT-303: a Decimal where the rule compares a boolean reads Unknown "
            "— never True, so 1 cannot stand in for the boolean it equals",
        ),
    ]
