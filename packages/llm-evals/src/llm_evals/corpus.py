"""The committed extraction eval corpus (INT-083).

A case is a transcript, the slot schema it is extracted under, and one
completion in recorded form. Replaying it exercises the real fence, the real
schema builder, the real gateway adapter and the real parser; nothing here
reimplements any of them, because an eval that reimplements what it evaluates
measures the reimplementation. (Where these completions come from is the
provenance paragraph below, and it matters.)

**Every string in the corpus is synthetic.** The one case that carries a TC
Kimlik number and a mobile number reuses the values already committed in
``tests/fixtures/deid/pattern_corpus.jsonl`` (INT-015), so this package
introduces no new identifier-shaped value into the repository. That case
exists to prove the negative: a transcript full of identifiers produces a
trace span carrying none of them (CLAUDE.md invariant 6, KVKK-9).

**Adversarial cases are marked and are scored separately.** A case whose
expected outcome is not ``ok`` is a refusal the boundary must make, not a
quality measurement; mixing the two would let a boundary regression be
absorbed as a lower schema-valid ratio instead of failing loudly. The scored
run is the non-adversarial subset (:func:`llm_evals.runner.run_corpus`), and
every adversarial case is asserted individually in
``tests/ai/test_extraction_contract.py``.

**Provenance, stated plainly, because it changes what these numbers mean.**
The completions committed here were **authored** in the exact shape a
recording takes; they were not captured from a model run. No pinned extraction
model has been served on this branch — there is no GPU and no daemon — so
there was nothing to record from. That is enough for what INT-083's acceptance
asks (the boundary, the schema, the refusals and the score wiring are all
exercised for real), and it is *not* evidence about how any model behaves.
``latency_ms`` and the token counts are ``0`` in every case and
``model_revision`` reads ``unrecorded-no-model-served``, for the same reason:
nothing was timed, counted or served, and a plausible-looking figure or a
real-looking commit hash would read as a measurement to every later reader
with no diff that makes it look wrong. The first run of a
pinned model on a GPU host replaces these files with real captures and nothing
else here moves.

**Nothing here is an accuracy claim.** The scores this corpus feeds are
counts and ratios over a named corpus on a date (CLAUDE.md invariant 20); the
measurements are reported in ``docs/evidence/INT-083.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from intake_platform.llm import SlotSchema, SlotSpec, SlotValueType, build_slot_schema
from intake_platform.observability.spans import SpanOutcome

__all__ = ["CASE_KEYS", "SCHEMA_KEYS", "ExtractionCase", "CorpusError", "load_cases"]

CASE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "case_id",
        "schema",
        "transcript_tr",
        "expected_outcome",
        "completion",
        "model_id",
        "model_revision",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "note",
    }
)

SCHEMA_KEYS: Final[frozenset[str]] = frozenset({"schema_id", "step_id", "specs", "valuesets"})


class CorpusError(ValueError):
    """A corpus file is not loadable. The run stops rather than skipping a case."""


@dataclass(frozen=True)
class ExtractionCase:
    """One recorded case, ready to replay."""

    case_id: str
    transcript_tr: str
    schema: SlotSchema
    expected_outcome: SpanOutcome
    completion_text: str
    model_id: str
    model_revision: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    note: str = ""

    @property
    def adversarial(self) -> bool:
        """A case the boundary must refuse. Excluded from the scored run."""
        return self.expected_outcome is not SpanOutcome.OK


def _require_keys(raw: dict[str, Any], keys: frozenset[str], what: str) -> None:
    unknown = sorted(set(raw) - keys)
    if unknown:
        raise CorpusError(f"{what} carries unknown key(s) {unknown}; the key set is closed")


def _load_schema(path: Path) -> SlotSchema:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CorpusError(f"{path.name} must be a JSON object")
    _require_keys(raw, SCHEMA_KEYS, path.name)
    specs = tuple(
        SlotSpec(
            ref=str(item["ref"]),
            value_type=SlotValueType(item["value_type"]),
            required=bool(item.get("required", False)),
            unit=item.get("unit"),
            valueset=item.get("valueset"),
        )
        for item in raw["specs"]
    )
    return build_slot_schema(
        step_id=str(raw["step_id"]), specs=specs, valuesets=raw.get("valuesets") or {}
    )


def _load_case(path: Path, schemas: dict[str, SlotSchema]) -> ExtractionCase:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CorpusError(f"{path.name} must be a JSON object")
    _require_keys(raw, CASE_KEYS, path.name)
    missing = sorted(CASE_KEYS - {"note"} - set(raw))
    if missing:
        raise CorpusError(f"{path.name} is missing {missing}")
    schema_name = str(raw["schema"])
    if schema_name not in schemas:
        raise CorpusError(f"{path.name} names schema {schema_name!r}, which is not committed")
    completion = raw["completion"]
    return ExtractionCase(
        case_id=str(raw["case_id"]),
        transcript_tr=str(raw["transcript_tr"]),
        schema=schemas[schema_name],
        expected_outcome=SpanOutcome(str(raw["expected_outcome"])),
        completion_text=(
            completion
            if isinstance(completion, str)
            else json.dumps(completion, ensure_ascii=False, sort_keys=True)
        ),
        model_id=str(raw["model_id"]),
        model_revision=str(raw["model_revision"]),
        input_tokens=int(raw["input_tokens"]),
        output_tokens=int(raw["output_tokens"]),
        latency_ms=int(raw["latency_ms"]),
        note=str(raw.get("note", "")),
    )


def load_cases(root: Path) -> tuple[ExtractionCase, ...]:
    """Load every committed case under ``root``, in case-id order."""
    schema_dir, case_dir = root / "schemas", root / "cases"
    if not schema_dir.is_dir() or not case_dir.is_dir():
        raise CorpusError(f"{root} is not an extraction corpus (expects schemas/ and cases/)")
    schemas = {path.stem: _load_schema(path) for path in sorted(schema_dir.glob("*.json"))}
    cases = tuple(_load_case(path, schemas) for path in sorted(case_dir.glob("*.json")))
    if not cases:
        raise CorpusError(f"{root} holds no cases — an empty eval set measures nothing")
    seen = {case.case_id for case in cases}
    if len(seen) != len(cases):
        raise CorpusError("two cases share a case_id")
    return tuple(sorted(cases, key=lambda case: case.case_id))
