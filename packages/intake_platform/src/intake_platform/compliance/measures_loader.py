"""Loading the KVKK 2018/10 mapping, checked against everything it cites (INT-215).

:func:`load_measures_mapping` either returns a :class:`MeasuresMapping` whose
every reference resolves, or raises :class:`MappingInvalid` listing every
problem at once — never a partial mapping. What it checks:

- the snapshot and the gazette PDF match their recorded sha256;
- the mapped measure ids are exactly the ones parsed out of the snapshot, in
  the decision's order, and each ``quote`` is the snapshot's line verbatim;
- each control's paths exist inside the repository and each test id names a
  real test function; each signal is a catalogued metric with the status the
  catalogue gives it, or a registered component probe;
- each gap's owner is in the mapping's own owner vocabulary, its ask is one
  question, and any HUMAN_BLOCKERS row or backlog issue it cites exists;
- no measure carries a declared ``status``, none maps to nothing, and a measure
  whose controls have no live signal owns that absence as a ``signal`` gap.
"""

from __future__ import annotations

import functools
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from intake_platform.compliance.measures_model import (
    Control,
    DecisionSource,
    Gap,
    GapKind,
    MappingInvalid,
    Measure,
    MeasuresMapping,
    Signal,
    SourceMeasure,
    inside_repo,
    parse_decision_measures,
    resolve_test_id,
)
from intake_platform.slo import load_metrics_catalog

__all__ = [
    "HUMAN_BLOCKERS_PATH",
    "ISSUES_PATH",
    "MAPPING_PATH",
    "METRICS_CATALOG_PATH",
    "PROBE_REGISTRY_PATH",
    "load_measures_mapping",
]

MAPPING_PATH: Final = Path("docs/legal/special-category-measures.yaml")
METRICS_CATALOG_PATH: Final = Path("observability/metrics_catalog.yaml")
PROBE_REGISTRY_PATH: Final = Path("observability/registry.yaml")
HUMAN_BLOCKERS_PATH: Final = Path("files/HUMAN_BLOCKERS.md")
ISSUES_PATH: Final = Path("docs/backlog/issues.yaml")

_BLOCKER: Final = re.compile(r"^HB-[A-Z]+\d+[a-z]?$")
_ISSUE: Final = re.compile(r"^INT-\d{3}$")
_HEX64: Final = re.compile(r"^[0-9a-f]{64}$")
_GAP_KINDS: Final = frozenset(kind.value for kind in GapKind)

_SOURCE_KEYS: Final = (
    "title",
    "board_decision",
    "decision_date",
    "gazette_date",
    "gazette_number",
    "gazette_url",
    "gazette_pdf_file",
    "gazette_pdf_sha256",
    "text_url",
    "text_file",
    "text_sha256",
    "text_note",
    "retrieved_on",
)


@dataclass(frozen=True)
class _Evidence:
    """What the references are checked against, read once per load."""

    repo: Path
    metrics: Mapping[str, str]
    probes: frozenset[str]
    blockers: str
    issues: frozenset[str]


def _read_evidence(repo: Path, problems: list[str]) -> _Evidence:
    metrics: dict[str, str] = {}
    probes: frozenset[str] = frozenset()
    blockers = ""
    issues: frozenset[str] = frozenset()
    try:
        catalog = load_metrics_catalog(repo / METRICS_CATALOG_PATH)
        metrics = {metric.name: metric.status for metric in catalog.metrics}
    except (OSError, ValueError, yaml.YAMLError):
        problems.append(f"{METRICS_CATALOG_PATH} could not be read")
    try:
        registry = yaml.safe_load((repo / PROBE_REGISTRY_PATH).read_text(encoding="utf-8"))
        probes = frozenset(
            str(row["component"]) for row in registry["components"] if row.get("probe")
        )
    except (OSError, KeyError, TypeError, AttributeError, yaml.YAMLError):
        problems.append(f"{PROBE_REGISTRY_PATH} could not be read")
    try:
        blockers = (repo / HUMAN_BLOCKERS_PATH).read_text(encoding="utf-8")
    except OSError:
        problems.append(f"{HUMAN_BLOCKERS_PATH} could not be read")
    try:
        backlog = repo / ISSUES_PATH
        stat = backlog.stat()
        issues = _issue_ids(backlog, stat.st_mtime_ns, stat.st_size)
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        problems.append(f"{ISSUES_PATH} could not be read")
    return _Evidence(repo, metrics, probes, blockers, issues)


@functools.lru_cache(maxsize=8)
def _issue_ids(backlog: Path, mtime_ns: int, size: int) -> frozenset[str]:
    """The backlog's issue ids. The backlog is the largest file read here, so
    it is parsed once per content version (mtime and size key the cache)."""
    rows = yaml.safe_load(backlog.read_text(encoding="utf-8"))
    return frozenset(str(row["id"]) for row in rows)


