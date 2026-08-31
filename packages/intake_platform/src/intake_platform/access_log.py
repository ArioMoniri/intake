"""The patient-visible access log (INT-016; KVKK-12, KSVY-7; files/06 §2, §4).

KVKK m.11(d) gives a data subject the right to learn whether their personal
data is being used for its purpose, and files/08 §2.5 turns that into a
concrete product surface: *the patient's own access log*, showing who reached
their record, when, and under what basis. This module is the projection
between what the hash chain stores and what a patient may be shown.

**Three things it is not.** It is not a screen: apps/** owns the rendering and
INT-139/INT-150 own the surfaces. It is not a second store: it reads the one
hash-chained log and adds nothing. And it authors no Turkish — every row
carries ``tr`` KEYS (invariant 5); the catalogue in ``apps/mobile`` holds the
copy, and until those keys exist the surface renders blanks rather than copy
invented here.

**What changes between the chain and the view.** The chain records an actor
id, a dotted action, an id-shaped resource ref and the consent scope or
statutory basis the access ran under. A patient needs *who, when, what for*.
So:

- *who* becomes :class:`ActorKind` (was it you, or someone else) plus, when a
  role directory records one, a files/08 §2.1 role id. Never a name: an
  identifier that is not one of the twelve ids is dropped, because the thing
  an unrecognised "role" is most likely to be is a person (invariant 6). No
  role directory exists yet — Keycloak and the console grants arrive with
  INT-180 — so :class:`NoRoleDirectory` answers "unrecorded", truthfully,
  the way ``NoAgeRecordSource`` answers for a missing date of birth.
- *what* becomes :class:`AccessKind` × :class:`RecordKind`, both derived by
  total rules over the action's dotted segments and the ref's prefix. An
  action nobody has classified still produces a VISIBLE row marked ``other``:
  fail-open is the right direction for a transparency surface, because the
  failure this view exists to prevent is an access the patient never learns
  about.
- *what for* stays the chain's own ``consent_scope_ref`` — ``scope:core``,
  ``basis:KVKK-11/13`` — which is already id-shaped and already PHI-free.

**The recursion, decided rather than left to the caller.** Reading an access
log is itself an access. Logging nothing is a hole (an insider could enumerate
a patient's log untraced); logging it and showing it is a loop (every read
adds a row, so the view grows by looking at it). The answer here: **the read
is always audited, and the subject's own access-log reads are suppressed in
the QUERY** — see :data:`SELF_READ_ACTION` and :class:`AccessLogQuery`. The
chain therefore stays complete for the auditor and for the DSAR export, which
read the chain rather than this view, while the view stays stable across
repeated reads. Suppression sits in the query, not after it, so a small
``limit`` is spent on entries the patient can actually see. A **non-self**
access-log read — staff, break-glass — is not suppressed: that is the entry
files/10 §3 most wants the patient to have.

**Ownership is a query predicate, not a caller's promise.** A source is asked
for a closed set of resource refs; it returns entries for those refs and
nothing else. The caller computes the set from the subject's own rows, so a
caller that computes it wrongly narrows the view, and can never widen it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Protocol

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from intake_platform.audit import AuditEntry, AuditStore
from intake_platform.db.audit_store import AuditChainRow

__all__ = [
    "ACCESS_LOG_TR_KEYS",
    "CONSOLE_ROLE_IDS",
    "SELF_READ_ACTION",
    "AccessKind",
    "AccessLogQuery",
    "AccessLogRow",
    "AccessLogSource",
    "ActorKind",
    "ActorRoleDirectory",
    "NoRoleDirectory",
    "RecordKind",
    "SqlAlchemyAccessLogSource",
    "StoreScanAccessLogSource",
    "access_tr_key",
    "actor_tr_key",
    "classify_access",
    "classify_record",
    "project",
    "record_tr_key",
]

#: The action every access-log read appends. It is a normal chain entry — the
#: read is audited like any other — and it is the ONE action suppressed from
#: the subject's own view (see the module docstring's recursion note).
SELF_READ_ACTION: Final = "api.access_log.read"

#: The console role set, verbatim from files/08 §2.1. A role identifier that is
#: not one of these is not rendered: it is far more likely to be a person's
#: name than a role we forgot, and a patient-facing surface is the last place
#: to find that out.
CONSOLE_ROLE_IDS: Final[frozenset[str]] = frozenset(
    {
        "platform_owner",
        "platform_admin",
        "tenant_admin",
        "tenant_clinical_responsible",
        "clinical_lead",
        "qms_owner",
        "investigator",
        "auditor",
        "sre_oncall",
        "compliance_officer",
        "researcher",
        "support",
    }
)


class ActorKind(StrEnum):
    """Who touched the record, from the subject's point of view."""

    SELF = "self"
    OTHER = "other"


