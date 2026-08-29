"""INT-059 golden families 1-2: every rule arm fires, and the near misses.

- ``fired_positive_arms`` (19): each disjunct arm of each merged rule fires
  on its own, with sibling arms bound to explicit negatives so the split is
  a clean TRUE-vs-FALSE rather than TRUE-vs-Unknown.
- ``near_miss_negatives`` (17): the load-bearing half. files/protocols/
  base.life_threat.yaml states why — a positive keeps passing under every
  loosening of the gate, so only a negative sitting one attribute away, on
  the exact attribute the gate turns on, can detect silent gate drift.
"""

from __future__ import annotations

from protocols.types import EK4Level
from triage_goldens_corpus import (
    BK,
    BS,
    C1,
    C2,
    CD,
    CG,
    OE,
    TODAY,
    GoldenCase,
    ab,
    d,
    p,
)
from triage_goldens_fixtures import (
    BK_REMOTE_TR,
    C1_REMOTE_TR,
    chest,
    green,
    lt01n,
    lt01p,
    lt02p,
    red,
    syn,
    yellow,
)

# ---------------------------------------------------------------------------
# Family 1 — every disjunct arm of every rule fires (19).
# Sibling arms are bound to explicit negatives here so each arm fires
# through a clean TRUE-vs-FALSE split; the merge matrix later exercises the
# same firings with siblings left Unknown (T ∨ U = T).
# ---------------------------------------------------------------------------


def fired_positive_arms() -> list[GoldenCase]:
    cases = [
        red(
            "arm/bk-renk",
            "base",
            syn(renk_tercihi=p("kirmizi"), bekleme_suresi_asildi=p(False)),
            (BK,),
            BK,
            "first disjunct arm alone fires the base RED",
            action_primary="CALL_112",
            action_show_112=True,
            action_tr=BK_REMOTE_TR,
            evidence_contains=((BK, 'renk_tercihi="kirmizi"'),),
        ),
        red(
            "arm/bk-bekleme",
            "base",
            syn(renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(True)),
            (BK,),
            BK,
            "second disjunct arm alone fires the base RED",
        ),
        red(
            "arm/bk-both",
            "base",
            syn(renk_tercihi=p("kirmizi"), bekleme_suresi_asildi=p(True)),
            (BK,),
            BK,
            "both arms true is still one firing of one rule",
        ),
        yellow(
            "arm/bs",
            "base",
            syn(bekleme_suresi_gun_asimi=p(True)),
            (BS,),
            EK4Level.SARI_K2,
            "the base SARI_K2 rule fires YELLOW with no RED axes",
        ),
        red(
            "arm/cg-ek",
            "child",
            syn(ek_soru=p(True), renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(False)),
            (CD, CG),
            CG,
            "the tightened rule's added disjunct fires it (and the child SARI)"
            " while the parent stays quiet",
        ),
        red(
            "arm/cg-renk",
            "child",
            syn(renk_tercihi=p("kirmizi"), bekleme_suresi_asildi=p(False), ek_soru=p(False)),
            (BK, CG),
            BK,
            "tighten_rule keeps the parent live: the parent's arm fires both",
        ),
        red(
            "arm/cg-bekleme",
            "child",
            syn(renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(True), ek_soru=p(False)),
            (BK, CG),
            BK,
            "the parent's second arm also fires parent and tightened child",
        ),
        yellow(
            "arm/oe",
            "overlay",
            syn(ek_katman_bulgusu=p(True)),
            (OE,),
            EK4Level.SARI_K2,
            "the overlay-added SARI_K2 rule fires on its own slot",
        ),
        yellow(
            "arm/c2-lt02p",
            "life",
            lt02p(),
            (C2,),
            EK4Level.SARI_K1,
            "LT-02-P: the negated-feature conjunction fires SARI_K1",
        ),
    ]
    for value in ("baskı", "sıkışma", "ağırlık"):
        cases.append(
            red(
                f"arm/c1-karakter-{value}",
                "life",
                chest(
                    p(TODAY),
                    present=p(True),
                    character=p(value),
                    radiation=p("yok"),
                    diaphoresis=ab(False),
                    dyspnoea=ab(False),
                    trauma=p(True),
                ),
                (C1,),
                C1,
                f"character set member {value!r} alone fires the cardiac arm",
            )
        )
    for value in ("kol", "çene", "sırt"):
        cases.append(
            red(
                f"arm/c1-yayilim-{value}",
                "life",
                chest(
                    p(TODAY),
                    present=p(True),
                    character=p("batıcı"),
                    radiation=p(value),
                    diaphoresis=p(False),
                    dyspnoea=p(False),
                    trauma=p(True),
                ),
                (C1,),
                C1,
                f"radiation set member {value!r} alone fires the cardiac arm",
            )
        )
    cases.extend(
        [
            red(
                "arm/c1-terleme",
                "life",
                chest(
                    p(TODAY),
                    present=p(True),
                    character=p("batıcı"),
                    radiation=p("yok"),
                    diaphoresis=p(True),
                    dyspnoea=p(False),
                    trauma=p(True),
                ),
                (C1,),
                C1,
                "diaphoresis alone fires the cardiac arm",
            ),
            red(
                "arm/c1-dispne",
                "life",
                chest(
                    p(TODAY),
                    present=p(True),
                    character=p("batıcı"),
                    radiation=p("yok"),
                    diaphoresis=p(False),
                    dyspnoea=p(True),
                    trauma=p(True),
                ),
                (C1,),
                C1,
                "dyspnoea alone fires the cardiac arm",
            ),
            red(
                "arm/c1-lt01p",
                "life",
                lt01p(),
                (C1,),
                C1,
                "LT-01-P verbatim: all four arms, KIRMIZI_K2 / EMERGENCY_NOW /"
                " ALERT / REMOTE / show_112",
                action_primary="CALL_112",
                action_show_112=True,
                action_tr=C1_REMOTE_TR,
            ),
            red(
                "arm/c1-iki-kol",
                "life",
                chest(
                    p(TODAY),
                    present=p(True),
                    character=p("sıkışma"),
                    radiation=p("yok"),
                    diaphoresis=p(False),
                    dyspnoea=p(True),
                    trauma=p(True),
                ),
                (C1,),
                C1,
                "two arms true is still exactly one firing",
            ),
        ]
    )
    return cases


