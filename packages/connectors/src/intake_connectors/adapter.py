"""The adapter seam, and the payload type that refuses to print itself.

An adapter turns a rendered clinical payload into one outbound call and reads
one thing back: the receiver's own reference for what it stored. It is
deliberately given no way to read a response **body**. A hospital's error body
is the single most likely place for a patient's name to arrive back at us
(FHIR ``OperationOutcome`` diagnostics routinely echo the submitted resource),
and a body the framework never reads is a body that cannot be logged, stored
in a receipt or attached to an exception (invariant 6). What survives is the
status code and, when the receiver supplies one, an id-shaped ``Location``.

Concrete adapters land with their own issues — FHIR/SMART with INT-161, the
HBYS/HL7v2 kit with INT-162. This module is the contract they implement and
the reason the contract is this narrow.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from intake_connectors.destinations import ConnectorDestination

__all__ = [
    "AdapterNotRegistered",
    "ClinicalPayload",
    "ConnectorAdapter",
    "OutboundCall",
]


class AdapterNotRegistered(Exception):
    """A registered destination names an adapter this process does not have."""


@dataclass(frozen=True, repr=False)
class ClinicalPayload:
    """The rendered body of one share, opaque to the framework.

    ``repr``/``str`` give the size and the digest and never the bytes: this
    object is the PHI, and the default dataclass representation would put it
    into every traceback that touches a send.
    """

    body: bytes
    media_type: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def byte_count(self) -> int:
        return len(self.body)

    def __repr__(self) -> str:
        return f"ClinicalPayload({self.byte_count} bytes, sha256={self.sha256[:12]}…)"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, repr=False)
class OutboundCall:
    """One request an adapter wants made. Same redaction rule as the payload."""

    method: Literal["POST", "PUT"]
    path: str
    media_type: str
    body: bytes

    def __repr__(self) -> str:
        return f"OutboundCall({self.method} {self.path}, {len(self.body)} bytes)"

    def __str__(self) -> str:
        return self.__repr__()


class ConnectorAdapter(Protocol):
    """What a hospital-system adapter must provide, and all it may see."""

    adapter_id: str

    def build(
        self, destination: ConnectorDestination, payload: ClinicalPayload
    ) -> OutboundCall: ...

    def receiver_ref(self, status: int, headers: Mapping[str, str]) -> str | None:
        """The receiver's reference for what it stored, from headers only."""
        ...
