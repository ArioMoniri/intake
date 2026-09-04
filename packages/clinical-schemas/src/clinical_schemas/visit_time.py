"""The time of day a visit is booked for, and who says so (INT-306).

files/02 §2b pins Doctor Link expiry to ``visit_datetime + 72 h`` and says in
terms that ``issue_time + 72 h`` is the wrong clock. Until now this repository
recorded a visit **date** and no time of day, and two issues reached that gap
from opposite ends: INT-150 could not compute the expiry its own spec states
and took the conservative approximation (anchor to the start of the visit day,
which is never later than the appointment), while INT-122 parsed an appointment
time off an MHRS message and had nowhere to put it. This module is the field
they were both missing.

**Three properties, and none of them is a check somebody could forget.**

1. *Unknown stays unknown.* :class:`VisitSchedule` carries ``time=None`` for a
   visit whose hour nobody has stated. It never carries a defaulted midnight,
   because a defaulted midnight is indistinguishable from a real ``00:00``
   appointment and would silently shorten every later link by up to a day. The
   two produce the same anchor instant — they are the same instant — and that
   is exactly why the distinction has to live in the recorded value rather than
   in what the anchor computes.

2. *Nothing arrives unattributed.* :class:`VisitTimeSource` is closed over the
   three producers a visit time can have — the patient typing it, a connector
   field, a document extraction — and the two that are not the patient's own
   typing must name the artefact they were read from. That is the same shape
   an extracted value already carries elsewhere in this repository
   (:class:`~clinical_schemas.record_extraction.SourceBox` and
   :class:`~clinical_schemas.overlay.Confirmation` both make the "where from"
   a required, defaultless field), reused rather than reinvented. A patient
   entry is refused a ``source_ref`` for the mirror-image reason: the patient
   read it off nothing this repository holds, and a ref attached to their
   typing would be a claim that some artefact was consulted.

3. *One spelling per value.* :meth:`VisitTime.render` emits ``HH:MM`` and
   :func:`parse_visit_time` accepts nothing else — not ``9:30``, not
   ``14:30:00``, not ``24:00``. Invariant 22 is about exactly this: two
   spellings of one minute at a representation boundary is how a value changes
   meaning on the way across. The digits are positional and ungrouped, and the
   time carries no timezone, because the zone belongs to the visit's calendar
   date and is applied once, at the anchor (``Europe/Istanbul``, in
   :mod:`intake_platform.doctor_link`). A tz-bearing time here would be a
   second opinion about the same instant.

**Frozen dataclasses rather than** :class:`~clinical_schemas.common.FrozenModel`,
for INT-170's reason, restated because it is load-bearing: this repository
enables no pydantic mypy plugin, so ``BaseModel.__init__`` type-checks as
``**data: Any`` and a missing ``source=`` would pass ``mypy --strict`` and fail
only at runtime. The synthesised ``__init__`` of a frozen dataclass refuses it
at the call site.

**No message here echoes a time, a date or a document's contents** — every one
of them is patient content and an exception message reaches a log (invariant 6).
"""

from __future__ import annotations

import datetime as dt
import enum
import re
from dataclasses import dataclass

__all__ = [
    "ATTRIBUTED_SOURCES",
    "VISIT_TIME_PATTERN",
    "VisitSchedule",
    "VisitTime",
    "VisitTimeError",
    "VisitTimeSource",
    "parse_visit_time",
]


class VisitTimeError(ValueError):
    """A visit time is not constructible as asked.

    Names the rule, never the value: a refusal reaches a log and an appointment
    time is patient content (invariant 6).
    """


class VisitTimeSource(enum.StrEnum):
    """Every producer of a visit time, enumerated (INT-306 acceptance 2).

    Three members and no fourth. A producer this set does not name has to be
    added here deliberately, in a diff a reviewer sees, rather than passed in
    as a string by whoever happens to be writing the row.

    - ``PATIENT_ENTRY`` — the patient typed it. The only source whose evidence
      is the person, so it names no artefact.
    - ``CONNECTOR_FIELD`` — an MHRS/e-Nabız connector answered with it. No
      connector in this repository produces one yet; the member exists so the
      first one that does inherits this vocabulary instead of minting a second.
    - ``DOCUMENT_EXTRACTION`` — read off a document the patient supplied
      (INT-122's MHRS message reader is the producer today).
    """

    PATIENT_ENTRY = "patient_entry"
    CONNECTOR_FIELD = "connector_field"
    DOCUMENT_EXTRACTION = "document_extraction"


