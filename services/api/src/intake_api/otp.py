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
- SMS delivery: no vendor contract exists (awaiting-human). The ONLY
  adapter is :class:`DevLogDeliveryAdapter`, which records a delivery EVENT
  (ids only — never the code, never the phone) and claims nothing more; the
  code is reachable solely through the peek endpoint behind
  ``INTAKE_DEV_OTP_PEEK=explicit-yes``. A vendor lands by implementing
  :class:`OtpDeliveryAdapter` against the contract.
- Attestation: the verifier seam fails closed (attestation.py).
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
from typing import Protocol

import redis
from fastapi import Request
from intake_platform.db.models import KvkkRole, Patient, Tenant
from intake_platform.tokenization import Tokenizer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.attestation import AttestationPayload, AttestationVerifier, parse_attestation
from intake_api.audit import AuditWriter
from intake_api.carrier_geo import CarrierGeoCheck
from intake_api.auth_store import (
    ACCESS_TTL_S,
    CHALLENGE_TTL_S,
    OTP_CODE_DIGITS,
    RESEND_COOLDOWN_S,
    AuthStore,
    code_digest,
)
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
    otp_invalid,
    otp_limited,
    phone_invalid,
    refresh_reused,
    unauthorized,
)

__all__ = [
    "ATTESTATION_HEADER",
    "CONSUMER_TENANT_ID",
    "AuthWiring",
    "DeliveryReceipt",
    "DevLogDeliveryAdapter",
    "OtpAuthService",
    "OtpDeliveryAdapter",
    "TokenBundle",
    "ensure_consumer_tenant",
    "normalise_tr_phone",
]

logger = logging.getLogger("intake_api.otp")

ATTESTATION_HEADER = "X-Intake-Attestation"

# Consumer-app tenant (files/06 §1: INTAKE is controller for the consumer
# app). Fixed UUIDv5 key → idempotent bootstrap, same shape as dev_fixture.
CONSUMER_TENANT_ID = uuid.uuid5(uuid.NAMESPACE_URL, "https://intake.app/tenants/consumer")

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


class OtpDeliveryAdapter(Protocol):
    """The SMS seam. The vendor adapter implements this once a contract
    exists (awaiting-human — docs/evidence/INT-131.md); until then only the
    dev adapter below is wired, and it never claims an SMS went out."""

    def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt: ...


class DevLogDeliveryAdapter:
    """Records the delivery EVENT with ids only (invariant 6): no code, no
    phone, no vendor claim. The code is reachable exclusively through the
    peek endpoint behind INTAKE_DEV_OTP_PEEK=explicit-yes."""

    def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
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


def _device_ref(device_id: str) -> str:
    """Redis key material for the per-device window — a digest, never the id."""
    return hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:32]


class OtpAuthService:
    """Orchestrates the OTP tier. Store calls hop off the event loop via
    ``asyncio.to_thread`` (sync Redis client, INT-012 precedent)."""

    def __init__(self, wiring: AuthWiring, *, engine: AsyncEngine, audit: AuditWriter) -> None:
        self._wiring = wiring
        self._store = AuthStore(wiring.redis_client, wiring.now_fn)
        self._tokenizer = wiring.tokenizer
        self._engine = engine
        self._audit = audit

    def _now(self) -> float:
        return self._wiring.now_fn() if self._wiring.now_fn is not None else time.time()

    # --- attestation (files/10 §2: on OTP request AND session start) --------------

    async def issue_challenge(self) -> dict[str, object]:
        challenge = await asyncio.to_thread(self._store.issue_challenge)
        return {"challenge": challenge, "expires_in": CHALLENGE_TTL_S}

    async def _require_attested(self, request: Request) -> AttestationPayload:
        raw = request.headers.get(ATTESTATION_HEADER)
        if raw is None:
            raise attestation_required()
        payload = parse_attestation(raw)
        if payload is None:
            raise attestation_invalid()
        result = self._wiring.attestation.verify(payload)
        if not result.ok:
            # ids-only breadcrumb; the reason code carries no device data
            logger.info("attestation refused reason=%s", result.reason)
            raise attestation_unverified()
        if not await asyncio.to_thread(self._store.consume_challenge, payload.nonce):
            raise challenge_invalid()
        return payload

    def _require_phone(self, raw: str) -> tuple[str, str]:
        phone = normalise_tr_phone(raw)
        if phone is None:
            raise phone_invalid()
        return phone, self._tokenizer.pseudonym(phone)

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

    async def request_code(self, request: Request, phone_raw: str) -> dict[str, object]:
        payload = await self._require_attested(request)
        phone, pseudonym = self._require_phone(phone_raw)
        ip = request.client.host if request.client is not None else "unknown"
        retry_after = await asyncio.to_thread(
            self._store.otp_request_gate, pseudonym, ip, _device_ref(payload.device_id)
        )
        if retry_after is not None:
            raise otp_limited(retry_after)
        code = f"{secrets.randbelow(10**OTP_CODE_DIGITS):0{OTP_CODE_DIGITS}d}"
        await asyncio.to_thread(
            self._store.store_code,
            pseudonym,
            code_digest(pseudonym, code),
            code if self._wiring.dev_otp_peek else None,
        )
        receipt = self._wiring.delivery.send(phone_e164=phone, code=code)
        await self._audit.record(
            actor=f"phone:{self._tokenizer.log_ref(phone)}",
            action="auth.otp.requested",
            resource_ref=f"delivery:{receipt.delivery_id}",
            consent_scope="scope:auth",
        )
        return {"delivery_id": receipt.delivery_id, "resend_after_s": RESEND_COOLDOWN_S}

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

    async def verify_code(self, request: Request, phone_raw: str, code: str) -> TokenBundle:
        await self._require_attested(request)
        phone, pseudonym = self._require_phone(phone_raw)
        jkt = await self._verify_proof(request)
        verdict = await asyncio.to_thread(
            self._store.check_code, pseudonym, code_digest(pseudonym, code)
        )
        if verdict != "ok":
            # one generic refusal for wrong/expired/exhausted (02 §8.2)
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
