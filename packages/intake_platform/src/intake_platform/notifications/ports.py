"""INT-141 — the delivery port, and the two adapters that exist.

**No push or SMS vendor is contracted.** The gap is recorded as an
awaiting-human item on INT-131 ("SMS vendor contract"; owner — vendor
contracts are human territory) and it has no HUMAN_BLOCKERS row of its own;
docs/evidence/INT-141.md carries the ask and the named human.

So there is no live adapter and, per CLAUDE.md, no fake one either: a stub
that returned a receipt would put "delivered" into a metric nobody earned and
would make the missing contract invisible. :class:`UnconfiguredTransport` is
what the app wires, and it raises. :class:`RecordedTransport` replays
committed responses for the test lane — the same recorded-fixture posture the
TTS gateway takes — and refuses to invent one that was never recorded.

What crosses this boundary is a :class:`SealedMessage`: a message class, a
channel, a tokenized recipient handle and a rendered payload built entirely
from constants. Nothing else — in particular no visit id, no branch, no slot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, final

from intake_platform.notifications.catalogue import (
    Channel,
    Locale,
    MessageClass,
    ReminderKind,
    RenderedMessage,
    render,
)

__all__ = [
    "DeliveryReceipt",
    "NotificationTransport",
    "RecordedTransport",
    "SealedMessage",
    "TransportUnconfigured",
    "UnconfiguredTransport",
    "seal_transactional",
]


class TransportUnconfigured(RuntimeError):
    """No delivery vendor is contracted for this channel."""


@final
@dataclass(frozen=True, slots=True)
class SealedMessage:
    """The only thing a transport accepts."""

    message_class: MessageClass
    channel: Channel
    recipient_ref: str
    rendered: RenderedMessage

    def as_wire(self) -> dict[str, str]:
        """Exactly the fields that leave the process. Enumerated by hand
        rather than reflected, so a field added to a dataclass upstream
        cannot silently join the payload."""
        return {
            "message_class": self.message_class.value,
            "channel": self.channel.value,
            "recipient_ref": self.recipient_ref,
            "template_key": self.rendered.template_key,
            "locale": self.rendered.locale.value,
            "route": self.rendered.route.value,
            "title": self.rendered.title,
            "body": self.rendered.body,
        }


@final
@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    """What a vendor said. ``delivery_id`` is the vendor's handle, kept so a
    delivery can be reconciled without storing anything about the content."""

    delivery_id: str
    accepted: bool
    vendor_status: str


class NotificationTransport(Protocol):
    channel: Channel

    def deliver(self, message: SealedMessage) -> DeliveryReceipt: ...


@final
class UnconfiguredTransport:
    """The wired adapter: it refuses, loudly, for the honest reason."""

    def __init__(self, channel: Channel) -> None:
        self.channel = channel

    def deliver(self, message: SealedMessage) -> DeliveryReceipt:
        raise TransportUnconfigured(
            f"no {self.channel.value} vendor is contracted; the live delivery path is "
            f"blocked pending the SMS/push vendor contract (docs/evidence/INT-141.md)"
        )


@final
class RecordedTransport:
    """Replays a committed response per (channel, template, locale).

    The recorded files are the port's own receipt shape, not any vendor's
    wire format — there is no vendor yet to record. When one is contracted,
    its real responses replace these files and the adapter is unchanged.
    """

    def __init__(self, channel: Channel, directory: Path) -> None:
        if not directory.is_dir():
            raise FileNotFoundError(
                f"no recorded notification responses at {directory}; a recorded adapter "
                f"never invents one"
            )
        self.channel = channel
        self._directory = directory

    def deliver(self, message: SealedMessage) -> DeliveryReceipt:
        path = self._directory / (
            f"{message.channel.value}.{message.rendered.template_key}."
            f"{message.rendered.locale.value}.json"
        )
        if not path.is_file():
            raise FileNotFoundError(
                f"no recorded response for {path.name}; record one rather than "
                f"letting the test lane assume a delivery"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
        return DeliveryReceipt(
            delivery_id=str(payload["delivery_id"]),
            accepted=bool(payload["accepted"]),
            vendor_status=str(payload["vendor_status"]),
        )


def seal_transactional(
    kind: ReminderKind,
    locale: Locale,
    *,
    channel: Channel,
    recipient_ref: str,
) -> SealedMessage:
    """The transactional seal. Its argument list is the gate: a
    ``ReminderKind`` and a ``Locale`` are the only inputs, so there is no
    parameter through which patient data could reach the payload."""
    return SealedMessage(
        message_class=MessageClass.TRANSACTIONAL,
        channel=channel,
        recipient_ref=recipient_ref,
        rendered=render(kind, locale),
    )
