"""INT-175 — annotation queues, their access control, and the shut content gate
(CLAUDE.md inv. 4/6/17; files/08 §2.5, §2.6, §3; files/HUMAN_BLOCKERS.md HB-L6).

Three queues are named in the acceptance — ``note_quality``,
``hallucination_audit``, ``false_red_review`` — and all three exist to put a
clinician in front of something a model produced from a patient's words. That
is a **staff read of patient content**, and files/08 §2.5 is unambiguous about
what governs one: a closed-category reason, a distinct approver, a TTL, a
watermark, an audit row written *before* the read, and an entry in the
patient's own access log within 24 h.

Two of those preconditions do not exist yet, and neither is ours to invent:

1. **HB-L6 is open.** Counsel has not ruled on staff access to patient content,
   and Langfuse spans are named in that blocker by name.
2. **There is no lawful basis to check.** files/08 §2.6 works it through: in
   the consumer deployment we are the controller, KVKK m.6/3's care ground
   runs to persons under an obligation of secrecy, and "an INTAKE support
   engineer is not that person". The purposes enumerated in files/06 §2 — and
   therefore in :mod:`intake_platform.consent.registry` — contain **nothing**
   covering staff access. The `support_access` explicit-consent purpose that
   would cover it is a question for counsel, not a row we may add.

So this module ships the mechanism with the gate wired and shut, per
CLAUDE.md ("build the mechanism, wire the gate, make it fail closed, leave the
content empty"):

- **Enqueue works today.** A queue item is a pointer — ids, a span ref and a
  timestamp — so putting one on a queue carries no content and is a real,
  useful thing to do now. It is consent-checked and audited anyway.
- **Labelling works today.** A review carries a closed enum verdict and a
  closed enum section reason. There is no free-text field, so the reviewer's
  note cannot become the place the transcript reappears.
- **Reading content does not work, and cannot be made to work by
  configuration.** :func:`authorize_content_read` returns
  :class:`ContentReadRefused` — and that is its *only* return type. There is
  no granted counterpart in this module, so the gate is a wall rather than a
  branch: opening it means adding a type and deleting the tests that assert
  its absence. The refusal is audited before it is returned, because the audit
  ordering rule (files/08 §2.5 item 6) applies to attempts, not only to
  successes, and a denial is a detection signal (files/10 §7).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Protocol

from prometheus_client import Counter

from intake_platform.consent.registry import resolve_scope
from intake_platform.observability.spans import refuse_unless_ref_shaped

__all__ = [
    "QUEUES",
    "AuditSink",
    "ConsentGate",
    "ConsentScopeRefused",
    "ContentReadRefused",
    "Label",
    "QueueDef",
    "QueueId",
    "QueueItem",
    "Review",
    "ReviewerRole",
    "ReviewerRoleRefused",
    "SectionReason",
    "authorize_content_read",
    "enqueue",
    "queue_def",
    "record_review",
]

#: The HUMAN_BLOCKERS.md row that keeps every content read shut. It is a
#: literal rather than a lookup on purpose: parsing the blockers file at
#: runtime would make the gate depend on a document's formatting.
CONTENT_BLOCKER_ID: Final = "HB-L6"

QUEUE_ENQUEUED_TOTAL: Final = Counter(
    "annotation_queue_enqueued_total",
    "Annotation-queue items enqueued, by queue (INT-175). Items are pointers: ids, a "
    "span ref and a timestamp, never clinical text.",
    ["queue"],
)

CONTENT_READS_REFUSED_TOTAL: Final = Counter(
    "annotation_content_reads_refused_total",
    "Staff attempts to read clinical content behind an annotation queue, refused by the "
    "open blocker (INT-175; HB-L6). Every attempt is audited before it is refused.",
    ["queue", "blocker"],
)


class QueueId(StrEnum):
    """The three queues the acceptance names. A closed set."""

    NOTE_QUALITY = "note_quality"
    HALLUCINATION_AUDIT = "hallucination_audit"
    FALSE_RED_REVIEW = "false_red_review"


class ReviewerRole(StrEnum):
    """Console roles that may touch a queue (files/08 §2.1)."""

    CLINICIAN = "clinician"
    CLINICAL_LEAD = "clinical_lead"
    COMPLIANCE_OFFICER = "compliance_officer"


class Label(StrEnum):
    """The reviewer's verdict — the same three INT-153 names."""

    ACCEPT = "accept"
    EDIT = "edit"
    REJECT = "reject"


class SectionReason(StrEnum):
    """Which part of the artefact the verdict is about.

    Closed on purpose. "Reason" is exactly the field a free-text box grows
    into, and a free-text box next to a clinical note is where the note gets
    pasted back in.
    """

    CHIEF_COMPLAINT = "chief_complaint"
    HISTORY = "history"
    MEDICATIONS = "medications"
    ALLERGIES = "allergies"
    RED_FLAGS = "red_flags"
    INSTRUMENTS = "instruments"
    SUMMARY = "summary"
    STRUCTURE = "structure"


