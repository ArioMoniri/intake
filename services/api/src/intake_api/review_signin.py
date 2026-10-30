"""INT-488 — the App Store review sign-in (owner decision D39, 30 Oct 2026).

A release build signs in only by an SMS code (INT-131), and an App Review
reviewer cannot receive one. D39 approves one way in for the reviewer. This
module holds the account, the gate and the owner's command; the request and
verify steps are ``intake_api.review_flow``, the window and the live guards
``intake_api.review_window``, the reset between reviews
``intake_api.review_reset``.

- **The account lives in OpenBao only**, at ``secret/api/review_signin``:
  ``{"number", "code"}``, both drawn from the host's CSPRNG by
  ``infra/staging/review_signin.sh --generate`` and read by the API under a
  read-only grant. The API keeps the number only as its Tokenizer pseudonym
  and the code only as an HMAC under the OTP pepper (``OtpPepper.review_code``).
- **The number is reserved**: wherever the document is readable, a request for
  it never reaches the SMS vendor, whatever the window or the gate says.
- **Only the synthetic host's synthetic tenant** (:func:`review_gate`, read at
  start): the environment is the synthetic host's, the image's baked data class
  is ``synthetic``, the tenant's real-patient flag (INT-465's tenant kind,
  ``real`` by default) says ``synthetic``, and the deployment is named. Live,
  on every step (``ReviewGuards``): the bound data class is not ``real_phi``,
  and hosted model lanes are switched off for the reviewer's tenant.
- **A review window, default OFF**, flipped by ``python -m
  intake_api.review_cli on|off``, every flip on the hash chain. Opening and
  closing both empty the reviewer tenant (the reviewer is a real person), and
  closing ends every reviewer session.
- **A synthetic reviewer patient per window**, in its own tenant, keyed by a
  fixed synthetic label, never by a number's pseudonym.

Every use is counted (``sec_review_signin_total``, every label pair created at
zero, so the first use of each kind alerts) and alerted on (``ReviewSignInUsed``,
``ReviewSignInRefused``). The runbook is ``docs/runbooks/review-signin.md``.
"""

from __future__ import annotations

import hmac
import logging
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

import httpx
from intake_platform.db.models import KvkkRole, Patient, Tenant
from intake_platform.model_lanes.model import ModelLanesControl, TenantDataClass
from intake_platform.model_lanes.store import ModelLanesUnavailable, model_lanes_store_from_env
from intake_platform.red_tenant import TenantKind
from intake_platform.secrets import SecretsBootError, SecretsProvider
from intake_platform.tokenization import Tokenizer
from intake_platform.voice_control.store import voice_control_store_from_env
from prometheus_client import Counter, Gauge
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.auth_store import OTP_CODE_DIGITS
from intake_api.db import tenant_session
from intake_api.otp_pepper import OtpPepper
from intake_api.review_record import review_record_problem
from intake_api.review_window import (
    REVIEW_TENANT_ID,
    ReviewGuards,
    ReviewWindow,
    review_patient,
)
from intake_api.settings import ApiSettings
from intake_api.sms_recipients import SYNTHETIC_ENVIRONMENTS

__all__ = [
    "GATE_FACTS",
    "REVIEW_LABELS",
    "REVIEW_MISS_CAP",
    "REVIEW_OUTCOMES",
    "REVIEW_SIGNIN_KV_PATH",
    "REVIEW_STEPS",
    "REVIEW_SIGNIN_DOCUMENT_UNREADABLE",
    "REVIEW_TENANT_ID",
    "SEC_REVIEW_SIGNIN_TOTAL",
    "ReviewGuards",
    "ReviewSignIn",
    "ReviewWindow",
    "ensure_review_patient",
    "ensure_review_tenant",
    "review_gate",
    "review_guards_from_env",
    "review_patient",
    "review_readiness",
    "review_signin_from_vault",
]

logger = logging.getLogger("intake_api.review_signin")

#: KV v2 path under ``secret/``; the intake-api policy grants read and nothing else.
REVIEW_SIGNIN_KV_PATH: Final = "api/review_signin"
_NUMBER: Final = re.compile(r"\+905[0-9]{9}")
_CODE: Final = re.compile(rf"[0-9]{{{OTP_CODE_DIGITS}}}")
REVIEW_TENANT_NAME: Final = "App Review reviewer (synthetic)"

#: The facts :func:`review_gate` checks, by the name a refusal reports.
GATE_FACTS: Final = ("environment", "data_class", "tenant_kind", "deployment")

#: Counted misses on one generated code before the window closes itself. The
#: code is fixed, so every miss rules one candidate out for good; the INT-578
#: lockout allows five an hour, and this ends a slow guess after three
#: lockouts. An engineering default (docs/evidence/INT-488.md), not D39's.
REVIEW_MISS_CAP: Final = 15

