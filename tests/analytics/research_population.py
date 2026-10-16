"""Synthetic populations and an INDEPENDENT recoverability oracle (tests only).

The oracle deliberately shares no code with
``intake_platform.analytics.research.audit``: it recomputes who is in each
shown cell from the records with its own partition rules, groups people by the
shown cells they fall in, and then tries EVERY union of those groups that holds
fewer than k people, testing exact rational row-space membership with
``fractions.Fraction``. Exhaustive, so it only runs on populations with a
handful of classes — which is what makes it a trustworthy second opinion.
"""

from __future__ import annotations

import itertools
from collections.abc import Hashable, Iterable, Sequence
from fractions import Fraction

from intake_platform.analytics.research import (
    AnswerTimeBand,
    InputMode,
    Platform,
    QuestionOutcome,
    QuestionRecord,
    Release,
    RepeatBand,
    Stage,
    SubjectRecord,
    TriageBucket,
    ViewId,
    ViewKind,
)

PROTOCOL = "int490.synthetic"
VERSION = "v1"

_counter = itertools.count(1)


def person(
    stage: Stage,
    *,
    protocol: str = PROTOCOL,
    version: str = VERSION,
    platform: Platform | None = None,
    triage: TriageBucket | None = None,
    questions: dict[str, QuestionRecord] | None = None,
    subject: Hashable | None = None,
    tenant: Hashable = "tenant-a",
) -> SubjectRecord:
    return SubjectRecord(
        subject=subject if subject is not None else f"s{next(_counter)}",
        tenant=tenant,
        protocol=protocol,
        protocol_version=version,
        stage=stage,
        locale="tr",
        triage=triage,
        platform=platform,
        questions=questions or {},
    )


def people(count: int, stage: Stage, **kwargs: object) -> list[SubjectRecord]:
    return [person(stage, **kwargs) for _ in range(count)]  # type: ignore[arg-type]


def typed_answer() -> QuestionRecord:
    return QuestionRecord(
        outcome=QuestionOutcome.ANSWERED,
        repeat=RepeatBand.NONE,
        input_mode=InputMode.TYPED,
        time_band=AnswerTimeBand.UNDER_10S,
    )


def skipped() -> QuestionRecord:
    return QuestionRecord(outcome=QuestionOutcome.SKIPPED, repeat=RepeatBand.NONE)


def _value(view: ViewId, record: SubjectRecord) -> str | None:
    """The oracle's own partition rules, written from the catalogue's prose."""
    if (record.protocol, record.protocol_version) != (view.protocol, view.protocol_version):
        return None
    if view.kind is ViewKind.FUNNEL:
        return str(record.stage)
    if view.kind is ViewKind.LOCALE:
        return record.locale
    if view.kind is ViewKind.PLATFORM:
        return None if record.platform is None else str(record.platform)
    if view.kind is ViewKind.TRIAGE:
        return None if record.triage is None else str(record.triage)
    answer = record.questions.get(view.question or "")
    if answer is None:
        return None
    by_kind = {
        ViewKind.QUESTION_OUTCOME: answer.outcome,
        ViewKind.QUESTION_REPEAT: answer.repeat,
        ViewKind.QUESTION_MODE: answer.input_mode,
        ViewKind.QUESTION_TIME: answer.time_band,
        ViewKind.QUESTION_ASR: answer.asr_band,
    }
    value = by_kind[view.kind]
    return None if value is None else str(value)


def shown_cells(
    views: Iterable[ViewId], records: Sequence[SubjectRecord]
) -> list[frozenset[Hashable]]:
    cells: list[frozenset[Hashable]] = []
    for view in views:
        values = {_value(view, record) for record in records} - {None}
        for value in sorted(v for v in values if v is not None):
            cells.append(
                frozenset(record.subject for record in records if _value(view, record) == value)
            )
    return cells


def _reduce(vector: list[Fraction], basis: list[tuple[int, list[Fraction]]]) -> list[Fraction]:
    out = list(vector)
    for pivot, row in basis:
        if out[pivot] != 0:
            factor = out[pivot]
            out = [a - factor * b for a, b in zip(out, row, strict=True)]
    return out


def _basis(rows: list[list[Fraction]]) -> list[tuple[int, list[Fraction]]]:
    basis: list[tuple[int, list[Fraction]]] = []
    for row in rows:
        reduced = _reduce(row, basis)
        pivot = next((i for i, value in enumerate(reduced) if value != 0), None)
        if pivot is None:
            continue
        reduced = [value / reduced[pivot] for value in reduced]
        basis = [(p, [a - r[pivot] * b for a, b in zip(r, reduced, strict=True)]) for p, r in basis]
        basis.append((pivot, reduced))
    return basis


def recoverable_small_groups(cells: Sequence[frozenset[Hashable]], k: int) -> list[int]:
    """Sizes of every union of people-classes, smaller than k and non-empty,
    whose size the shown cells determine. Empty means the release is safe."""
    subjects = sorted(set().union(*cells), key=repr) if cells else []
    classes: dict[tuple[bool, ...], int] = {}
    for subject in subjects:
        signature = tuple(subject in cell for cell in cells)
        classes[signature] = classes.get(signature, 0) + 1
    order = sorted(classes)
    assert len(order) <= 14, "the oracle is exhaustive; keep its populations small"
    rows = [[Fraction(int(sig[i])) for sig in order] for i in range(len(cells))]
    basis = _basis(rows)
    found: list[int] = []
    for mask in range(1, 1 << len(order)):
        chosen = [j for j in range(len(order)) if mask >> j & 1]
        size = sum(classes[order[j]] for j in chosen)
        if size >= k:
            continue
        vector = [Fraction(1 if mask >> j & 1 else 0) for j in range(len(order))]
        if all(value == 0 for value in _reduce(vector, basis)):
            found.append(size)
    return found


def release_is_safe(release: Release, records: Sequence[SubjectRecord]) -> bool:
    cells = shown_cells((view.id for view in release.shown), records)
    return not recoverable_small_groups(cells, release.k)