#: The sources whose evidence is an artefact rather than a person, and which
#: therefore may not be written down without naming it.
ATTRIBUTED_SOURCES: frozenset[VisitTimeSource] = frozenset(
    {VisitTimeSource.CONNECTOR_FIELD, VisitTimeSource.DOCUMENT_EXTRACTION}
)

#: The one accepted spelling: 24-hour, zero-padded, minute resolution. Written
#: as a full-match pattern rather than handed to ``time.fromisoformat``, which
#: accepts ``14:30:00`` and ``14:30:00.5`` for the same minute (invariant 22).
VISIT_TIME_PATTERN = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")


@dataclass(frozen=True, slots=True)
class VisitTime:
    """An appointment's time of day, with the provenance that makes it usable.

    ``at`` is a civil time in the visit's own calendar — no timezone, no
    seconds. Minute resolution is what an appointment is booked at; a second
    would be precision nobody has, and two spellings of the same minute is the
    representation slack invariant 22 exists to stop.
    """

    at: dt.time
    source: VisitTimeSource
    source_ref: str | None = None

    def __post_init__(self) -> None:
        if self.at.tzinfo is not None:
            raise VisitTimeError(
                "a visit time is a civil time in the visit's own calendar; the zone "
                "belongs to the date and is applied once, at the expiry anchor"
            )
        if self.at.second or self.at.microsecond:
            raise VisitTimeError(
                "a visit time is booked to the minute; sub-minute precision here is "
                "precision no producer has (invariant 22: one spelling per value)"
            )
        if self.source in ATTRIBUTED_SOURCES:
            if self.source_ref is None or not self.source_ref.strip():
                raise VisitTimeError(
                    "a time read off an artefact names the artefact it was read from, "
                    "the way every other extracted value in this repository does "
                    "(invariant 6: an id, never the reading)"
                )
        elif self.source_ref is not None:
            raise VisitTimeError(
                "a time the patient typed was read off no artefact this repository "
                "holds; a ref attached to it would claim one was consulted"
            )

    def render(self) -> str:
        """``HH:MM`` — the one spelling that crosses a boundary (invariant 22).

        Positional digits, zero-padded, no grouping separator, one atom.
        """
        return f"{self.at.hour:02d}:{self.at.minute:02d}"


def parse_visit_time(
    raw: str, *, source: VisitTimeSource, source_ref: str | None = None
) -> VisitTime:
    """Build a :class:`VisitTime` from the ``HH:MM`` wire spelling.

    Refuses anything else — including spellings that denote a real minute
    (``9:30``, ``14:30:00``) — so a value cannot mean one thing on the way in
    and another on the way out.
    """
    match = VISIT_TIME_PATTERN.fullmatch(raw.strip())
    if match is None:
        raise VisitTimeError(
            "a visit time is written HH:MM, 24-hour and zero-padded (invariant 22: "
            "one spelling per value at a representation boundary)"
        )
    return VisitTime(
        at=dt.time(int(match.group(1)), int(match.group(2))),
        source=source,
        source_ref=source_ref,
    )


@dataclass(frozen=True, slots=True)
class VisitSchedule:
    """When a visit is booked for: a date, and a time that may be unknown.

    The absent time is a first-class state rather than a sentinel value. What
    reads this — :func:`intake_platform.doctor_link.link_expires_at` — is
    therefore forced to say which of the two rules it is applying, instead of
    receiving a midnight it cannot tell from a booking.
    """

    date: dt.date
    time: VisitTime | None = None

    @property
    def time_is_known(self) -> bool:
        """Whether an hour was ever stated. ``False`` is a recorded fact here,
        not a missing one — see the module docstring."""
        return self.time is not None
