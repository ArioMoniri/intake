"""Receipts, the push ledger, and the two decisions this module exists to make.

**Decision 1 — the receipt is written before the send, not after.**

There is no third option. A receipt written *after* delivery cannot record a
push that left the building and never came back; a receipt written *before*
can claim an attempt that never left. This product takes the second failure,
for one reason: invariant 4 says every share of clinical data is audited, and
an unrecorded share is an unauditable disclosure — the failure the invariant
exists to prevent. An over-recorded attempt is a reconciliation task; an
under-recorded delivery is a KVKK-12 evidence hole that nobody can even
discover, because nothing points at it.

The cost is paid honestly rather than hidden. The write-ahead receipt says
``attempted`` and never ``delivered``; the outcome is a **second** state
transition and a second audit entry. A process that dies in between leaves an
open receipt and an ``in_flight`` ledger row, both of which are visible
(``connector_receipts_unresolved_total``, :meth:`ReceiptStore.open_count`) and
neither of which is resolved by guessing. This is the same shape INT-137 chose
when it refused to mark a data-subject request ``COMPLETED`` at the moment of
delivery: the record of what we know is separate from the claim that it
worked.

**Decision 2 — the idempotency key is ours, and the receiver is not trusted
to honour it.**

The key is derived from *what* is being sent and *where*: tenant, endpoint,
resource reference and the payload's own digest. So a retry of the same note
to the same destination is the same key (a retry), an edited note is a new key
(a genuine second share), and the same note to a second hospital is a new key
(each destination gets its own delivery). Consent is deliberately **not** in
the derivation: consent decides whether a share may happen at all, and
re-granting a withdrawn scope does not make an unchanged record a different
record.

The key travels on the wire so a receiver that implements idempotency can
deduplicate — but "we sent it twice and the hospital deduplicated" is not a
guarantee this system can make on the hospital's behalf. The authority is
local: this ledger. Once a key is ``delivered`` we do not send it again, ever,
whatever the receiver does. And when an outcome is *ambiguous* — a timeout, a
5xx, a connection dropped after the body was written — the ledger consults
what the destination's own DPA declares: an endpoint whose agreement states
that it honours the key is retryable, and an endpoint that has not declared it
is parked as ``needs_human``. Auto-retrying into a receiver that may not
deduplicate risks a duplicate clinical record in a hospital system, which is
worse than a push that visibly did not complete.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

__all__ = [
    "InMemoryPushLedger",
    "InMemoryReceiptStore",
    "PushLedger",
    "PushState",
    "Receipt",
    "ReceiptState",
    "ReceiptStore",
    "ReplayRefused",
    "idempotency_key",
    "new_receipt_id",
]


class ReceiptState(StrEnum):
    """What the receipt claims. ``ATTEMPTED`` is the only open state."""

    ATTEMPTED = "attempted"
    DELIVERED = "delivered"
    #: The receiver answered and did not accept it. Terminal: the same bytes
    #: will be refused again.
    REJECTED = "rejected"
    #: Nothing left this process (consent, credentials, egress policy).
    FAILED = "failed"
    #: Bytes may or may not have arrived. The honest state, and the one that
    #: decides whether a retry is safe.
    UNRESOLVED = "unresolved"
    #: A consent scope did not stand. Recorded, because a refusal to share is
    #: itself evidence that the guard ran (invariant 4).
    REFUSED = "refused"


class PushState(StrEnum):
    """What the ledger will allow next for one idempotency key."""

    IN_FLIGHT = "in_flight"
    DELIVERED = "delivered"
    REJECTED = "rejected"
    FAILED_RETRYABLE = "failed_retryable"
    NEEDS_HUMAN = "needs_human"


class ReplayRefused(RuntimeError):
    """A second send of the same key is not safe to make automatically."""


@dataclass(frozen=True)
class Receipt:
    """The evidence that one share was attempted, and what came of it.

    Every field is an id, a digest, a count or an enumeration. There is no
    key a body, a header, a URL or a credential could occupy even by accident,
    which is why the default ``repr`` is safe to keep — a receipt that cannot
    be printed is a receipt nobody reads.
    """

    receipt_id: str
    attempted_at: datetime
    tenant_id: str
    endpoint_id: str
    patient_ref: str
    resource_ref: str
    consent_scope: str
    idempotency_key: str
    payload_sha256: str
    byte_count: int
    state: ReceiptState
    #: An id-shaped outcome code (``http_201``, ``egress_denied``,
    #: ``credential_missing``, ``timeout``), never a message from a receiver.
    outcome_code: str | None = None
    #: The receiver's own reference, from a response header, when it gave one.
    receiver_ref: str | None = None
    settled_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.state is ReceiptState.ATTEMPTED


class ReceiptStore(Protocol):
    """Where receipts live. Open-then-settle, never overwrite-in-place."""

    def open(self, receipt: Receipt) -> None: ...

    def settle(
        self,
        receipt_id: str,
        *,
        state: ReceiptState,
        outcome_code: str,
        receiver_ref: str | None,
        settled_at: datetime,
    ) -> Receipt: ...

    def get(self, receipt_id: str) -> Receipt | None: ...

    def all(self) -> Sequence[Receipt]: ...

    def open_count(self) -> int: ...


class InMemoryReceiptStore:
    """The unit-lane store. A SQLAlchemy implementation maps ``open`` to an
    INSERT and ``settle`` to the one UPDATE this table permits — the attempt
    row is never rewritten, only completed."""

    def __init__(self) -> None:
        self._receipts: dict[str, Receipt] = {}

    def open(self, receipt: Receipt) -> None:
        if receipt.receipt_id in self._receipts:
            raise ValueError("receipt id already open")
        self._receipts[receipt.receipt_id] = receipt

    def settle(
        self,
        receipt_id: str,
        *,
        state: ReceiptState,
        outcome_code: str,
        receiver_ref: str | None,
        settled_at: datetime,
    ) -> Receipt:
        current = self._receipts[receipt_id]
        settled = replace(
            current,
            state=state,
            outcome_code=outcome_code,
            receiver_ref=receiver_ref,
            settled_at=settled_at,
        )
        self._receipts[receipt_id] = settled
        return settled

    def get(self, receipt_id: str) -> Receipt | None:
        return self._receipts.get(receipt_id)

    def all(self) -> Sequence[Receipt]:
        return tuple(self._receipts.values())

    def open_count(self) -> int:
        return sum(1 for receipt in self._receipts.values() if receipt.is_open)


class PushLedger(Protocol):
    """The local authority on what has already been sent."""

    def state(self, key: str) -> PushState | None: ...

    def receipt_id(self, key: str) -> str | None: ...

    def claim(self, key: str, receipt_id: str) -> None: ...

    def settle(self, key: str, state: PushState) -> None: ...


class InMemoryPushLedger:
    """The unit-lane ledger. Production maps ``claim`` to an INSERT ... ON
    CONFLICT DO NOTHING on the key, which is what makes two workers racing the
    same push resolve to one attempt rather than two."""

    def __init__(self) -> None:
        self._states: dict[str, PushState] = {}
        self._receipts: dict[str, str] = {}

    def state(self, key: str) -> PushState | None:
        return self._states.get(key)

    def receipt_id(self, key: str) -> str | None:
        return self._receipts.get(key)

    def claim(self, key: str, receipt_id: str) -> None:
        self._states[key] = PushState.IN_FLIGHT
        self._receipts[key] = receipt_id

    def settle(self, key: str, state: PushState) -> None:
        self._states[key] = state


def idempotency_key(
    *, tenant_id: str, endpoint_id: str, resource_ref: str, payload_sha256: str
) -> str:
    """The key, derived rather than generated.

    A generated key would make every retry a new share. Deriving it from the
    tuple that identifies the share means a retry is recognisably the same
    request to us *and* to a receiver that honours the header. ``\\x1f`` (unit
    separator) joins the parts so no concatenation of two fields can collide
    with another pair.
    """
    material = "\x1f".join((tenant_id, endpoint_id, resource_ref, payload_sha256))
    return "ik-" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def new_receipt_id() -> str:
    return f"rcpt-{uuid.uuid4().hex}"


def utc_now() -> datetime:
    return datetime.now(UTC)
