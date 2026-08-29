"""INT-059 golden families 7-9 and 12: axes, inheritance, the sibling set.

- ``red_axes_locations`` (15): invariant 21 — every active RED at REMOTE,
  ON_SITE and UNKNOWN, with the verbatim script for each, plus YELLOW's
  location-invariance (register/location are RED-only fields).
- ``merge_matrix`` (42): 8 answer contexts × the inheritance sets, every
  cell an absolute expectation. Reading DOWN a column is invariant 7 at
  runtime — as the rule set grows the level never falls.
- ``sibling_life_threat`` (3): base.life_threat rides alongside every
  chain without being extendable or dilutable.
- ``register_tiebreak`` (3): at equal acuity and equal register the winner
  is the lowest rule id, so register and script always travel together
  from one clinician-approved rule.
"""

from __future__ import annotations

from clinical_schemas.triage import RedLocation
from protocols.triage import SlotAnswer
from protocols.types import EK4Level
from triage_goldens_corpus import (
    ANCHOR,
    ASK_ONE_TR,
    BK,
    BS,
    C1,
    C2,
    CD,
    CG,
    OE,
    GoldenCase,
    d,
    p,
)
from triage_goldens_fixtures import (
    BK_ONSITE_TR,
    BK_REMOTE_TR,
    C1_REMOTE_TR,
    green,
    lt01n,
    lt01p,
    lt02p,
    red,
    syn,
    yellow,
)

# ---------------------------------------------------------------------------
# Family 7 — invariant 21 axes and verbatim scripts, per location (15):
# every active RED × {REMOTE, ON_SITE, UNKNOWN}, plus YELLOW location
# invariance (register/location are RED-only fields).
# ---------------------------------------------------------------------------


def red_axes_locations() -> list[GoldenCase]:
    cases = [
        red(
            "axes/bk-remote",
            "base",
            syn(renk_tercihi=p("kirmizi")),
            (BK,),
            BK,
            "REMOTE resolves the rule's own REMOTE script",
            location=RedLocation.REMOTE,
            action_primary="CALL_112",
            action_show_112=True,
            action_tr=BK_REMOTE_TR,
        ),
        red(
            "axes/bk-onsite",
            "base",
            syn(renk_tercihi=p("kirmizi")),
            (BK,),
            BK,
            "ON_SITE: staff notified, and the 112 affordance is ABSENT",
            location=RedLocation.ON_SITE,
            action_primary="GO_TO_IN_HOUSE_ACIL",
            action_show_112=False,
            action_tr=BK_ONSITE_TR,
        ),
        red(
            "axes/bk-unknown",
            "base",
            syn(renk_tercihi=p("kirmizi")),
            (BK,),
            BK,
            "UNKNOWN asks exactly one question, then branches — never guesses",
            location=RedLocation.UNKNOWN,
            ask_one_tr=ASK_ONE_TR,
        ),
        red(
            "axes/cg-remote",
            "child",
            syn(ek_soru=p(True), renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(False)),
            (CD, CG),
            CG,
            "the tightened rule carries its own full action block",
            location=RedLocation.REMOTE,
            action_primary="CALL_112",
            action_show_112=True,
            action_tr=BK_REMOTE_TR,
        ),
        red(
            "axes/cg-onsite",
            "child",
            syn(ek_soru=p(True), renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(False)),
            (CD, CG),
            CG,
            "tightened rule, ON_SITE — no 112",
            location=RedLocation.ON_SITE,
            action_primary="GO_TO_IN_HOUSE_ACIL",
            action_show_112=False,
        ),
        red(
            "axes/cg-unknown",
            "child",
            syn(ek_soru=p(True), renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(False)),
            (CD, CG),
            CG,
            "tightened rule, UNKNOWN — the single disambiguation question",
            location=RedLocation.UNKNOWN,
            ask_one_tr=ASK_ONE_TR,
        ),
        red(
            "axes/c1-remote",
            "life",
            lt01p(),
            (C1,),
            C1,
            "LT-01-P REMOTE: CALL_112, show_112, the verbatim Turkish script",
            location=RedLocation.REMOTE,
            action_primary="CALL_112",
            action_show_112=True,
            action_tr=C1_REMOTE_TR,
        ),
        red(
            "axes/c1-onsite",
            "life",
            lt01p(),
            (C1,),
            C1,
            "LT-01-P ON_SITE: in-house acil, staff notified, 112 absent",
            location=RedLocation.ON_SITE,
            action_primary="GO_TO_IN_HOUSE_ACIL",
            action_show_112=False,
        ),
        red(
            "axes/c1-unknown",
            "life",
            lt01p(),
            (C1,),
            C1,
            "LT-01-P UNKNOWN: ask one question, branch, never guess",
            location=RedLocation.UNKNOWN,
            ask_one_tr=ASK_ONE_TR,
        ),
    ]
    for location in (RedLocation.ON_SITE, RedLocation.UNKNOWN):
        tag = location.value.lower()
        cases.extend(
            [
                yellow(
                    f"loc/bs-{tag}",
                    "base",
                    syn(bekleme_suresi_gun_asimi=p(True)),
                    (BS,),
                    EK4Level.SARI_K2,
                    "YELLOW carries no location axis wherever the patient is",
                    location=location,
                ),
                yellow(
                    f"loc/oe-{tag}",
                    "overlay",
                    syn(p(d(30)), ek_katman_bulgusu=p(True)),
                    (OE,),
                    EK4Level.SARI_K2,
                    "overlay YELLOW carries no location axis",
                    location=location,
                ),
                yellow(
                    f"loc/c2-{tag}",
                    "life",
                    lt02p(),
                    (C2,),
                    EK4Level.SARI_K1,
                    "clinical SARI carries no location axis",
                    location=location,
                ),
            ]
        )
    return cases


