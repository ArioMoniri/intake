"""One Safety inbox entry (INT-406; files/10 §9.1 invariant 49; files/08 §3).

An entry is **a pointer and a clock**, never a message. files/08 §3's Safety
queue shows *"every RED with its inbox timestamp, acknowledgement clock,
acknowledging person and elapsed time against the tenant SLA"* — ids, closed
kinds and instants. So that is the whole field set:

- **Ids only** (CLAUDE.md invariant 6). The tenant, session and visit are
  identifiers; the rule ids are the rules engine's own (invariant 1); the
  acknowledging person is a staff subject. ``RuleFire.evidence`` — *"which
  slot values satisfied the rule"* — is patient material and has no field
  here, which is how it cannot reach the inbox, a log line or a label.
- **The id is derived, not minted.** ``entry_id`` is a digest of the tenant,
  the kind and the source (the RED's content-addressed ``work_id``, or the
  transition's id), so a re-derived RED — files/03 §4.6 invariant 6 — lands on
  the entry already there instead of opening a second clock for one event.
- **Four RED kinds, and only these.** ``red`` is the RED itself. Two are files/02
  §2b's rule that *"``rescheduled`` or ``cancelled`` on a RED visit raises a
  clinic inbox entry regardless of connector presence"*: each is its own entry
  with its own clock, because the moved visit is new news to the clinic even
  when the RED was answered. ``red_on_site`` is the staff notification of
  files/02 §5.3 Axis 3 and files/04 §8.1 rule 7 (INT-475): under ``ON_SITE``
  *"the clinic inbox entry is the primary channel"* and fires automatically,
  because a qualified human is fifty metres away. It names the RED by its
  ``work_id``, so there is one per RED, and it carries its own clock: the
  patient being in the building is new news even when the RED was answered.
  It is the one record of the RED location axis (ids and the kind only), and
  it does not index the visit — files/02 §2b reads a visit's REDs, and this is
  not one.
- **Clinician-only clinic items, which are not REDs** (INT-547, INT-525).
  CD-08 routes the items the clinical decisions raise to the booked clinic's
  inbox: ``chest_pain_arms_unresolved`` is CD-04's (a chest-pain slot still
  UNCLEAR after its follow-up), and ``proxy_chest_pain_screen_unasked`` is
  CD-01's (a proxy session left the chest-pain screen unasked). An item entry
  names the item by its own reference,
  which the session derives from itself and the kind, so an item is one entry
  per session however often it is raised. The rule ids are the chest-pain
  rules the item concerns, never a fired RED. No item kind carries a register
  or indexes the visit, and while CD-08 leaves their SLA
  ``draft_needs_source`` none has an acknowledgement SLA
  (:meth:`~intake_platform.safety_inbox.sla.AckSlaPolicy.sla_for_entry`).
- **The clock is ``created_at``.** It is stamped where the entry is made — on
  the RED path, in-process — and nothing later moves it: a store that was
  down when the RED fired writes the entry late, but the clinic's clock still
  started at the RED.
- **A RED entry records the register it was told in** (INT-407). files/02 §2b
  re-shows the crisis signposting *"in the register the original RED used"*
  when a RED visit moves, and this entry is the only server-side record of a
  RED — so the register rides on it, a closed enum and never words. It is
  optional only because an entry written before INT-407 has none; a reader
  that finds none withholds the re-show rather than choose a register, since a
  default register *"would be chosen once, by an engineer, for all future
  rules"* (files/02 §5.3). The transition kinds carry none.
"""

from __future__ import annotations

import enum
import hashlib
import re
import warnings
from datetime import datetime, timedelta
from typing import Annotated, Final, Literal, Self

from clinical_schemas.triage import RedRegister
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ID_SHAPE",
    "RULE_ID_SHAPE",
    "CLINIC_ITEM_KINDS",
    "AlreadyAcknowledged",
    "EntryKind",
    "InboxEntry",
    "VisitTransition",
    "entry_id_for",
    "require_id",
    "require_rule_id",
    "require_subject",
    "require_tenant_id",
]

#: The tenant shape the voice control store keys on (INT-182), so one tenant id
#: is valid in both stores or in neither.
_TENANT: Final = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
#: Session, visit, work and transition ids: UUIDs and content digests. Public
#: so a route that takes an id for an entry (INT-475) refuses what the entry would.
ID_SHAPE: Final = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_ID: Final = re.compile(ID_SHAPE)
#: ``ID_SHAPE`` of the RED trigger (intake_voice_runtime.talker.red_path),
#: which every rules-engine rule id (``rf.<segments>``) already satisfies.
RULE_ID_SHAPE: Final = r"^[a-z0-9][a-z0-9._-]{0,127}$"
_RULE: Final = re.compile(RULE_ID_SHAPE)
#: A console subject, the id shape the audit chain accepts (files/08 §8.1).
_SUBJECT: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")
_ENTRY: Final = re.compile(r"^sx_[0-9a-f]{32}$")