class AccessKind(StrEnum):
    """What kind of access it was. ``OTHER`` is reachable and deliberate: an
    unclassified action must still appear."""

    VIEW = "view"
    SHARE = "share"
    EXPORT = "export"
    CHANGE = "change"
    ERASE = "erase"
    CONSENT = "consent"
    REFUSED = "refused"
    ACCESS_LOG = "access_log"
    OTHER = "other"


class RecordKind(StrEnum):
    """Which of the subject's records it touched."""

    ACCOUNT = "account"
    VISIT = "visit"
    NOTE = "note"
    DOCUMENT = "document"
    SHARE = "share"
    CONSENT = "consent"
    REQUEST = "request"
    OTHER = "other"


_TR_PREFIX: Final = "access_log"


def access_tr_key(kind: AccessKind) -> str:
    return f"{_TR_PREFIX}.access.{kind.value}"


def record_tr_key(kind: RecordKind) -> str:
    return f"{_TR_PREFIX}.record.{kind.value}"


def actor_tr_key(kind: ActorKind, role: str | None) -> str:
    """``self`` beats a role: a patient reading their own log is told "you",
    not the role their account happens to carry."""
    if kind is ActorKind.SELF:
        return f"{_TR_PREFIX}.actor.self"
    if role is None:
        return f"{_TR_PREFIX}.actor.unrecorded"
    return f"{_TR_PREFIX}.actor.role.{role}"


#: Every key a row can name — the ask handed to the ``tr`` catalogue
#: (apps/mobile/src/lib/i18n/tr.ts, invariant 5). Declared here as a KEY SET,
#: never as copy: a "temporary" Turkish string in source is indistinguishable
#: from reviewed copy once merged, which is the reason
#: intake_api.dsar.strings declares keys and no text either.
ACCESS_LOG_TR_KEYS: Final[frozenset[str]] = frozenset(
    {f"{_TR_PREFIX}.actor.self", f"{_TR_PREFIX}.actor.unrecorded"}
    | {f"{_TR_PREFIX}.actor.role.{role}" for role in CONSOLE_ROLE_IDS}
    | {access_tr_key(kind) for kind in AccessKind}
    | {record_tr_key(kind) for kind in RecordKind}
)


# --- classification: total rules over the chain's own vocabulary ---------------------

# Priority order matters and is fixed here rather than per call site.
# ``dsar.delete.request`` is an ERASE (the request is about deletion), not a
# CHANGE; ``api.consent.read`` is a VIEW of a consent record, not a consent
# action — the record kind already carries "consent".
_ACCESS_RULES: Final[tuple[tuple[AccessKind, frozenset[str]], ...]] = (
    (AccessKind.REFUSED, frozenset({"refused", "denied", "detected"})),
    (AccessKind.ACCESS_LOG, frozenset({"access_log"})),
    (AccessKind.ERASE, frozenset({"delete", "shred", "destroy", "erase"})),
    (AccessKind.SHARE, frozenset({"share", "shared"})),
    (AccessKind.EXPORT, frozenset({"export", "download", "issue", "copied", "served"})),
    (AccessKind.VIEW, frozenset({"read", "list", "view", "peek"})),
    (AccessKind.CONSENT, frozenset({"consent", "consents"})),
    (
        AccessKind.CHANGE,
        frozenset(
            {
                "cancel",
                "create",
                "created",
                "enqueue",
                "ingest",
                "link",
                "record",
                "rectify",
                "request",
                "requested",
                "review",
                "update",
                "verified",
                "write",
            }
        ),
    ),
)