# ---------------------------------------------------------------------------
# Family 8 — the merge matrix (42): 8 contexts × the inheritance sets, every
# cell an absolute expectation. Reading DOWN a column shows invariant 7 at
# runtime: as the rule set grows base → child → +overlay → +life, a level
# never decreases (test_triage_goldens.py additionally asserts the pairwise
# monotonicity over these cells).
# ---------------------------------------------------------------------------

_CHAIN_SETS = ("base", "child", "overlay", "child_overlay", "child_overlay_life")


def _ctx_h() -> dict[str, SlotAnswer]:
    answers = syn(
        renk_tercihi=p("kirmizi"),
        bekleme_suresi_asildi=p(True),
        bekleme_suresi_gun_asimi=p(True),
        ek_soru=p(True),
        ek_katman_bulgusu=p(True),
    )
    answers.update(lt01p())
    return answers


def merge_matrix() -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    # Context a — nothing asked at all: GREEN under every set.
    for rule_set in _CHAIN_SETS:
        cases.append(
            green(f"merge/a-{rule_set}", rule_set, {}, "empty state is GREEN under every set")
        )
    # Context b — parent RED slot: fires BK wherever base is inherited, and
    # the tightened child alongside it (siblings left Unknown: T ∨ U = T).
    ctx_b = syn(renk_tercihi=p("kirmizi"))
    for rule_set, fired in (
        ("base", (BK,)),
        ("child", (BK, CG)),
        ("child_overlay", (BK, CG)),
        ("child_overlay_life", (BK, CG)),
    ):
        cases.append(
            red(
                f"merge/b-{rule_set}",
                rule_set,
                ctx_b,
                fired,
                BK,
                "the inherited RED fires in every descendant set",
            )
        )
    cases.append(green("merge/b-overlay", "overlay", ctx_b, "the overlay alone knows no BK slot"))
    # Context c — the child-added slot: silent under base, RED under child.
    ctx_c = syn(ek_soru=p(True))
    for rule_set, fires in (
        ("base", False),
        ("child", True),
        ("overlay", False),
        ("child_overlay", True),
        ("child_overlay_life", True),
    ):
        if fires:
            cases.append(
                red(
                    f"merge/c-{rule_set}",
                    rule_set,
                    ctx_c,
                    (CD, CG),
                    CG,
                    "a child can only ADD acuity the base did not see",
                )
            )
        else:
            cases.append(
                green(
                    f"merge/c-{rule_set}",
                    rule_set,
                    ctx_c,
                    "sets without the child pack read the slot as Unknown",
                )
            )
    # Context d — the base SARI on its 7-day boundary.
    ctx_d = {ANCHOR: p(d(7)), "bekleme_suresi_gun_asimi": p(True)}
    for rule_set, fires in (
        ("base", True),
        ("child", True),
        ("overlay", False),
        ("child_overlay", True),
        ("child_overlay_life", True),
    ):
        if fires:
            cases.append(
                yellow(
                    f"merge/d-{rule_set}",
                    rule_set,
                    ctx_d,
                    (BS,),
                    EK4Level.SARI_K2,
                    "the inherited SARI fires identically down the chain",
                )
            )
        else:
            cases.append(green(f"merge/d-{rule_set}", rule_set, ctx_d, "overlay alone: Unknown"))
    # Context e — the overlay-added rule on its 30-day boundary.
    ctx_e = {ANCHOR: p(d(30)), "ek_katman_bulgusu": p(True)}
    for rule_set, fires in (
        ("base", False),
        ("child", False),
        ("overlay", True),
        ("child_overlay", True),
        ("child_overlay_life", True),
    ):
        if fires:
            cases.append(
                yellow(
                    f"merge/e-{rule_set}",
                    rule_set,
                    ctx_e,
                    (OE,),
                    EK4Level.SARI_K2,
                    "overlay rules join the union without touching the chain",
                )
            )
        else:
            cases.append(
                green(f"merge/e-{rule_set}", rule_set, ctx_e, "no overlay, no overlay rule")
            )
    # Context f — LT-01-P: only sets carrying the life-threat siblings fire.
    ctx_f = lt01p()
    for rule_set in ("base", "child", "overlay", "child_overlay"):
        cases.append(
            green(
                f"merge/f-{rule_set}",
                rule_set,
                ctx_f,
                "chest slots mean nothing to the synthetic chain",
            )
        )
    for rule_set in ("life", "child_overlay_life"):
        cases.append(
            red(
                f"merge/f-{rule_set}",
                rule_set,
                ctx_f,
                (C1,),
                C1,
                "the life-threat RED fires alone and alongside the whole chain",
            )
        )
    # Context g — LT-02-P mirrors f at SARI_K1.
    ctx_g = lt02p()
    for rule_set in ("base", "child", "overlay", "child_overlay"):
        cases.append(
            green(f"merge/g-{rule_set}", rule_set, ctx_g, "chest slots unknown to the chain")
        )
    for rule_set in ("life", "child_overlay_life"):
        cases.append(
            yellow(
                f"merge/g-{rule_set}",
                rule_set,
                ctx_g,
                (C2,),
                EK4Level.SARI_K1,
                "the life-threat SARI joins the union unchanged",
            )
        )
    # Context h — everything at once: the lattice max across every layer.
    ctx_h = _ctx_h()
    cases.extend(
        [
            red(
                "merge/h-base",
                "base",
                ctx_h,
                (BK, BS),
                BK,
                "base sees its two rules; RED wins the lattice",
            ),
            red(
                "merge/h-child",
                "child",
                ctx_h,
                (BK, BS, CD, CG),
                BK,
                "child adds firings, never removes",
            ),
            yellow(
                "merge/h-overlay",
                "overlay",
                ctx_h,
                (OE,),
                EK4Level.SARI_K2,
                "overlay alone caps at its own SARI",
            ),
            red(
                "merge/h-child_overlay",
                "child_overlay",
                ctx_h,
                (BK, BS, CD, CG, OE),
                BK,
                "five firings, one level: the max",
            ),
            red(
                "merge/h-child_overlay_life",
                "child_overlay_life",
                ctx_h,
                (BK, BS, CD, CG, OE, C1),
                C1,
                "the full union; the id-total tiebreak lands on the clinical RED",
            ),
        ]
    )
    return cases


