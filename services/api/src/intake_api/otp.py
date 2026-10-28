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
from typing import Protocol

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
    AuthStore,
    Budget,
)
from intake_api.carrier_geo import CarrierGeoCheck
from intake_api.db import tenant_session
from intake_api.dev_fixture import DevAccount
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
from intake_api.sms_recipients import ADMIT_ALL, RecipientGate
from intake_api.sms_spend import DAY_S, SmsBudget, SpendKillSwitch, SpendStateUnreadable

__all__ = [
    "ATTESTATION_HEADER",
    "BLOCK_DIMENSIONS",
    "CONSUMER_TENANT_ID",
    "OTP_VERIFY_TOTAL",
    "REQUEST_OUTCOMES",
    "SEC_OTP_ABUSE_BLOCKS",
    "SEC_OTP_REQUESTS_TOTAL",
    "VERIFY_OUTCOMES",
    "AuthWiring",
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
    {"admitted", "limited", "kill_switch", "locked", "phone_invalid", "refused"}
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
    """What a code is bound to (INT-578): the key App Attest proved, when the
    call carries one, and otherwise the install id — which only the dev tier
    accepts. In a real mode the install id is the client's claim, and binding
    to it would let any key that claims it spend the code."""
    if payload.mode == "app-attest" and payload.key_id:
        return f"{payload.mode}:{payload.key_id}"
    return f"{payload.mode}:{payload.device_id}"


class OtpAuthService:
    """Orchestrates the OTP tier. Store calls hop off the event loop via
    ``asyncio.to_thread`` (sync Redis client, INT-012 precedent)."""

    def __init__(self, wiring: AuthWiring, *, engine: AsyncEngine, audit: AuditWriter) -> None:
        self._wiring = wiring
        self._store = AuthStore(wiring.redis_client, wiring.now_fn)
        self._tokenizer = wiring.tokenizer
        self._pepper = wiring.pepper
        self._kill_switch = SpendKillSwitch(wiring.redis_client, wiring.now_fn)
        self._engine = engine
        self._audit = audit

    def _now(self) -> float:
        return self._wiring.now_fn() if self._wiring.now_fn is not None else time.time()

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
        try:
            phone, pseudonym = self._require_phone(phone_raw)
        except HTTPException:
            SEC_OTP_REQUESTS_TOTAL.labels(outcome="phone_invalid").inc()
            raise
        # INT-578: a locked number gets no code, and asking costs no budget
        locked = await asyncio.to_thread(self._store.lockout_wait, pseudonym)
        if locked is not None:
            SEC_OTP_REQUESTS_TOTAL.labels(outcome="locked").inc()
            raise otp_limited(locked)
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
                self._pepper.rate_key("device", _bound_device(payload)),
                extra=self._budgets(),
                backoff=True,
            )
        )
        if not decision.admitted:
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
        if self._wiring.carrier_geo.evaluate(phone).refuses:
            SEC_OTP_REQUESTS_TOTAL.labels(outcome="refused").inc()
            raise phone_invalid()
        # INT-528 — on the synthetic host SMS is real, so a number off the
        # owner's test allow-list starts no login: no code is minted and no SMS
        # leaves. Same place and same answer as the carrier check above, for the
        # same reasons; the line logged names no number.
        if not self._wiring.recipients.admits(phone):
            logger.info("otp request refused: the number is not on the SMS test allow-list")
            SEC_OTP_REQUESTS_TOTAL.labels(outcome="refused").inc()
            raise phone_invalid()
        SEC_OTP_REQUESTS_TOTAL.labels(outcome="admitted").inc()
        # INT-578: the code is bound to this request and to this device
        request_id = secrets.token_hex(16)
        code = f"{secrets.randbelow(10**OTP_CODE_DIGITS):0{OTP_CODE_DIGITS}d}"
        await asyncio.to_thread(
            self._store.store_code,
            pseudonym,
            self._pepper.code_digest(pseudonym, request_id, code),
            code if self._wiring.dev_otp_peek else None,
            binding=self._pepper.device_binding(_bound_device(payload)),
        )
        try:
            receipt = await self._wiring.delivery.send(phone_e164=phone, code=code)
        except OtpDeliveryError:
            # the adapter logged the reason (ids only); the caller gets one
            # generic code whatever the cause, and nothing was "sent"
            raise otp_delivery_unavailable() from None
        await self._audit.record(
            actor=f"phone:{self._tokenizer.log_ref(phone)}",
            action="auth.otp.requested",
            resource_ref=f"delivery:{receipt.delivery_id}",
            consent_scope="scope:auth",
        )
        return {
            "delivery_id": receipt.delivery_id,
            "request_id": request_id,
            # INT-577: the doubled wait this number's next code is held to
            "resend_after_s": int(decision.wait),
        }

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
        )
        await asyncio.to_thread(
            self._store.save_refresh,
            _token_hash(refresh),
            family_id=family,
            patient_id=patient_id,
            tenant_id=CONSUMER_TENANT_ID,
            jkt=jkt,
        )
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
        phone, pseudonym = self._require_phone(phone_raw)
        jkt = await self._verify_proof(request)
        if await asyncio.to_thread(self._store.lockout_wait, pseudonym) is not None:
            OTP_VERIFY_TOTAL.labels(outcome="locked").inc()
            raise otp_invalid()
        verdict = await asyncio.to_thread(
            self._store.check_code,
            pseudonym,
            self._pepper.code_digest(pseudonym, request_id, code),
            binding=self._pepper.device_binding(_bound_device(payload)),
        )
        OTP_VERIFY_TOTAL.labels(outcome=verdict).inc()
        if verdict == "exhausted":
            # INT-578: the miss that spent the budget locks the number
            await asyncio.to_thread(self._store.engage_lockout, pseudonym)
        if verdict != "ok":
            # one generic refusal for wrong/expired/exhausted/unbound (02 §8.2)
            raise otp_invalid()
        patient_id = await self._get_or_create_patient(pseudonym)
        await self._audit.record(
            actor=f"patient:{patient_id}",
            action="auth.otp.verified",
            resource_ref=f"phone:{self._tokenizer.log_ref(phone)}",
            consent_scope="scope:auth",
        )
        return await self._issue_tokens(patient_id, jkt)

    async def refresh_tokens(self, request: Request, refresh_token: str) -> TokenBundle:
        jkt = await self._verify_proof(request)
        token_hash = _token_hash(refresh_token)
        record = await asyncio.to_thread(self._store.get_refresh, token_hash)
        if record is None:
            raise unauthorized()
        if record.status == "rotated":
            # REUSE: the whole family dies, and the event is audited
            # (files/10 §2: "refresh reuse detection revokes the family")
            await asyncio.to_thread(self._store.revoke_family, record.family_id)
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
        return await self._issue_tokens(record.patient_id, jkt, family_id=record.family_id)

    # --- resource-request resolution (Authorization: DPoP <token>) -----------------

    async def resolve_access(self, request: Request, token: str) -> DevAccount:
        jkt = await self._verify_proof(request, access_token=token)
        record = await asyncio.to_thread(self._store.get_access, _token_hash(token))
        if record is None:
            raise unauthorized()
        if record.jkt != jkt:
            raise dpop_invalid("dpop_mismatch")
        return DevAccount(
            account_id=f"patient:{record.patient_id}",
            role="patient",
            tenant_id=record.tenant_id,
            patient_id=record.patient_id,
        )
