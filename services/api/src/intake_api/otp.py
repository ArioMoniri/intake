"""OTP auth service (INT-131) — real account creation over the INT-030 schema.

The flow files/10 §2 specifies: attested OTP request (rate-limited) →
attested verify (session start) → DPoP-bound access + rotating refresh
tokens → the patient row keyed by the Tokenizer pseudonym of the phone
(invariant 14: the raw phone never reaches an app table, a log line or a
Redis key). New accounts join the consumer tenant (files/06 §1: consumer
app → INTAKE is controller) and receive NO consent rows — consent arrives
in context with INT-132/INT-038, so every clinical read stays behind the
consent gate from the first second (invariant 4).

Honest tiering:
- SMS delivery (INT-329): the seam is :class:`OtpDeliveryAdapter`, and it is
  async so a vendor call never holds the event loop. Dev wires
  :class:`DevLogDeliveryAdapter`, which records a delivery EVENT (ids only —
  never the code, never the phone) and claims nothing more; the code is
  reachable solely through the peek endpoint behind
  ``INTAKE_DEV_OTP_PEEK=explicit-yes``. Outside dev the only adapter is
  ``intake_api.otp_netgsm`` (INT-528; the owner's vendor decision, INT-358),
  wired only when its credentials are in OpenBao and the egress policy admits
  the vendor (the owner's patch), otherwise the tier stays 503. A failed delivery is a typed
  :class:`OtpDeliveryError` and a generic 503, never a claimed "sent".
- Attestation (INT-344): iOS registers an App Attest key once
  (``/attest/key``) and signs every OTP call with an assertion from it; the
  verifier is real when the Apple team id is configured and fails closed with
  a typed reason when it is not. Android fails closed until HB-A3
  (attestation.py, app_attest.py, play_integrity.py).

INT-578 (owner order, 28 Oct 2026): a code is useless anywhere but where it was
asked for. Each 202 carries a server-minted ``request_id``; the code is kept
only as an HMAC under the OpenBao pepper over (pseudonym, request id, code),
with the device binding beside it — the App Attest key the request proved, or
in dev the install id; never the install id a real-mode payload merely claims.
A verify must come from that device with that request id. The fifth miss
locks the number for a request window (``auth_store.OTP_LOCKOUT_S``): no code
is minted for it and no verify compared until it ends. Every verify outcome is
counted by a closed label (``otp_verify_total``); the caller still gets one
generic refusal.

INT-577 (the same order): what a request may cost. The device budget is keyed by
the key App Attest proved, never the install id a payload claims, and the
caller's address only as a keyed hash; the tenant hour budget and the global
hour and day caps (``intake_api.sms_spend``) sit beside the per-caller ones;
the resend wait doubles with each code a number has had in the window; and the
spend kill switch is read first, failing closed — reaching the day cap latches
it, and nothing is sent until an operator releases it. Every request and every
block is counted by a closed label (``sec_otp_requests_total``,
``sec_otp_abuse_blocks``).

INT-579 (the same order): the route says nothing about a number. A refusal that
is a fact about the number — its resend wait, its hourly budget, the INT-578
lockout, the synthetic host's test list — is WITHHELD: the caller gets the
202 an admission gets (a fresh request id and a wait read from its own device)
and nothing is minted or sent; the same Redis work and one audit row make it
take the same time. The vendor call runs after the response
(:meth:`OtpAuthService.settle` waits for it in tests and at shutdown), so a
send's latency, and a vendor's refusal of an unreachable number, are not on the
route either: the 202 carries no vendor job id, and a failed send is audited
and counted. What still differs is what is the same for every number: a
malformed one (422), the caller's own device or address budget (429), the
platform's caps and switch (429, 503). Verify takes an attempt and runs both
comparisons whether or not a code exists or the number is locked.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import partial
from typing import Final, Protocol

import redis
from fastapi import HTTPException, Request
from intake_platform.db.models import KvkkRole, Patient, Tenant
from intake_platform.tokenization import Tokenizer
from prometheus_client import Counter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.attestation import (
    AttestationPayload,
    AttestationReason,
    AttestationVerifier,
    AttestPurpose,
    FailClosedAttestationVerifier,
    KeyAttestationRegistrar,
    attestation_client_data,
    parse_attestation,
)
from intake_api.audit import AuditWriter
from intake_api.auth_store import (
    ACCESS_TTL_S,
    CHALLENGE_TTL_S,
    OTP_CODE_DIGITS,
    AccessRecord,
    AuthStore,
    Budget,
)
from intake_api.carrier_geo import CarrierGeoCheck
from intake_api.db import tenant_session
from intake_api.dev_fixture import DevAccount
from intake_api.device_sessions import DeviceSession, DeviceSessionStore
from intake_api.dpop import DpopError, verify_dpop_proof
from intake_api.errors import (
    attestation_invalid,
    attestation_required,
    attestation_unverified,
    challenge_invalid,
    dpop_invalid,
    not_found,
    otp_delivery_unavailable,
    otp_invalid,
    otp_limited,
    phone_invalid,
    refresh_reused,
    unauthorized,
)
from intake_api.otp_pepper import OtpPepper
from intake_api.sign_in_notice import (
    SEC_SIGN_IN_NOTICES_TOTAL,
    NoSignInNoticeChannel,
    NoticeOutcome,
    SignInNotice,
)
from intake_api.sms_recipients import ADMIT_ALL, RecipientGate
from intake_api.sms_spend import DAY_S, SmsBudget, SpendKillSwitch, SpendStateUnreadable

__all__ = [
    "ATTESTATION_HEADER",
    "BLOCK_DIMENSIONS",
    "CONSUMER_TENANT_ID",
    "DELIVERY_MAY_HAVE_SENT",
    "OTP_VERIFY_TOTAL",
    "REQUEST_OUTCOMES",
    "SEC_OTP_ABUSE_BLOCKS",
    "SEC_NEW_DEVICE_LOGINS",
    "SEC_OTP_REQUESTS_TOTAL",
    "NoSignInNoticeChannel",
    "SignInNotice",
    "VERIFY_OUTCOMES",
    "AuthWiring",
    "CurrentSession",
    "DeliveryReceipt",
    "DevLogDeliveryAdapter",
    "OtpAuthService",
    "OtpDeliveryAdapter",
    "OtpDeliveryError",
    "OtpDeliveryFailure",
    "TokenBundle",
    "ensure_consumer_tenant",
    "normalise_tr_phone",
]

logger = logging.getLogger("intake_api.otp")

ATTESTATION_HEADER = "X-Intake-Attestation"

# Consumer-app tenant (files/06 §1: INTAKE is controller for the consumer
# app). Fixed UUIDv5 key → idempotent bootstrap, same shape as dev_fixture.
CONSUMER_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_URL, "https://intake.app/tenants/consumer")

#: Every value ``otp_verify_total``'s ``outcome`` label can take (INT-578):
#: the store's verdicts, and ``locked`` for a verify refused by the lockout
#: before anything was compared.
VERIFY_OUTCOMES = frozenset({"ok", "invalid", "unbound", "exhausted", "missing", "locked"})

OTP_VERIFY_TOTAL = Counter(
    "otp_verify_total",
    "OTP verify attempts by outcome (ok, or why not). The caller sees one refusal.",
    ("outcome",),
)

#: INT-577. How an OTP request ended (``sec.otp_requests_total``, files/08
#: §4): a code minted, refused by a budget, by the spend kill switch, by the
#: INT-578 lockout, as not a Turkish mobile, or by the carrier check or the
#: synthetic host's test list.
REQUEST_OUTCOMES = frozenset(
    {
        "admitted",
        "limited",
        "kill_switch",
        "locked",
        "withheld",
        "not_listed",
        "phone_invalid",
        "refused",
    }
)
#: Which budget refused (``sec.otp_abuse_blocks``): one request can be refused
#: by several, and each is counted.
BLOCK_DIMENSIONS = frozenset(
    {"cooldown", "phone", "ip", "device", "tenant", "global_hour", "global_day"}
)

SEC_OTP_REQUESTS_TOTAL = Counter(
    "sec_otp_requests_total",
    "OTP requests by outcome (admitted, or why not).",
    ("outcome",),
)
SEC_OTP_ABUSE_BLOCKS = Counter(
    "sec_otp_abuse_blocks",
    "OTP requests refused by a request budget, by the budget that refused.",
    ("dimension",),
)

#: INT-580 (``sec.new_device_logins``, files/08 §4): sign-ins from a device the
#: account had not signed in from.
SEC_NEW_DEVICE_LOGINS = Counter(
    "sec_new_device_logins",
    "Sign-ins from a device the account had not signed in from before.",
)

_TR_MOBILE = re.compile(r"^(?:\+90|90|0)?(5\d{9})$")
_STRIP = re.compile(r"[\s\-().]")


def normalise_tr_phone(raw: str) -> str | None:
    """Turkish mobile → canonical E.164 (+905xxxxxxxxx); None when it is not
    one. Formatting must not fork pseudonyms or rate buckets (tokenization
    precedent), so all accepted spellings collapse to one canonical form."""
    if len(raw) > 32:
        return None
    stripped = _STRIP.sub("", raw)
    match = _TR_MOBILE.match(stripped)
    if match is None:
        return None
    return f"+90{match.group(1)}"


@dataclass(frozen=True)
class DeliveryReceipt:
    delivery_id: str


class OtpDeliveryFailure(StrEnum):
    """Why a delivery failed — an id-shaped vocabulary, safe to log."""

    EGRESS_DENIED = "egress_denied"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    REJECTED = "rejected"
    VENDOR_UNAVAILABLE = "vendor_unavailable"
    MALFORMED_RESPONSE = "malformed_response"


#: INT-576: the failures after which the vendor may already have sent the
#: code: an answer the adapter could not read (Netgsm had sent it, on 28 Oct
#: 2026), no answer before the timeout, or a vendor-side failure that does not
#: say whether the message left. Sending again could put a second code in
#: flight, so none of these is ever sent again automatically.
DELIVERY_MAY_HAVE_SENT: Final = frozenset(
    {
        OtpDeliveryFailure.MALFORMED_RESPONSE,
        OtpDeliveryFailure.TIMEOUT,
        OtpDeliveryFailure.VENDOR_UNAVAILABLE,
    }
)


class OtpDeliveryError(Exception):
    """The SMS vendor could not deliver the code (INT-329). The tier fails
    closed: it never claims a code was sent. Carries a reason, the HTTP status
    and the vendor's numeric error code — never the code, the phone, a
    credential or a vendor body (invariant 6)."""

    def __init__(
        self,
        reason: OtpDeliveryFailure,
        *,
        status_code: int | None = None,
        vendor_code: int | None = None,
    ) -> None:
        self.reason = reason
        self.status_code = status_code
        self.vendor_code = vendor_code
        super().__init__(f"otp delivery failed: {reason} (status {status_code or '-'})")

    @property
    def retryable(self) -> bool:
        """Whether a second send could not double-deliver: False wherever the
        vendor may already have sent the code (:data:`DELIVERY_MAY_HAVE_SENT`).
        Nothing sends twice today, and the patient's resend after the
        cooldown is the only second attempt; this is what any caller that
        ever does must honour (INT-576)."""
        return self.reason not in DELIVERY_MAY_HAVE_SENT


class OtpDeliveryAdapter(Protocol):
    """The SMS seam (INT-131; async since INT-329). ``send`` returns the
    vendor's delivery id or raises :class:`OtpDeliveryError`."""

    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt: ...


