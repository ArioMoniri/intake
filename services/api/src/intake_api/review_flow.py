"""INT-488 — the App Review reviewer's request and verify steps (D39).

``intake_api.otp`` hands a request or a verify here when, and only when, its
number's pseudonym is the reserved reviewer number's. From then on nothing
reaches the SMS vendor: this module has no delivery adapter at all.

It reuses INT-578 exactly, so the reviewer is held to the same code rules as
any patient: the request mints an ordinary code record — an HMAC under the OTP
pepper over (pseudonym, request id, the reviewer code's own HMAC), bound to the
device that asked — and the verify spends one attempt of the NUMBER's budget
through :meth:`AuthStore.check_code`. A wrong code is a miss like any other;
the fifth in a rolling hour locks the number for a whole window. Because the
code is fixed, misses also add up per generated code: the
:data:`~intake_api.review_signin.REVIEW_MISS_CAP`-th closes the window and
retires the code, so reopening the window buys no more guesses. The
request is under the number's, the device's and the address's budgets and the
resend backoff; it is not charged to the SMS spend caps, because it sends
nothing, but the spend kill switch is read before it, as for every number.

Refusals, in the order of D39's clauses: a deployment that is not the
synthetic host's synthetic tenant (the start-time gate, then the bound data
class), hosted lanes not switched off for the reviewer tenant, a closed window
(all withheld: the answer an admission gets, with nothing minted), then a
document with no usable code (a typed 503). Every step is counted and appended
to the hash chain with ids only: the number appears as its 8-character log ref.

Each window has its own reviewer patient (``review_window.review_patient``),
and every reviewer session is bound to the window it was issued in: a token
from one review is dead in every later one.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from collections.abc import Awaitable, Callable
from functools import partial

import redis
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.audit import AuditWriter
from intake_api.auth_store import REFRESH_TTL_S, AuthStore
from intake_api.errors import otp_invalid, otp_limited, review_signin_unconfigured
from intake_api.otp_pepper import OtpPepper
from intake_api.review_reset import (
    REVIEW_RESET_FAILURES_TOTAL,
    ReviewReset,
    unerased_review_subjects,
)
from intake_api.review_signin import (
    REVIEW_MISS_CAP,
    SEC_REVIEW_SIGNIN_TOTAL,
    ReviewSignIn,
    ensure_review_patient,
)
from intake_api.review_window import (
    REVIEW_WINDOW_S,
    UNATTRIBUTED_CLOSE,
    ReviewWindow,
    ReviewWindowUnreadable,
    WindowState,
)
from intake_api.sms_spend import DAY_S

__all__ = ["ReviewSignInFlow"]

logger = logging.getLogger("intake_api.review_signin")

_SCOPE = "scope:auth"
#: Set while an unattended erasure is failing, so its row is written once per episode.
_RESET_FAILING_KEY = "auth:review:reset_failing"


class ReviewSignInFlow:
    """The reviewer's two steps over the OTP tier's own store, pepper and chain."""

    def __init__(
        self,
        review: ReviewSignIn,
        *,
        store: AuthStore,
        pepper: OtpPepper,
        window: ReviewWindow,
        audit: AuditWriter,
        engine: AsyncEngine,
        redis_client: redis.Redis,
        reset: ReviewReset | None = None,
    ) -> None:
        self._review = review
        self._store = store
        self._pepper = pepper
        self._window = window
        self._audit = audit
        self._engine = engine
        self._r = redis_client
        # the reviewer tenant's erasure (intake_api.review_reset), which only
        # the API's sweep runs, never a reviewer's request; None erases nothing
        self._reset = reset

    async def _close_recorded(self, *, actor: str, expect_id: str | None = None) -> bool:
        """Close the window, then record it. The close is noted before its row
        is tried, so a row lost to a failed append or a crash is re-recorded
        by the next sweep, under the same actor (security review N2)."""
        if not await asyncio.to_thread(partial(self._window.close, expect_id=expect_id)):
            return False
        await asyncio.to_thread(self._window.note_unrecorded_close, actor)
        await self._record_closes()
        return True

    async def _record_closes(self) -> None:
        """Append the row of every close still waiting for one, oldest first.
        An entry naming no close actor is on the chain as an unattributed close
        under the API's own actor, never under its own words (security review R3)."""
        while (actor := await asyncio.to_thread(self._window.first_unrecorded_close)) is not None:
            unattributed = actor == UNATTRIBUTED_CLOSE
            await self._audit.record(
                actor="system:review-guard" if unattributed else actor,
                action=(
                    "auth.review.window.closed_unattributed"
                    if unattributed
                    else "auth.review.window.closed"
                ),
                resource_ref="review_signin:window",
                consent_scope=_SCOPE,
            )
            await asyncio.to_thread(self._window.recorded_close)

    async def expire_if_due(self) -> bool:
        """Close a window whose time has run out, as ``--off`` closes one: the
        document first, then the row (``system:review-expiry``). The window
        already reads closed to every reviewer step from the instant it
        expired; this only records it. The erasure is left to the sweep (it
        never runs on a reviewer's request). True when this call closed it —
        of several callers racing, exactly one."""
        state = await asyncio.to_thread(self._window.due_for_expiry)
        if state is None:
            return False
        if not await self._close_recorded(actor="system:review-expiry", expect_id=state.id):
            return False
        logger.warning("review window closed itself: its %d days ran out", REVIEW_WINDOW_S // DAY_S)
        return True

    async def sweep(self) -> None:
        """The API's own sweep, once a minute: record a close whose row was
        lost, close an expired window, then retry an erasure still pending.
        The stages are isolated (security review R3): one that fails is logged
        by type and the next still runs, so nothing on the close queue or in
        the audit store can hold the expiry or the erasure back."""
        stages: tuple[tuple[str, Callable[[], Awaitable[object]]], ...] = (
            ("record_closes", self._record_closes),
            ("expire", self.expire_if_due),
            ("erase", self._erase_pending),
        )
        for name, stage in stages:
            try:
                await stage()
            except Exception as exc:  # noqa: BLE001 — one stage never stops the next
                logger.warning("review sweep stage %s failed (%s)", name, type(exc).__name__)

    async def _erase_pending(self) -> None:
        """Erase the reviewer tenant while no window is open and a reviewer
        subject is unerased. A failure counts toward the page every time and is
        on the chain once per failing episode, its refusal rows included
        (security review R2); the next sweep tries again."""
        if self._reset is None:
            return
        try:
            if await asyncio.to_thread(self._window.state) is not None:
                return  # never under a live review, and an expired one is closed first
        except ReviewWindowUnreadable:
            return
        if await unerased_review_subjects(self._engine) == 0:
            await asyncio.to_thread(self._r.delete, _RESET_FAILING_KEY)
            return
        failing = bool(await asyncio.to_thread(self._r.exists, _RESET_FAILING_KEY))
        try:
            await self._reset("system:review-expiry", record_blocked=not failing)
        except Exception as exc:  # noqa: BLE001 — a pending erasure pages and is retried
            REVIEW_RESET_FAILURES_TOTAL.inc()
            logger.warning(
                "review tenant erasure failed (%s); the next sweep retries it", type(exc).__name__
            )
            if not failing:
                await self._audit.record(
                    actor="system:review-expiry",
                    action="auth.review.reset_failed",
                    resource_ref="review_signin:reset",
                    consent_scope=_SCOPE,
                )
                await asyncio.to_thread(self._r.set, _RESET_FAILING_KEY, "1")
            return
        await asyncio.to_thread(self._r.delete, _RESET_FAILING_KEY)

    def matches(self, pseudonym: str) -> bool:
        return self._review.matches(pseudonym)

    def _live(self) -> tuple[str | None, WindowState | None]:
        """Why a reviewer may not proceed now, and the open window. Sync: it
        reads Redis, so callers hop it off the loop."""
        if not self._review.admitted:
            return "not_synthetic", None
        guarded = self._review.guards.refusal()
        if guarded is not None:
            return guarded, None
        window = self._window.current()
        if window is None:
            return "window_closed", None
        if self._review.code_key is None:
            return "unconfigured", window
        misses = self._r.get(self._misses_key(self._review.code_key))
        if misses is not None and int(misses) >= REVIEW_MISS_CAP:
            # the code that reached its cap stays retired: reopening the window
            # buys no more guesses, only --generate does (security review)
            return "code_retired", window
        return None, window

    def _misses_key(self, code_key: str) -> str:
        return f"auth:review:misses:{self._pepper.rate_key('review_generation', code_key)}"

    async def _record(
        self, step: str, outcome: str, *, actor: str, action: str, resource: str
    ) -> None:
        SEC_REVIEW_SIGNIN_TOTAL.labels(step=step, outcome=outcome).inc()
        if outcome not in ("admitted", "signed_in"):
            logger.info("review sign-in %s refused: %s", step, outcome)
        await self._audit.record(
            actor=actor, action=action, resource_ref=resource, consent_scope=_SCOPE
        )

    # --- sessions ------------------------------------------------------------------------

    def _session_key(self, token_hash: str) -> str:
        return f"auth:review:session:{token_hash}"

    async def bind_session(self, *token_hashes: str) -> None:
        """Bind freshly issued reviewer tokens to the window they were issued in."""
        window = await asyncio.to_thread(self._window.current)
        if window is None:
            return
        for token_hash in token_hashes:
            await asyncio.to_thread(
                partial(self._r.set, self._session_key(token_hash), window.id, ex=REFRESH_TTL_S)
            )

    async def session_live(self, token_hash: str) -> bool:
        """A reviewer token lives only inside the window it was issued in, and
        only while a reviewer could sign in. Closing the window ends it."""
        await self.expire_if_due()
        refusal, window = await asyncio.to_thread(self._live)
        if refusal is not None or window is None:
            return False
        bound = await asyncio.to_thread(self._r.get, self._session_key(token_hash))
        if bound is None:
            return False
        held = bound.decode("ascii") if isinstance(bound, bytes) else str(bound)
        return held == window.id

    # --- the two steps -----------------------------------------------------------------------

    async def request(
        self, *, pseudonym: str, ip_key: str, device_key: str, binding: str, actor: str
    ) -> dict[str, object]:
        await self.expire_if_due()
        refusal, _ = await asyncio.to_thread(self._live)
        if refusal == "unconfigured":
            await self._record(
                "request",
                "unconfigured",
                actor=actor,
                action="auth.review.refused",
                resource="review:unconfigured",
            )
            raise review_signin_unconfigured()
        locked = await asyncio.to_thread(self._store.lockout_wait, pseudonym) is not None
        decision = await asyncio.to_thread(
            partial(
                self._store.otp_request_decision,
                pseudonym,
                ip_key,
                device_key,
                backoff=True,
                withhold=locked or refusal is not None,
            )
        )
        if not decision.admitted and not decision.withheld:
            await self._record(
                "request",
                "limited",
                actor=actor,
                action="auth.review.refused",
                resource="review:limited",
            )
            raise otp_limited(decision.wait)
        request_id = secrets.token_hex(16)
        code_key = self._review.code_key
        if decision.withheld or code_key is None:
            outcome = refusal or ("locked" if locked else "withheld")
            await asyncio.to_thread(self._store.withhold_code)
            await self._record(
                "request",
                outcome,
                actor=actor,
                action="auth.review.refused",
                resource=f"review:{outcome}",
            )
        else:
            digest = self._pepper.code_digest(pseudonym, request_id, code_key)
            # never a dev peek copy: the API does not hold the code to copy
            await asyncio.to_thread(
                partial(self._store.store_code, pseudonym, digest, None, binding=binding)
            )
            await self._record(
                "request",
                "admitted",
                actor=actor,
                action="auth.review.requested",
                resource=f"request:{request_id}",
            )
        return {"request_id": request_id, "resend_after_s": int(decision.wait)}

    async def verify(
        self, *, pseudonym: str, request_id: str, code: str, binding: str, actor: str
    ) -> uuid.UUID:
        """The window's reviewer patient id, or a refusal: the generic
        ``otp_invalid`` for every wrong, spent, stray or locked code and every
        refused deployment or closed window, the typed 503 for an open window
        with no code."""
        await self.expire_if_due()
        refusal, window = await asyncio.to_thread(self._live)
        if refusal == "unconfigured":
            await self._record(
                "verify",
                "unconfigured",
                actor=actor,
                action="auth.review.verify_refused",
                resource="otp_verify:unconfigured",
            )
            raise review_signin_unconfigured()
        code_key = self._review.code_key
        if refusal is not None or window is None or code_key is None:
            outcome = refusal or "window_closed"
            await self._record(
                "verify",
                outcome,
                actor=actor,
                action="auth.review.verify_refused",
                resource=f"otp_verify:{outcome}",
            )
            raise otp_invalid()
        locked = await asyncio.to_thread(self._store.lockout_wait, pseudonym) is not None
        submitted = self._pepper.code_digest(pseudonym, request_id, self._pepper.review_code(code))
        verdict = await asyncio.to_thread(
            partial(
                self._store.check_code, pseudonym, submitted, binding=binding, charge=not locked
            )
        )
        if verdict == "exhausted" and not locked:
            # INT-578: the miss that spent the number's budget locks it
            await asyncio.to_thread(self._store.engage_lockout, pseudonym)
        outcome = "locked" if locked else verdict
        if outcome != "ok":
            await self._record(
                "verify",
                outcome,
                actor=actor,
                action="auth.review.verify_refused",
                resource=f"otp_verify:{outcome}",
            )
            if outcome in ("invalid", "exhausted"):
                await self._count_miss(code_key)
            raise otp_invalid()
        patient_id, created = await ensure_review_patient(self._engine, window.id)
        if created:
            await self._audit.record(
                actor=f"patient:{patient_id}",
                action="auth.account.created",
                resource_ref=f"patient:{patient_id}",
                consent_scope=_SCOPE,
            )
        await self._record(
            "verify",
            "signed_in",
            actor=f"patient:{patient_id}",
            action="auth.review.signed_in",
            resource=f"patient:{patient_id}",
        )
        return patient_id

    async def _count_miss(self, code_key: str) -> None:
        """A miss against the fixed code rules a candidate out for good, so
        misses add up per generated code; the cap closes the window."""
        key = self._misses_key(code_key)
        misses = int(await asyncio.to_thread(self._r.incr, key))
        if misses < REVIEW_MISS_CAP:
            await asyncio.to_thread(partial(self._r.expire, key, REFRESH_TTL_S))
            return
        # the latch: kept until a new code makes a new key
        await asyncio.to_thread(self._r.persist, key)
        if await self._close_recorded(actor="system:review-guard"):
            logger.warning("review window closed: the reviewer code reached its miss cap")