_RECORD_RULES: Final[dict[str, RecordKind]] = {
    "patient": RecordKind.ACCOUNT,
    "visit": RecordKind.VISIT,
    "session": RecordKind.VISIT,
    "note": RecordKind.NOTE,
    "doc": RecordKind.DOCUMENT,
    "document": RecordKind.DOCUMENT,
    "share": RecordKind.SHARE,
    "consent": RecordKind.CONSENT,
    "dsar-request": RecordKind.REQUEST,
    "dsar-rectification": RecordKind.REQUEST,
}


def _tokens(action: str) -> frozenset[str]:
    """Dot segments PLUS their underscore parts: ``audit.worm_copied`` has to
    reach ``copied`` and ``auth.refresh.reuse_detected`` has to reach
    ``detected``, while ``api.access_log.read`` must still offer the whole
    ``access_log`` segment — so both granularities are in the set."""
    parts: set[str] = set()
    for segment in action.split("."):
        parts.add(segment)
        parts.update(segment.split("_"))
    return frozenset(parts)


def classify_access(action: str) -> AccessKind:
    """Dotted action name -> what the patient is told happened. Total: an
    unrecognised action is ``OTHER`` and still renders."""
    tokens = _tokens(action)
    for kind, markers in _ACCESS_RULES:
        if tokens & markers:
            return kind
    return AccessKind.OTHER


def classify_record(resource_ref: str) -> RecordKind:
    """``<kind>:<id>`` -> which record of the subject's it was. Total."""
    prefix, _, _ = resource_ref.partition(":")
    return _RECORD_RULES.get(prefix, RecordKind.OTHER)


# --- who: a directory seam, empty and honest until INT-180 --------------------------


class ActorRoleDirectory(Protocol):
    """Actor id -> a files/08 §2.1 role id, or ``None`` when none is recorded.

    Deliberately a seam: no directory of accounts exists in the product today
    (the dev tier has two synthetic accounts; Keycloak and the console role
    grants land with INT-131/INT-180), and inventing a mapping would put a
    guessed role in front of a patient.
    """

    def role_of(self, actor: str) -> str | None: ...


class NoRoleDirectory:
    """The default: no role directory exists, so no role is recorded. Reports
    that truthfully rather than guessing — the ``NoAgeRecordSource`` posture."""

    def role_of(self, actor: str) -> str | None:
        return None


# --- the view model ------------------------------------------------------------------


@dataclass(frozen=True)
class AccessLogRow:
    """One line of the patient's access log. Closed enums, id-shaped refs and
    ``tr`` keys only — the field set carries no place to put free text."""

    seq: int
    occurred_at: str
    actor_kind: ActorKind
    actor_role: str | None
    access_kind: AccessKind
    record_kind: RecordKind
    record_ref: str
    basis_ref: str
    actor_tr_key: str
    access_tr_key: str
    record_tr_key: str