class DevLogDeliveryAdapter:
    """Records the delivery EVENT with ids only (invariant 6): no code, no
    phone, no vendor claim. The code is reachable exclusively through the
    peek endpoint behind INTAKE_DEV_OTP_PEEK=explicit-yes. Dev only: outside
    dev it is never wired (INT-325)."""

    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
        del phone_e164, code  # never logged; the peek store is the only dev exposure
        receipt = DeliveryReceipt(delivery_id=uuid.uuid4().hex)
        logger.info(
            "otp delivery event recorded (dev adapter, no SMS vendor wired) delivery_id=%s",
            receipt.delivery_id,
        )
        return receipt


@dataclass
class AuthWiring:
    """Everything the OTP tier needs, injectable for tests; the env path is
    built by ``intake_api.app.wiring_from_env`` and fails closed when the
    tokenization key is absent."""

    redis_client: redis.Redis
    tokenizer: Tokenizer
    delivery: OtpDeliveryAdapter
    attestation: AttestationVerifier
    dev_otp_peek: bool = False
    now_fn: Callable[[], float] | None = None
    # INT-308: files/10 §2's carrier/geo sanity check. The default has no
    # authority and therefore admits everything, which is the correct state for
    # a wiring nobody gave one to; the env path builds the file-backed one.
    carrier_geo: CarrierGeoCheck = field(default_factory=CarrierGeoCheck)
    # INT-344: who registers App Attest keys. The default registers nobody.
    key_attestation: KeyAttestationRegistrar = field(
        default_factory=lambda: FailClosedAttestationVerifier(
            AttestationReason.APP_ATTEST_NOT_CONFIGURED
        )
    )
    # INT-528: on the synthetic host, the owner's SMS test allow-list; a
    # number off it starts no login. Elsewhere there is no list.
    recipients: RecipientGate = field(default_factory=lambda: ADMIT_ALL)
    # INT-578: the key every code is kept under. The env path always passes
    # the one OpenBao holds (secret/api/otp) and refuses to wire without it;
    # this default — random, process-local — is what a harness gets.
    pepper: OtpPepper = field(default_factory=OtpPepper.ephemeral)
    # INT-577: the tenant and global send caps (engineering defaults in
    # intake_api.sms_spend; a test harness passes small ones)
    sms_budget: SmsBudget = field(default_factory=SmsBudget)
    # INT-580: who tells the patient about a sign-in from a new device; INT-583:
    # a push to the devices already signed in (intake_api.sign_in_notice), or
    # no channel, which fails closed with its typed reason
    sign_in_notice: SignInNotice = field(default_factory=NoSignInNoticeChannel)


