"""The MHRS SMS screenshot: the weakest source on the records path (INT-122).

files/01 §5, on why this exists at all: *"MHRS has no public API; capture
appointments by manual entry, SMS/screenshot OCR, calendar"*. So the input is
an OCR of a photograph of a text message, and every reading it produces is a
candidate (:mod:`intake_platform.records.visit_candidate`).

**What is read, and what is refused, per field.**

* **branch** — resolved against the *committed* taxonomy
  (``packages/protocols/taxonomy/branches.yaml``), which the caller supplies
  as a vocabulary because ``intake_platform`` sits below ``protocols`` in the
  dependency graph. Matching is over **whole adjacent tokens**, never a
  substring: ``Göğüs Hastalıkları`` is a whole-token subsequence of ``Çocuk
  Göğüs Hastalıkları``, and reading the child appointment as the adult branch
  runs an adult protocol pack on a child. This is CLAUDE.md invariant 22's
  ``üre`` rule — *never substring-match* — applied to the thing an SMS names.
  Two *different* branches in one message refuse the field.
* **date and time** — :mod:`intake_platform.records.turkish_dates`, which
  refuses every printed form that reads two ways and every message that states
  more than one distinct date. No order is passed: no committed source states
  the order an MHRS SMS prints, so the ambiguous form stays refused.
* **hospital and visit type** — not attempted, and the candidate has no field
  for either. See :mod:`intake_platform.records.visit_candidate`.

**When it is unsure it produces nothing and names the field.** A missing
appointment is visible to the patient the moment they open the app; a wrong
one is not visible until they arrive at the hospital on the wrong day. That
asymmetry is the whole design, and it is why there is no nearest-match, no
fuzzy distance and no default reading order anywhere in this module.

**The screenshot's text is data, never instructions** (invariant 14): it
crosses the one fence :mod:`intake_platform.data_boundary` owns, exactly as a
document's text layer does.

**No message here echoes what the screenshot printed** (invariant 6).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from intake_platform.records.analytes import fold_tr
from intake_platform.records.document import FencedDocument
from intake_platform.records.turkish_dates import (
    PrintedDateAmbiguous,
    PrintedDateNotFound,
    PrintedDateUnreadable,
    PrintedTimeAmbiguous,
    PrintedTimeNotFound,
    PrintedTimeUnreadable,
    find_printed_date,
    find_printed_time,
)
from intake_platform.records.visit_candidate import (
    CandidateVisitFields,
    VisitCandidateError,
    VisitFieldRefusal,
)

__all__ = [
    "BranchNameAmbiguous",
    "BranchVocabulary",
    "parse_mhrs_sms",
    "resolve_printed_branch",
]

_TOKEN: Final = re.compile(r"\w+")


class BranchNameAmbiguous(ValueError):
    """The message names more than one committed branch.

    Not a fallback to the first or the longest: two branches can serve two
    different protocol packs, so a message that names both is refused. The
    message names no printed content (invariant 6).
    """


def _tokens(text: str) -> tuple[str, ...]:
    """Whole tokens, Turkish-folded.

    The fold is :func:`~intake_platform.records.analytes.fold_tr` rather than a
    second copy of it: ``İç Hastalıkları`` under Python's default ``casefold``
    grows a combining dot and stops matching its own committed name, which is
    the same trap that guard was written for.
    """
    return tuple(_TOKEN.findall(fold_tr(text)))


@dataclass(frozen=True, slots=True)
class BranchVocabulary:
    """The committed branch names, keyed by their token sequence.

    Built by the caller from ``protocols.taxonomy``: ``intake_platform`` does
    not depend on ``intake-protocols`` (``services/api`` depends on both), and
    a second copy of the branch list here would be a second thing to keep in
    step with files/09 §1.
    """

    entries: Mapping[tuple[str, ...], str]
    longest_name: int

    @classmethod
    def from_names(cls, names: Mapping[str, str]) -> BranchVocabulary:
        """``{name_tr: branch_id}`` from the taxonomy, refusing a collision."""
        entries: dict[tuple[str, ...], str] = {}
        for name, branch_id in names.items():
            tokens = _tokens(name)
            if not tokens:
                raise VisitCandidateError(
                    "a committed branch name folds to no tokens, so nothing could match it"
                )
            if entries.get(tokens, branch_id) != branch_id:
                raise VisitCandidateError(
                    "two committed branch names fold to one token sequence, so a printed "
                    "name cannot decide between their branch ids; the taxonomy is fixed "
                    "rather than the match being guessed"
                )
            entries[tokens] = branch_id
        if not entries:
            raise VisitCandidateError(
                "a branch vocabulary with no committed names resolves nothing; it fails "
                "closed rather than reading every message as an unknown branch"
            )
        return cls(
            entries=MappingProxyType(entries),
            longest_name=max(len(tokens) for tokens in entries),
        )


def resolve_printed_branch(text: str, vocabulary: BranchVocabulary) -> str | None:
    """The one committed branch a message names, ``None``, or a refusal.

    Matching is over adjacent whole tokens. Where one match's token span sits
    strictly inside another's, the shorter reading is **the same printed
    characters counted twice** rather than a second occurrence, so the maximal
    span is what the document printed; that is what makes ``Çocuk Göğüs
    Hastalıkları`` the child branch instead of an ambiguity. Two spans that
    resolve to different branches without one containing the other are a real
    ambiguity and are refused.
    """
    tokens = _tokens(text)
    spans: list[tuple[int, int, str]] = []
    for start in range(len(tokens)):
        limit = min(vocabulary.longest_name, len(tokens) - start)
        for length in range(limit, 0, -1):
            branch_id = vocabulary.entries.get(tokens[start : start + length])
            if branch_id is not None:
                spans.append((start, start + length, branch_id))
    resolved = {
        branch_id
        for index, (start, end, branch_id) in enumerate(spans)
        if not any(
            other_start <= start and end <= other_end and other_end - other_start > end - start
            for other_index, (other_start, other_end, _) in enumerate(spans)
            if other_index != index
        )
    }
    if not resolved:
        return None
    if len(resolved) > 1:
        raise BranchNameAmbiguous(
            "the message names more than one committed branch, and two branches can "
            "serve two different protocol packs, so neither is taken (files/09 §1). "
            "No printed name is echoed here (invariant 6)."
        )
    return resolved.pop()


def parse_mhrs_sms(
    text: str, *, document_ref: str, vocabulary: BranchVocabulary
) -> CandidateVisitFields:
    """Read what a screenshot's text can defend, and name what it cannot.

    Raises :class:`~intake_platform.records.document.DocumentBoundaryEscape`
    for an empty screenshot — the ``NoOcr`` answer, which is a refusal and
    never "no appointment" — and for one whose text carries the data-block
    control token.
    """
    fenced = FencedDocument(text)
    refusals: list[str] = []

    branch_id: str | None = None
    try:
        branch_id = resolve_printed_branch(fenced.text, vocabulary)
    except BranchNameAmbiguous:
        refusals.append(f"branch_id:{VisitFieldRefusal.AMBIGUOUS.value}")
    else:
        if branch_id is None:
            refusals.append(f"branch_id:{VisitFieldRefusal.NOT_FOUND.value}")

    date = None
    try:
        date = find_printed_date(fenced.text)
    except PrintedDateAmbiguous:
        refusals.append(f"date:{VisitFieldRefusal.AMBIGUOUS.value}")
    except PrintedDateNotFound:
        refusals.append(f"date:{VisitFieldRefusal.NOT_FOUND.value}")
    except PrintedDateUnreadable:
        refusals.append(f"date:{VisitFieldRefusal.UNREADABLE.value}")

    time = None
    try:
        time = find_printed_time(fenced.text)
    except PrintedTimeAmbiguous:
        refusals.append(f"time:{VisitFieldRefusal.AMBIGUOUS.value}")
    except PrintedTimeNotFound:
        refusals.append(f"time:{VisitFieldRefusal.NOT_FOUND.value}")
    except PrintedTimeUnreadable:
        refusals.append(f"time:{VisitFieldRefusal.UNREADABLE.value}")

    return CandidateVisitFields(
        document_ref=document_ref,
        branch_id=branch_id,
        date=date,
        time=time,
        refusals=tuple(refusals),
    )
