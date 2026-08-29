"""INT-141 — the reminder dispatcher.

One entry point, and its signature is most of the safety argument: it takes a
:class:`ReminderKind` (a closed enum of transactional kinds), a locale, a
tokenized recipient handle and the patient's preferences. There is no
argument for a body, a campaign, a visit or a branch, so there is nothing to
sanitise on the way through.

Order of refusal, strongest first:

1. **Opt-out.** 6563 puts service messages outside the *consent* requirement;
   it does not oblige us to keep messaging someone who asked us to stop. This
   dispatcher honours the refusal for every class it can send, as a product
   choice recorded in docs/evidence/INT-141.md. (The duties that genuinely
   cannot be opted out of — a KVKK m.12 breach notice to the data subject —
   are not reminders and do not route through here, so no bypass exists for
   anyone to widen.)
2. **An unset baseline quiet window refuses.** No file names an hour and none
   is invented; see ``preferences``.
3. **Quiet hours**, baseline ∪ patient, on the Türkiye clock.
4. **Content-freedom**, asserted on the rendered payload before any transport
   sees it.
5. **Transport.** Unconfigured is reported as a blocked outcome rather than
   raised, because "no vendor is contracted" is a state of the world the
   scheduler should record, not an exception it should crash on.

Logging is ids and enum values only: no body, no title, and not even the
recipient handle — a pseudonym in a log line is still an identifier
(invariant 6).
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import final

from intake_platform.notifications.catalogue import Locale, ReminderKind
from intake_platform.notifications.contentfree import assert_content_free
from intake_platform.notifications.metrics import NOTIFICATION_DISPATCH_TOTAL
from intake_platform.notifications.ports import (
    DeliveryReceipt,
    NotificationTransport,
    TransportUnconfigured,
    seal_transactional,
)
from intake_platform.notifications.preferences import (
    NotificationPreferences,
    QuietWindow,
    local_minute_of_day,
)

__all__ = ["DispatchOutcome", "DispatchStatus", "ReminderDispatcher"]

logger = logging.getLogger(__name__)


class DispatchStatus(enum.StrEnum):
    DELIVERED = "delivered"
    SUPPRESSED_OPT_OUT = "suppressed_opt_out"
    DEFERRED_QUIET_HOURS = "deferred_quiet_hours"
    REFUSED_QUIET_HOURS_UNSET = "refused_quiet_hours_unset"
    BLOCKED_TRANSPORT_UNCONFIGURED = "blocked_transport_unconfigured"


@final
@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    status: DispatchStatus
    template_key: str
    receipt: DeliveryReceipt | None = None


@final
class ReminderDispatcher:
    """Sends transactional reminders, or says honestly why it did not."""

    def __init__(
        self,
        transport: NotificationTransport,
        *,
        baseline_quiet: QuietWindow | None = None,
    ) -> None:
        self._transport = transport
        self._baseline_quiet = baseline_quiet

    def send(
        self,
        kind: ReminderKind,
        *,
        locale: Locale,
        recipient_ref: str,
        preferences: NotificationPreferences,
        at: datetime,
    ) -> DispatchOutcome:
        status, receipt = self._decide(kind, locale, recipient_ref, preferences, at)
        NOTIFICATION_DISPATCH_TOTAL.labels(
            channel=self._transport.channel.value,
            message_class="transactional",
            status=status.value,
        ).inc()
        logger.info(
            "notification_dispatch kind=%s status=%s channel=%s message_class=transactional",
            kind.value,
            status.value,
            self._transport.channel.value,
        )
        return DispatchOutcome(status=status, template_key=kind.value, receipt=receipt)

    def _decide(
        self,
        kind: ReminderKind,
        locale: Locale,
        recipient_ref: str,
        preferences: NotificationPreferences,
        at: datetime,
    ) -> tuple[DispatchStatus, DeliveryReceipt | None]:
        if preferences.opted_out:
            return DispatchStatus.SUPPRESSED_OPT_OUT, None
        if self._baseline_quiet is None:
            return DispatchStatus.REFUSED_QUIET_HOURS_UNSET, None
        minute = local_minute_of_day(at)
        if self._baseline_quiet.covers(minute) or (
            preferences.quiet is not None and preferences.quiet.covers(minute)
        ):
            return DispatchStatus.DEFERRED_QUIET_HOURS, None
        sealed = seal_transactional(
            kind, locale, channel=self._transport.channel, recipient_ref=recipient_ref
        )
        assert_content_free(sealed.rendered)
        try:
            receipt = self._transport.deliver(sealed)
        except TransportUnconfigured:
            return DispatchStatus.BLOCKED_TRANSPORT_UNCONFIGURED, None
        return DispatchStatus.DELIVERED, receipt