def _shaped(pattern: re.Pattern[str], what: str) -> AfterValidator:
    def check(value: str) -> str:
        if not pattern.fullmatch(value):
            # the value is never echoed: a refused id may be the prose that
            # should never have been handed in (invariant 6)
            raise ValueError(f"{what} is not id-shaped")
        return value

    return AfterValidator(check)


def require_tenant_id(value: str) -> str:
    if not isinstance(value, str) or not _TENANT.fullmatch(value):
        raise ValueError("a tenant id is id-shaped; the submitted value is not echoed")
    return value


def require_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("an id is id-shaped; the submitted value is not echoed")
    return value


def require_rule_id(value: str) -> str:
    if not isinstance(value, str) or not _RULE.fullmatch(value):
        raise ValueError("a rule id is id-shaped; the submitted value is not echoed")
    return value


def require_subject(value: str) -> str:
    if not isinstance(value, str) or not _SUBJECT.fullmatch(value):
        raise ValueError("a subject is id-shaped; the submitted value is not echoed")
    return value


type _TenantId = Annotated[str, _shaped(_TENANT, "tenant_id")]
type _Id = Annotated[str, _shaped(_ID, "id")]
type _RuleId = Annotated[str, _shaped(_RULE, "rule id")]
type _Subject = Annotated[str, _shaped(_SUBJECT, "subject")]
type _EntryId = Annotated[str, _shaped(_ENTRY, "entry_id")]


class AlreadyAcknowledged(Exception):
    """The entry was acknowledged before. An acknowledgement is recorded once;
    a second one would overwrite who answered, and when."""

    code = "safety_entry_already_acknowledged"


class EntryKind(enum.StrEnum):
    RED = "red"
    VISIT_RESCHEDULED = "visit_rescheduled"
    VISIT_CANCELLED = "visit_cancelled"
    #: INT-475: the RED's patient is on site; staff are notified (files/04 §8.1 rule 7).
    RED_ON_SITE = "red_on_site"
    #: INT-547 (CD-04, CD-08): a chest-pain slot still UNCLEAR after its follow-up.
    CHEST_PAIN_ARMS_UNRESOLVED = "chest_pain_arms_unresolved"
    #: INT-525 (CD-01, CD-08): a proxy session left the chest-pain screen unasked.
    PROXY_CHEST_PAIN_SCREEN_UNASKED = "proxy_chest_pain_screen_unasked"

    @property
    def is_clinic_item(self) -> bool:
        """A CD-08 clinician-only item: not a RED, and no SLA while CD-08's is draft."""
        return self in CLINIC_ITEM_KINDS


#: The CD-08 clinic items (INT-547, INT-525). Never a RED.
CLINIC_ITEM_KINDS: Final = frozenset(
    {EntryKind.CHEST_PAIN_ARMS_UNRESOLVED, EntryKind.PROXY_CHEST_PAIN_SCREEN_UNASKED}
)


class VisitTransition(enum.StrEnum):
    """files/02 §2b's two transitions a RED visit may not make silently."""

    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"

    @property
    def kind(self) -> EntryKind:
        return _TRANSITION_KIND[self]


_TRANSITION_KIND: Final = {
    VisitTransition.RESCHEDULED: EntryKind.VISIT_RESCHEDULED,
    VisitTransition.CANCELLED: EntryKind.VISIT_CANCELLED,
}


def entry_id_for(tenant_id: str, kind: EntryKind, source_ref: str) -> str:
    """``sx_`` + the first 32 hex of sha256(tenant, kind, source)."""
    digest = hashlib.sha256(
        "\x00".join((tenant_id, kind.value, source_ref)).encode("utf-8")
    ).hexdigest()
    return f"sx_{digest[:32]}"


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


# The blueprint names the RED axis field `register` (CLAUDE.md invariant 21;
# files/02 §5.3); pydantic warns because ABCMeta exposes a classmethod of the
# same name. The blueprint name wins — suppress exactly that warning, as
# clinical_schemas.triage does for its own.
warnings.filterwarnings(
    "ignore",
    message='Field name "register" in "InboxEntry" shadows an attribute in parent',
    category=UserWarning,
)


