"""Request/response bodies (INT-197/134), pydantic v2, validated at the boundary.

The note shape mirrors the app's ``buildNote`` exactly: the closed section
set {chief_complaint, hpi, medications} with per-section share scopes
(scope-off excludes a section from what is SENT, never from what the patient
sees — 02 §5.1). Visit creation mirrors ``validateNewVisit`` and its reason
codes; the calendar check here is stricter on purpose (the server is the
boundary of record). Since INT-134 a visit is created against the branch
TAXONOMY (files/09 §1): ``branch_id`` + ``visit_type`` with the department
label derived from the taxonomy's own ``name_tr`` (invariant 5); the
free-text ``department`` body survives only as the INT-197 mirror path."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import dataclass
from typing import Annotated, Literal

from protocols.taxonomy import Taxonomy, UnknownBranchError
from protocols.types import VisitType
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from intake_api.errors import taxonomy_unconfigured, visit_invalid

__all__ = [
    "NewVisitData",
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
    # INT-134: the taxonomy path — branch id + visit type, department derived.
    branch_id: str | None = Field(default=None, max_length=100)
    visit_type: str | None = Field(default=None, max_length=40)
    # INT-197 mirror path only; refused when branch_id is present.
    department: str | None = Field(default=None, max_length=300)
    # Optional since INT-134: a planned visit may not be booked yet, and an
    # invented date would be a lie the whole timing model then trusts (02 §2b).
    date: str | None = Field(default=None, max_length=40)


class VisitOut(BaseModel):
    id: uuid.UUID
    hospital: str
    department: str
    branch_id: str | None
    visit_type: str | None
    date: str | None
    note_status: Literal["draft", "sent"] | None


@dataclass(frozen=True)
class NewVisitData:
    """A validated visit-to-be: what the store persists."""

    hospital: str
    department: str
    branch_id: str | None
    visit_type: str | None
    date: str | None


_VISIT_TYPE_IDS = frozenset(member.value for member in VisitType)


def _validated_date(raw: str | None) -> str | None:
    date = (raw or "").strip()
    if not date:
        return None
    if not _ISO_DATE.fullmatch(date):
        raise visit_invalid("bad_date")
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        raise visit_invalid("bad_date") from None
    return date


def _validated_visit_type(raw: str | None) -> str | None:
    """Membership in the closed files/09 §1 set; per-branch narrowing is the
    caller's taxonomy check."""
    visit_type = (raw or "").strip()
    if not visit_type:
        return None
    if visit_type not in _VISIT_TYPE_IDS:
        raise visit_invalid("bad_visit_type")
    return visit_type


def validated_new_visit(payload: VisitCreate, taxonomy: Taxonomy | None) -> NewVisitData:
    """The app's ``validateNewVisit`` semantics with its reason codes, plus
    the taxonomy checks the client cannot be trusted with (the server is the
    boundary of record):

    - ``branch_id`` must name a taxonomy branch (``unknown_branch`` — an
      unmapped booking fails closed, INT-042), in an intake cluster
      (``excluded_branch`` — Acil Tıp books no pre-visit intake), booking
      the given ``visit_type`` (``bad_visit_type``);
    - ``branch_id`` and free-text ``department`` are mutually exclusive
      (``department_conflict``) — one source of truth per visit;
    - the branch path needs the loaded taxonomy; without it the request
      fails CLOSED (503), never falls back to trusting the client.
    """
    hospital = payload.hospital.strip()
    branch_id = (payload.branch_id or "").strip()
    department = (payload.department or "").strip()
    visit_type = _validated_visit_type(payload.visit_type)
    date = _validated_date(payload.date)
    if not hospital:
        raise visit_invalid("missing_fields")
    if branch_id and department:
        raise visit_invalid("department_conflict")
    if not branch_id:
        # INT-197 mirror path: free-text department, no branch, no type check
        # beyond set membership (already done above).
        if not department:
            raise visit_invalid("missing_fields")
        return NewVisitData(
            hospital=hospital,
            department=department,
            branch_id=None,
            visit_type=visit_type,
            date=date,
        )
    if taxonomy is None:
        raise taxonomy_unconfigured()
    try:
        branch = taxonomy.branch(branch_id)
    except UnknownBranchError:
        raise visit_invalid("unknown_branch") from None
    if not taxonomy.cluster_of(branch).intake:
        raise visit_invalid("excluded_branch")
    if visit_type is None:
        # the taxonomy path always carries a type (the picker enforces it);
        # only the INT-197 mirror path may honestly not know one
        raise visit_invalid("missing_fields")
    if visit_type not in {member.value for member in branch.visit_types}:
        raise visit_invalid("bad_visit_type")
    return NewVisitData(
        hospital=hospital,
        department=branch.name_tr,
        branch_id=branch.id,
        visit_type=visit_type,
        date=date,
    )
