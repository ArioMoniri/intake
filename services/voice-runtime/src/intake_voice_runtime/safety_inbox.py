"""The clinician route into the clinic Safety inbox (INT-406; invariant 49).

:class:`SafetyInboxNotifier` is the production
:class:`~intake_voice_runtime.talker.red_path.ClinicNotifier`: it turns one
:class:`~intake_voice_runtime.talker.red_path.RedNotification` into one
:class:`~intake_platform.safety_inbox.InboxEntry` and puts it in the process's
:class:`~intake_platform.safety_inbox.SafetyInboxOutbox`. That is the whole of
it, and each property of the port survives:

- **Nothing awaits and nothing dials.** ``notify`` is an append under a lock;
  the outbox's worker writes the shared store. The RED path's first step
  cannot delay its stop (the port's contract), and no connector, network call
  or hospital system sits between the RED and the entry — "regardless of
  connector presence" (files/02 §8.2) holds by construction.
- **Ids only** (invariant 6). The notification carries ids and closed axes and
  the entry keeps the ids plus the register — a closed enum the clinician
  queue does not show, recorded because files/02 §2b re-shows a RED "in the
  register the original RED used" when its visit moves (INT-407). The RED
  entry keeps no location: a §2b re-show re-derives it for wherever the
  patient then stands.
- **ON_SITE notifies staff in the same put** (INT-475; files/02 §5.3 Axis 3,
  files/04 §8.1 rule 7). Under ``ON_SITE`` the clinic notification is the
  primary channel and fires automatically, so a RED determined there puts its
  ``red_on_site`` entry beside the RED's own. Every register: the DSL requires
  ``notify_staff_immediate`` on every KIRMIZI rule's ON_SITE action
  (``protocols.dsl``), so there is no RED whose on-site action spares staff.
  A RED determined at ``UNKNOWN`` notifies no staff here; the patient's answer
  to the one location question does, through the API (``intake_api.red_notify``).
- **Bound per session, checked at binding.** The tenant, session and visit are
  the session's; a mis-shaped one raises here, when the session is composed,
  rather than at the RED.

The same notifier may be bound to both of the RED path's clinician routes —
Layer B's, at the determination, and the preemption path's — because the
entry id is derived from the RED's content-addressed ``work_id``: the second
notification lands on the first entry. So does a third, the one that says the
device was not reached (INT-545, ``RedNotification.delivery``): the entry
records neither the delivery nor ``patient_facing`` nor ``silent_generic``, so
that statement is carried by the notification and counted on
``red_watch_failures_total{kind="unreached"}``, not stored on the entry.

:class:`ClinicItemNotifier` (INT-547) is the production
:class:`~intake_voice_runtime.clinical_agent.clinic_items.ClinicItemRoute`:
the same inbox, for the CD-08 clinician-only items, which are not REDs.
It puts one :meth:`~intake_platform.safety_inbox.InboxEntry.for_clinic_item`
entry, keyed by the item's own id so a second raise lands on the first, and
then appends one row to the audit chain naming that entry (invariant 4: the
item shares a clinical fact with the clinic). INT-475's order: the clinic
first and the paperwork after, so a row that cannot be appended is counted
(``clinic_inbox_item_unaudited_total``) and never holds the item back. A put
that fails raises, writes no row, and the session's watch raises the item
again on its next Work.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from clinical_schemas.triage import RedLocation
from intake_platform.audit import AuditChain
from intake_platform.safety_inbox import EntryKind, InboxEntry, SafetyInboxOutbox
from intake_platform.safety_inbox.metrics import CLINIC_INBOX_ITEM_UNAUDITED_TOTAL
from intake_platform.safety_inbox.model import require_id, require_tenant_id

from intake_voice_runtime.clinical_agent.clinic_items import ClinicItem
from intake_voice_runtime.talker.red_path import RedNotification

__all__ = ["ClinicItemNotifier", "SafetyInboxNotifier"]

logger = logging.getLogger("intake_voice_runtime.safety_inbox")

#: Who appends a clinic item's audit row: this service, never a person.
CLINIC_ITEM_ACTOR: Final = "svc:voice-runtime"
#: The audit action for a CD-08 item put in the clinic inbox.
CLINIC_ITEM_ACTION: Final = "voice.clinic_item.raised"
#: The consent scope an intake session runs under (INT-475's ``scope:core``).
CLINIC_ITEM_SCOPE: Final = "scope:core"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class SafetyInboxNotifier:
    outbox: SafetyInboxOutbox
    tenant_id: str
    session_id: str
    #: INT-197: a visit is a session row, so this is usually the session's id;
    #: it is separate because files/02 §2b's transitions are keyed by visit.
    visit_id: str
    wall_clock: Callable[[], datetime] = field(default=_utc_now)

    def __post_init__(self) -> None:
        require_tenant_id(self.tenant_id)
        require_id(self.session_id)
        require_id(self.visit_id)

    def notify(self, notification: RedNotification) -> None:
        at = self.wall_clock()
        self.outbox.put(
            InboxEntry.for_red(
                tenant_id=self.tenant_id,
                session_id=self.session_id,
                visit_id=self.visit_id,
                work_id=notification.work_id,
                rule_ids=notification.rule_ids,
                at=at,
                # INT-407: the register rides on the one server-side record of
                # the RED, so a later files/02 §2b re-show is told the same way
                register=notification.register,
            )
        )
        if notification.location is RedLocation.ON_SITE:
            # INT-475: the staff notification, in the same action as the RED
            self.outbox.put(
                InboxEntry.for_on_site(
                    tenant_id=self.tenant_id,
                    session_id=self.session_id,
                    visit_id=self.visit_id,
                    work_id=notification.work_id,
                    rule_ids=notification.rule_ids,
                    at=at,
                )
            )


@dataclass(frozen=True)
class ClinicItemNotifier:
    """The clinic route for a CD-08 item: one inbox entry and one audit row."""

    outbox: SafetyInboxOutbox
    audit: AuditChain
    tenant_id: str
    session_id: str
    visit_id: str
    wall_clock: Callable[[], datetime] = field(default=_utc_now)

    def __post_init__(self) -> None:
        require_tenant_id(self.tenant_id)
        require_id(self.session_id)
        require_id(self.visit_id)

    def raise_item(self, item: ClinicItem) -> None:
        if item.session_id != self.session_id:
            raise ValueError("an item of another session reached this session's route")
        entry = InboxEntry.for_clinic_item(
            tenant_id=self.tenant_id,
            session_id=self.session_id,
            visit_id=self.visit_id,
            kind=EntryKind(item.kind.value),
            item_ref=item.item_id,
            rule_ids=item.rule_ids,
            at=self.wall_clock(),
        )
        self.outbox.put(entry)
        try:
            self.audit.append(
                actor=CLINIC_ITEM_ACTOR,
                action=CLINIC_ITEM_ACTION,
                resource_ref=f"safety_inbox:{self.tenant_id}:{entry.entry_id}",
                consent_scope_ref=CLINIC_ITEM_SCOPE,
            )
        except Exception as err:  # counted; the item is already in the inbox
            CLINIC_INBOX_ITEM_UNAUDITED_TOTAL.labels(kind=item.kind.value).inc()
            logger.error(
                "clinic item unaudited",
                extra={
                    "session_id": self.session_id,
                    "entry_id": entry.entry_id,
                    "error": type(err).__name__,
                },
            )
