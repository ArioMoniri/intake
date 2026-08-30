"""Replay the corpus through the real boundary and score it (INT-083).

The run is entirely offline. Each case's recorded completion is materialised
into a recording directory keyed exactly as
:class:`~intake_platform.llm.RecordedLlmGateway` looks one up, and the case is
then driven through the ordinary
:class:`~intake_platform.llm.ExtractionWork` — the same fence, the same
schema, the same parser, the same trace emission that production runs. No
model is called; CLAUDE.md is explicit that CI never calls a paid or live API,
and ``make eval-live`` is the only path that ever would.

The output is the structural row INT-175's gate loads
(``intake_platform.observability.experiment``), so a regression in the
extraction boundary shows up as a failing committed threshold rather than as
a number in a report nobody reads.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from intake_platform.llm import (
    ExtractionRun,
    ExtractionWork,
    RecordedLlmGateway,
    build_extraction_prompt,
    extraction_record,
)
from intake_platform.observability.experiment import ExperimentRecord
from intake_platform.observability.spans import SpanKind, SpanOutcome

from llm_evals.corpus import ExtractionCase, load_cases

__all__ = [
    "CollectingSpanSink",
    "recorded_gateway_for",
    "run_case",
    "run_corpus",
    "run_corpus_rows",
]

#: The corpus is replayed with a fixed nonce so a recording is reproducible.
#: Production mints a fresh one per call — that is what makes the closing
#: fence unguessable — but a replay has nobody to hide it from and a moving
#: nonce would make every recording a one-shot.
REPLAY_NONCE = "0" * 16

_TENANT = "t_evalcorpus"
_SESSION_HASH = "e" * 64
_PROTOCOL_HASH = "0" * 64


class CollectingSpanSink:
    """A :class:`~intake_platform.observability.spans.SpanSink` that keeps what
    it was given, so an eval run can be inspected without a trace store.

    Not a stand-in for one: the payloads it holds are the very payloads the
    OTLP sink would export, and the point of keeping them is to assert what
    left the process.
    """

    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict[str, str | int]]] = []

    def emit(self, name: str, attributes: Mapping[str, str | int]) -> None:
        self.emitted.append((name, dict(attributes)))


def recorded_gateway_for(cases: Sequence[ExtractionCase], *, root: Path) -> RecordedLlmGateway:
    """Materialise each case's recorded completion under ``root``.

    The file name is the input digest the gateway computes from the schema and
    the fenced content, so a case whose transcript or schema drifts stops
    matching its own recording instead of silently replaying a stale answer.
    """
    root.mkdir(parents=True, exist_ok=True)
    for case in cases:
        prompt = build_extraction_prompt(
            schema=case.schema, transcript_tr=case.transcript_tr, nonce=REPLAY_NONCE
        )
        (root / f"{prompt.input_digest}.json").write_text(
            json.dumps(
                {
                    "input_digest": prompt.input_digest,
                    "schema_id": case.schema.schema_id,
                    "model_id": case.model_id,
                    "model_revision": case.model_revision,
                    "input_tokens": case.input_tokens,
                    "output_tokens": case.output_tokens,
                    "latency_ms": case.latency_ms,
                    "text": case.completion_text,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return RecordedLlmGateway(root=root)


def run_case(
    case: ExtractionCase, *, workdir: Path, sink: CollectingSpanSink | None = None
) -> ExtractionRun:
    """Replay one case through the real Extraction Work."""
    gateway = recorded_gateway_for((case,), root=workdir)
    work = ExtractionWork(gateway=gateway, sink=sink or CollectingSpanSink())
    return work.run(
        work_id=f"w_{case.case_id}",
        session_id_hash=_SESSION_HASH,
        tenant_id=_TENANT,
        transcript_tr=case.transcript_tr,
        schema=case.schema,
        protocol_hash=_PROTOCOL_HASH,
        nonce=REPLAY_NONCE,
    )


def run_corpus_rows(root: Path, *, workdir: Path) -> list[dict[str, Any]]:
    """Replay the scored (non-adversarial) subset and return the score rows."""
    rows: list[dict[str, Any]] = []
    for case in load_cases(root):
        if case.adversarial:
            continue
        run = run_case(case, workdir=workdir)
        rows.append(extraction_record(case_id=case.case_id, run=run, schema=case.schema))
    return rows


def run_corpus(root: Path, *, workdir: Path) -> tuple[ExperimentRecord, ...]:
    """The same rows, as the records INT-175's ``score``/``gate`` consume."""
    return tuple(
        ExperimentRecord(
            case_id=str(row["case_id"]),
            kind=SpanKind(row["kind"]),
            outcome=SpanOutcome(row["outcome"]),
            schema_valid=bool(row["schema_valid"]),
            required_slots_filled=int(row["required_slots_filled"]),
            required_slots_total=int(row["required_slots_total"]),
            llm_triage_level=str(row["llm_triage_level"]),
            policyguard_pass=bool(row["policyguard_pass"]),
            latency_ms=int(row["latency_ms"]),
        )
        for row in run_corpus_rows(root, workdir=workdir)
    )
