"""Request/response bodies (INT-197/134), pydantic v2, validated at the boundary.

The note shape mirrors the app's ``buildNote`` exactly: the closed section
set {chief_complaint, hpi, medications} with per-section share scopes
(scope-off excludes a section from what is SENT, never from what the patient
sees — 02 §5.1). Visit creation mirrors ``validateNewVisit`` and its reason
codes; the calendar check here is stricter on purpose (the server is the
boundary of record). Since INT-134 a visit is created against the branch
TAXONOMY (files/09 §1): ``branch_id`` + ``visit_type`` with the department
label derived from the taxonomy's own ``name_tr`` (invariant 5); the
free-text ``department`` body survives only as the INT-197 mirror path.

Since INT-306 a visit may also carry the appointment's TIME of day, with the
producer that stated it. Absent means unknown and stays unknown: a defaulted
midnight is indistinguishable from a real 00:00 booking and would silently
shorten every Doctor Link on that visit by up to a day (files/02 §2b). The
spelling and provenance rules live in :mod:`clinical_schemas.visit_time`, so
this boundary and the document-extraction path cannot disagree about them."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from clinical_schemas.visit_time import (
    ATTRIBUTED_SOURCES,
    VisitTime,
    VisitTimeError,
    VisitTimeSource,
    parse_visit_time,
)
from intake_platform.profiles import (
    AttributionDecision,
    ProxyAcknowledgement,
    Speaker,
    SubjectRole,
    resolve_attribution,
)
from protocols.department_routing import DepartmentMatch, map_department
from protocols.taxonomy import Taxonomy, UnknownBranchError
from protocols.types import VisitType
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from intake_api.errors import (
    proxy_acknowledgement_required,
    taxonomy_unconfigured,
    visit_invalid,
)

__all__ = [
    "AttributionIn",
    "NewVisitData",
    "NoteBody",
    "NoteOut",
    "NotePut",
    "NoteSection",
    "ProfileOut",
    "SectionId",
    "VisitCreate",
    "VisitOut",
    "resolved_attribution",
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
    # INT-133 / files/06 §6 — projected from the session that produced the
    # note. A clinician must be able to tell an observed symptom from a
    # reported one before they read a word of it.
    proxy_reported: bool = False
    third_party_present: bool = False


class AttributionIn(BaseModel):
    """INT-133 — the companion declaration a session may carry.

    The client declares only the two FACTS it can know (who holds the
    device, who is answering) plus the acknowledgement. It never sends
    ``proxy_reported``: files/06 §6 makes that flag a consequence, and a
    client-settable flag is a client-clearable one.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["self", "companion"] = "self"
    speaker: Literal["patient", "companion"] = "patient"
    acknowledged: bool = False
    third_party_present: bool = False


class VisitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hospital: str = Field(max_length=300)
    # INT-134: the taxonomy path — branch id + visit type, department derived.
    branch_id: str | None = Field(default=None, max_length=100)
    visit_type: str | None = Field(default=None, max_length=40)
    # INT-197 mirror path only; refused when branch_id is present.
    department: str | None = Field(default=None, max_length=300)
    # INT-323: an inbound source (Acıbadem/MHRS connector, or any bridge) that
    # carries only a free-text department asks the server to MAP it onto the
    # branch taxonomy — department-dynamic previsit routing. Default False
    # keeps the INT-197 mirror path byte-for-byte: a patient's pre-taxonomy
    # local visit derives no branch. An unmappable department fails closed
    # (free text kept, no branch), never a silent wrong specialty.
    resolve_department: bool = False
    # Optional since INT-134: a planned visit may not be booked yet, and an
    # invented date would be a lie the whole timing model then trusts (02 §2b).
    date: str | None = Field(default=None, max_length=40)
    # INT-306: the hour of the appointment where a producer knows it, ``HH:MM``.
    # Absent means UNKNOWN and stays unknown — never a defaulted midnight, which
    # is indistinguishable from a real 00:00 booking and would silently shorten
    # every Doctor Link on that visit by up to a day (files/02 §2b).
    time: str | None = Field(default=None, max_length=40)
    # INT-306: which of the three producers stated it. Declared by the producer
    # rather than derived by the server, and the comparison with INT-133's
    # ``proxy_reported`` is the reason: that flag is a CONSEQUENCE the platform
    # rules engine computes, so a client-settable one would be client-clearable.
    # Where a time was read is not a consequence of anything the server holds —
    # only the producer knows, and the two non-patient sources must name the
    # artefact, which is what makes the claim checkable rather than free.
    time_source: str | None = Field(default=None, max_length=40)
    time_source_ref: str | None = Field(default=None, max_length=200)
    # INT-133: absent means the default self-report session.
    attribution: AttributionIn | None = None


class VisitOut(BaseModel):
    id: uuid.UUID
    hospital: str
    department: str
    branch_id: str | None
    visit_type: str | None
    date: str | None
    # INT-306 — on EVERY record, and ``None`` is a stated fact rather than a
    # missing one: "we do not know the hour" is what the patient and the expiry
    # rule both have to be able to read.
    time: str | None = None
    time_source: str | None = None
    time_source_ref: str | None = None
    note_status: Literal["draft", "sent"] | None
    # INT-133 / files/06 §6 — on EVERY record, not only the ones a companion
    # created: an absent flag reads as "unknown", and a clinician must be
    # able to tell "self-reported" from "not recorded".
    proxy_reported: bool = False
    third_party_present: bool = False


class ProfileOut(BaseModel):
    """INT-133 — what the companion/profile screen may offer.

    Facts about the SYSTEM, never about the subject: an age band or a policy
    row id here would disclose the subject's minority (invariant 6). A
    subject the age gate refuses never reaches this body at all — the route
    401/403s through the one enforcement point first.
    """

    attributions: list[str]
    proxy_acknowledgement_required: bool
    guardian_flow_available: bool


