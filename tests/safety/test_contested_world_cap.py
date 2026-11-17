"""INT-604 round 1 — the contested-world product is bounded, and the bound escalates.

A multi-select answer is a set of contested worlds (files/12 §7.3), and a rule
reading several multi-valued slots is evaluated over their product. Four lists
of 64 are about 16.7 million worlds, which no RED budget survives. Past
``MAX_CONTESTED_WORLDS`` the predicate is not evaluated and reads TRUE: the
rule fires (over-triage, the fail-closed direction). It is never skipped,
because a skip is a silent under-triage.

Pinned here, deterministically: the cap's both sides with a near miss, and the
NUMBER of worlds evaluated (every ``evaluate_node`` call is counted): at most
the cap per rule, and none at all past it. Wall-clock time is kept only as a
p95 over several runs, with headroom, so a slow CI host cannot flake it
(INT-604 runtime review round 1).
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, TriageLevel
from protocols.compile.life_threat import load_life_threat_set
from protocols.triage import TriageContext, engine, evaluate_triage, when_truth
from protocols.triage.context import SlotAnswer
from protocols.triage.engine import MAX_CONTESTED_WORLDS
from protocols.triage.expr import Truth
from protocols.types import RuleStatus

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
REFERENCE = datetime.fromisoformat("2026-08-29T10:00:00+03:00")
RED_BUDGET_MS = 300.0


#: Runs behind the timing p95: enough that one slow sample cannot decide it.
TIMING_RUNS = 10


@pytest.fixture()
def evaluated(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """Counts every world the engine evaluates (one ``evaluate_node`` call each)."""
    count = [0]
    real: Callable[..., Any] = engine.evaluate_node

    def counting(*args: Any, **kwargs: Any) -> Any:
        count[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(engine, "evaluate_node", counting)
    yield count


def _p95_ms(run: Callable[[], object]) -> float:
    samples = []
    for _ in range(TIMING_RUNS):
        started = time.perf_counter()
        run()
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.quantiles(samples, n=20)[-1]


def _set(*values: object) -> SlotAnswer:
    if len(values) == 1:
        return SlotAnswer(state=AnswerState.ASKED_PRESENT, values=values)  # type: ignore[arg-type]
    return SlotAnswer(state=AnswerState.CONTESTED, values=values)  # type: ignore[arg-type]


def _context(**answers: SlotAnswer) -> TriageContext:
    return TriageContext(reference_time=REFERENCE, answers=answers)


def _members(prefix: str, count: int) -> tuple[str, ...]:
    return tuple(f"{prefix}{index}" for index in range(count))


def test_at_the_cap_every_world_is_evaluated(evaluated: list[int]) -> None:
    # 64 × 64 = 4096 worlds, none firing: the exact answer, FALSE.
    assert MAX_CONTESTED_WORLDS == 64 * 64
    context = _context(a=_set(*_members("a", 64)), b=_set(*_members("b", 64)))
    assert when_truth("a == 'yok_degil' && b == 'b0'", context) is Truth.FALSE
    assert evaluated[0] == MAX_CONTESTED_WORLDS


def test_past_the_cap_the_predicate_escalates_to_true(evaluated: list[int]) -> None:
    # Past the cap, still none firing: the rule fires rather than being skipped,
    # and not one world is evaluated.
    context = _context(a=_set(*_members("a", 64)), b=_set(*_members("b", 64)), c=_set("x", "y"))
    assert when_truth("a == 'yok_degil' && b == 'b0' && c == 'x'", context) is Truth.TRUE
    assert evaluated[0] == 0


def test_near_miss_a_slot_the_predicate_does_not_read_never_counts() -> None:
    context = _context(
        a=_set(*_members("a", 64)), b=_set(*_members("b", 64)), unread=_set("x", "y", "z")
    )
    assert when_truth("a == 'yok_degil' && b == 'b0'", context) is Truth.FALSE


def test_sixteen_million_worlds_cost_nothing(evaluated: list[int]) -> None:
    context = _context(**{name: _set(*_members(name, 64)) for name in ("a", "b", "c", "d")})
    truth = when_truth("a == 'x' && b == 'x' && c == 'x' && d == 'x'", context)
    assert truth is Truth.TRUE
    assert evaluated[0] == 0


def test_the_worst_case_under_the_cap_fits_the_red_budget(evaluated: list[int]) -> None:
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
            "chest_pain.onset_at": _set("2026-08-29", "2026-08-28", "2026-08-27", "2026-08-26"),
        }
    )
    result = evaluate_triage(rules, context, RedLocation.REMOTE).result
    assert result.level is TriageLevel.RED
    # Deterministic: every world is evaluated and none past the cap. The widest
    # rule (the SARI sibling, which also reads trauma.recent) is 2·5·6·2·2·2·4 =
    # 3840 worlds, under the cap of 4096; the K2 RED is 960.
    assert 0 < evaluated[0] <= MAX_CONTESTED_WORLDS * len(rules)
    p95 = _p95_ms(lambda: evaluate_triage(rules, context, RedLocation.REMOTE))
    assert p95 < RED_BUDGET_MS, f"p95 {p95:.1f} ms"
