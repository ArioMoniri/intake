"""INT-141 — the İYS gate: why a marketing message cannot be sent.

CLAUDE.md invariant 18: *"reminders are transactional-only unless an İYS
consent record exists."* files/06 §1 row 6563-İYS: *"Appointment/service
messages are non-commercial; **any** marketing message requires İYS-registered
consent; sender records kept."*

The requirement is not "check a flag before sending". It is that the code be
**unable** to send a marketing-class message without a record. Four
independent locks, each of which alone stops it:

1. **The catalogue has no commercial template.** Every entry in
   ``TEMPLATES`` is transactional, and the helper that builds one takes a
   ``ReminderKind`` — an enum with no commercial member. There is nothing to
   send.
2. **The record type is abstract and has no concrete subclass anywhere.**
   :class:`IysConsentRecord` declares abstract members and is never
   subclassed outside the test tree, so ``IysConsentRecord()`` raises and no
   value of that type exists to pass. :func:`seal_commercial` therefore
   cannot be *called*, not merely cannot succeed.
3. **The only registry refuses.** :class:`UnconfiguredIysRegistry` raises on
   every lookup, so nothing produces a record at runtime either.
4. **``commercial_messaging`` is a pre-declared safety flag.** It sits in
   ``SAFETY_FLAG_DEFAULTS`` at False, where a call-site default cannot open
   it; only the gated-capability authority of files/10 §0b can.

**The record's shape is not invented, and this is the ask.** files/ names the
obligation and no file names a field: there is no İYS integration contract,
no ``iys_id``, no consent-date format, no *hizmet sağlayıcı* code, nothing.
Writing plausible fields here would produce a schema that reads as
authoritative to every later reader and matches no real registry. So the type
declares what any record must be able to answer — a reference into the
registry, and when it was recorded — and stops. A real adapter subclasses it
with the fields İYS actually returns, and that subclass is exactly the change
that must be reviewed, which is why its absence is a test rather than a
coincidence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, final

from intake_platform.flags import FlagProvider, InMemoryProvider
from intake_platform.notifications.catalogue import (
    Channel,
    Locale,
    MessageClass,
    Template,
)
from intake_platform.notifications.ports import SealedMessage

__all__ = [
    "COMMERCIAL_MESSAGING_FLAG",
    "CommercialRequest",
    "IysConsentRecord",
    "IysRegistry",
    "IysRegistryUnconfigured",
    "UnconfiguredIysRegistry",
    "seal_commercial",
]

#: The safety flag, pre-declared False in ``intake_platform.flags``.
COMMERCIAL_MESSAGING_FLAG = "commercial_messaging"


class IysRegistryUnconfigured(RuntimeError):
    """No İYS integration exists. Raised rather than answered falsely: a
    lookup that returned "no record" would be indistinguishable from a real
    negative, and only one of those two is honest today."""


class IysConsentRecord(ABC):
    """Opaque proof that İYS holds a commercial-message consent for a
    recipient. Abstract on purpose — see the module docstring; the shape is
    awaiting a human who has read the İYS integration specification."""

    @abstractmethod
    def registry_reference(self) -> str:
        """The registry's own identifier for the consent record — the thing
        a *sender record* must be able to cite (6563 keeps sender records)."""

    @abstractmethod
    def recorded_at(self) -> datetime:
        """When the registry recorded the consent."""


class IysRegistry(Protocol):
    """The seam a real İYS adapter implements."""

    def lookup(self, recipient_ref: str) -> IysConsentRecord: ...


@final
class UnconfiguredIysRegistry:
    """The only implementation in the tree, and it always refuses."""

    def lookup(self, recipient_ref: str) -> IysConsentRecord:
        raise IysRegistryUnconfigured(
            "no İYS registry is configured; a marketing-class message cannot be "
            "sent without a recorded consent (CLAUDE.md invariant 18)"
        )


@final
@dataclass(frozen=True, slots=True)
class CommercialRequest:
    """A marketing-class send, before the gate. Ids only: the campaign is a
    reference, never copy, and the recipient is the tokenized handle."""

    recipient_ref: str
    campaign_ref: str


def seal_commercial(
    request: CommercialRequest,
    record: IysConsentRecord,
    template: Template,
    locale: Locale,
    *,
    channel: Channel,
    flags: FlagProvider | None = None,
) -> SealedMessage:
    """Turn a marketing request into something a transport will accept.

    Reachable only by a caller holding an :class:`IysConsentRecord`, which no
    production code can construct, and only while ``commercial_messaging`` is
    open, which no production configuration does. Both conditions are
    checked; neither is the only lock.
    """
    provider = flags if flags is not None else InMemoryProvider()
    if not provider.get_bool(COMMERCIAL_MESSAGING_FLAG, False):
        raise PermissionError(
            "commercial_messaging is shut; marketing-class messages are not sent "
            "(CLAUDE.md invariant 18 — reminders are transactional-only)"
        )
    if template.message_class is not MessageClass.COMMERCIAL:
        raise ValueError("seal_commercial is for commercial templates; use seal_transactional")
    # The record is consumed rather than merely present: its reference is what
    # a 6563 sender record has to cite, so a record that cannot answer is not
    # a record.
    if not record.registry_reference().strip():
        raise ValueError("an İYS record must carry a registry reference")
    return SealedMessage(
        message_class=MessageClass.COMMERCIAL,
        channel=channel,
        recipient_ref=request.recipient_ref,
        rendered=template.render(locale),
    )