class ConsentScopeRefused(ValueError):
    """The consent scope this queue rides does not stand for this session."""


class ReviewerRoleRefused(ValueError):
    """This role may not act on this queue."""


@dataclass(frozen=True)
class QueueDef:
    """One queue's contract.

    ``enqueue_scope`` is the consent purpose that covers putting a pointer on
    the queue. ``content_scope`` is the purpose that would cover a staff read
    of the underlying clinical content — ``None`` for every queue, because
    files/06 §2 enumerates no such purpose (files/08 §2.6). ``content_blocker``
    names the HUMAN_BLOCKERS.md row that must be answered first.
    """

    id: QueueId
    enqueue_scope: str
    reviewer_roles: frozenset[ReviewerRole]
    requires_clinical_content: bool
    content_scope: str | None
    content_blocker: str


QUEUES: Final[tuple[QueueDef, ...]] = (
    QueueDef(
        id=QueueId.NOTE_QUALITY,
        # files/06 §2: de-identified aggregates for service improvement, an
        # opt-out purpose. It covers the POINTER, not the content behind it.
        enqueue_scope="learning:service_improvement",
        reviewer_roles=frozenset({ReviewerRole.CLINICIAN, ReviewerRole.CLINICAL_LEAD}),
        requires_clinical_content=True,
        content_scope=None,
        content_blocker=CONTENT_BLOCKER_ID,
    ),
    QueueDef(
        id=QueueId.HALLUCINATION_AUDIT,
        enqueue_scope="learning:service_improvement",
        # comparing a completion against what the patient actually said is the
        # single most content-exposing review there is
        reviewer_roles=frozenset({ReviewerRole.CLINICAL_LEAD}),
        requires_clinical_content=True,
        content_scope=None,
        content_blocker=CONTENT_BLOCKER_ID,
    ),
    QueueDef(
        id=QueueId.FALSE_RED_REVIEW,
        enqueue_scope="learning:service_improvement",
        reviewer_roles=frozenset({ReviewerRole.CLINICAL_LEAD}),
        # the rule id and the branch are structural, but deciding whether the
        # RED was right means reading the answer that fired it
        requires_clinical_content=True,
        content_scope=None,
        content_blocker=CONTENT_BLOCKER_ID,
    ),
)

_BY_ID: Final[dict[QueueId, QueueDef]] = {definition.id: definition for definition in QUEUES}

# Import-time contract: every enqueue scope must resolve against the closed
# files/06 §2 purpose list, so a typo is a boot failure and not a silently
# unenforced consent check.
for _definition in QUEUES:
    resolve_scope(_definition.enqueue_scope)


def queue_def(queue: QueueId) -> QueueDef:
    return _BY_ID[queue]


class ConsentGate(Protocol):
    """The consent seam (invariant 4). ``services/api`` binds this to
    :func:`intake_platform.consent.service.is_scope_allowed` against the
    session's tenant and patient; the unit lane injects a decision."""

    def allows(self, *, tenant_id: str, session_id_hash: str, scope: str) -> bool: ...


class AuditSink(Protocol):
    """The hash-chained audit seam (invariant 4). :class:`intake_platform.
    audit.AuditChain` satisfies it as written."""

    def append(
        self, *, actor: str, action: str, resource_ref: str, consent_scope_ref: str
    ) -> object: ...


@dataclass(frozen=True)
class QueueItem:
    """A pointer onto a queue. Ids only — every string field is id-shaped, so
    a sentence cannot be constructed into one."""

    item_id: str
    queue: QueueId
    tenant_id: str
    session_id_hash: str
    work_id: str
    span_ref: str
    created_at_utc: str

    def __post_init__(self) -> None:
        for field_name in (
            "item_id",
            "tenant_id",
            "session_id_hash",
            "work_id",
            "span_ref",
            "created_at_utc",
        ):
            refuse_unless_ref_shaped(field_name, getattr(self, field_name))
        if not isinstance(self.queue, QueueId):
            raise ValueError("field 'queue' must be a QueueId member")


@dataclass(frozen=True)
class Review:
    """A reviewer's verdict. Two closed enums and ids — no free text."""

    item_id: str
    queue: QueueId
    actor: str
    reviewer_role: ReviewerRole
    label: Label
    section_reason: SectionReason
    recorded_at_utc: str


@dataclass(frozen=True)
class ContentReadRefused:
    """The only outcome of asking to read the clinical content behind an item.

    There is deliberately no granted counterpart in this module. The object
    carries the attempt's identifiers and the blocker id — never a handle, a
    url or a token that could later be exchanged for content.
    """

    item_id: str
    queue: QueueId
    actor: str
    reviewer_role: ReviewerRole
    blocker_id: str
    reason: str
    audited: bool