def project(
    entries: Iterable[AuditEntry],
    *,
    subject_actor: str,
    roles: ActorRoleDirectory,
) -> tuple[AccessLogRow, ...]:
    """Chain entries -> patient-visible rows, in the order given.

    Pure: no filtering, no ordering, no suppression. Those belong to the query
    (:class:`AccessLogQuery`), where they cannot be forgotten by a caller that
    assembles entries some other way.
    """
    rows: list[AccessLogRow] = []
    for entry in entries:
        kind = ActorKind.SELF if entry.actor == subject_actor else ActorKind.OTHER
        role = roles.role_of(entry.actor) if kind is ActorKind.OTHER else None
        if role is not None and role not in CONSOLE_ROLE_IDS:
            role = None  # not a role we know; far likelier a person (invariant 6)
        access = classify_access(entry.action)
        record = classify_record(entry.resource_ref)
        rows.append(
            AccessLogRow(
                seq=entry.seq,
                occurred_at=entry.timestamp_utc,
                actor_kind=kind,
                actor_role=role,
                access_kind=access,
                record_kind=record,
                record_ref=entry.resource_ref,
                basis_ref=entry.consent_scope_ref,
                actor_tr_key=actor_tr_key(kind, role),
                access_tr_key=access_tr_key(access),
                record_tr_key=record_tr_key(record),
            )
        )
    return tuple(rows)


# --- the query and its sources -------------------------------------------------------


@dataclass(frozen=True)
class AccessLogQuery:
    """What the subject may see, stated as data.

    ``resource_refs`` is the CLOSED set of refs the app database says belong to
    this subject; a source returns entries for those refs and nothing else, so
    the ownership rule cannot be relaxed at a call site. An empty set means an
    empty log — never an unfiltered one.

    ``subject_actor`` is the subject's own actor id, used for exactly one
    thing: suppressing their own :data:`SELF_READ_ACTION` entries (see the
    module docstring). Suppression is part of the query so a small ``limit``
    is not consumed by rows that will be dropped.
    """

    resource_refs: tuple[str, ...]
    subject_actor: str
    limit: int


class AccessLogSource(Protocol):
    """Newest-first entries matching a query. Synchronous, like the audit
    store it reads; the API runs it off the event loop."""

    def fetch(self, query: AccessLogQuery) -> tuple[AuditEntry, ...]: ...


def _visible(entry: AuditEntry, query: AccessLogQuery) -> bool:
    if entry.resource_ref not in query.resource_refs:
        return False
    return not (entry.action == SELF_READ_ACTION and entry.actor == query.subject_actor)


class StoreScanAccessLogSource:
    """The protocol-level implementation: scan an :class:`AuditStore`.

    Not a stand-in — it is the correct answer for any deployment whose store
    is not SQLAlchemy, and it applies exactly the same ownership and
    suppression rules. It reads the whole chain, so the SQLAlchemy source
    below is what production wires.
    """

    def __init__(self, store: AuditStore) -> None:
        self._store = store

    def fetch(self, query: AccessLogQuery) -> tuple[AuditEntry, ...]:
        if not query.resource_refs:
            return ()
        matched = [entry for entry in self._store.entries() if _visible(entry, query)]
        matched.reverse()
        return tuple(matched[: query.limit])


class SqlAlchemyAccessLogSource:
    """The production source: one indexed ``ORDER BY seq DESC LIMIT`` over
    ``audit_chain`` with the ownership and suppression predicates in the WHERE
    clause. Read-only by construction — it issues SELECT and nothing else,
    matching the grant where no principal holds UPDATE or DELETE on the table
    (files/10 §2, invariant 40)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def fetch(self, query: AccessLogQuery) -> tuple[AuditEntry, ...]:
        if not query.resource_refs:
            return ()
        statement = (
            select(AuditChainRow)
            .where(AuditChainRow.resource_ref.in_(query.resource_refs))
            .where(
                ~(
                    (AuditChainRow.action == SELF_READ_ACTION)
                    & (AuditChainRow.actor == query.subject_actor)
                )
            )
            .order_by(AuditChainRow.seq.desc())
            .limit(query.limit)
        )
        with Session(self._engine) as session:
            rows: Sequence[AuditChainRow] = session.scalars(statement).all()
            return tuple(
                AuditEntry(
                    seq=row.seq,
                    timestamp_utc=row.timestamp_utc,
                    actor=row.actor,
                    action=row.action,
                    resource_ref=row.resource_ref,
                    consent_scope_ref=row.consent_scope_ref,
                    prev_hash=row.prev_hash,
                    entry_hash=row.entry_hash,
                )
                for row in rows
            )