class InboxEntry(BaseModel):
    """Immutable; acknowledging returns a new entry."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    schema_version: Literal[1] = 1
    entry_id: _EntryId
    tenant_id: _TenantId
    session_id: _Id
    visit_id: _Id
    kind: EntryKind
    rule_ids: tuple[_RuleId, ...] = Field(min_length=1)
    #: The RED's ``work_id``, the visit transition's id, or a clinic item's reference.
    source_ref: _Id
    created_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: _Subject | None = None
    #: INT-407: how the RED was told (files/02 §5.3 Axis 2), for the §2b re-show.
    register: RedRegister | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _aware(self.created_at, "created_at")
        if self.entry_id != entry_id_for(self.tenant_id, self.kind, self.source_ref):
            raise ValueError("entry_id is derived from tenant, kind and source, never chosen")
        if self.register is not None and self.kind is not EntryKind.RED:
            raise ValueError("only a RED entry records a register; a transition was told nothing")
        if (self.acknowledged_at is None) != (self.acknowledged_by is None):
            raise ValueError("an acknowledgement names both who and when, or neither")
        if self.acknowledged_at is not None:
            _aware(self.acknowledged_at, "acknowledged_at")
            if self.acknowledged_at < self.created_at:
                raise ValueError("an entry cannot be acknowledged before it existed")
        return self

    @classmethod
    def for_red(
        cls,
        *,
        tenant_id: str,
        session_id: str,
        visit_id: str,
        work_id: str,
        rule_ids: tuple[str, ...],
        at: datetime,
        register: RedRegister | None = None,
    ) -> InboxEntry:
        return cls(
            entry_id=entry_id_for(tenant_id, EntryKind.RED, work_id),
            tenant_id=tenant_id,
            session_id=session_id,
            visit_id=visit_id,
            kind=EntryKind.RED,
            rule_ids=rule_ids,
            source_ref=work_id,
            created_at=at,
            register=register,
        )

    @classmethod
    def for_on_site(
        cls,
        *,
        tenant_id: str,
        session_id: str,
        visit_id: str,
        work_id: str,
        rule_ids: tuple[str, ...],
        at: datetime,
    ) -> InboxEntry:
        """The staff notification for the RED ``work_id`` names: its patient is on
        site. Derived from the same ``work_id`` as the RED's own entry, so a
        second ON_SITE for one RED lands on the first."""
        return cls(
            entry_id=entry_id_for(tenant_id, EntryKind.RED_ON_SITE, work_id),
            tenant_id=tenant_id,
            session_id=session_id,
            visit_id=visit_id,
            kind=EntryKind.RED_ON_SITE,
            rule_ids=rule_ids,
            source_ref=work_id,
            created_at=at,
        )

    @classmethod
    def for_visit_transition(
        cls,
        *,
        tenant_id: str,
        session_id: str,
        visit_id: str,
        transition: VisitTransition,
        transition_id: str,
        rule_ids: tuple[str, ...],
        at: datetime,
    ) -> InboxEntry:
        return cls(
            entry_id=entry_id_for(tenant_id, transition.kind, transition_id),
            tenant_id=tenant_id,
            session_id=session_id,
            visit_id=visit_id,
            kind=transition.kind,
            rule_ids=rule_ids,
            source_ref=transition_id,
            created_at=at,
        )

    @classmethod
    def for_clinic_item(
        cls,
        *,
        tenant_id: str,
        session_id: str,
        visit_id: str,
        kind: EntryKind,
        item_ref: str,
        rule_ids: tuple[str, ...],
        at: datetime,
    ) -> InboxEntry:
        """A CD-08 clinic item (INT-547), named by its own reference.

        ``item_ref`` is derived by the session from itself and the kind, so the
        entry id (tenant, kind, reference) is one per session and kind: a second
        raise lands on the first entry and its clock.
        """
        if not kind.is_clinic_item:
            raise ValueError("a RED-family kind is never raised as a clinic item")
        return cls(
            entry_id=entry_id_for(tenant_id, kind, item_ref),
            tenant_id=tenant_id,
            session_id=session_id,
            visit_id=visit_id,
            kind=kind,
            rule_ids=rule_ids,
            source_ref=item_ref,
            created_at=at,
        )

    @property
    def is_open(self) -> bool:
        return self.acknowledged_at is None

    def age(self, now: datetime) -> timedelta:
        return now - self.created_at

    def acknowledge(self, *, by: str, at: datetime) -> InboxEntry:
        if not self.is_open:
            raise AlreadyAcknowledged("the entry was already acknowledged")
        if at < self.created_at:
            raise ValueError("an entry cannot be acknowledged before it existed")
        return self.model_copy(update={"acknowledged_at": at, "acknowledged_by": by}).validated()

    def validated(self) -> InboxEntry:
        """Re-run the validators (``model_copy`` skips them)."""
        return InboxEntry.model_validate(self.model_dump())