# ---------------------------------------------------------------------------
# Family 2 — near-miss negatives (17): one attribute away from the positive,
# on the attribute the gate turns on (the repo's own golden convention,
# files/protocols/base.life_threat.yaml goldens block).
# ---------------------------------------------------------------------------


def near_miss_negatives() -> list[GoldenCase]:
    return [
        green(
            "miss/bk-diakritik",
            "base",
            syn(renk_tercihi=p("kırmızı"), bekleme_suresi_asildi=p(False)),
            "one diacritic away from the pack's ASCII 'kirmizi' — exact match only",
        ),
        green(
            "miss/bk-buyuk-harf",
            "base",
            syn(renk_tercihi=p("Kirmizi"), bekleme_suresi_asildi=p(False)),
            "capitalisation is a different value — no case folding in the grammar",
        ),
        green(
            "miss/bk-mavi",
            "base",
            syn(renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(False)),
            "both arms explicitly false",
        ),
        green(
            "miss/bs",
            "base",
            syn(bekleme_suresi_gun_asimi=p(False)),
            "boolean gate false on the reference day",
        ),
        green(
            "miss/child-all-off",
            "child",
            syn(ek_soru=p(False), renk_tercihi=p("mavi"), bekleme_suresi_asildi=p(False)),
            "every disjunct of parent, tightened child and child SARI false",
        ),
        green(
            "miss/oe",
            "overlay",
            syn(p(d(30)), ek_katman_bulgusu=p(False)),
            "overlay slot false exactly on the window boundary day",
        ),
        green(
            "miss/lt01n",
            "life",
            lt01n(),
            "LT-01-N verbatim: pleuritic pattern, 3 days old — neither chest rule may fire",
        ),
        green(
            "miss/c1-karakter",
            "life",
            chest(
                p(TODAY),
                present=p(True),
                character=p("yanma"),
                radiation=p("yok"),
                diaphoresis=p(False),
                dyspnoea=p(False),
                trauma=p(True),
            ),
            "character outside the set; trauma keeps the SARI sibling out",
        ),
        green(
            "miss/c1-yayilim",
            "life",
            chest(
                p(TODAY),
                present=p(True),
                character=p("batıcı"),
                radiation=p("bacak"),
                diaphoresis=p(False),
                dyspnoea=p(False),
                trauma=p(True),
            ),
            "radiation outside the set",
        ),
        green(
            "miss/c1-diakritik",
            "life",
            chest(
                p(TODAY),
                present=p(True),
                character=p("baski"),
                radiation=p("yok"),
                diaphoresis=p(False),
                dyspnoea=p(False),
                trauma=p(True),
            ),
            "ASCII 'baski' is one diacritic away from the set member 'baskı'",
        ),
        green(
            "miss/c1-kill-switch",
            "life",
            chest(
                p(TODAY),
                present=p(False),
                character=p("baskı"),
                radiation=p("kol"),
                diaphoresis=p(True),
                dyspnoea=p(True),
                trauma=p(True),
            ),
            "present == false kills the rule however loud the arms are"
            " (F ∧ T = F) — the conjunct a weakened gate would lose",
        ),
        red(
            "miss/c2-karakter",
            "life",
            lt02p(**{"chest_pain.character": p("baskı")}),
            (C1,),
            C1,
            "flipping character lands the case in the KIRMIZI arm, not nowhere",
        ),
        red(
            "miss/c2-yayilim",
            "life",
            lt02p(**{"chest_pain.radiation": p("kol")}),
            (C1,),
            C1,
            "flipping radiation lands KIRMIZI",
        ),
        red(
            "miss/lt02n-dispne",
            "life",
            lt02p(**{"associated.dyspnoea": p(True)}),
            (C1,),
            C1,
            "LT-02-N verbatim: added dyspnoea must fall OUT of SARI and INTO"
            " KIRMIZI — asserts where the case lands, not only where it does not",
        ),
        red(
            "miss/c2-terleme",
            "life",
            lt02p(**{"associated.diaphoresis": p(True)}),
            (C1,),
            C1,
            "flipping diaphoresis lands KIRMIZI",
        ),
        green(
            "miss/c2-travma",
            "life",
            lt02p(**{"trauma.recent": p(True)}),
            "recent trauma falls out of the SARI arm entirely (and matches no cardiac feature)",
        ),
        green(
            "miss/c2-mevcut-degil",
            "life",
            lt02p(**{"chest_pain.present": p(False)}),
            "no chest pain present — the shared kill-switch conjunct",
        ),
    ]
