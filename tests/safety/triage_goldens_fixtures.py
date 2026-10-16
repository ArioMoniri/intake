"""INT-059 golden-case fixtures: the answer-state shorthands and the
case constructors every family builds on.

Split out of ``triage_goldens_cases`` so no module in the corpus runs past
the 500-line ceiling CLAUDE.md sets. Nothing here encodes an expectation —
these are the shapes the families fill in.

``chest`` spells the life-threat slot names exactly as the gates in
files/protocols/base.life_threat.yaml reference them; ``lt01p``/``lt02p``/
``lt01n`` reproduce that file's own worked cases LT-01-P, LT-02-P and
LT-01-N so the corpus and the YAML cannot drift apart silently.
"""

from __future__ import annotations

from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, RedRegister, TriageLevel
from protocols.triage import SlotAnswer
from protocols.types import EK4Level, RedFlagRoute
from triage_goldens_corpus import ANCHOR, CP_ANCHOR, TODAY, GoldenCase, d, p

# Verbatim scripted strings from the packs (a disk edit to any of these is a
# golden failure — the mutation harness proves it).
BK_REMOTE_TR = "Hemen yardım isteyin."
BK_ONSITE_TR = "Görevlilere haber verin ve bekleyin."
C1_REMOTE_TR = "Hemen **112**'yi arayın."
# CD-111's decided do-not lists (INT-468), applied by INT-494: each location's
# list, exact and in record order. The removed nil-by-mouth line is in neither.
C1_REMOTE_DO_NOTS = (
    "Hastaneye kendiniz araba kullanarak gitmeyin.",
    "Yanınızda biri varsa sizi yalnız bırakmasına izin vermeyin.",
)
C1_ONSITE_DO_NOTS = (
    "Poliklinik sırasında beklemeyin.",
    "Tek başınıza gitmeyin — yanınızdaki kişiden ya da bir görevliden yardım isteyin.",
)

# Every active RED in merged content routes EMERGENCY_NOW, so the route
# axis is pinned by default on every RED golden; a case overrides it the
# same way it overrides register or ek4.
_RED_DEFAULTS = {
    "level": TriageLevel.RED,
    "ek4": EK4Level.KIRMIZI_K2,
    "register": RedRegister.ALERT,
    "route": RedFlagRoute.EMERGENCY_NOW,
}


def syn(anchor: SlotAnswer | None = None, **slots: SlotAnswer) -> dict[str, SlotAnswer]:
    """Synthetic-pack answers; ``anchor`` defaults to the reference day."""
    answers: dict[str, SlotAnswer] = {}
    if anchor is None:
        anchor = p(TODAY)
    if anchor.values or anchor.state is not AnswerState.NOT_ASKED:
        answers[ANCHOR] = anchor
    answers.update(slots)
    return answers


def no_anchor(**slots: SlotAnswer) -> dict[str, SlotAnswer]:
    """Synthetic answers with the tense anchor never asked at all."""
    return dict(slots)


def chest(
    anchor: SlotAnswer | None,
    present: SlotAnswer | None = None,
    character: SlotAnswer | None = None,
    radiation: SlotAnswer | None = None,
    diaphoresis: SlotAnswer | None = None,
    dyspnoea: SlotAnswer | None = None,
    trauma: SlotAnswer | None = None,
) -> dict[str, SlotAnswer]:
    """Life-threat answers, spelled exactly as the gates reference them."""
    pairs: tuple[tuple[str, SlotAnswer | None], ...] = (
        (CP_ANCHOR, anchor),
        ("chest_pain.present", present),
        ("chest_pain.character", character),
        ("chest_pain.radiation", radiation),
        ("associated.diaphoresis", diaphoresis),
        ("associated.dyspnoea", dyspnoea),
        ("trauma.recent", trauma),
    )
    return {name: answer for name, answer in pairs if answer is not None}


def lt01p(anchor: SlotAnswer | None = None) -> dict[str, SlotAnswer]:
    """The file's own LT-01-P: pressure + radiation + sweating + dyspnoea."""
    return chest(
        anchor if anchor is not None else p(TODAY),
        present=p(True),
        character=p("baskı"),
        radiation=p("kol"),
        diaphoresis=p(True),
        dyspnoea=p(True),
    )


def lt02p(anchor: SlotAnswer | None = None, **overrides: SlotAnswer) -> dict[str, SlotAnswer]:
    """The file's own LT-02-P: stabbing, local, everything cardiac negated."""
    answers = chest(
        anchor if anchor is not None else p(TODAY),
        present=p(True),
        character=p("batıcı"),
        radiation=p("yok"),
        diaphoresis=p(False),
        dyspnoea=p(False),
        trauma=p(False),
    )
    answers.update(overrides)
    return answers


def lt01n() -> dict[str, SlotAnswer]:
    """The file's own LT-01-N near miss: pleuritic-pattern pain, 3 days old."""
    return chest(
        p(d(3)),
        present=p(True),
        character=p("batıcı"),
        radiation=p("yok"),
        diaphoresis=p(False),
        dyspnoea=p(False),
    )


def green(case_id: str, rule_set: str, answers: dict[str, SlotAnswer], note: str) -> GoldenCase:
    return GoldenCase(id=case_id, rule_set=rule_set, answers=answers, note=note)


def yellow(
    case_id: str,
    rule_set: str,
    answers: dict[str, SlotAnswer],
    fired: tuple[str, ...],
    ek4: EK4Level,
    note: str,
    location: RedLocation = RedLocation.REMOTE,
) -> GoldenCase:
    return GoldenCase(
        id=case_id,
        rule_set=rule_set,
        answers=answers,
        note=note,
        location=location,
        level=TriageLevel.YELLOW,
        ek4=ek4,
        fired=fired,
    )


def red(
    case_id: str,
    rule_set: str,
    answers: dict[str, SlotAnswer],
    fired: tuple[str, ...],
    winner: str,
    note: str,
    location: RedLocation = RedLocation.REMOTE,
    **expectations: object,
) -> GoldenCase:
    return GoldenCase(
        id=case_id,
        rule_set=rule_set,
        answers=answers,
        note=note,
        location=location,
        fired=fired,
        winner=winner,
        **{**_RED_DEFAULTS, **expectations},  # type: ignore[arg-type]
    )