@dataclass(frozen=True)
class NewVisitData:
    """A validated visit-to-be: what the store persists.

    ``time`` is the typed :class:`VisitTime` rather than the wire strings,
    because the store writes the provenance beside the value and a triple of
    loose strings is three chances to write two of them.
    """

    hospital: str
    department: str
    branch_id: str | None
    visit_type: str | None
    date: str | None
    time: VisitTime | None = None


_VISIT_TYPE_IDS = frozenset(member.value for member in VisitType)


def resolved_attribution(declared: AttributionIn | None) -> AttributionDecision:
    """Turn a client declaration into the derived session facts.

    The derivation is the platform rules engine's
    (``intake_platform.profiles``); this function only translates the wire
    literals and turns its refusal into the api's typed 422. Nothing here
    re-implements the rules — the same call answers for the voice runtime
    and any other producer.
    """
    if declared is None:
        return resolve_attribution(role=SubjectRole.SELF, speaker=Speaker.PATIENT)
    role = SubjectRole(declared.role)
    speaker = Speaker(declared.speaker)
    if role is SubjectRole.SELF and speaker is not Speaker.PATIENT:
        raise visit_invalid("attribution_incoherent")
    acknowledgement = (
        ProxyAcknowledgement(acknowledged=True, at=datetime.now(UTC))
        if declared.acknowledged
        else ProxyAcknowledgement(acknowledged=False)
    )
    decision = resolve_attribution(
        role=role,
        speaker=speaker,
        acknowledgement=acknowledgement,
        third_party_present=declared.third_party_present,
    )
    if not decision.permitted:
        raise proxy_acknowledgement_required()
    return decision


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


def _validated_visit_time(payload: VisitCreate, *, date: str | None) -> VisitTime | None:
    """INT-306 — the appointment's hour, or nothing, and never a default.

    Seven reason codes, kept apart rather than collapsed into one ``bad_time``,
    because each names a different engineering problem and a client that cannot
    tell them apart cannot fix any of them:

    - ``time_source_without_time`` — provenance for nothing is a claim that a
      reading happened with the reading missing;
    - ``time_source_required`` — a time with no producer is exactly the
      unattributed value the issue exists to stop;
    - ``time_source_unknown`` — the producer set is closed (files/09 §3's rule
      for a fact's provenance, and the same shape as ``LearnedFactSource``);
    - ``time_without_date`` — a time of day is not a schedule; storing one
      against no date hands the expiry rule half an anchor to guess the rest of;
    - ``bad_time`` / ``time_source_ref_*`` — the spelling and the artefact rules,
      both owned by :mod:`clinical_schemas.visit_time` so the wire boundary and
      the extraction path cannot disagree about them.

    An empty or whitespace-only ``time`` is ``bad_time`` rather than "absent":
    a client that sends the field is asserting it has a value, and silently
    reading that as unknown is how a dropped field becomes a shortened link.
    """
    raw_time = payload.time
    raw_source = (payload.time_source or "").strip()
    raw_ref = payload.time_source_ref
    if raw_time is None:
        if raw_source or raw_ref is not None:
            raise visit_invalid("time_source_without_time")
        return None
    if not raw_source:
        raise visit_invalid("time_source_required")
    try:
        source = VisitTimeSource(raw_source)
    except ValueError:
        raise visit_invalid("time_source_unknown") from None
    if date is None:
        raise visit_invalid("time_without_date")
    ref = raw_ref.strip() if raw_ref is not None else None
    if source in ATTRIBUTED_SOURCES and not ref:
        raise visit_invalid("time_source_ref_required")
    if source not in ATTRIBUTED_SOURCES and ref:
        raise visit_invalid("time_source_ref_refused")
    try:
        return parse_visit_time(raw_time, source=source, source_ref=ref or None)
    except VisitTimeError:
        # the rule, never the value: an appointment time is patient content
        # and a 422 body is a place it must not appear (invariant 6)
        raise visit_invalid("bad_time") from None


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
    time = _validated_visit_time(payload, date=date)
    if not hospital:
        raise visit_invalid("missing_fields")
    if branch_id and department:
        raise visit_invalid("department_conflict")
    if not branch_id:
        # INT-197 mirror path: free-text department, no branch, no type check
        # beyond set membership (already done above).
        if not department:
            raise visit_invalid("missing_fields")
        if payload.resolve_department:
            # INT-323: an inbound source asks the server to map the free-text
            # department onto the branch taxonomy (department-dynamic routing).
            # The branch path needs the loaded taxonomy; without it, fail CLOSED
            # (503) rather than trust the client — same rule as the branch path.
            if taxonomy is None:
                raise taxonomy_unconfigured()
            routing = map_department(taxonomy, department)
            if routing.match is not DepartmentMatch.UNMAPPED and routing.branch_id is not None:
                branch = taxonomy.branch(routing.branch_id)
                # A department that maps to Acil Tıp books no pre-visit intake —
                # RED routing only (files/09 §1), the same refusal the branch
                # path gives via `excluded_branch`.
                if not taxonomy.cluster_of(branch).intake:
                    raise visit_invalid("excluded_branch")
                return NewVisitData(
                    hospital=hospital,
                    # invariant 5: the tr label is the taxonomy's own name_tr.
                    department=branch.name_tr,
                    branch_id=branch.id,
                    visit_type=visit_type,
                    date=date,
                    time=time,
                )
            # UNMAPPED: fall through and keep the free-text department with no
            # branch — an unknown department never silently gets a specialty.
        return NewVisitData(
            hospital=hospital,
            department=department,
            branch_id=None,
            visit_type=visit_type,
            date=date,
            time=time,
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
        time=time,
    )