def _stamp(now: datetime) -> str:
    """UTC, second precision, ``Z``-suffixed — id-shaped, unlike the ``+00:00``
    form ``datetime.isoformat`` produces."""
    if now.tzinfo is None:
        raise ValueError("annotation timestamps must be timezone-aware (UTC)")
    return now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def enqueue(
    queue: QueueId,
    *,
    item_id: str,
    tenant_id: str,
    session_id_hash: str,
    work_id: str,
    span_ref: str,
    now: datetime,
    consent: ConsentGate,
    audit: AuditSink,
    actor: str,
) -> QueueItem:
    """Put a pointer on ``queue``. Consent-checked and audited both ways."""
    definition = queue_def(queue)
    resource_ref = f"annotation:{queue.value}:{refuse_unless_ref_shaped('item_id', item_id)}"
    if not consent.allows(
        tenant_id=tenant_id, session_id_hash=session_id_hash, scope=definition.enqueue_scope
    ):
        audit.append(
            actor=actor,
            action="annotation.enqueue.refused",
            resource_ref=resource_ref,
            consent_scope_ref=definition.enqueue_scope,
        )
        raise ConsentScopeRefused(
            f"consent scope {definition.enqueue_scope!r} does not stand for this session; "
            f"queue {queue.value!r} refuses the item (invariant 4)"
        )
    item = QueueItem(
        item_id=item_id,
        queue=queue,
        tenant_id=tenant_id,
        session_id_hash=session_id_hash,
        work_id=work_id,
        span_ref=span_ref,
        created_at_utc=_stamp(now),
    )
    audit.append(
        actor=actor,
        action="annotation.enqueue",
        resource_ref=resource_ref,
        consent_scope_ref=definition.enqueue_scope,
    )
    QUEUE_ENQUEUED_TOTAL.labels(queue=queue.value).inc()
    return item


def record_review(
    item: QueueItem,
    *,
    actor: str,
    role: ReviewerRole,
    label: Label,
    section_reason: SectionReason,
    now: datetime,
    audit: AuditSink,
) -> Review:
    """Record a closed-enum verdict against ``item``."""
    definition = queue_def(item.queue)
    resource_ref = f"annotation:{item.queue.value}:{item.item_id}"
    if role not in definition.reviewer_roles:
        audit.append(
            actor=actor,
            action="annotation.review.refused",
            resource_ref=resource_ref,
            consent_scope_ref=definition.enqueue_scope,
        )
        raise ReviewerRoleRefused(
            f"role {role.value!r} may not review queue {item.queue.value!r} "
            f"(permitted: {sorted(r.value for r in definition.reviewer_roles)})"
        )
    if not isinstance(label, Label):
        raise ValueError("field 'label' must be a Label member")
    if not isinstance(section_reason, SectionReason):
        audit.append(
            actor=actor,
            action="annotation.review.refused",
            resource_ref=resource_ref,
            consent_scope_ref=definition.enqueue_scope,
        )
        raise ValueError(
            "field 'section_reason' must be a SectionReason member: the reason is a closed "
            "enum precisely so it cannot become the free-text box the note gets pasted into"
        )
    review = Review(
        item_id=item.item_id,
        queue=item.queue,
        actor=refuse_unless_ref_shaped("actor", actor),
        reviewer_role=role,
        label=label,
        section_reason=section_reason,
        recorded_at_utc=_stamp(now),
    )
    audit.append(
        actor=actor,
        action="annotation.review",
        resource_ref=resource_ref,
        consent_scope_ref=definition.enqueue_scope,
    )
    return review


def authorize_content_read(
    item: QueueItem, *, actor: str, role: ReviewerRole, audit: AuditSink
) -> ContentReadRefused:
    """Ask to read the clinical content behind ``item``. Always refused.

    The audit row is written **before** the decision is returned (files/08
    §2.5 item 6), so the attempt is on the chain whatever happens next. The
    return type is the refusal and nothing else: see this module's docstring
    for why that is a wall rather than a default.
    """
    definition = queue_def(item.queue)
    audit.append(
        actor=actor,
        action="annotation.content_read.refused",
        resource_ref=f"annotation:{item.queue.value}:{item.item_id}",
        consent_scope_ref=definition.content_blocker,
    )
    CONTENT_READS_REFUSED_TOTAL.labels(
        queue=item.queue.value, blocker=definition.content_blocker
    ).inc()
    return ContentReadRefused(
        item_id=item.item_id,
        queue=item.queue,
        actor=actor,
        reviewer_role=role,
        blocker_id=definition.content_blocker,
        reason=(
            "staff reads of patient content are unruled: files/HUMAN_BLOCKERS.md "
            f"{definition.content_blocker} is open, and files/06 §2 enumerates no purpose "
            "covering staff access (files/08 §2.6). No lawful basis exists to check, so "
            "there is nothing to grant."
        ),
        audited=True,
    )


def pending_items(items: Iterable[QueueItem], queue: QueueId) -> tuple[QueueItem, ...]:
    """The queue's items, in insertion order. Pointers only — listing a queue
    is not a read of content and needs no grant."""
    return tuple(item for item in items if item.queue is queue)
