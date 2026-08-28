"""Request/response bodies (INT-197), pydantic v2, validated at the boundary.

The note shape mirrors the app's ``buildNote`` exactly: the closed section
set {chief_complaint, hpi, medications} with per-section share scopes
(scope-off excludes a section from what is SENT, never from what the patient
sees — 02 §5.1). Visit creation mirrors ``validateNewVisit`` and its two
reason codes; the calendar check here is stricter on purpose (the server is
the boundary of record)."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from intake_api.errors import visit_invalid

__all__ = [
    "NoteBody",
    "NoteOut",
    "NotePut",
    "NoteSection",
    "SectionId",
    "VisitCreate",
    "VisitOut",
    "validated_new_visit",
]

SectionId = Literal["chief_complaint", "hpi", "medications"]

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

Line = Annotated[str, StringConstraints(min_length=1, max_length=2000)]
Title = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class NoteSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: SectionId
    title: Title
    lines: list[Line] = Field(min_length=1, max_length=100)


class NoteBody(BaseModel):
    """What the envelope carries at rest: sections + share scopes. A section
    id absent from ``scopes`` means shared (default-on, matching the app)."""

    model_config = ConfigDict(extra="forbid")

    sections: list[NoteSection] = Field(min_length=1, max_length=3)
    scopes: dict[SectionId, bool] = Field(default_factory=dict)

    @field_validator("sections")
    @classmethod
    def _unique_section_ids(cls, sections: list[NoteSection]) -> list[NoteSection]:
        ids = [section.id for section in sections]
        if len(set(ids)) != len(ids):
            raise ValueError("section ids must be unique")
        return sections

    def shared_section_ids(self) -> list[str]:
        return [s.id for s in self.sections if self.scopes.get(s.id, True)]


class NotePut(NoteBody):
    status: Literal["draft", "sent"]


class NoteOut(BaseModel):
    visit_id: uuid.UUID
    sections: list[NoteSection]
    scopes: dict[SectionId, bool]
    status: Literal["draft", "sent"]


class VisitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hospital: str = Field(max_length=300)
    department: str = Field(max_length=300)
    date: str = Field(max_length=40)


class VisitOut(BaseModel):
    id: uuid.UUID
    hospital: str
    department: str
    date: str
    note_status: Literal["draft", "sent"] | None


def validated_new_visit(payload: VisitCreate) -> tuple[str, str, str]:
    """The app's ``validateNewVisit`` semantics with its reason codes, plus a
    real calendar check (the regex alone accepts 2026-02-31)."""
    hospital = payload.hospital.strip()
    department = payload.department.strip()
    date = payload.date.strip()
    if not hospital or not department:
        raise visit_invalid("missing_fields")
    if not _ISO_DATE.fullmatch(date):
        raise visit_invalid("bad_date")
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        raise visit_invalid("bad_date") from None
    return hospital, department, date