#: ``sec_review_signin_total``'s closed label pairs, by step. A request is
#: admitted (a code record minted; nothing is ever sent), withheld (the
#: number's own budget), locked (the INT-578 lockout), limited (the caller's
#: device or address budget), or refused: not_synthetic, hosted_lanes_open,
#: window_closed, unconfigured, code_retired (the miss cap retired the code).
#: A verify is signed_in, an INT-578 verdict (invalid, unbound, missing,
#: exhausted), locked, or refused the same ways.
REVIEW_LABELS: Final[Mapping[str, frozenset[str]]] = {
    "request": frozenset(
        {
            "admitted",
            "withheld",
            "locked",
            "limited",
            "not_synthetic",
            "hosted_lanes_open",
            "window_closed",
            "unconfigured",
            "code_retired",
        }
    ),
    "verify": frozenset(
        {
            "signed_in",
            "invalid",
            "unbound",
            "missing",
            "exhausted",
            "locked",
            "not_synthetic",
            "hosted_lanes_open",
            "window_closed",
            "unconfigured",
            "code_retired",
        }
    ),
}
REVIEW_STEPS: Final = frozenset(REVIEW_LABELS)
REVIEW_OUTCOMES: Final = frozenset().union(*REVIEW_LABELS.values())

#: 1 while OpenBao could not answer for the reviewer document at start (not
#: "absent": unreachable, refused, malformed), else 0. Security review N3.
REVIEW_SIGNIN_DOCUMENT_UNREADABLE: Final = Gauge(
    "review_signin_document_unreadable",
    "1 while OpenBao could not be read for the App Review reviewer document, else 0.",
)
SEC_REVIEW_SIGNIN_TOTAL: Final = Counter(
    "sec_review_signin_total",
    "Uses of the App Review sign-in, by step (request, verify) and outcome.",
    ("step", "outcome"),
)
# Every pair exists at zero from the start: a series born at one is invisible
# to increase(), so the first use of a kind would not alert (security review).
for _step, _outcomes in REVIEW_LABELS.items():
    for _outcome in _outcomes:
        SEC_REVIEW_SIGNIN_TOTAL.labels(step=_step, outcome=_outcome)


class KvSecrets(Protocol):
    """The slice of :class:`intake_platform.secrets.SecretsProvider` read here."""

    def get_kv(self, path: str) -> dict[str, Any]: ...


# --- the gate ----------------------------------------------------------------------------------


def review_gate(settings: ApiSettings) -> tuple[str, ...]:
    """The :data:`GATE_FACTS` this deployment fails; empty only on the
    synthetic host's synthetic tenant. Each defaults to the real reading."""
    failed: list[str] = []
    if settings.environment not in SYNTHETIC_ENVIRONMENTS:
        failed.append("environment")
    if settings.deployment_data_class is not TenantDataClass.SYNTHETIC:
        failed.append("data_class")
    if settings.triage_tenant_kind is not TenantKind.SYNTHETIC:
        # INT-465: the tenant's real-patient flag. A tenant that has not said it
        # is synthetic may see a real patient.
        failed.append("tenant_kind")
    if not settings.triage_deployment:
        failed.append("deployment")
    return tuple(failed)


class _UnreadableLanes:
    """A model-lane control address that is not a redis URL: every read fails,
    so the bound class reads ``real_phi``."""

    def read(self) -> ModelLanesControl:
        raise ModelLanesUnavailable("model_lanes_malformed")


def review_guards_from_env(environ: Mapping[str, str]) -> ReviewGuards:
    """The live guards, from the stores the router itself reads."""
    try:
        lanes: Any = model_lanes_store_from_env(environ)
    except ValueError:
        lanes = _UnreadableLanes()
    try:
        voice = voice_control_store_from_env(environ)
    except ValueError:
        voice = None
    return ReviewGuards(lanes=lanes, voice=voice)


# --- the account, as the API holds it --------------------------------------------------------


@dataclass(frozen=True)
class ReviewSignIn:
    """The reviewer account as the API holds it: the reviewer number's
    pseudonym, its code as an HMAC under the OTP pepper (None when the document
    holds no usable code), the gate facts this deployment fails, and the live
    guards. ``repr`` and ``str`` show no value."""

    pseudonym: str = field(repr=False)
    code_key: str | None = field(repr=False)
    refused_by: tuple[str, ...] = ()
    guards: ReviewGuards = field(default_factory=ReviewGuards, repr=False, compare=False)

    def __str__(self) -> str:
        return f"ReviewSignIn(admitted={self.admitted})"

    @property
    def admitted(self) -> bool:
        return not self.refused_by

    def matches(self, pseudonym: str) -> bool:
        return hmac.compare_digest(self.pseudonym, pseudonym)

    @classmethod
    def build(
        cls,
        *,
        number: str,
        code: str | None,
        tokenizer: Tokenizer,
        pepper: OtpPepper,
        refused_by: tuple[str, ...] = (),
        guards: ReviewGuards | None = None,
    ) -> ReviewSignIn:
        return cls(
            pseudonym=tokenizer.pseudonym(number),
            code_key=pepper.review_code(code) if code is not None else None,
            refused_by=refused_by,
            guards=guards if guards is not None else ReviewGuards(),
        )


def _document_values(document: Mapping[str, object]) -> tuple[str | None, str | None]:
    number = document.get("number")
    code = document.get("code")
    return (
        number if isinstance(number, str) and _NUMBER.fullmatch(number) else None,
        code if isinstance(code, str) and _CODE.fullmatch(code) else None,
    )


