"""The shapes of the KVKK 2018/10 mapping, and how the decision text is read (INT-215).

Kept apart from the loader (:mod:`intake_platform.compliance.measures_loader`)
and the packet (:mod:`intake_platform.compliance.adequate_measures`), so each
module has one job. Nothing here reads a file except :func:`resolve_test_id`,
which parses a test module with :mod:`ast` and never imports it.
"""

from __future__ import annotations

import ast
import functools
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

__all__ = [
    "Control",
    "DecisionSource",
    "Gap",
    "GapKind",
    "MappingInvalid",
    "Measure",
    "MeasureStatus",
    "MeasuresMapping",
    "Signal",
    "SourceMeasure",
    "inside_repo",
    "parse_decision_measures",
    "resolve_test_id",
]

_TOP: Final = re.compile(r"^(\d+)- \S")
_SUB: Final = re.compile(r"^([a-zçğıöşü])\) \S")

#: Signal states that count as live: a metric something emits today, or a
#: synthetic probe the registry runs against a component.
LIVE_SIGNAL_STATES: Final = frozenset({"live", "registered"})


class MeasureStatus(StrEnum):
    IMPLEMENTED = "implemented"
    PARTIAL = "partial"
    NOT_IMPLEMENTED = "not_implemented"


class GapKind(StrEnum):
    #: The controller's people, premises or paper — no software discharges it.
    ORGANISATIONAL = "organisational"
    #: A control the repository does not have yet.
    ENGINEERING = "engineering"
    #: A legal reading nobody here may make.
    DETERMINATION = "determination"
    #: A control with no live signal.
    SIGNAL = "signal"
    #: A text this mapping has not read.
    SOURCE = "source"


@dataclass(frozen=True)
class SourceMeasure:
    """One measure as the snapshot states it: its id, its item's lead-in, its line."""

    id: str
    lead_in: str | None
    text: str


@dataclass(frozen=True)
class DecisionSource:
    title: str
    board_decision: str
    decision_date: str
    gazette_date: str
    gazette_number: str
    gazette_url: str
    gazette_pdf_file: str
    gazette_pdf_sha256: str
    text_url: str
    text_file: str
    text_sha256: str
    text_note: str
    retrieved_on: str


@dataclass(frozen=True)
class Signal:
    kind: str
    ref: str
    status: str

    @property
    def live(self) -> bool:
        return self.status in LIVE_SIGNAL_STATES

    def label(self) -> str:
        return f"{self.kind}:{self.ref} ({self.status})"


@dataclass(frozen=True)
class Control:
    id: str
    summary: str
    paths: tuple[str, ...]
    tests: tuple[str, ...]
    signals: tuple[Signal, ...]

    @property
    def has_live_signal(self) -> bool:
        return any(signal.live for signal in self.signals)


@dataclass(frozen=True)
class Gap:
    id: str
    kind: GapKind
    owner: str
    ask: str
    human_blocker: str | None
    tracking: tuple[str, ...]


@dataclass(frozen=True)
class Measure:
    id: str
    lead_in: str | None
    quote: str
    controls: tuple[Control, ...]
    gaps: tuple[Gap, ...]

    @property
    def status(self) -> MeasureStatus:
        """Derived, never declared: no control, any open gap, or neither."""
        if not self.controls:
            return MeasureStatus.NOT_IMPLEMENTED
        if self.gaps:
            return MeasureStatus.PARTIAL
        return MeasureStatus.IMPLEMENTED


@dataclass(frozen=True)
class MeasuresMapping:
    source: DecisionSource
    owners: Mapping[str, str]
    measures: tuple[Measure, ...]


class MappingInvalid(ValueError):
    """The mapping disagrees with the evidence it cites. Every problem is listed."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("2018/10 mapping refused: " + "; ".join(self.problems))


def parse_decision_measures(text: str) -> tuple[SourceMeasure, ...]:
    """The measures of the decision, in its own order.

    A numbered item with lettered sub-items is a lead-in and each sub-item is a
    measure (``2a``, ``2ç`` …); a numbered item with none is a measure itself.
    Lines that are neither (the preamble) are not measures.
    """
    measures: list[SourceMeasure] = []
    item: tuple[str, str] | None = None
    item_has_subs = False
    for line in text.splitlines():
        top = _TOP.match(line)
        sub = _SUB.match(line)
        if top:
            if item is not None and not item_has_subs:
                measures.append(SourceMeasure(item[0], None, item[1]))
            item, item_has_subs = (top.group(1), line), False
        elif sub and item is not None:
            measures.append(SourceMeasure(item[0] + sub.group(1), item[1], line))
            item_has_subs = True
    if item is not None and not item_has_subs:
        measures.append(SourceMeasure(item[0], None, item[1]))
    return tuple(measures)


def inside_repo(repo: Path, relative: str) -> Path | None:
    """``relative`` resolved inside ``repo``, or None for anything that escapes it."""
    candidate = Path(relative)
    if not relative or candidate.is_absolute() or ".." in candidate.parts:
        return None
    root = repo.resolve()
    resolved = (root / candidate).resolve()
    return resolved if resolved.is_relative_to(root) else None


def _qualified_functions(body: Sequence[ast.stmt], prefix: str = "") -> Iterator[str]:
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield prefix + node.name
        elif isinstance(node, ast.ClassDef):
            yield from _qualified_functions(node.body, f"{prefix}{node.name}::")


@functools.lru_cache(maxsize=256)
def _functions_in(file: Path, mtime_ns: int, size: int) -> frozenset[str]:
    """Every ``[Class::]function`` a module defines. Keyed on the file's mtime
    and size, so an edited file is parsed again rather than served stale."""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return frozenset()
    return frozenset(_qualified_functions(tree.body))


def resolve_test_id(repo: Path, node_id: str) -> bool:
    """True when ``path::[Class::]test_name`` names a test function in that file."""
    path_part, separator, rest = node_id.partition("::")
    file = inside_repo(repo, path_part) if separator and rest else None
    if file is None or file.suffix != ".py" or not file.is_file():
        return False
    stat = file.stat()
    function = rest.rsplit("::", 1)[-1]
    return function.startswith("test") and rest in _functions_in(
        file, stat.st_mtime_ns, stat.st_size
    )