async def ensure_consumer_tenant(engine: AsyncEngine) -> None:
    """Idempotent consumer-tenant bootstrap (needs INSERT on tenants — the
    dev-compose owner engine, exactly like the dev fixture's tenant)."""
    async with tenant_session(engine, CONSUMER_TENANT_ID) as session:
        if await session.get(Tenant, CONSUMER_TENANT_ID) is None:
            session.add(
                Tenant(
                    id=CONSUMER_TENANT_ID,
                    display_name="INTAKE consumer app",
                    kvkk_role=KvkkRole.CONTROLLER,
                )
            )


@dataclass(frozen=True)
class CurrentSession:
    """INT-583: who is calling, and from which signed-in device."""

    patient_id: uuid.UUID
    device: DeviceSession | None


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    patient_id: str
    tenant_id: str


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _bound_device(payload: AttestationPayload) -> str:
    """What a code is bound to (INT-578): the key App Attest proved, or, on
    the dev tier only, the install id. In a real mode the install id is the
    client's claim, and binding to it would let any device that claims it
    spend the code, so a real mode with no key it proved is refused here,
    before any budget is spent or any code minted. Play Integrity proves no
    key, so Android stays refused until its binding has one (HB-A3)."""
    if payload.mode == "app-attest" and payload.key_id:
        return f"{payload.mode}:{payload.key_id}"
    if payload.mode == "dev-unattested":
        return f"{payload.mode}:{payload.device_id}"
    logger.info("otp binding refused: a real attestation mode proved no key")
    raise attestation_unverified()


