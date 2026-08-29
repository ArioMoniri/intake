"""INT-141 — content-free reminders, quiet hours, opt-out, transactional-only.

files/10 §9 row "Notifications / reminders"; sec_row ``notifications``;
CLAUDE.md invariants 6 (no PHI in logs) and 18 (reminders are
transactional-only unless an İYS consent record exists).

Read the module docstrings in this order — each states the argument its part
of the design rests on:

- ``catalogue`` — why every body is a constant.
- ``contentfree`` — how "carries nothing about the patient" is checked, and
  why the naive version of that check is useless.
- ``preferences`` — why no quiet-hours window is shipped.
- ``iys`` — the four locks on the marketing path, and the record shape that
  is deliberately not invented.
- ``ports`` — why there is no fake sender.
- ``service`` — the order of refusal.
"""

from __future__ import annotations

from intake_platform.notifications.catalogue import (
    CORPUS_VOCABULARY,
    TEMPLATES,
    Channel,
    DeepLinkRoute,
    Locale,
    MessageClass,
    ReminderKind,
    RenderedMessage,
    Template,
    render,
    template_for,
)
from intake_platform.notifications.contentfree import (
    ContentLeak,
    assert_content_free,
    leaked_terms,
    outside_vocabulary,
)
from intake_platform.notifications.folding import fold, tokens
from intake_platform.notifications.iys import (
    COMMERCIAL_MESSAGING_FLAG,
    CommercialRequest,
    IysConsentRecord,
    IysRegistry,
    IysRegistryUnconfigured,
    UnconfiguredIysRegistry,
    seal_commercial,
)
from intake_platform.notifications.metrics import (
    NOTIFICATION_DISPATCH_TOTAL,
    NOTIFICATION_PREFERENCE_CHANGED_TOTAL,
)
from intake_platform.notifications.ports import (
    DeliveryReceipt,
    NotificationTransport,
    RecordedTransport,
    SealedMessage,
    TransportUnconfigured,
    UnconfiguredTransport,
    seal_transactional,
)
from intake_platform.notifications.preferences import (
    MINUTES_PER_DAY,
    SCHEDULING_OFFSET,
    NotificationPreferences,
    QuietVerdict,
    QuietWindow,
    local_minute_of_day,
    quiet_verdict,
)
from intake_platform.notifications.service import (
    DispatchOutcome,
    DispatchStatus,
    ReminderDispatcher,
)

__all__ = [
    "COMMERCIAL_MESSAGING_FLAG",
    "CORPUS_VOCABULARY",
    "MINUTES_PER_DAY",
    "NOTIFICATION_DISPATCH_TOTAL",
    "NOTIFICATION_PREFERENCE_CHANGED_TOTAL",
    "SCHEDULING_OFFSET",
    "TEMPLATES",
    "Channel",
    "CommercialRequest",
    "ContentLeak",
    "DeepLinkRoute",
    "DeliveryReceipt",
    "DispatchOutcome",
    "DispatchStatus",
    "IysConsentRecord",
    "IysRegistry",
    "IysRegistryUnconfigured",
    "Locale",
    "MessageClass",
    "NotificationPreferences",
    "NotificationTransport",
    "QuietVerdict",
    "QuietWindow",
    "RecordedTransport",
    "ReminderDispatcher",
    "ReminderKind",
    "RenderedMessage",
    "SealedMessage",
    "Template",
    "TransportUnconfigured",
    "UnconfiguredIysRegistry",
    "UnconfiguredTransport",
    "assert_content_free",
    "fold",
    "leaked_terms",
    "local_minute_of_day",
    "outside_vocabulary",
    "quiet_verdict",
    "render",
    "seal_commercial",
    "seal_transactional",
    "template_for",
    "tokens",
]
