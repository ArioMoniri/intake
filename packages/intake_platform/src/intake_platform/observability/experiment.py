"""INT-175 — the recorded-experiment gate (files/08 §9 "eval gates (Langfuse
experiments...)"; CLAUDE.md inv. 1/6/17; "Never call paid/live APIs in tests
or CI").

The acceptance asks CI to "run a recorded simulator experiment and gate on
scores". Two properties make that safe to run in CI at all:

1. **It is recorded.** No model is called. The run file is the output of a
   simulator pass, committed as a fixture, so the gate is deterministic and
   costs nothing.
2. **It carries no content.** A recorded run is a list of *structural*
   results — did the output validate against the slot schema, how many
   required slots were filled, did PolicyGuard pass, how long it took. It is
   loaded through the same deny-by-default rule as a trace span: unknown keys
   are refused rather than ignored, and every string must be id-shaped, so a
   run file that somebody regenerated with transcripts in it **fails to
   load** rather than being quietly scrubbed. A gate that repairs its own
   input teaches nobody anything.

The scores themselves are deliberately boring and structural. Nothing here is
an accuracy figure: these are counts and ratios over a named recorded corpus,
which is what invariant 20 permits, and they live in ``docs/evidence/`` when
they are reported.

One score is not a threshold but a hard rule: **invariant 1**. Triage
RED/YELLOW come from ``packages/protocols/triage`` alone; the LLM may emit
``candidate_flag`` and nothing more. A recorded run in which any case shows
the model producing a triage level fails the gate outright, whatever the
other numbers say.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from intake_platform.observability.spans import (
    SpanFieldRefused,
    SpanKind,
    SpanOutcome,
    refuse_unless_ref_shaped,
)

__all__ = [
    "PERMITTED_LLM_TRIAGE_LEVELS",
    "ExperimentRecord",
    "ExperimentScores",
    "GateResult",
    "RecordRefused",
    "Thresholds",
    "gate",
    "load_records",
    "load_thresholds",
    "score",
]

#: What the extractor is allowed to have produced. Anything else in a recorded
#: run means the LLM reached a triage level, which invariant 1 forbids.
PERMITTED_LLM_TRIAGE_LEVELS: Final[frozenset[str]] = frozenset({"none", "candidate_flag"})

_RECORD_KEYS: Final[tuple[str, ...]] = (
    "case_id",
    "kind",
    "outcome",
    "schema_valid",
    "required_slots_filled",
    "required_slots_total",
    "llm_triage_level",
    "policyguard_pass",
    "latency_ms",
)

_THRESHOLD_KEYS: Final[tuple[str, ...]] = (
    "min_schema_valid_ratio",
    "min_slot_fill_ratio",
    "min_policyguard_pass_ratio",
    "max_latency_p95_ms",
)


class RecordRefused(ValueError):
    """A recorded-run row is not loadable.

    Like every other refusal on this boundary, the message names the key and
    never the value: a run file that leaked a transcript must not leak it
    again through the error that caught it (invariant 6).
    """


@dataclass(frozen=True)
class ExperimentRecord:
    """One recorded simulator case, structurally."""

    case_id: str
    kind: SpanKind
    outcome: SpanOutcome
    schema_valid: bool
    required_slots_filled: int
    required_slots_total: int
    llm_triage_level: str
    policyguard_pass: bool
    latency_ms: int

    def __post_init__(self) -> None:
        refuse_unless_ref_shaped("case_id", self.case_id)
        refuse_unless_ref_shaped("llm_triage_level", self.llm_triage_level)
        if self.required_slots_total <= 0:
            raise RecordRefused("key 'required_slots_total' must be positive")
        if not 0 <= self.required_slots_filled <= self.required_slots_total:
            raise RecordRefused("key 'required_slots_filled' must be within required_slots_total")
        if self.latency_ms < 0:
            raise RecordRefused("key 'latency_ms' must be non-negative")


@dataclass(frozen=True)
class Thresholds:
    """The committed pass bar. Ratios in [0, 1]; latency in milliseconds."""

    min_schema_valid_ratio: float
    min_slot_fill_ratio: float
    min_policyguard_pass_ratio: float
    max_latency_p95_ms: int

    def __post_init__(self) -> None:
        for name in (
            "min_schema_valid_ratio",
            "min_slot_fill_ratio",
            "min_policyguard_pass_ratio",
        ):
            value = float(getattr(self, name))
            if not 0.0 < value <= 1.0:
                raise RecordRefused(f"threshold {name!r} must be in (0, 1]")
        if self.max_latency_p95_ms <= 0:
            raise RecordRefused("threshold 'max_latency_p95_ms' must be positive")


@dataclass(frozen=True)
class ExperimentScores:
    """What the run measured. Counts and ratios over a named corpus — never
    described as a property of the product (invariant 20)."""

    cases: int
    schema_valid_ratio: float
    slot_fill_ratio: float
    policyguard_pass_ratio: float
    latency_p95_ms: int
    llm_triage_violations: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "schema_valid_ratio": round(self.schema_valid_ratio, 4),
            "slot_fill_ratio": round(self.slot_fill_ratio, 4),
            "policyguard_pass_ratio": round(self.policyguard_pass_ratio, 4),
            "latency_p95_ms": self.latency_p95_ms,
            "llm_triage_violations": list(self.llm_triage_violations),
        }


@dataclass(frozen=True)
class GateResult:
    passed: bool
    failures: tuple[str, ...]
    scores: ExperimentScores


def _require_keys(raw: dict[str, Any], keys: tuple[str, ...], what: str) -> None:
    present = set(raw)
    missing = sorted(set(keys) - present)
    if missing:
        raise RecordRefused(f"{what} is missing {missing}")
    unknown = sorted(present - set(keys))
    if unknown:
        raise RecordRefused(
            f"{what} carries unknown keys {unknown} — the key set is closed so a run "
            "regenerated with prompts or completions in it fails to load rather than "
            "being scrubbed (CLAUDE.md invariant 6, HB-L6). The values are not echoed."
        )


def _bool(raw: dict[str, Any], key: str) -> bool:
    value = raw[key]
    if not isinstance(value, bool):
        raise RecordRefused(f"key {key!r} must be a JSON boolean")
    return value


def _int(raw: dict[str, Any], key: str) -> int:
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise RecordRefused(f"key {key!r} must be a JSON integer")
    return value


def _enum_member(raw: dict[str, Any], key: str, kind: type[SpanKind] | type[SpanOutcome]) -> Any:
    value = raw[key]
    if not isinstance(value, str):
        raise RecordRefused(f"key {key!r} must be a string")
    try:
        return kind(value)
    except ValueError:
        raise RecordRefused(
            f"key {key!r} is not one of {sorted(member.value for member in kind)}"
        ) from None


def load_records(path: Path) -> tuple[ExperimentRecord, ...]:
    """Load a recorded run (JSON lines), refusing anything off the closed schema."""
    records: list[ExperimentRecord] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as err:
            raise RecordRefused(f"line {lineno} is not JSON: {err.msg}") from None
        if not isinstance(raw, dict):
            raise RecordRefused(f"line {lineno} is not a JSON object")
        _require_keys(raw, _RECORD_KEYS, f"line {lineno}")
        try:
            records.append(
                ExperimentRecord(
                    case_id=str(raw["case_id"]),
                    kind=_enum_member(raw, "kind", SpanKind),
                    outcome=_enum_member(raw, "outcome", SpanOutcome),
                    schema_valid=_bool(raw, "schema_valid"),
                    required_slots_filled=_int(raw, "required_slots_filled"),
                    required_slots_total=_int(raw, "required_slots_total"),
                    llm_triage_level=str(raw["llm_triage_level"]),
                    policyguard_pass=_bool(raw, "policyguard_pass"),
                    latency_ms=_int(raw, "latency_ms"),
                )
            )
        except SpanFieldRefused as err:
            # re-raised, never chained: the chained exception would be logged
            # alongside this one and it must not carry the value either.
            raise RecordRefused(f"line {lineno}: {err}") from None
    if not records:
        raise RecordRefused(f"{path.name} holds no records — an empty run gates nothing")
    return tuple(records)


def load_thresholds(path: Path) -> Thresholds:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RecordRefused(f"{path.name} must be a mapping")
    _require_keys(raw, _THRESHOLD_KEYS, path.name)
    return Thresholds(
        min_schema_valid_ratio=float(raw["min_schema_valid_ratio"]),
        min_slot_fill_ratio=float(raw["min_slot_fill_ratio"]),
        min_policyguard_pass_ratio=float(raw["min_policyguard_pass_ratio"]),
        max_latency_p95_ms=_int(raw, "max_latency_p95_ms"),
    )


def _p95(values: list[int]) -> int:
    """Nearest-rank p95 — no interpolation, so the number is always one that
    was actually observed."""
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return ordered[rank - 1]


def score(records: tuple[ExperimentRecord, ...] | list[ExperimentRecord]) -> ExperimentScores:
    rows = list(records)
    if not rows:
        raise RecordRefused("cannot score an empty run")
    slots_total = sum(row.required_slots_total for row in rows)
    return ExperimentScores(
        cases=len(rows),
        schema_valid_ratio=sum(1 for row in rows if row.schema_valid) / len(rows),
        slot_fill_ratio=sum(row.required_slots_filled for row in rows) / slots_total,
        policyguard_pass_ratio=sum(1 for row in rows if row.policyguard_pass) / len(rows),
        latency_p95_ms=_p95([row.latency_ms for row in rows]),
        llm_triage_violations=tuple(
            row.case_id for row in rows if row.llm_triage_level not in PERMITTED_LLM_TRIAGE_LEVELS
        ),
    )


def gate(scores: ExperimentScores, thresholds: Thresholds) -> GateResult:
    """Judge ``scores`` against ``thresholds``. Every failure is named."""
    failures: list[str] = []
    if scores.llm_triage_violations:
        failures.append(
            "invariant 1: the extractor produced a triage level in "
            f"{list(scores.llm_triage_violations)} — RED/YELLOW come from "
            "packages/protocols/triage alone, and the LLM may reach candidate_flag at most"
        )
    if scores.schema_valid_ratio < thresholds.min_schema_valid_ratio:
        failures.append(
            f"schema_valid_ratio {scores.schema_valid_ratio:.4f} < "
            f"{thresholds.min_schema_valid_ratio:.4f}"
        )
    if scores.slot_fill_ratio < thresholds.min_slot_fill_ratio:
        failures.append(
            f"slot_fill_ratio {scores.slot_fill_ratio:.4f} < {thresholds.min_slot_fill_ratio:.4f}"
        )
    if scores.policyguard_pass_ratio < thresholds.min_policyguard_pass_ratio:
        failures.append(
            f"policyguard_pass_ratio {scores.policyguard_pass_ratio:.4f} < "
            f"{thresholds.min_policyguard_pass_ratio:.4f}"
        )
    if scores.latency_p95_ms > thresholds.max_latency_p95_ms:
        failures.append(f"latency_p95_ms {scores.latency_p95_ms} > {thresholds.max_latency_p95_ms}")
    return GateResult(passed=not failures, failures=tuple(failures), scores=scores)
