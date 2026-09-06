"""INT-230 — what a research extract may contain, and what it may not.

This module is the *content* boundary; :mod:`intake_platform.research.extract`
is the *permission* boundary. Splitting them is not tidiness: the question
"may this value appear in an export at all" has to be answerable without a
session, a study or a consent ledger, because it is asked at spec-construction
time by whoever authors a study's extract shape — long before any patient row
exists.

**Acceptance comes from the closed vocabulary; the de-identifier only ever
adds refusals.** :class:`ResearchExtractSpec` declares, per dimension, the
complete set of values that dimension may take, and a value outside it is
refused. :func:`check_export_value` then bounds the *carrier* (id-shaped,
ASCII, ≤64 characters, so a Turkish sentence cannot be one) and the known
*identifier classes* (the INT-015 pattern tier — a TCKN, a mobile number, an
IBAN, an email and a date are all id-shaped, and a shape rule on its own would
have admitted every one of them). Neither check can widen what is admitted;
each can only narrow it. That ordering is why the absence of the NER tier is
harmless here and fatal in ``deidentify_for_egress``, whose contract runs the
other way and fails closed for exactly that reason.

Free text is **excluded, not scrubbed** (files/10 §3, HB-L6): Turkish clinical
narrative is not de-identifiable to a standard this repo will assert, so no
amount of scrubbing makes a sentence an export value.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from intake_platform.analytics import AnalyticsView
from intake_platform.deid import Deidentifier
from intake_platform.research.studies import STUDY_FIELD_SHAPE

__all__ = [
    "EXPORT_VALUE_SHAPE",
    "RESEARCH_SCOPE",
    "ResearchExportRefused",
    "ResearchExtractSpec",
    "ResearchRefusalReason",
    "check_export_field",
    "check_export_value",
]

RESEARCH_SCOPE = "research"

#: An export value is an identifier or an enumeration member, never prose.
#: ASCII-only and short by design: a Turkish sentence fails on its first space
#: or its first ``ı``. Deliberately the same alphabet the analytics gate uses,
#: so a value that clears this clears that.
EXPORT_VALUE_SHAPE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}")

#: A measure whose name reads as an order statistic. Each of these is one real
#: patient's value however large the cohort is, so no cohort size makes it
#: safe and the spec refuses to declare one.
_ORDER_STATISTIC = re.compile(
    r"(?:^|[_.])(?:min|max|earliest|latest|oldest|newest|first|last|top|bottom)(?:$|[_.])",
    re.IGNORECASE,
)

#: ``materialise`` reads a view's name, dimensions and measures only. The
#: research path holds its rows in memory and never queries a relation, so
#: this names that fact rather than a schema object that does not exist.
_IN_MEMORY_RELATION = "research-extract:in-memory"


class ResearchRefusalReason(enum.StrEnum):
    """Why an export refused. A class, never a cohort."""

    UNKNOWN_STUDY = "unknown_study"
    APPROVAL_NOT_IN_FORCE = "approval_not_in_force"
    APPROVAL_LAPSED = "approval_lapsed"
    RECIPIENT_NOT_APPROVED = "recipient_not_approved"
    RETENTION_UNSET = "retention_unset"
    # INT-262 — the differencing gate. A window overlapping a prior extract of
    # the same study+spec refuses: UNBUDGETED when the study states no query
    # budget (fail closed), EXHAUSTED when it states one and this request would
    # exceed it. Neither carries the window or the cohort size.
    OVERLAPPING_WINDOW_UNBUDGETED = "overlapping_window_unbudgeted"
    QUERY_BUDGET_EXHAUSTED = "query_budget_exhausted"
    VALUE_NOT_ID_SHAPED = "value_not_id_shaped"
    VALUE_CARRIES_IDENTIFIER = "value_carries_identifier"
    VALUE_OUTSIDE_VOCABULARY = "value_outside_vocabulary"
    DIMENSION_SET_MISMATCH = "dimension_set_mismatch"
    MEASURE_NOT_A_COUNT = "measure_not_a_count"
    ORDER_STATISTIC_MEASURE = "order_statistic_measure"
    SPEC_FIELD_NOT_ID_SHAPED = "spec_field_not_id_shaped"


class ResearchExportRefused(Exception):
    """The export did not happen.

    Carries the reason class and nothing derived from the data — never the
    refused value, never a cohort size, never a patient reference. A caller
    that needs a figure widens the window or coarsens the dimensions and asks
    again.
    """

    def __init__(self, reason: ResearchRefusalReason, detail: str) -> None:
        super().__init__(f"research export refused: {reason} — {detail}")
        self.reason = reason


@lru_cache(maxsize=1)
def _pattern_tier() -> Deidentifier:
    """The pattern tier, used here to REFUSE rather than to scrub.

    ``subject_key`` keys the date shifter, which this path never invokes: only
    :meth:`Deidentifier.analyze` is called, and only to ask whether a value
    contains a known identifier class. No NER model is loaded and none is
    needed — acceptance comes from the declared vocabulary, so the absence of
    the names tier can never widen what is admitted (contrast
    ``deidentify_for_egress``, whose contract is the opposite way round and
    fails closed for exactly that reason).
    """
    return Deidentifier(ner_model_dir=None, subject_key="research-export-value-scan")


def check_export_value(name: str, value: str) -> None:
    """Refuse ``value`` as an export field value, or return.

    Two independent refusals. The shape rule bounds the *carrier*: no space,
    no non-ASCII, at most 64 characters, so a sentence cannot be one. The
    pattern tier bounds the known *identifier classes*: a TCKN, a Turkish
    mobile number, an IBAN, an email and a date are all id-shaped, and a shape
    rule on its own would have admitted every one of them.

    Neither refusal echoes what it refused (invariant 6) — for the free-text
    case that is the whole point, and for the identifier case echoing it would
    put a TC Kimlik number in a traceback.
    """
    if EXPORT_VALUE_SHAPE.fullmatch(value) is None:
        raise ResearchExportRefused(
            ResearchRefusalReason.VALUE_NOT_ID_SHAPED,
            f"{name!r} must be id-shaped ([A-Za-z0-9_.:-], ≤64, ASCII); narrative is "
            "excluded from research exports rather than scrubbed (files/10 §3, HB-L6). "
            "The refused value is not echoed",
        )
    if _pattern_tier().analyze(value).entities:
        raise ResearchExportRefused(
            ResearchRefusalReason.VALUE_CARRIES_IDENTIFIER,
            f"{name!r} carries a direct identifier (INT-015 pattern tier). The refused "
            "value is not echoed",
        )


def check_export_field(value: str, *, what: str) -> str:
    """Refuse a NAME — a spec name, a dimension name, a measure, a study id, a
    recipient — that is not id-shaped. Same alphabet the study registry and
    the audit chain use, so a value that clears this can travel into an audit
    ref without a second rule to keep in step. The refused value is not
    echoed (invariant 6)."""
    if STUDY_FIELD_SHAPE.fullmatch(value) is None:
        raise ResearchExportRefused(
            ResearchRefusalReason.SPEC_FIELD_NOT_ID_SHAPED,
            f"{what} must be id-shaped; the refused value is not echoed",
        )
    return value


@dataclass(frozen=True)
class ResearchExtractSpec:
    """What an extract is allowed to contain: named dimensions, each with its
    CLOSED value set, and count measures.

    The vocabulary is the acceptance rule, and it is what closes the hole a
    shape check leaves open — a bare ASCII given name is id-shaped and carries
    no pattern identifier, and it is refused here because it is not a declared
    member of any dimension.
    """

    name: str
    dimensions: Mapping[str, tuple[str, ...]]
    measures: tuple[str, ...]
    cohort_description: str
    narrative_exclusion: str

    def __post_init__(self) -> None:
        check_export_field(self.name, what="extract spec name")
        if not self.dimensions:
            raise ResearchExportRefused(
                ResearchRefusalReason.DIMENSION_SET_MISMATCH,
                "an extract spec must declare at least one dimension: a row with no "
                "quasi-identifier has nothing for the k gate to cross",
            )
        for dimension, vocabulary in self.dimensions.items():
            check_export_field(dimension, what="dimension name")
            if not vocabulary:
                raise ResearchExportRefused(
                    ResearchRefusalReason.VALUE_OUTSIDE_VOCABULARY,
                    f"dimension {dimension!r} declares an empty vocabulary; an open "
                    "dimension is not a declaration",
                )
            for member in vocabulary:
                check_export_value(dimension, member)
        if not self.measures:
            raise ResearchExportRefused(
                ResearchRefusalReason.MEASURE_NOT_A_COUNT,
                "an extract spec must declare at least one count measure",
            )
        for measure in self.measures:
            check_export_field(measure, what="measure name")
            if _ORDER_STATISTIC.search(measure) is not None:
                raise ResearchExportRefused(
                    ResearchRefusalReason.ORDER_STATISTIC_MEASURE,
                    f"measure {measure!r} reads as an order statistic; a min or a max is "
                    "one real patient's value at any cohort size, so no threshold makes "
                    "it publishable",
                )

    @property
    def view(self) -> AnalyticsView:
        """The INT-171 view this spec's cross-tab is gated as. The relation is
        the in-memory sentinel: this package holds its rows already and never
        issues a query (no ``cells_query``, no ``read_cells``)."""
        return AnalyticsView(
            name=self.name,
            relation=_IN_MEMORY_RELATION,
            dimensions=tuple(self.dimensions),
            measures=self.measures,
            cohort_description=self.cohort_description,
            narrative_exclusion=self.narrative_exclusion,
        )
