"""The LOINC+unit agreement harness, and the corpus it refuses to run without
(INT-121).

The INT-121 acceptance ends *"accuracy metric on corpus >=90 percent
LOINC+unit"*. CLAUDE.md invariant 20 governs what that sentence may become:

    No sensitivity, specificity, AUROC, WER or accuracy figure appears in
    docs/regulatory/, docs/legal/, patient or clinician copy, marketing or a
    store listing. Measurements live in docs/evidence/ **with a date and a
    named corpus**, and are described as measurements, never as properties of
    the product.

So this module builds the *measurement*, and the shape of the measurement is
the enforcement:

* :class:`LoincUnitMeasurement` cannot be constructed without a corpus name, a
  corpus retrieval date and a measurement date. A figure with no named corpus
  and no date is not a weaker measurement; it is not one, and here it is not
  representable.
* :func:`load_records_corpus` raises :class:`CorpusNotCommitted` when the
  corpus is absent, unnamed, undated, or disagrees with its own manifest. It
  does not fall back to a sample, a synthetic set or a default.
* :data:`LOINC_UNIT_THRESHOLD` is the acceptance's ``90 percent``. It is not
  this module's number to move.

**No records corpus is committed to this repository, so no figure exists.**
:data:`RECORDS_CORPUS_ROOT` does not exist on disk and
:func:`load_records_corpus` refuses. Two HUMAN_BLOCKERS.md rows stand between
here and a figure, and neither is an agent's to close:

* **HB-A10** — a free LOINC account, to obtain the CSV distribution and the
  tr-TR linguistic variant. Its standing prohibition rides with it: *do not
  author Turkish LOINC display names* (§12 of the licence assigns any
  translation to Regenstrief); concatenate the translated FSN axes instead.
* **HB-A2** — SKRS access credentials, which is where the Turkish lab display
  names (``TURKCEKARSILIGI``) live, and which the Regenstrief LOINC variant
  lacks entirely. The row already names *"INT-121's ``LOINC + unit`` accuracy
  target"* as what it blocks.

A corpus also needs documents, and a Turkish lab report is patient data: the
named corpus this measurement is finally taken on is a decision about
persisting a new category of personal data, which CLAUDE.md sends to a human
by name. See docs/evidence/INT-121.md.

**"LOINC+unit" is one agreement over two axes, not two scores.** A case counts
only when the code *and* the unit both agree with the corpus; a run that got
every code right and every unit wrong scores zero, which is the honest answer
for a pipeline whose output is a quantity.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from llm_evals.corpus import CorpusError

__all__ = [
    "CASE_KEYS",
    "LOINC_UNIT_THRESHOLD",
    "MANIFEST_KEYS",
    "RECORDS_CORPUS_ROOT",
    "CorpusNotCommitted",
    "LoincUnitCase",
    "LoincUnitMeasurement",
    "RecordsCorpus",
    "RecordsCorpusManifest",
    "gate_loinc_unit",
    "load_records_corpus",
    "measure_loinc_unit_agreement",
]

#: Where a committed records corpus would live, beside INT-083's extraction
#: corpus. It does not exist: nothing here creates it, and nothing here
#: substitutes for it.
RECORDS_CORPUS_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "corpus" / "records"

#: The acceptance's threshold, verbatim: ">=90 percent LOINC+unit".
LOINC_UNIT_THRESHOLD: Final[Decimal] = Decimal("0.90")

MANIFEST_KEYS: Final[frozenset[str]] = frozenset(
    {"corpus_name", "retrieved_on", "document_count", "source", "licence"}
)

CASE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "case_id",
        "document_ref",
        "page",
        "bbox",
        "start",
        "end",
        "printed_name",
        "printed_value",
        "printed_unit",
        "expected_loinc",
        "expected_unit",
    }
)

#: The blockers a human must clear before this measurement can be taken at all.
#: Named in the refusal so the next reader does not re-derive them.
_BLOCKER_ROWS: Final = (
    "HB-A10 (a LOINC account, for the CSV distribution and the tr-TR variant) and "
    "HB-A2 (SKRS credentials, where the Turkish lab display names live)"
)


class CorpusNotCommitted(CorpusError):
    """No named, dated, committed corpus — so no measurement.

    Deliberately not a warning and not an empty result: an empty result would
    score 0/0 and every ratio over it would read as a figure.
    """


def _not_committed(reason: str) -> CorpusNotCommitted:
    return CorpusNotCommitted(
        f"{reason}. A measurement lives in docs/evidence/ with a date and a named "
        f"corpus (CLAUDE.md invariant 20), so there is nothing to report until one "
        f"exists. Blocked on {_BLOCKER_ROWS}."
    )


@dataclass(frozen=True, slots=True)
class RecordsCorpusManifest:
    """What names and dates a corpus. Every field is required."""

    corpus_name: str
    retrieved_on: dt.date
    document_count: int
    source: str
    licence: str


@dataclass(frozen=True, slots=True)
class LoincUnitCase:
    """One printed lab line and what the corpus says it means.

    The box fields are carried so a disagreement can be looked at on the page
    it came from — a measurement whose failures cannot be inspected teaches
    nobody anything.
    """

    case_id: str
    document_ref: str
    page: int
    bbox: tuple[float, float, float, float]
    start: int
    end: int
    printed_name: str
    printed_value: str
    printed_unit: str
    expected_loinc: str
    expected_unit: str


@dataclass(frozen=True, slots=True)
class RecordsCorpus:
    """A loaded corpus: its manifest, and its cases in case-id order."""

    manifest: RecordsCorpusManifest
    cases: tuple[LoincUnitCase, ...]


@dataclass(frozen=True, slots=True)
class LoincUnitMeasurement:
    """A count and a ratio over a named corpus, on a date.

    There is no constructor here that omits the corpus name or either date, so
    a figure that could travel without its provenance does not exist. The
    per-axis counts are reported alongside the joint one because "the codes are
    fine and the units are not" and "both are half wrong" are different
    engineering problems with the same joint score.
    """

    corpus_name: str
    retrieved_on: dt.date
    measured_on: dt.date
    matched: int
    total: int
    loinc_matched: int
    unit_matched: int

    def __post_init__(self) -> None:
        if not self.corpus_name.strip():
            raise CorpusNotCommitted(
                "a measurement names the corpus it was taken on (CLAUDE.md invariant 20)"
            )
        if self.total < 1:
            raise CorpusNotCommitted("an empty corpus measures nothing; 0/0 is not a ratio")

    @property
    def ratio(self) -> Decimal:
        """The joint LOINC+unit agreement, exact."""
        return Decimal(self.matched) / Decimal(self.total)

    def describe(self) -> str:
        """The measurement, in the measurement voice.

        A sentence about what was counted, on which corpus, on which date —
        never a sentence about what the product is.
        """
        return (
            f"LOINC+unit agreement: {self.matched}/{self.total} cases "
            f"(LOINC alone {self.loinc_matched}/{self.total}, unit alone "
            f"{self.unit_matched}/{self.total}) measured on "
            f"{self.measured_on.isoformat()} against corpus "
            f"{self.corpus_name!r} retrieved {self.retrieved_on.isoformat()}"
        )


def _require_keys(raw: Mapping[str, Any], keys: frozenset[str], what: str) -> None:
    unknown = sorted(set(raw) - keys)
    if unknown:
        raise _not_committed(f"{what} carries unknown key(s) {unknown}; the key set is closed")
    missing = sorted(keys - set(raw))
    if missing:
        raise _not_committed(f"{what} is missing {missing}")


def _load_manifest(path: Path) -> RecordsCorpusManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise _not_committed(f"{path.name} is not readable JSON") from err
    if not isinstance(raw, Mapping):
        raise _not_committed(f"{path.name} must be a JSON object")
    _require_keys(raw, MANIFEST_KEYS, path.name)

    name = str(raw["corpus_name"]).strip()
    if not name:
        raise _not_committed(f"{path.name} names no corpus")
    licence = str(raw["licence"]).strip()
    if not licence:
        raise _not_committed(f"{path.name} records no licence for the corpus documents")
    source = str(raw["source"]).strip()
    if not source:
        raise _not_committed(f"{path.name} records no source for the corpus documents")
    try:
        retrieved_on = dt.date.fromisoformat(str(raw["retrieved_on"]))
    except ValueError as err:
        raise _not_committed(f"{path.name} carries no ISO-8601 retrieval date") from err
    try:
        document_count = int(raw["document_count"])
    except (TypeError, ValueError) as err:
        raise _not_committed(f"{path.name} carries no document count") from err
    if document_count < 1:
        raise _not_committed(f"{path.name} declares no documents")

    return RecordsCorpusManifest(
        corpus_name=name,
        retrieved_on=retrieved_on,
        document_count=document_count,
        source=source,
        licence=licence,
    )


def _load_case(path: Path) -> LoincUnitCase:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise _not_committed(f"{path.name} is not readable JSON") from err
    if not isinstance(raw, Mapping):
        raise _not_committed(f"{path.name} must be a JSON object")
    _require_keys(raw, CASE_KEYS, path.name)
    bbox = raw["bbox"]
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise _not_committed(f"{path.name} carries no four-coordinate source box")
    for field in ("case_id", "expected_loinc", "expected_unit"):
        if not str(raw[field]).strip():
            raise _not_committed(f"{path.name} carries an empty {field}")
    return LoincUnitCase(
        case_id=str(raw["case_id"]),
        document_ref=str(raw["document_ref"]),
        page=int(raw["page"]),
        bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
        start=int(raw["start"]),
        end=int(raw["end"]),
        printed_name=str(raw["printed_name"]),
        printed_value=str(raw["printed_value"]),
        printed_unit=str(raw["printed_unit"]),
        expected_loinc=str(raw["expected_loinc"]).strip(),
        expected_unit=str(raw["expected_unit"]).strip(),
    )


def load_records_corpus(root: Path) -> RecordsCorpus:
    """Load a committed records corpus, or refuse.

    Every failure is the same refusal, because from the caller's side they are
    the same thing: there is no corpus to measure against, so there is no
    measurement to report.
    """
    if not root.exists():
        raise _not_committed(f"no records corpus is committed at {root.name}/")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise _not_committed(f"{root.name}/ has no manifest naming and dating the corpus")
    manifest = _load_manifest(manifest_path)

    case_dir = root / "cases"
    if not case_dir.is_dir():
        raise _not_committed(f"{root.name}/ holds no cases/ directory")
    cases = tuple(_load_case(path) for path in sorted(case_dir.glob("*.json")))
    if not cases:
        raise _not_committed(f"{root.name}/ holds no cases — an empty set measures nothing")
    if len({case.case_id for case in cases}) != len(cases):
        raise _not_committed(f"{root.name}/ has two cases sharing a case_id")
    documents = {case.document_ref for case in cases}
    if len(documents) != manifest.document_count:
        raise _not_committed(
            f"{root.name}/ declares {manifest.document_count} document(s) and its cases "
            f"cite {len(documents)}; a corpus that disagrees with its own manifest is "
            "not a named corpus"
        )
    return RecordsCorpus(
        manifest=manifest, cases=tuple(sorted(cases, key=lambda case: case.case_id))
    )


def measure_loinc_unit_agreement(
    corpus: RecordsCorpus,
    *,
    produced: Mapping[str, tuple[str | None, str | None]],
    measured_on: dt.date,
) -> LoincUnitMeasurement:
    """Count joint LOINC+unit agreement over ``corpus``.

    ``produced`` maps a case id to what one extraction run produced for it —
    ``(loinc_code, unit)``, either of which may be ``None`` when nothing bound
    (which is the state :class:`~intake_platform.records_extraction.
    NoTerminology` leaves every code in today). A case the run produced nothing
    for counts against the total: silence is not agreement.

    A produced case id the corpus does not contain is refused rather than
    ignored — it means the run and the corpus are not the same experiment.
    """
    known = {case.case_id for case in corpus.cases}
    unknown = sorted(set(produced) - known)
    if unknown:
        raise _not_committed(
            f"the run produced {len(unknown)} case id(s) the corpus does not contain, so "
            "the run and the corpus are not the same experiment"
        )

    matched = loinc_matched = unit_matched = 0
    for case in corpus.cases:
        code, unit = produced.get(case.case_id, (None, None))
        code_ok = code is not None and code.strip() == case.expected_loinc
        unit_ok = unit is not None and unit.strip() == case.expected_unit
        loinc_matched += int(code_ok)
        unit_matched += int(unit_ok)
        matched += int(code_ok and unit_ok)

    return LoincUnitMeasurement(
        corpus_name=corpus.manifest.corpus_name,
        retrieved_on=corpus.manifest.retrieved_on,
        measured_on=measured_on,
        matched=matched,
        total=len(corpus.cases),
        loinc_matched=loinc_matched,
        unit_matched=unit_matched,
    )


def gate_loinc_unit(measurement: LoincUnitMeasurement) -> bool:
    """The acceptance's gate: ``>= 90 percent`` joint agreement.

    Returns a verdict rather than raising, so a caller reports the measurement
    with it instead of only the failure.
    """
    return measurement.ratio >= LOINC_UNIT_THRESHOLD