def _keys(
    row: Any, required: Sequence[str], optional: Sequence[str], where: str, problems: list[str]
) -> Mapping[str, Any]:
    if not isinstance(row, Mapping):
        problems.append(f"{where}: not a mapping")
        return {}
    for key in required:
        if key not in row:
            problems.append(f"{where}: {key} is missing")
    for key in row:
        if key == "status":
            problems.append(f"{where}: status is derived, never declared")
        elif key not in required and key not in optional:
            problems.append(f"{where}: unknown key {key!r}")
    return row


def _text(row: Mapping[str, Any], key: str, where: str, problems: list[str]) -> str:
    value = row.get(key)
    if key in row and (not isinstance(value, str) or not value.strip()):
        problems.append(f"{where}: {key} must be non-empty text")
    return value if isinstance(value, str) else ""


def _texts(row: Mapping[str, Any], key: str, where: str, problems: list[str]) -> tuple[str, ...]:
    value = row.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        problems.append(f"{where}: {key} must be a list of text")
        return ()
    return tuple(value)


def _items(row: Mapping[str, Any], key: str) -> list[Any]:
    value = row.get(key, [])
    return value if isinstance(value, list) else []


def _digest_of(repo: Path, relative: str) -> str | None:
    file = inside_repo(repo, relative)
    if file is None or not file.is_file():
        return None
    return hashlib.sha256(file.read_bytes()).hexdigest()


def _source(repo: Path, row: Any, problems: list[str]) -> DecisionSource:
    fields = _keys(row, _SOURCE_KEYS, (), "decision", problems)
    values = {key: _text(fields, key, "decision", problems) for key in _SOURCE_KEYS}
    for file_key, digest_key in (
        ("text_file", "text_sha256"),
        ("gazette_pdf_file", "gazette_pdf_sha256"),
    ):
        recorded, actual = values[digest_key], _digest_of(repo, values[file_key])
        if not _HEX64.match(recorded):
            problems.append(f"decision: {digest_key} is not a sha256 hex digest")
        elif actual is None:
            problems.append(f"decision: {file_key} {values[file_key]!r} is absent")
        elif actual != recorded:
            problems.append(f"decision: {digest_key} does not match {values[file_key]}")
    return DecisionSource(**values)


def _signal(item: Any, evidence: _Evidence, where: str, problems: list[str]) -> Signal | None:
    if not isinstance(item, Mapping) or len(item) != 2 or "status" not in item:
        problems.append(f"{where}: a signal is {{metric|probe: <ref>, status: <state>}}")
        return None
    kind = "metric" if "metric" in item else "probe" if "probe" in item else ""
    ref, status = str(item.get(kind, "")), str(item["status"])
    if kind == "metric":
        actual = evidence.metrics.get(ref)
        if actual is None:
            problems.append(f"{where}: metric {ref!r} is not in {METRICS_CATALOG_PATH}")
        elif actual != status:
            problems.append(f"{where}: metric {ref!r} is {actual}, declared {status}")
    elif kind == "probe":
        if ref not in evidence.probes or status != "registered":
            problems.append(f"{where}: probe {ref!r} is not a registered component probe")
    else:
        problems.append(f"{where}: a signal names a metric or a probe")
        return None
    return Signal(kind=kind, ref=ref, status=status)


def _control(row: Any, evidence: _Evidence, where: str, problems: list[str]) -> Control:
    fields = _keys(row, ("id", "summary", "paths", "tests", "signals"), (), where, problems)
    control_id = _text(fields, "id", where, problems)
    where = f"{where} control {control_id}"
    paths = _texts(fields, "paths", where, problems)
    tests = _texts(fields, "tests", where, problems)
    if not paths or not tests:
        problems.append(f"{where}: a control names at least one path and one test")
    for path in paths:
        resolved = inside_repo(evidence.repo, path)
        if resolved is None or not resolved.exists():
            problems.append(f"{where}: path {path!r} does not exist inside the repository")
    for node_id in tests:
        if not node_id.startswith("tests/") or not resolve_test_id(evidence.repo, node_id):
            problems.append(f"{where}: test id {node_id!r} does not resolve")
    signals = tuple(
        signal
        for item in _items(fields, "signals")
        if (signal := _signal(item, evidence, where, problems)) is not None
    )
    return Control(control_id, _text(fields, "summary", where, problems), paths, tests, signals)


