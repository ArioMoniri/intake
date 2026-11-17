"""INT-604 round 1 — the contested-world product is bounded, and the bound escalates.

A multi-select answer is a set of contested worlds (files/12 §7.3), and a rule
reading several multi-valued slots is evaluated over their product. Four lists
of 64 are about 16.7 million worlds, which no RED budget survives. Past
``MAX_CONTESTED_WORLDS`` the predicate is not evaluated and reads TRUE: the
rule fires (over-triage, the fail-closed direction). It is never skipped,
because a skip is a silent under-triage.

Pinned here: the cap's both sides with a near miss, and a timing bound on the
worst case the cap still evaluates, over the served chest-pain rules.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, TriageLevel
from protocols.compile.life_threat import load_life_threat_set
from protocols.triage import TriageContext, evaluate_triage, when_truth
from protocols.triage.context import SlotAnswer
from protocols.triage.engine import MAX_CONTESTED_WORLDS
from protocols.triage.expr import Truth
from protocols.types import RuleStatus

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
REFERENCE = datetime.fromisoformat("2026-08-29T10:00:00+03:00")
RED_BUDGET_MS = 300.0


def _set(*values: object) -> SlotAnswer:
    if len(values) == 1:
        return SlotAnswer(state=AnswerState.ASKED_PRESENT, values=values)  # type: ignore[arg-type]
    return SlotAnswer(state=AnswerState.CONTESTED, values=values)  # type: ignore[arg-type]


def _context(**answers: SlotAnswer) -> TriageContext:
    return TriageContext(reference_time=REFERENCE, answers=answers)


def _members(prefix: str, count: int) -> tuple[str, ...]:
    return tuple(f"{prefix}{index}" for index in range(count))


def test_at_the_cap_every_world_is_evaluated() -> None:
    # 64 × 64 = 4096 worlds, none firing: the exact answer, FALSE.
    assert MAX_CONTESTED_WORLDS == 64 * 64
    context = _context(a=_set(*_members("a", 64)), b=_set(*_members("b", 64)))
    assert when_truth("a == 'yok_degil' && b == 'b0'", context) is Truth.FALSE


def test_past_the_cap_the_predicate_escalates_to_true() -> None:
    # One more world, still none firing: the rule fires rather than being skipped.
    context = _context(a=_set(*_members("a", 64)), b=_set(*_members("b", 64)), c=_set("x", "y"))
    assert when_truth("a == 'yok_degil' && b == 'b0' && c == 'x'", context) is Truth.TRUE


def test_near_miss_a_slot_the_predicate_does_not_read_never_counts() -> None:
    context = _context(
        a=_set(*_members("a", 64)), b=_set(*_members("b", 64)), unread=_set("x", "y", "z")
    )
    assert when_truth("a == 'yok_degil' && b == 'b0'", context) is Truth.FALSE


def test_sixteen_million_worlds_cost_nothing() -> None:
    context = _context(**{name: _set(*_members(name, 64)) for name in ("a", "b", "c", "d")})
    started = time.perf_counter()
    truth = when_truth("a == 'x' && b == 'x' && c == 'x' && d == 'x'", context)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert truth is Truth.TRUE
    assert elapsed_ms < RED_BUDGET_MS


def test_the_worst_case_under_the_cap_fits_the_red_budget() -> None:
    """Every slot the served chest-pain rules read, contested as widely as the
    committed sets allow, with the product held just under the cap."""
    rules = [
        entry.rule
        for entry in load_life_threat_set(LIFE_THREAT).rules
        if entry.rule.status is RuleStatus.ACTIVE
    ]
    context = _context(
        **{
            "chest_pain.present": _set(True, False),
            "chest_pain.character": _set("yanma", "başka bir his", "baskı", "sıkışma", "ağırlık"),
            "chest_pain.radiation": _set("omuz", "boyun", "başka bir yer", "kol", "çene", "sırt"),
            "associated.diaphoresis": _set(True, False),
            "associated.dyspnoea": _set(True, False),
            "trauma.recent": _set(True, False),
            "chest_pain.onset_at": _set(
                "2026-08-29", "2026-08-28", "2026-08-27", "2026-08-26", "2026-08-25"
            ),
        }
    )
    started = time.perf_counter()
    result = evaluate_triage(rules, context, RedLocation.REMOTE).result
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert result.level is TriageLevel.RED
    assert elapsed_ms < RED_BUDGET_MS, f"{elapsed_ms:.1f} ms"
