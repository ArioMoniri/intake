"""INT-150 — the volatile half of a Doctor Link: OTP state and token routing.

Two jobs, both in Redis, both deliberately NOT in the database:

**1. The OTP.** files/10 §2 gives the Doctor Link an OTP, and this service
does not write a second one. It drives the very same
:class:`intake_api.auth_store.AuthStore` the phone tier drives (6 digits,
5-minute TTL, 5 attempts, the request budgets and the resend cooldown),
constructed with its own ``dlink`` key prefix so the two tiers cannot spend
each other's budgets. The identifier the budgets are counted against is the
LINK, not the patient: a brute-forcer working on one link must not be able to
lock out another link to the same person, and two links must not share a
five-attempt budget.

The gate is inherited whole, limitation included. ``otp_request_gate`` is
read-decide-write (INT-263 records why: the atomic form needs a Lua script
``fakeredis`` cannot execute), so two workers racing on one link can both be
admitted one request over budget. That is stated rather than narrowed here,
because narrowing it in a copy would leave two gates with two behaviours. The
VIEW limit — the control that actually bounds disclosure — is atomic and lives
in ``doctor_link_store.spend_one_view``.

**2. Token routing.** A redemption arrives with no principal and therefore no
tenant, and every clinical read runs inside a tenant-scoped RLS session. The
fingerprint→(tenant, link) index that makes that session openable lives here,
in Redis, with the link's own lifetime. It is a HINT and never the authority:
the row's ``token_fingerprint`` is re-checked in constant time after the row
is loaded, so an attacker who could write this index still cannot point a
token at a grant that does not carry it. Losing the index makes every live
link stop working — fail closed, and the patient can issue another.

**Delivery.** files/10 §2 says the code goes "to the phone/e-mail the patient
chose". No such destination is recorded anywhere in this repo (invariant 14
keeps contact identifiers out of every app table, and no file records a
Doctor-Link delivery preference at all), and no messaging vendor is contracted
(INT-131, awaiting-human). So the adapter seam exists, the abuse gate in front
of it is real, and :class:`FailClosedDoctorLinkDelivery` refuses — the
mechanism is built, the gate is wired, it fails closed, and the content stays
empty (CLAUDE.md). The channel that DOES exist is the patient's own
authenticated session: :meth:`mint_for_patient` hands the code to the patient,
who passes it to the clinician in the room. Nothing fake is wired anywhere.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

import redis

from intake_api.auth_store import (
    OTP_CODE_DIGITS,
    OTP_TTL_S,
    RESEND_COOLDOWN_S,
    AuthStore,
    code_digest,
)

__all__ = [
    "DOCTOR_LINK_KEY_PREFIX",
    "DoctorLinkDelivery",
    "DoctorLinkRef",
    "DoctorLinkService",
    "DoctorLinkWiring",
    "RequestChannel",
    "FailClosedDoctorLinkDelivery",
    "RecipientChannelUnconfiguredError",
]

#: Its own Redis namespace, so the Doctor Link OTP budgets and the phone-login
#: OTP budgets can never be spent against each other.
DOCTOR_LINK_KEY_PREFIX = "dlink"

_INDEX_KEY = "dlink:idx:"

#: Which request path asked for a code. The two never share a budget.
RequestChannel = Literal["patient", "delivery"]


class RecipientChannelUnconfiguredError(RuntimeError):
    """No delivery destination and no vendor exist for a Doctor Link OTP."""


class DoctorLinkDelivery(Protocol):
    """The seam a real channel implements. It receives the link REFERENCE and
    the code — never the note, never the patient, never a name."""

    def send(self, *, link_ref: str, code: str) -> str: ...


class FailClosedDoctorLinkDelivery:
    """The only adapter wired today: it refuses.

    An adapter that logged the code, or returned a receipt for a message
    nobody sent, would be a mock on the PHI path pretending to be a control.
    """

    def send(self, *, link_ref: str, code: str) -> str:
        del link_ref, code  # never logged, never stored, never claimed sent
        raise RecipientChannelUnconfiguredError(
            "no Doctor Link OTP delivery channel is configured: this repo records no "
            "patient-chosen destination and no messaging vendor is contracted"
        )


@dataclass(frozen=True)
class DoctorLinkRef:
    """What the Redis index resolves a token fingerprint to."""

    link_id: uuid.UUID
    tenant_id: uuid.UUID


@dataclass
class DoctorLinkWiring:
    """Injectable for tests; the env path builds it beside the OTP tier."""

    redis_client: redis.Redis
    delivery: DoctorLinkDelivery
    dev_otp_peek: bool = False
    now_fn: Callable[[], float] | None = None


class DoctorLinkService:
    """Redis-side orchestration. Store calls hop off the event loop via
    ``asyncio.to_thread`` (sync client, the INT-012/INT-131 precedent)."""

    def __init__(self, wiring: DoctorLinkWiring) -> None:
        self._wiring = wiring
        self._r = wiring.redis_client
        self._store = AuthStore(
            wiring.redis_client, wiring.now_fn, key_prefix=DOCTOR_LINK_KEY_PREFIX
        )

    def now(self) -> float:
        return self._wiring.now_fn() if self._wiring.now_fn is not None else time.time()

    def utcnow(self) -> datetime:
        """The clock every Doctor Link deadline is read against.

        One clock for the OTP windows AND for expiry, the view budget and the
        watermark instant, so a test can advance time instead of sleeping
        (docs/TDD.md rule 6) and so the two halves of one decision — "the code
        is still valid" and "the link is still live" — can never disagree.
        """
        return datetime.fromtimestamp(self.now(), UTC)

    # --- token routing index ------------------------------------------------------

    @staticmethod
    def _pseudonym(link_id: uuid.UUID) -> str:
        """What the shared OTP gate counts against: the LINK, never a person."""
        return f"link:{link_id}"

    async def register(
        self, *, fingerprint: str, link_id: uuid.UUID, tenant_id: uuid.UUID, ttl_s: int
    ) -> None:
        payload = json.dumps({"link_id": str(link_id), "tenant_id": str(tenant_id)})
        await asyncio.to_thread(self._r.set, _INDEX_KEY + fingerprint, payload, ex=max(ttl_s, 1))

    async def resolve(self, fingerprint: str) -> DoctorLinkRef | None:
        raw = await asyncio.to_thread(self._r.get, _INDEX_KEY + fingerprint)
        if raw is None:
            return None
        record = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else str(raw))
        return DoctorLinkRef(
            link_id=uuid.UUID(record["link_id"]), tenant_id=uuid.UUID(record["tenant_id"])
        )

    async def forget(self, fingerprint: str) -> None:
        """Revocation drops the routing hint as well as setting the column, so
        a revoked link stops resolving instead of merely being refused."""
        await asyncio.to_thread(self._r.delete, _INDEX_KEY + fingerprint)

    # --- the OTP, on the shared gate ------------------------------------------------

    @staticmethod
    def _request_id(link_id: uuid.UUID, channel: RequestChannel) -> str:
        """What the REQUEST budgets are counted against.

        Per link AND per channel, deliberately. The five verify attempts are
        shared (there is one code per link, and that is the thing being
        guessed), but the request budgets are not: if they were, anyone holding
        the token could spend the patient's own minting budget and lock them
        out of the link they issued — a denial of service built out of a rate
        limit.
        """
        return f"link:{link_id}:{channel}"

    async def gate(self, *, link_id: uuid.UUID, ip: str, channel: RequestChannel) -> float | None:
        """One request against the INT-131 budgets. Returns retry-after
        seconds on refusal, ``None`` on admission.

        The gate takes three dimensions (identifier, IP, device). A Doctor Link
        caller presents no attested device, so the device dimension is given the
        same per-link-per-channel identifier rather than a fabricated device id:
        the two per-identifier budgets then coincide, which is the intended
        bound, and the gate itself is reused unchanged.
        """
        request_id = self._request_id(link_id, channel)
        result: float | None = await asyncio.to_thread(
            self._store.otp_request_gate, request_id, ip, request_id
        )
        return result

    @staticmethod
    def generate_code() -> str:
        """A code, not yet stored. Split from :meth:`remember` so a caller can
        put it on a channel FIRST and only then invalidate whatever code the
        link already had — a delivery that fails must not silently kill a code
        the patient already handed to the clinician in the room."""
        return f"{secrets.randbelow(10**OTP_CODE_DIGITS):0{OTP_CODE_DIGITS}d}"

    async def remember(self, link_id: uuid.UUID, code: str) -> None:
        """Store the keyed digest of the current code for this link. The
        plaintext is never written anywhere by this method."""
        pseudonym = self._pseudonym(link_id)
        await asyncio.to_thread(
            self._store.store_code,
            pseudonym,
            code_digest(pseudonym, code),
            code if self._wiring.dev_otp_peek else None,
        )

    async def mint(self, link_id: uuid.UUID) -> str:
        """Generate, store and return one code — the patient-session path."""
        code = self.generate_code()
        await self.remember(link_id, code)
        return code

    def deliver(self, *, link_id: uuid.UUID, code: str) -> str:
        """Hand the code to the patient's chosen channel. Raises today."""
        return self._wiring.delivery.send(link_ref=f"doctor_link:{link_id}", code=code)

    async def check(self, *, link_id: uuid.UUID, code: str) -> bool:
        pseudonym = self._pseudonym(link_id)
        verdict = await asyncio.to_thread(
            self._store.check_code, pseudonym, code_digest(pseudonym, code)
        )
        return verdict == "ok"

    async def peek(self, link_id: uuid.UUID) -> str | None:
        """Dev tier ONLY (INTAKE_DEV_OTP_PEEK=explicit-yes)."""
        if not self._wiring.dev_otp_peek:
            return None
        return await asyncio.to_thread(self._store.peek_code, self._pseudonym(link_id))

    @property
    def code_ttl_s(self) -> int:
        return OTP_TTL_S

    @property
    def resend_after_s(self) -> int:
        return RESEND_COOLDOWN_S