def _gap(
    row: Any, owners: Mapping[str, str], evidence: _Evidence, where: str, problems: list[str]
) -> Gap:
    fields = _keys(
        row, ("id", "kind", "owner", "ask"), ("human_blocker", "tracking"), where, problems
    )
    gap_id = _text(fields, "id", where, problems)
    where = f"{where} gap {gap_id}"
    kind = str(fields.get("kind", ""))
    if kind not in _GAP_KINDS:
        problems.append(f"{where}: kind {kind!r} is not one of {sorted(_GAP_KINDS)}")
    owner = str(fields.get("owner", ""))
    if "owner" in fields and owner not in owners:
        problems.append(f"{where}: owner {owner!r} is not declared under owners")
    ask = _text(fields, "ask", where, problems)
    if not ask.strip().endswith("?") or ask.count("?") != 1:
        problems.append(f"{where}: ask must be exactly one question")
    blocker = fields.get("human_blocker")
    if blocker is not None and (
        not isinstance(blocker, str)
        or not _BLOCKER.match(blocker)
        or f"**{blocker}**" not in evidence.blockers
    ):
        problems.append(f"{where}: human_blocker {blocker!r} is not a {HUMAN_BLOCKERS_PATH} row")
    tracking = _texts(fields, "tracking", where, problems)
    for issue in tracking:
        if not _ISSUE.match(issue) or issue not in evidence.issues:
            problems.append(f"{where}: tracking {issue!r} is not an issue in {ISSUES_PATH}")
    return Gap(
        id=gap_id,
        kind=GapKind(kind) if kind in _GAP_KINDS else GapKind.ENGINEERING,
        owner=owner,
        ask=ask,
        human_blocker=blocker if isinstance(blocker, str) else None,
        tracking=tracking,
    )


def _measure(
    row: Any,
    parsed: Mapping[str, SourceMeasure],
    owners: Mapping[str, str],
    evidence: _Evidence,
    problems: list[str],
) -> Measure:
    fields = _keys(row, ("id", "quote", "controls", "gaps"), (), "measure", problems)
    measure_id = str(fields.get("id", ""))
    where = f"measure {measure_id}"
    quote = _text(fields, "quote", where, problems)
    stated = parsed.get(measure_id)
    if stated is None:
        problems.append(f"{where}: the decision has no measure {measure_id!r}")
    elif quote != stated.text:
        problems.append(f"{where}: quote is not the snapshot text verbatim")
    controls = tuple(_control(i, evidence, where, problems) for i in _items(fields, "controls"))
    gaps = tuple(_gap(i, owners, evidence, where, problems) for i in _items(fields, "gaps"))
    if not controls and not gaps:
        problems.append(f"{where}: maps to no control and names no gap")
    if (
        controls
        and not any(c.has_live_signal for c in controls)
        and not any(g.kind is GapKind.SIGNAL for g in gaps)
    ):
        problems.append(f"{where}: no control has a live signal and no signal gap owns that")
    for label, ids in (("control", [c.id for c in controls]), ("gap", [g.id for g in gaps])):
        if len(set(ids)) != len(ids):
            problems.append(f"{where}: duplicate {label} id")
    return Measure(measure_id, stated.lead_in if stated else None, quote, controls, gaps)


def _owners(raw: Any, problems: list[str]) -> dict[str, str]:
    owners: dict[str, str] = {}
    if not isinstance(raw, Mapping) or not raw:
        problems.append("owners: the owner vocabulary is empty")
        return owners
    for key, description in raw.items():
        if not isinstance(description, str) or not description.strip():
            problems.append(f"owners: {key!r} has no description")
        owners[str(key)] = str(description)
    return owners


def load_measures_mapping(
    repo: Path, *, document: Mapping[str, Any] | None = None
) -> MeasuresMapping:
    """The mapping, checked against everything it cites — or :class:`MappingInvalid`."""
    if document is None:
        path = repo / MAPPING_PATH
        if not path.is_file():
            raise MappingInvalid([f"{MAPPING_PATH} is absent"])
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    top = _keys(
        document, ("schema_version", "decision", "owners", "measures"), (), "mapping", problems
    )
    if top.get("schema_version") != 1:
        problems.append("mapping: schema_version must be 1")
    evidence = _read_evidence(repo, problems)
    source = _source(repo, top.get("decision"), problems)
    snapshot = inside_repo(repo, source.text_file)
    text = snapshot.read_text(encoding="utf-8") if snapshot and snapshot.is_file() else ""
    parsed = {measure.id: measure for measure in parse_decision_measures(text)}
    owners = _owners(top.get("owners"), problems)
    measures = tuple(
        _measure(row, parsed, owners, evidence, problems) for row in _items(top, "measures")
    )
    mapped = [measure.id for measure in measures]
    for missing in [measure_id for measure_id in parsed if measure_id not in mapped]:
        problems.append(f"measure {missing}: in the decision but not mapped")
    if len(set(mapped)) != len(mapped):
        problems.append("mapping: a measure is mapped twice")
    elif set(mapped) == set(parsed) and mapped != list(parsed):
        problems.append("mapping: measures are not in the decision's order")
    if problems:
        raise MappingInvalid(problems)
    return MeasuresMapping(source=source, owners=owners, measures=measures)
