"""INT-604 — a question is anchored to when it is answered, not to the visit date.

The intake is answered hours or days before the visit, so "bugün" in a question
means the day the patient answers, while a clinician reads the note on the visit
day. Owner decision M2 (17 Nov 2026, D18 scope): where the meaning is "these
days", the wording says so ("şu sıralar"); where it means this appointment, it
says "bu randevu" / "bu görüşme"; where the clinical meaning is genuinely today
(onset today), "bugün" stays and the anchor is stated (the mobile note records
the answering day; apps/mobile lib/intake/note.ts).

Scope: the served-candidate packs — base.intake and the generated L0 specialty
tree, which is what a serve path can reach. The review queue
(``packages/protocols/review/``) is generated from proposal evidence and is not
servable (HB-C1); its day-relative lines are listed for the physician in
docs/evidence/INT-604.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
PACKS = (
    REPO / "packages" / "protocols" / "base" / "intake.yaml",
    *sorted((REPO / "packages" / "protocols" / "specialty").glob("*.yaml")),
)

#: Day-relative words, matched as whole words, any case (Turkish-aware lower()).
DAY_RELATIVE = re.compile(
    r"(?<!\w)(bugün\w*|dün\w*|yarın\w*|bu sabah|bu akşam|bu gece|bu hafta\w*)(?!\w)"
)

#: (pack file name, slot pointer) pairs that keep a day-relative word because
#: the clinical meaning IS that day, each with its stated anchor. Empty: no
#: served-candidate pack question needs one today.
ANCHORED: dict[tuple[str, str], str] = {}


def _strings(node: Any, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{pointer}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _strings(value, f"{pointer}/{index}")
    elif isinstance(node, str) and "_tr/" in pointer + "/":
        yield pointer, node


def _hits(text: str) -> list[str]:
    return DAY_RELATIVE.findall(text.replace("İ", "i").lower())


@pytest.mark.parametrize("pack", PACKS, ids=lambda p: p.name)
def test_no_unanchored_day_relative_word_in_a_served_candidate_question(pack: Path) -> None:
    doc = yaml.safe_load(pack.read_text(encoding="utf-8"))
    offenders = [
        (pointer, text)
        for pointer, text in _strings(doc.get("sections", {}), "/sections")
        if _hits(text) and (pack.name, pointer) not in ANCHORED
    ]
    assert offenders == []


@pytest.mark.parametrize(
    ("text", "hit"),
    [
        ("Bugünkü randevunuzun sebebini kısaca anlatır mısınız?", True),
        ("Sizi bugün hekime getiren nedir?", True),
        ("Bu sabah başladı mı?", True),
        ("Sizi şu sıralar hekime getiren şeyi anlatır mısınız?", False),
        ("Bu randevunuzun sebebini kısaca anlatır mısınız?", False),
        ("Bu görüşmeden ayrılırken en çok neyin çözülmüş olmasını istersiniz?", False),
    ],
)
def test_the_matcher_and_its_near_misses(text: str, hit: bool) -> None:
    assert bool(_hits(text)) is hit


def test_the_rewritten_base_intake_questions() -> None:
    doc = yaml.safe_load(PACKS[0].read_text(encoding="utf-8"))
    slots = doc["sections"]["reason_for_visit"]["slots"]
    assert slots["chief_complaint_text"]["ask_tr"]["tr"].startswith(
        "Sizi şu sıralar hekime getiren"
    )
    assert slots["patient_goals"]["follow_up_tr"]["tr"] == (
        "Bu görüşmeden ayrılırken en çok neyin çözülmüş olmasını istersiniz?"
    )