def _absent(exc: Exception) -> bool:
    """A document that does not exist, as opposed to an OpenBao that cannot answer."""
    if isinstance(exc, KeyError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404


def _read_document(secrets: KvSecrets | None) -> Mapping[str, object] | None:
    try:
        vault = secrets if secrets is not None else SecretsProvider.from_env()
        document = vault.get_kv(REVIEW_SIGNIN_KV_PATH)
    except (SecretsBootError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        if _absent(exc):
            REVIEW_SIGNIN_DOCUMENT_UNREADABLE.set(0)
            logger.info(
                "review sign-in not configured: no document at OpenBao secret/%s",
                REVIEW_SIGNIN_KV_PATH,
            )
        else:
            # security review N3: an OpenBao that cannot answer is not "no reviewer"
            REVIEW_SIGNIN_DOCUMENT_UNREADABLE.set(1)
            logger.warning(
                "review sign-in not configured: OpenBao secret/%s could not be read (%s)",
                REVIEW_SIGNIN_KV_PATH,
                type(exc).__name__,
            )
        return None
    REVIEW_SIGNIN_DOCUMENT_UNREADABLE.set(0)
    return document


def review_signin_from_vault(
    secrets: KvSecrets | None,
    *,
    settings: ApiSettings,
    tokenizer: Tokenizer,
    pepper: OtpPepper,
    guards: ReviewGuards | None = None,
) -> ReviewSignIn | None:
    """The reviewer account, or None when the document is absent or its number
    malformed. The plaintext code exists only inside this call; log lines name
    the path, the field and the failed gate facts, never a value."""
    document = _read_document(secrets)
    if document is None:
        return None
    number, code = _document_values(document)
    if number is None:
        logger.warning(
            "review sign-in not configured: OpenBao secret/%s has no well-formed number",
            REVIEW_SIGNIN_KV_PATH,
        )
        return None
    if code is None:
        logger.warning(
            "review sign-in: OpenBao secret/%s has no well-formed code; the reviewer number "
            "is reserved and answers review_signin_unconfigured (run --generate)",
            REVIEW_SIGNIN_KV_PATH,
        )
    failed = review_gate(settings)
    if failed:
        logger.warning(
            "review sign-in refused on this deployment (D39: the synthetic host's synthetic "
            "tenant only): %s; the reviewer number is reserved and never sent",
            ", ".join(failed),
        )
    return ReviewSignIn.build(
        number=number,
        code=code,
        tokenizer=tokenizer,
        pepper=pepper,
        refused_by=failed,
        guards=guards,
    )


def review_readiness(
    settings: ApiSettings,
    secrets: KvSecrets | None,
    guards: ReviewGuards,
    record: Callable[[], str | None] = review_record_problem,
) -> str | None:
    """Why the window may not open here, or None: the owner's ``on`` refuses
    unless a reviewer could sign in, and unless the reviewer's processing
    record and notice are complete and hash-bound (``intake_api.review_record``).
    Names facts, never a value."""
    failed = review_gate(settings)
    if failed:
        return "not the synthetic host's synthetic tenant (" + ", ".join(failed) + ")"
    live = guards.refusal()
    if live == "not_synthetic":
        return "the deployment's bound data class is not synthetic (ADR-035)"
    if live == "hosted_lanes_open":
        return (
            f"hosted model lanes are not switched off for the reviewer tenant {REVIEW_TENANT_ID}: "
            "engage its kill switch in the admin console's voice controls first"
        )
    document = _read_document(secrets)
    if document is None:
        return f"no reviewer document at OpenBao secret/{REVIEW_SIGNIN_KV_PATH}: run --generate"
    number, code = _document_values(document)
    if number is None or code is None:
        return f"no well-formed reviewer number and code at secret/{REVIEW_SIGNIN_KV_PATH}"
    return record()


# --- the reviewer's tenant and patient --------------------------------------------------------


async def ensure_review_tenant(engine: AsyncEngine) -> None:
    """Idempotent: the reviewer tenant (tenant INSERT needs the owner engine,
    like the consumer tenant). Called at start only where the gate admits."""
    async with tenant_session(engine, REVIEW_TENANT_ID) as session:
        if await session.get(Tenant, REVIEW_TENANT_ID) is None:
            session.add(
                Tenant(
                    id=REVIEW_TENANT_ID,
                    display_name=REVIEW_TENANT_NAME,
                    kvkk_role=KvkkRole.CONTROLLER,
                )
            )


async def ensure_review_patient(engine: AsyncEngine, window_id: str) -> tuple[uuid.UUID, bool]:
    """The window's synthetic reviewer patient id, and whether this call
    created it."""
    patient_id, pseudonym = review_patient(window_id)
    async with tenant_session(engine, REVIEW_TENANT_ID) as session:
        if await session.get(Patient, patient_id) is not None:
            return patient_id, False
        session.add(Patient(id=patient_id, tenant_id=REVIEW_TENANT_ID, pseudonym=pseudonym))
    return patient_id, True
