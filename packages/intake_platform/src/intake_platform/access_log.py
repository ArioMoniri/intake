"""Patient-visible access log — the view model (INT-016; files/10 §3; KVKK m.11/m.13).

files/10 §3 states both the requirement and the failure it repairs. The access
log used to cover Doctor Link only, so the honest answer to *"does the patient
ever find out a member of staff read their intake?"* was *"only if they file a
KVKK m.11 request, and the DSAR export is not specified to include staff reads
at all."* The fix is to render the patient's log **from the hash-chained audit
entries themselves**: a row the patient sees is a row an auditor can re-verify
against the WORM bundle, and an access that never reached the chain is a breach
of invariant 4, not a hole in this projection.

This module is the view model and nothing else. It owns no route, no query and
no copy:

- **Routes** belong to the share centre (INT-139) and Doctor Link (INT-150);
  the DSAR export (INT-037) is the third consumer.
- **Turkish copy** belongs to the app: rows carry a closed
  :class:`AccessCategory`, never a rendered sentence. `tr` resource keys are
  the source of truth (invariant 5) and they live where the UI lives, so a
  backend projection that emitted Turkish prose would be authoring patient
  copy in the wrong place and in the wrong review path.

Four properties it does guarantee:

1. **Scoped by construction.** ``patient_refs`` is the caller's list of the
   patient's own resources; entries naming anything else are not rendered. An
   empty scope yields an empty log — the failure direction is "shows nothing",
   never "shows someone else's".
2. **Role, never identity** (files/10 §3: *actor role (not name)*). The chain
   records an actor **id**, not a role, so the resolver is an argument. An
   actor nobody resolves renders :attr:`AccessorRole.UNKNOWN`; the raw actor
   id — which may be an account id or a ``phone:<log-ref>`` — never reaches a
   row.
3. **Nothing silently dropped.** Every in-scope entry becomes exactly one row.
   An action the table has never seen becomes :attr:`AccessCategory.OTHER`,
   because an omitted share is precisely what this log exists to prevent.
4. **No PHI** (invariant 6). The audit entry's field set is closed and
   id-shaped; this projection narrows it and adds nothing.

**Deliberately absent: reason category and grant duration.** files/10 §3 names
both for break-glass reads. They live in the richer ``admin_audit.v1`` schema
(files/08 §8.1) that the break-glass module writes, and no human has yet
answered whether 24 h is the right notice window under KSVY / KVKK m.11
(files/HUMAN_BLOCKERS.md HB-L6). A nullable column here would read as a
promise the platform does not keep.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass

from intake_platform.audit import AuditEntry

__all__ = [
    "DEFAULT_ROLE_OF",
    "AccessCategory",
    "AccessLogRow",
    "AccessorRole",
    "build_access_log",
    "classify_action",
]


class AccessCategory(enum.StrEnum):
    """What happened, in terms a patient can act on. Closed on purpose: the
    set is small enough that every member can be given reviewed Turkish copy,
    which an open set of dotted action names could never be."""

    RECORD_VIEWED = "record_viewed"
    RECORD_SHARED = "record_shared"
    RECORD_UPDATED = "record_updated"
    CONSENT_CHANGED = "consent_changed"
    ACCOUNT_SECURITY = "account_security"
    DATA_REQUEST = "data_request"
    PREFERENCES_CHANGED = "preferences_changed"
    STAFF_REVIEW = "staff_review"
    SYSTEM_INTEGRITY = "system_integrity"
    OTHER = "other"


class AccessorRole(enum.StrEnum):
    """Who did it, as a role. files/10 §3 is explicit that the patient sees
    the role and not the name — an insider's identity is the auditor's
    business, and publishing it to patients creates its own hazard."""

    SELF = "self"
    GUARDIAN = "guardian"
    CLINICIAN = "clinician"
    CLINIC_STAFF = "clinic_staff"
    SYSTEM = "system"
    UNKNOWN = "unknown"


#: Exact action names, checked first. A near-miss must not be absorbed by a
#: prefix rule: ``api.note.share`` reading as an ordinary view would understate
#: what happened to the patient, which is the one error that matters here.
_EXACT: dict[str, AccessCategory] = {
    "api.note.read": AccessCategory.RECORD_VIEWED,
    "api.note.share": AccessCategory.RECORD_SHARED,
    "api.note.write": AccessCategory.RECORD_UPDATED,
    "api.visit.read": AccessCategory.RECORD_VIEWED,
    "api.visit.list": AccessCategory.RECORD_VIEWED,
    "api.visit.create": AccessCategory.RECORD_UPDATED,
    "api.document.download": AccessCategory.RECORD_VIEWED,
    "api.document.list": AccessCategory.RECORD_VIEWED,
    "api.document.create": AccessCategory.RECORD_UPDATED,
    "api.document.ingest": AccessCategory.RECORD_UPDATED,
    "api.experience.wait_times.read": AccessCategory.RECORD_VIEWED,
    "api.experience.wait_times.export": AccessCategory.DATA_REQUEST,
    "api.consent.read": AccessCategory.CONSENT_CHANGED,
    "api.csat.record": AccessCategory.PREFERENCES_CHANGED,
    "api.nps.record": AccessCategory.PREFERENCES_CHANGED,
    "guardian.link": AccessCategory.ACCOUNT_SECURITY,
}

#: Dotted-prefix families, longest match wins. Each entry matches ``family``
#: exactly or ``family.`` followed by anything — never a bare string prefix,
#: so ``api.noteworthy.read`` cannot be swallowed by ``api.note``.
_PREFIX: dict[str, AccessCategory] = {
    "api.notification_prefs": AccessCategory.PREFERENCES_CHANGED,
    "consent": AccessCategory.CONSENT_CHANGED,
    "auth": AccessCategory.ACCOUNT_SECURITY,
    "dsar": AccessCategory.DATA_REQUEST,
    "annotation": AccessCategory.STAFF_REVIEW,
    "audit": AccessCategory.SYSTEM_INTEGRITY,
    "retention": AccessCategory.SYSTEM_INTEGRITY,
}

#: A sharing action is never anything but sharing. This runs after the exact
#: and prefix tables and before the fallback, so a share that arrives from a
#: module nobody has mapped yet still reads as a share rather than as "other".
_SHARING_SEGMENT = "share"

#: Actor ids the platform gives its own services. This is the only role the
#: chain's own data supports: everything else is an account id, and inferring
#: a role from an account id is how a display name reaches a patient's screen.
_SERVICE_ACTOR_PREFIX = "svc-"


def classify_action(action: str) -> AccessCategory:
    """Map an audit action name to a patient-facing category.

    Total by design: an unrecognised action returns
    :attr:`AccessCategory.OTHER` rather than raising, because a new action
    somewhere in the platform must not be able to break a patient's screen —
    and must not be able to disappear from it either.
    """
    exact = _EXACT.get(action)
    if exact is not None:
        return exact
    segments = action.split(".")
    for length in range(len(segments) - 1, 0, -1):
        family = _PREFIX.get(".".join(segments[:length]))
        if family is not None:
            return family
    if _SHARING_SEGMENT in segments:
        return AccessCategory.RECORD_SHARED
    return AccessCategory.OTHER


def DEFAULT_ROLE_OF(actor: str) -> AccessorRole:  # noqa: N802 — a named default, not a class
    """The only actor→role mapping the audit entry alone can justify.

    ``svc-api``, ``svc-documents`` and ``svc-audit-writer`` are platform
    service identities by convention (files/10 §2), so they resolve to
    :attr:`AccessorRole.SYSTEM`. Everything else is an account id and resolves
    to :attr:`AccessorRole.UNKNOWN` — deliberately, because the caller holds
    the account directory and this module does not. Wire a real resolver at
    the route; do not widen this one by guessing at id shapes.
    """
    return AccessorRole.SYSTEM if actor.startswith(_SERVICE_ACTOR_PREFIX) else AccessorRole.UNKNOWN


@dataclass(frozen=True)
class AccessLogRow:
    """One row of the patient's access log.

    ``seq`` and ``entry_hash`` are carried so the patient's view is anchored
    to the tamper-evident record: the same row appears at the same position in
    the WORM bundle, which is what makes the log evidence rather than a
    rendering. Frozen, and the field set is closed — a field that does not
    exist cannot accumulate PHI (invariant 6).
    """

    seq: int
    occurred_at_utc: str
    category: AccessCategory
    action: str
    accessor_role: AccessorRole
    resource_ref: str
    consent_scope_ref: str
    entry_hash: str


def build_access_log(
    entries: Iterable[AuditEntry],
    *,
    patient_refs: Collection[str],
    role_of: Callable[[str], AccessorRole] = DEFAULT_ROLE_OF,
) -> tuple[AccessLogRow, ...]:
    """Project audit entries into the patient's access log.

    Rows come back in chain order (ascending ``seq``). No ordering policy is
    invented here: chain order is the order the events happened in and the
    order the WORM bundle holds them in, so a consumer that wants newest-first
    reverses it at the surface where that choice belongs.
    """
    scope = frozenset(patient_refs)
    return tuple(
        AccessLogRow(
            seq=entry.seq,
            occurred_at_utc=entry.timestamp_utc,
            category=classify_action(entry.action),
            action=entry.action,
            accessor_role=role_of(entry.actor),
            resource_ref=entry.resource_ref,
            consent_scope_ref=entry.consent_scope_ref,
            entry_hash=entry.entry_hash,
        )
        for entry in entries
        if entry.resource_ref in scope
    )