# ---------------------------------------------------------------------------
# Family 9 — base.life_threat is a SIBLING set (invariant 7): it rides
# alongside every chain without being extendable or dilutable (3).
# ---------------------------------------------------------------------------


def sibling_life_threat() -> list[GoldenCase]:
    answers = syn(renk_tercihi=p("kirmizi"))
    answers.update(lt01n())
    return [
        green(
            "sib/life-synthetic-slots",
            "life",
            syn(renk_tercihi=p("kirmizi")),
            "the life-threat set reads no chain slot — no cross-talk",
        ),
        green(
            "sib/col-lt01n",
            "child_overlay_life",
            lt01n(),
            "the chain around the life-threat set never widens its near miss",
        ),
        red(
            "sib/col-mixed",
            "child_overlay_life",
            answers,
            (BK, CG),
            BK,
            "a chain RED fires while the life-threat near miss stays quiet",
        ),
    ]


# ---------------------------------------------------------------------------
# Family 12 — the equal-severity RED winner is total and stable (3): equal
# acuity, equal register → lowest rule id, so register and script always
# travel together from one clinician-approved rule.
# ---------------------------------------------------------------------------


def register_tiebreak() -> list[GoldenCase]:
    col_answers = lt01p()
    col_answers.update(syn(renk_tercihi=p("kirmizi")))
    return [
        red(
            "tie/child-renk-ek",
            "child",
            syn(renk_tercihi=p("kirmizi"), ek_soru=p(True)),
            (BK, CD, CG),
            BK,
            "two equal REDs: the id-total order picks the parent",
        ),
        red(
            "tie/child-bekleme-ek",
            "child",
            syn(bekleme_suresi_asildi=p(True), renk_tercihi=p("mavi"), ek_soru=p(True)),
            (BK, CD, CG),
            BK,
            "same winner from the parent's other arm",
        ),
        red(
            "tie/col-clinical-first",
            "child_overlay_life",
            col_answers,
            (C1, BK, CG),
            C1,
            "three equal REDs across chain and sibling set — deterministic winner",
        ),
    ]
