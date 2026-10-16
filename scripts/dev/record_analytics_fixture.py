"""Record the `GET /admin/analytics` bodies admin-web renders (INT-490).

`apps/admin-web/e2e/analytics.spec.ts` needs payloads to render. As with every
other ``record_*_fixture.py`` here, the payload is projected out of the real
code rather than hand-written: a hand-kept copy of the release shape, the
floor or the suppression rules would keep passing on the day the API stopped
matching it.

The INPUT is the one thing that cannot be real: no patient's data may reach a
fixture (invariant 6; files/06 §5 "CI: no PHI, synthetic fixtures"). It is
``tests/fixtures/analytics/synthetic_population.json`` — counts of simulated
people, no identifiers, no answers — and every figure in the output is what
the real :func:`~intake_platform.analytics.research.build_release` and
:func:`~intake_platform.analytics.research.release_payload` make of it:

- ``analytics.payload.json`` — the release as the live API builds it today:
  the funnel and the language live, the triage level and every per-question
  and platform view reported not collected, retention undecided;
- ``analytics.full.payload.json`` — the same population with EVERY view kind
  collected, which is what the page will be handed once the owner decides the
  raw-telemetry retention and consent scope (LD-06) and a producer records it.
  It exercises the per-question rendering and both withheld reasons;
- ``analytics.unconfigured.payload.json`` — no tenant registry: no view at all.

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import itertools
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from intake_platform.analytics import K_ANONYMITY_FLOOR
from intake_platform.analytics.research import (
    AnalyticsRetention,
    AnswerTimeBand,
    AsrBand,
    InputMode,
    Period,
    Platform,
    QuestionOutcome,
    QuestionRecord,
    RepeatBand,
    Stage,
    SubjectRecord,
    ViewKind,
    assert_payload_safe,
    build_release,
    release_payload,
)
from intake_platform.analytics.research.sources import LIVE_VIEW_KINDS, not_collected_reasons

REPO = Path(__file__).resolve().parents[2]
POPULATION = REPO / "tests" / "fixtures" / "analytics" / "synthetic_population.json"
OUT = REPO / "apps" / "admin-web" / "e2e" / "fixtures"
UNDECIDED = AnalyticsRetention(aggregates=None, raw_telemetry=None)


def _question(raw: dict[str, str]) -> QuestionRecord:
    mode = raw.get("input_mode")
    time = raw.get("time_band")
    asr = raw.get("asr_band")
    return QuestionRecord(
        outcome=QuestionOutcome(raw["outcome"]),
        repeat=RepeatBand(raw["repeat"]),
        input_mode=InputMode(mode) if mode else None,
        time_band=AnswerTimeBand(time) if time else None,
        asr_band=AsrBand(asr) if asr else None,
    )


def _records(groups: list[dict[str, Any]]) -> list[SubjectRecord]:
    keys = itertools.count(1)
    return [
        SubjectRecord(
            subject=f"synthetic-{next(keys)}",
            tenant="synthetic-tenant",
            protocol=group["protocol"],
            protocol_version=group["version"],
            stage=Stage(group["stage"]),
            locale="tr",
            platform=Platform(group["platform"]) if group.get("platform") else None,
            questions={q: _question(raw) for q, raw in group.get("questions", {}).items()},
        )
        for group in groups
        for _ in range(group["count"])
    ]


def _write(name: str, payload: dict[str, Any]) -> None:
    assert_payload_safe(payload, k=K_ANONYMITY_FLOOR)
    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    population = json.loads(POPULATION.read_text(encoding="utf-8"))
    period = Period.parse(population["period"])
    measured_at = datetime.fromisoformat(population["measured_at"])
    records = _records(population["groups"])

    live = build_release(
        records,
        period=period,
        k=K_ANONYMITY_FLOOR,
        collected=LIVE_VIEW_KINDS,
        not_collected=not_collected_reasons(UNDECIDED),
        measured_at=measured_at,
    )
    _write(
        "analytics.payload.json",
        release_payload(live, retention=UNDECIDED, admitted=1, refused=0),
    )

    full = build_release(
        records,
        period=period,
        k=K_ANONYMITY_FLOOR,
        collected=frozenset(ViewKind),
        not_collected={},
        measured_at=measured_at,
    )
    _write(
        "analytics.full.payload.json",
        release_payload(full, retention=UNDECIDED, admitted=1, refused=0),
    )

    empty = build_release(
        [],
        period=period,
        k=K_ANONYMITY_FLOOR,
        collected=LIVE_VIEW_KINDS,
        not_collected=not_collected_reasons(UNDECIDED),
        measured_at=measured_at,
    )
    _write(
        "analytics.unconfigured.payload.json",
        release_payload(empty, retention=UNDECIDED, admitted=None, refused=0),
    )


if __name__ == "__main__":
    main()
