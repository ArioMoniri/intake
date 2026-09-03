"""What an MHRS SMS screenshot may become, and what it may not (INT-122).

An OCR of a photograph of a text message is a candidate in the strongest
sense the word has on this project. CLAUDE.md invariant 12 says an inferred
fact needs confirmation, and INT-170 established that this is carried by the
**type** rather than by a rule somebody remembers: the candidate has no field
a confirmation could occupy, the confirmed form cannot be built without one,
and there is exactly one bridge. That is the shape reused here, with INT-170's
confirmation vocabulary rather than a second one — ``CONFIRMED_IMPORTED_RECORD``
maps to ``PATIENT`` in a closed, total table, so *"the patient confirmed it"*
is read off the vocabulary rather than passed in by a caller who could pass
something else.

**Two fields are missing on purpose, and their absence is the design.**

* There is no ``hospital``. No hospital list is committed to this repository,
  so a screenshot's hospital name cannot be resolved against anything, and a
  field that is always ``None`` is a claim that the parser tried.
* There is no ``visit_type``. files/09 §1's ten visit types are ids; **no
  committed source maps a printed Turkish word to one of them**, and inventing
  that table would be authoring clinical vocabulary. The picker already
  narrows the type per branch (INT-134), which is where the patient supplies
  it.

Both are supplied by the person at :func:`confirm_visit_candidate`, alongside
their confirmation of what *was* read. So the confirmed form carries three
things a patient agreed to and two things a patient typed, and neither set can
be mistaken for the other.

**Confirming is agreeing, never restating** (INT-121's rule): the candidate
crosses into the confirmed form unchanged. A patient who disagrees with the
date on the screenshot produces a correction — they type the visit themselves
— rather than an edited extraction.

**No message here echoes what a screenshot printed** (invariant 6).
"""

from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field

from clinical_schemas.overlay import Confirmation, LearnedFactSource

__all__ = [
    "CandidateVisitFields",
    "ConfirmedVisitFields",
    "VisitCandidateError",
    "VisitFieldRefusal",
    "VisitFields",
    "confirm_visit_candidate",
]


class VisitCandidateError(ValueError):
    """A visit candidate is not constructible as asked.

    No message names a printed branch, a printed date or a line of a message:
    every one of them is patient content and an exception reaches a log.
    """


class VisitFieldRefusal(enum.StrEnum):
    """Why a field the parser attempted came back empty.

    Three outcomes, and they are different engineering problems: *not found*
    means the message did not state it, *ambiguous* means it stated more than
    one, and *unreadable* means it stated one this guard will not resolve.
    Collapsing them into a single "missing" would hide which of the three a
    fix should address.
    """

    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class CandidateVisitFields:
    """What a screenshot proposes. Not a visit, by construction.

    Nothing here names a confirmer or a confirmation time, so "a screenshot
    reading that says it was confirmed" is not a case to reject — it cannot be
    written down.
    """

    document_ref: str
    branch_id: str | None = None
    date: dt.date | None = None
    time: dt.time | None = None
    refusals: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.document_ref.strip():
            raise VisitCandidateError(
                "a visit candidate names the screenshot it was read from, so the patient "
                "can be shown the image they are confirming against (invariant 6: an id)"
            )


@dataclass(frozen=True, slots=True)
class VisitFields:
    """The four fields ``POST /v1/visits`` takes, and nothing else.

    ``date`` is ISO-8601 — plain positional digits, no grouping, one atom
    (invariant 22) — which is the form the API's own validator accepts, so the
    representation crossing happens once and here.
    """

    hospital: str
    branch_id: str | None
    visit_type: str | None
    date: str | None


@dataclass(frozen=True, slots=True)
class ConfirmedVisitFields:
    """The only shape that may become a visit.

    It cannot be built without a :class:`~clinical_schemas.overlay.Confirmation`
    and the confirmation cannot be re-pointed afterwards, so a caller cannot
    walk an unconfirmed reading in through a later assignment either.
    """

    candidate: CandidateVisitFields
    hospital: str
    visit_type: str | None
    confirmation: Confirmation

    def __post_init__(self) -> None:
        if self.confirmation.source is not LearnedFactSource.CONFIRMED_IMPORTED_RECORD:
            raise VisitCandidateError(
                "a confirmed visit reading carries the imported-record provenance; a "
                "confirmation minted for another source describes another event"
            )
        if self.confirmation.source_ref != self.candidate.document_ref:
            raise VisitCandidateError(
                "the confirming artefact is the screenshot the reading came from; a "
                "confirmation naming a different document confirms a different thing"
            )
        if not self.hospital.strip():
            raise VisitCandidateError(
                "a visit names the hospital it is at; the screenshot never resolved one, "
                "so this is the patient's own entry and it may not be empty"
            )

    def as_visit_fields(self) -> VisitFields:
        return VisitFields(
            hospital=self.hospital.strip(),
            branch_id=self.candidate.branch_id,
            visit_type=self.visit_type,
            date=self.candidate.date.isoformat() if self.candidate.date is not None else None,
        )


def confirm_visit_candidate(
    candidate: CandidateVisitFields,
    *,
    hospital: str,
    visit_type: str | None,
    at: dt.datetime,
) -> ConfirmedVisitFields:
    """The one bridge from a screenshot reading to something usable.

    There is no ``by=`` parameter and its absence is the point: the actor is
    derived from INT-170's closed table, so *"the patient confirms"* cannot be
    asserted by a caller. ``source_ref`` is derived from the candidate, so a
    confirmation naming some other artefact is not a case to reject here
    either — the bridge cannot mint one.

    ``hospital`` and ``visit_type`` are the patient's own entries: neither was
    read from the screenshot, and neither has a field on the candidate.
    """
    return ConfirmedVisitFields(
        candidate=candidate,
        hospital=hospital,
        visit_type=visit_type,
        confirmation=Confirmation(
            source=LearnedFactSource.CONFIRMED_IMPORTED_RECORD,
            source_ref=candidate.document_ref,
            confirmed_at=at,
        ),
    )