def _retrieve_by_type(task: asyncio.Task[None]) -> None:
    """Done-callback for a delivery task: retrieve whatever it ended with and
    name it by type only. An exception left unretrieved is logged by asyncio
    with its full chain when the task is freed, and a delivery's chain can hold
    the number and the code (security review, 28 Oct 2026)."""
    if task.cancelled():
        return
    failure = task.exception()
    if failure is not None:
        logger.warning("otp delivery task failed (%s)", type(failure).__name__)


class OtpAuthService:
    """Orchestrates the OTP tier. Store calls hop off the event loop via
    ``asyncio.to_thread`` (sync Redis client, INT-012 precedent)."""

    def __init__(self, wiring: AuthWiring, *, engine: AsyncEngine, audit: AuditWriter) -> None:
        self._wiring = wiring
        self._store = AuthStore(wiring.redis_client, wiring.now_fn)
        self._tokenizer = wiring.tokenizer
        self._pepper = wiring.pepper
        self._kill_switch = SpendKillSwitch(wiring.redis_client, wiring.now_fn)
        # INT-583: the devices the account is signed in on, and their push tokens
        self.device_sessions = DeviceSessionStore(
            wiring.redis_client, wiring.pepper, self._store, wiring.now_fn
        )
        # INT-579: deliveries in flight, off the response path
        self._dispatches: set[asyncio.Task[None]] = set()
        self._engine = engine
        self._audit = audit

    def _now(self) -> float:
        return self._wiring.now_fn() if self._wiring.now_fn is not None else time.time()

    def now(self) -> float:
        """The tier's clock (injectable), for the INT-583 sessions routes."""
        return self._now()

    @property
    def notices_on(self) -> bool:
        """INT-583: whether a push channel is wired for the new-device notice.
        Without one, no push token is accepted, because none would be used."""
        return not isinstance(self._wiring.sign_in_notice, NoSignInNoticeChannel)

    # --- attestation (files/10 §2: on OTP request AND session start) --------------

    async def issue_challenge(self) -> dict[str, object]:
        challenge = await asyncio.to_thread(self._store.issue_challenge)
        return {"challenge": challenge, "expires_in": CHALLENGE_TTL_S}

    async def _consume(self, challenge: str) -> None:
        """Spend the challenge BEFORE any verifier runs: single-use whatever the
        outcome, so nobody retries verification against one challenge, and the
        App Attest counter only ever moves under a live challenge (INT-344)."""
        if not await asyncio.to_thread(self._store.consume_challenge, challenge):
            raise challenge_invalid()

    async def _require_attested(
        self, request: Request, purpose: AttestPurpose
    ) -> AttestationPayload:
        raw = request.headers.get(ATTESTATION_HEADER)
        if raw is None:
            raise attestation_required()
        payload = parse_attestation(raw)
        if payload is None:
            raise attestation_invalid()
        await self._consume(payload.nonce)
        result = await asyncio.to_thread(
            self._wiring.attestation.verify,
            payload,
            client_data=attestation_client_data(purpose, payload.nonce),
        )
        if not result.ok:
            # ids-only breadcrumb; the reason code carries no device data
            logger.info("attestation refused reason=%s", result.reason)
            raise attestation_unverified()
        return payload

    async def register_attested_key(
        self, key_id: str, attestation: str, challenge: str
    ) -> dict[str, str]:
        """App Attest key registration (INT-344): the attestation, bound to a
        server challenge, proves a genuine instance of this app holds the key;
        from then on its OTP calls carry assertions from that key."""
        await self._consume(challenge)
        result = await asyncio.to_thread(
            self._wiring.key_attestation.register,
            key_id,
            attestation,
            client_data=attestation_client_data("attest.key", challenge),
        )
        if not result.ok:
            logger.info("app attest key registration refused reason=%s", result.reason)
            raise attestation_unverified()
        return {"key_id": key_id}

    def _require_phone(self, raw: str) -> tuple[str, str]:
        phone = normalise_tr_phone(raw)
        if phone is None:
            raise phone_invalid()
        return phone, self._tokenizer.pseudonym(phone)

    def pseudonym_for(self, phone_raw: str) -> str | None:
        """The pseudonym the OTP tier keys a patient by for a raw phone, or
        ``None`` when it is not a Turkish mobile.

        Same normalisation + tokenisation ``verify`` used to create the
        account, exposed so an ownership check elsewhere (INT-318: is this the
        caller's *own* number?) resolves the identical pseudonym rather than a
        second, divergent one."""
        phone = normalise_tr_phone(phone_raw)
        if phone is None:
            return None
        return self._tokenizer.pseudonym(phone)

    async def _verify_proof(self, request: Request, access_token: str | None = None) -> str:
        header = request.headers.get("DPoP")
        if header is None:
            raise dpop_invalid("dpop_required")
        try:
            proof = verify_dpop_proof(
                header,
                method=request.method,
                url=str(request.url),
                now=int(self._now()),
                access_token=access_token,
            )
        except DpopError as exc:
            raise dpop_invalid(exc.code) from exc
        if not await asyncio.to_thread(self._store.jti_first_use, proof.jti):
            raise dpop_invalid("dpop_replayed")
        return proof.jkt

    # --- the OTP flow -----------------------------------------------------------------

    def _budgets(self) -> tuple[Budget, ...]:
        """INT-577: the tenant hour budget and the global caps."""
        caps = self._wiring.sms_budget
        return (
            Budget("tenant", str(CONSUMER_TENANT_ID), caps.tenant_sends_per_hour),
            Budget("global_hour", "all", caps.global_sends_per_hour),
            Budget("global_day", "all", caps.global_sends_per_day, DAY_S),
        )

    async def request_code(self, request: Request, phone_raw: str) -> dict[str, object]:
        payload = await self._require_attested(request, "otp.request")
        bound = _bound_device(payload)
        try:
            phone, pseudonym = self._require_phone(phone_raw)
        except HTTPException:
            SEC_OTP_REQUESTS_TOTAL.labels(outcome="phone_invalid").inc()
            raise
        # INT-578: a locked number gets no code. INT-579: and the caller cannot
        # tell — the request is withheld below, never refused here.
        locked = await asyncio.to_thread(self._store.lockout_wait, pseudonym) is not None
        # INT-528: on the synthetic host a number off the owner's test list gets
        # no code either, withheld in the same way (the line logged names no
        # number)
        listed = self._wiring.recipients.admits(phone)
        # INT-577: the spend kill switch, read before any budget is spent. An
        # unreadable switch may be on, so it refuses too (fail closed).
        try:
            engaged = await asyncio.to_thread(self._kill_switch.state) is not None
        except SpendStateUnreadable:
            logger.warning("otp request refused: the SMS spend kill switch is unreadable")
            engaged = True
        if engaged:
            SEC_OTP_REQUESTS_TOTAL.labels(outcome="kill_switch").inc()
            raise otp_delivery_unavailable()
        ip = request.client.host if request.client is not None else "unknown"
        decision = await asyncio.to_thread(
            partial(
                self._store.otp_request_decision,
                pseudonym,
                # INT-577: the address as a keyed hash, the device as the key it proved
                self._pepper.rate_key("ip", ip),
                self._pepper.rate_key("device", bound),
                extra=self._budgets(),
                backoff=True,
                withhold=locked or not listed,
            )
        )
        if not decision.admitted and not decision.withheld:
            for dimension in decision.dimensions:
                SEC_OTP_ABUSE_BLOCKS.labels(dimension=dimension).inc()
            if "global_day" in decision.dimensions:
                # the day's spend ceiling: latch the switch, page, stop sending
                if await asyncio.to_thread(self._kill_switch.engage, "day_cap"):
                    await self._audit.record(
                        actor="system:sms-spend",
                        action="sms.spend.kill_switch.engaged",
                        resource_ref="sms_spend:day_cap",
                        consent_scope="scope:auth",
                    )
                SEC_OTP_REQUESTS_TOTAL.labels(outcome="kill_switch").inc()
                raise otp_delivery_unavailable()
            SEC_OTP_REQUESTS_TOTAL.labels(outcome="limited").inc()
            raise otp_limited(decision.wait)
        # INT-308 — files/10 §2's carrier/geo sanity check, and it sits HERE for
        # two reasons. AFTER the gate, so a refusal costs the caller its budget
        # and probing which prefixes refuse is not free; and BEFORE the code is
        # minted, because the whole point is that no SMS is sent to a number no
        # operator has allocated. The refusal reuses ``phone_invalid`` rather
        # than a code of its own: 422 is what it is, and a distinct code would
        # be an oracle telling a caller which of its numbers exist (files/10 §9
        # row 1, generic errors). It fails OPEN — see carrier_geo — so today,
        # with an empty authority, this branch is unreachable in production.
        # INT-308 — the numbering plan's answer is the same for every caller and
        # every subscriber in a prefix, so it is no oracle about a person: it
        # still answers 422, after the gate charged the caller (withheld or not)
        if self._wiring.carrier_geo.evaluate(phone).refuses:
            SEC_OTP_REQUESTS_TOTAL.labels(outcome="refused").inc()
            raise phone_invalid()
        for dimension in decision.dimensions:
            SEC_OTP_ABUSE_BLOCKS.labels(dimension=dimension).inc()
        # the same work whether the code is real or withheld: an id, a code, its
        # digest, a store write and one audit row (INT-579)
        request_id = secrets.token_hex(16)
        code = f"{secrets.randbelow(10**OTP_CODE_DIGITS):0{OTP_CODE_DIGITS}d}"
        digest = self._pepper.code_digest(pseudonym, request_id, code)
        actor = f"phone:{self._tokenizer.log_ref(phone)}"
        if decision.withheld:
            outcome = "locked" if locked else ("not_listed" if not listed else "withheld")
            if not listed:
                logger.info("otp request withheld: the number is not on the SMS test allow-list")
            SEC_OTP_REQUESTS_TOTAL.labels(outcome=outcome).inc()
            await asyncio.to_thread(self._store.withhold_code, self._wiring.dev_otp_peek)
            await self._audit.record(
                # legal review, 30 Oct 2026: a number off the test list is a
                # stranger's, typed by a caller; the chain is kept ten years in
                # WORM storage, so its row names no ref of it (INT-308)
                actor=actor if listed else "system:otp-withheld",
                action="auth.otp.withheld",
                resource_ref=f"request:{request_id}",
                consent_scope="scope:auth",
            )
        else:
            SEC_OTP_REQUESTS_TOTAL.labels(outcome="admitted").inc()
            # INT-578: the code is bound to this request and to this device
            await asyncio.to_thread(
                self._store.store_code,
                pseudonym,
                digest,
                code if self._wiring.dev_otp_peek else None,
                binding=self._pepper.device_binding(bound),
            )
            await self._audit.record(
                actor=actor,
                action="auth.otp.requested",
                resource_ref=f"request:{request_id}",
                consent_scope="scope:auth",
            )
            self._dispatch(phone=phone, code=code, request_id=request_id, actor=actor)
        # INT-577/579: the wait read from the caller's own device
        return {"request_id": request_id, "resend_after_s": int(decision.wait)}

    def _dispatch(self, *, phone: str, code: str, request_id: str, actor: str) -> None:
        """Send the code after the response (INT-579). The task holds the
        number and the code in memory only, and is tracked until it ends."""
        task = asyncio.create_task(
            self._deliver(phone=phone, code=code, request_id=request_id, actor=actor)
        )
        self._dispatches.add(task)
        task.add_done_callback(self._dispatches.discard)
        task.add_done_callback(_retrieve_by_type)

    async def _deliver(self, *, phone: str, code: str, request_id: str, actor: str) -> None:
        receipt: DeliveryReceipt | None = None
        try:
            receipt = await self._wiring.delivery.send(phone_e164=phone, code=code)
        except Exception as exc:  # noqa: BLE001 — a send must never leak or be lost
            if not isinstance(exc, OtpDeliveryError):
                # INT-581: an adapter bug can carry the number or the code in its
                # message, and an unretrieved task exception is logged with its
                # text. Contain it here: its type is logged, never its words.
                logger.warning("otp delivery crashed (%s); recorded as failed", type(exc).__name__)
        # The audit runs OUTSIDE the handler above (security review, 28 Oct
        # 2026): an append that fails inside it carries the vendor's exception
        # as its context, and the code and the number travel with it into any
        # traceback. Out here a failed append chains nothing, and the task's
        # done-callback names it by type. The adapter logged and counted a typed
        # reason (ids only); the caller was told nothing either way, and nothing
        # claims a send that failed.
        if receipt is None:
            action, resource = "auth.otp.delivery_failed", f"request:{request_id}"
        else:
            action, resource = "auth.otp.sent", f"delivery:{receipt.delivery_id}"
        await self._audit.record(
            actor=actor, action=action, resource_ref=resource, consent_scope="scope:auth"
        )

    async def settle(self, timeout_s: float | None = None) -> None:
        """Wait for every delivery in flight: the tests, and the API's shutdown,
        which would otherwise drop a code a patient was promised."""
        while self._dispatches:
            pending = list(self._dispatches)
            done, _ = await asyncio.wait(pending, timeout=timeout_s)
            if len(done) < len(pending):
                logger.warning(
                    "otp deliveries still in flight at shutdown: %d", len(pending) - len(done)
                )
                return

    async def peek_code(self, phone_raw: str) -> dict[str, str]:
        """Dev tier ONLY (INTAKE_DEV_OTP_PEEK=explicit-yes; 404 otherwise —
        the route itself refuses before calling this when the flag is off)."""
        if not self._wiring.dev_otp_peek:
            raise not_found()
        phone = normalise_tr_phone(phone_raw)
        if phone is None:
            raise phone_invalid()
        code = await asyncio.to_thread(self._store.peek_code, self._tokenizer.pseudonym(phone))
        if code is None:
            raise not_found()
        return {"code": code}

    async def _get_or_create_patient(self, pseudonym: str) -> uuid.UUID:
        async with tenant_session(self._engine, CONSUMER_TENANT_ID) as session:
            existing = await session.scalar(
                select(Patient).where(
                    Patient.tenant_id == CONSUMER_TENANT_ID, Patient.pseudonym == pseudonym
                )
            )
            if existing is not None:
                return existing.id
            patient = Patient(id=uuid.uuid4(), tenant_id=CONSUMER_TENANT_ID, pseudonym=pseudonym)
            session.add(patient)
        await self._audit.record(
            actor=f"patient:{patient.id}",
            action="auth.account.created",
            resource_ref=f"patient:{patient.id}",
            consent_scope="scope:auth",
        )
        return patient.id

    async def _issue_tokens(
        self, patient_id: uuid.UUID, jkt: str, family_id: str | None = None
    ) -> TokenBundle:
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(48)
        family = family_id if family_id is not None else uuid.uuid4().hex
        await asyncio.to_thread(
            self._store.save_access,
            _token_hash(access),
            patient_id=patient_id,
            tenant_id=CONSUMER_TENANT_ID,
            jkt=jkt,
            family_id=family,
        )
        kept = await asyncio.to_thread(
            self._store.save_refresh,
            _token_hash(refresh),
            family_id=family,
            patient_id=patient_id,
            tenant_id=CONSUMER_TENANT_ID,
            jkt=jkt,
        )
        if not kept:
            # INT-583: the family was revoked while this rotation was in
            # flight (its device signed out); the write was undone
            raise unauthorized()
        return TokenBundle(
            access_token=access,
            refresh_token=refresh,
            token_type="DPoP",  # noqa: S106 — RFC 9449 token_type label, not a secret
            expires_in=ACCESS_TTL_S,
            patient_id=str(patient_id),
            tenant_id=str(CONSUMER_TENANT_ID),
        )

    async def verify_code(
        self, request: Request, phone_raw: str, code: str, request_id: str
    ) -> TokenBundle:
        payload = await self._require_attested(request, "otp.verify")
        bound = _bound_device(payload)
        phone, pseudonym = self._require_phone(phone_raw)
        jkt = await self._verify_proof(request)
        locked = await asyncio.to_thread(self._store.lockout_wait, pseudonym) is not None
        # INT-579: the attempt is taken and compared under a lockout too, so a
        # locked number costs the same work as any other wrong answer
        verdict = await asyncio.to_thread(
            partial(
                self._store.check_code,
                pseudonym,
                self._pepper.code_digest(pseudonym, request_id, code),
                binding=self._pepper.device_binding(bound),
                # INT-578: a guess under the lockout spends nothing of the
                # number's budget, so it can neither extend the lockout nor
                # outlive it in the window
                charge=not locked,
            )
        )
        outcome = "locked" if locked else verdict
        OTP_VERIFY_TOTAL.labels(outcome=outcome).inc()
        if verdict == "exhausted" and not locked:
            # INT-578: the miss that spent the budget locks the number
            await asyncio.to_thread(self._store.engage_lockout, pseudonym)
        if outcome != "ok":
            # INT-581: every verify is on the chain, a refused one too — the
            # number's 8-character log ref and the closed outcome, nothing more.
            # INT-579: one row for every kind of refusal, so the work is alike.
            # Legal review, 30 Oct 2026: a `missing` verify names a number that
            # has no code, typed by a caller; its row keeps no ref of it.
            await self._audit.record(
                actor=(
                    "system:otp-verify"
                    if outcome == "missing"
                    else f"phone:{self._tokenizer.log_ref(phone)}"
                ),
                action="auth.otp.verify_refused",
                resource_ref=f"otp_verify:{outcome}",
                consent_scope="scope:auth",
            )
            # one generic refusal for wrong/expired/exhausted/unbound/locked (02 §8.2)
            raise otp_invalid()
        patient_id = await self._get_or_create_patient(pseudonym)
        await self._audit.record(
            actor=f"patient:{patient_id}",
            action="auth.otp.verified",
            resource_ref=f"phone:{self._tokenizer.log_ref(phone)}",
            consent_scope="scope:auth",
        )
        device_ref = self._pepper.rate_key("known_device", bound)
        await self._note_device(patient_id, device_ref)
        # INT-583: the session is the device's, so the sessions screen can name
        # it, sign it out, and register a push token for it alone
        family = uuid.uuid4().hex
        bundle = await self._issue_tokens(patient_id, jkt, family_id=family)
        await asyncio.to_thread(self.device_sessions.bind, patient_id, device_ref, family)
        return bundle

    async def _note_device(self, patient_id: uuid.UUID, device_ref: str) -> None:
        """INT-580: a sign-in from a device the account has not used is
        counted, put on the hash chain where the patient's own access log reads
        (``auth.*`` is ACCOUNT_SECURITY there), and handed to the notice
        channel. A stolen code entered on the thief's phone is exactly this
        event; so is a SIM swap's first sign-in. ``device_ref`` is the keyed
        hash of the proven device (the OTP pepper's ``rate_key``).

        INT-583: the notice is told after the response, like an SMS send
        (INT-579), so a slow push provider never holds a sign-in."""
        new = await asyncio.to_thread(self._store.remember_device, str(patient_id), device_ref)
        if not new:
            return
        SEC_NEW_DEVICE_LOGINS.inc()
        await self._audit.record(
            actor=f"patient:{patient_id}",
            action="auth.login.new_device",
            resource_ref=f"patient:{patient_id}",
            consent_scope="scope:auth",
        )
        task = asyncio.create_task(self._tell(patient_id, device_ref))
        self._dispatches.add(task)
        task.add_done_callback(self._dispatches.discard)
        task.add_done_callback(_retrieve_by_type)

    async def _tell(self, patient_id: uuid.UUID, new_device_ref: str) -> None:
        """INT-583: hand the new-device sign-in to the notice channel, which
        leaves ``new_device_ref`` out, and put each outcome on the hash chain
        (ids only, under the patient, so their own access log shows it)."""
        try:
            outcomes = await self._wiring.sign_in_notice.new_device_sign_in(
                patient_id=patient_id, new_device_ref=new_device_ref
            )
        except Exception as exc:  # noqa: BLE001 — a notice must never take a sign-in down
            logger.warning("new-device sign-in notice crashed (%s)", type(exc).__name__)
            outcomes = (NoticeOutcome.FAILED,)
        for outcome in outcomes:
            SEC_SIGN_IN_NOTICES_TOTAL.labels(outcome=outcome.value).inc()
            await self._audit.record(
                actor=f"patient:{patient_id}",
                action=f"auth.notice.{outcome.value}",
                resource_ref=f"patient:{patient_id}",
                consent_scope="scope:auth",
            )

    async def refresh_tokens(self, request: Request, refresh_token: str) -> TokenBundle:
        jkt = await self._verify_proof(request)
        token_hash = _token_hash(refresh_token)
        record = await asyncio.to_thread(self._store.get_refresh, token_hash)
        if record is None:
            raise unauthorized()
        if record.status == "rotated":
            # REUSE: the whole family dies, and the event is audited
            # (files/10 §2: "refresh reuse detection revokes the family").
            # INT-583: the device is forgotten too, so its return is told.
            device = await asyncio.to_thread(
                self.device_sessions.session_of_family, record.patient_id, record.family_id
            )
            await asyncio.to_thread(self._store.revoke_family, record.family_id)
            if device is not None:
                await asyncio.to_thread(
                    self._store.forget_device, str(record.patient_id), device.device_ref
                )
            await self._audit.record(
                actor=f"patient:{record.patient_id}",
                action="auth.refresh.reuse_detected",
                resource_ref=f"token_family:{record.family_id}",
                consent_scope="scope:auth",
            )
            raise refresh_reused()
        if record.jkt != jkt:
            # wrong device key is NOT reuse — refuse without killing the
            # family, or a stolen token becomes a denial-of-service lever
            raise dpop_invalid("dpop_mismatch")
        await asyncio.to_thread(self._store.mark_refresh_rotated, token_hash)
        bundle = await self._issue_tokens(record.patient_id, jkt, family_id=record.family_id)
        # INT-583: a session that keeps refreshing keeps its device row and the
        # account's known devices for another session lifetime
        await asyncio.to_thread(self.device_sessions.touch, record.patient_id)
        await asyncio.to_thread(self._store.renew_known_devices, str(record.patient_id))
        return bundle

    # --- resource-request resolution (Authorization: DPoP <token>) -----------------

    async def _access_record(self, request: Request, token: str) -> AccessRecord:
        jkt = await self._verify_proof(request, access_token=token)
        record = await asyncio.to_thread(self._store.get_access, _token_hash(token))
        if record is None:
            raise unauthorized()
        if record.jkt != jkt:
            raise dpop_invalid("dpop_mismatch")
        # INT-583: a device signed out (or a family revoked on reuse) ends its
        # access tokens now, not at their expiry
        if record.family_id is not None and not await asyncio.to_thread(
            self._store.family_alive, record.family_id
        ):
            raise unauthorized()
        return record

    async def resolve_session(self, request: Request, token: str) -> CurrentSession:
        """INT-583: the signed-in device behind an access token, for the
        sessions and push-token routes. A session issued before devices were
        bound has no device, and is answered with ``device=None``."""
        record = await self._access_record(request, token)
        device: DeviceSession | None = None
        if record.family_id is not None:
            device = await asyncio.to_thread(
                self.device_sessions.session_of_family, record.patient_id, record.family_id
            )
        return CurrentSession(patient_id=record.patient_id, device=device)

    async def audit_account(self, patient_id: uuid.UUID, action: str) -> None:
        """INT-583: one ``auth.*`` row under the patient (ids only)."""
        await self._audit.record(
            actor=f"patient:{patient_id}",
            action=action,
            resource_ref=f"patient:{patient_id}",
            consent_scope="scope:auth",
        )

    async def resolve_access(self, request: Request, token: str) -> DevAccount:
        record = await self._access_record(request, token)
        return DevAccount(
            account_id=f"patient:{record.patient_id}",
            role="patient",
            tenant_id=record.tenant_id,
            patient_id=record.patient_id,
        )
