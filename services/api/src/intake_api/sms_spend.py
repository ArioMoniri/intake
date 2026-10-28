"""INT-577 — the SMS spend controls: the send caps and the spend kill switch.

The owner's order of 28 Oct 2026 asked for "all security measures to stop … sms
loading … overuse". INT-131's per-number, per-IP and per-device budgets bound
what one caller can cost; nothing bounded the sum. A pumping attack spread over
many numbers, devices and addresses — each inside its own budget — had no
ceiling at all. This module is that ceiling, in three parts:

- **the tenant hour budget** — every code minted for one tenant in a rolling
  hour (the patient OTP tier is the consumer tenant's);
- **the global hour cap** — every code minted, in a rolling hour; reaching it
  refuses with the usual 429 and rolls on, like any budget;
- **the global day cap, and the kill switch it trips** — reaching it LATCHES
  the spend kill switch. Every send then stops, for everyone, until an
  operator releases it (``python -m intake_api.sms_spend release``, on the
  host). A day window that rolls over does not release it: a pump that ran the
  bill to the ceiling is an incident, and a human decides when sending resumes.

**Fail closed.** The switch is read on every request, before any budget is
spent or any code minted. A switch that cannot be read (Redis unreachable) or
whose stored state cannot be parsed counts as engaged: the request answers the
generic 503 and nothing is sent. The kill switch only ever moves the system to
the safer state on its own; releasing it is a deliberate operator act, audited
on the hash chain (files/10 §2, "asymmetric authority"). The row is appended
FIRST and the switch released only when that succeeded, so a release the audit
store could not record does not happen.

**The alert.** ``sms_spend_kill_switch_engaged`` (a gauge, set on every read)
and ``sms_spend_kill_switch_trips_total{reason}``; the page is
``SmsSpendKillSwitchEngaged`` in ``infra/observability/security-rules.yaml``,
and the ops console's ``sms`` tile shows the switch and the request spike
(:func:`is_spike`, the one definition the alert ``OtpRequestSpike`` mirrors).

**The numbers are engineering defaults, not the owner's budget.** No SMS price
or monthly ceiling is recorded anywhere in this repository (the owner's Netgsm
account holds it). The caps below are sized from the pilot's planned volume —
50 concurrent intakes (files/00 §1), a sign-in per device and then 30-day
refresh tokens — with an order of magnitude of headroom, so that they only ever
bind on abuse. They are an owner input: the evidence for INT-577 asks for the
daily ceiling the owner is willing to pay for, and a change here is a reviewed
diff, never an environment variable.

Nothing here holds a number, a code, a device or an address: the counters are
sorted sets of admission instants under ``auth:otp:w:{tenant,global_*}`` and
the switch is one document under ``auth:otp:kill``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, TextIO

import redis
from prometheus_client import Counter, Gauge

__all__ = [
    "DAY_S",
    "GLOBAL_SENDS_PER_DAY",
    "GLOBAL_SENDS_PER_HOUR",
    "KILL_SWITCH_REASONS",
    "SMS_SPEND_KILL_SWITCH_ENGAGED",
    "SMS_SPEND_KILL_SWITCH_TRIPS_TOTAL",
    "SPIKE_FACTOR",
    "SPIKE_FLOOR_PER_HOUR",
    "TENANT_SENDS_PER_HOUR",
    "KillSwitchState",
    "SmsBudget",
    "SpendKillSwitch",
    "SpendStateUnreadable",
    "is_spike",
    "main",
]

logger = logging.getLogger("intake_api.sms_spend")

DAY_S: Final = 24 * 3600

# The owner's caps, D37 (files/00_STATE.md, 28 Oct 2026): 1000 a day globally,
# 120 an hour globally and 120 an hour per tenant; a breach of the day cap stops
# every send until the owner releases it. Every code a tenant or the platform
# may mint, counted over a rolling window.
TENANT_SENDS_PER_HOUR: Final = 120
GLOBAL_SENDS_PER_HOUR: Final = 120
GLOBAL_SENDS_PER_DAY: Final = 1000

#: A spike: the last hour's OTP requests over SPIKE_FACTOR times the hourly
#: rate of the last day AND over SPIKE_FLOOR_PER_HOUR, so a quiet night's
#: three requests are never a page. The alert rule carries the same numbers.
SPIKE_FACTOR: Final = 3
SPIKE_FLOOR_PER_HOUR: Final = 20

#: Why the switch is engaged: the day cap tripped it, or an operator did.
KILL_SWITCH_REASONS: Final = frozenset({"day_cap", "manual"})
_UNREADABLE_STATE: Final = "unreadable_state"

SMS_SPEND_KILL_SWITCH_ENGAGED: Final = Gauge(
    "sms_spend_kill_switch_engaged",
    "1 while the SMS spend kill switch is engaged (no OTP SMS is sent), else 0.",
)
SMS_SPEND_KILL_SWITCH_TRIPS_TOTAL: Final = Counter(
    "sms_spend_kill_switch_trips_total",
    "Times the SMS spend kill switch was engaged, by reason (day_cap, manual).",
    ("reason",),
)


@dataclass(frozen=True)
class SmsBudget:
    """The tenant and global send caps. Built from the defaults above; a test
    harness builds a small one."""

    tenant_sends_per_hour: int = TENANT_SENDS_PER_HOUR
    global_sends_per_hour: int = GLOBAL_SENDS_PER_HOUR
    global_sends_per_day: int = GLOBAL_SENDS_PER_DAY

    def __post_init__(self) -> None:
        for name in ("tenant_sends_per_hour", "global_sends_per_hour", "global_sends_per_day"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"SmsBudget.{name} must be a positive integer")


def is_spike(last_hour: float, last_day: float) -> bool:
    """The last hour against the day's own hourly rate (the ops tile and the
    ``OtpRequestSpike`` alert use this one definition)."""
    return last_hour > SPIKE_FACTOR * (last_day / 24) and last_hour > SPIKE_FLOOR_PER_HOUR


class SpendStateUnreadable(Exception):
    """The kill switch could not be read. The caller refuses (fail closed)."""


@dataclass(frozen=True)
class KillSwitchState:
    reason: str
    since: float


class SpendKillSwitch:
    """The latch, one Redis document. Synchronous, like the auth store: the
    service hops it off the event loop."""

    def __init__(
        self,
        redis_client: redis.Redis,
        now_fn: Callable[[], float] | None = None,
        key_prefix: str = "auth",
    ) -> None:
        self._r = redis_client
        self._now_fn = now_fn
        self._key = f"{key_prefix}:otp:kill"

    def _now(self) -> float:
        return self._now_fn() if self._now_fn is not None else time.time()

    def state(self) -> KillSwitchState | None:
        """The engaged state, or None when released. Raises
        :class:`SpendStateUnreadable` when the store cannot answer; a stored
        document that does not parse reads as engaged."""
        try:
            raw = self._r.get(self._key)
        except redis.RedisError:
            raise SpendStateUnreadable("the SMS spend kill switch is unreadable") from None
        if raw is None:
            SMS_SPEND_KILL_SWITCH_ENGAGED.set(0)
            return None
        SMS_SPEND_KILL_SWITCH_ENGAGED.set(1)
        try:
            document = json.loads(raw)
            reason, since = str(document["reason"]), float(document["since"])
        except (ValueError, KeyError, TypeError):
            return KillSwitchState(reason=_UNREADABLE_STATE, since=0.0)
        if reason not in KILL_SWITCH_REASONS:
            return KillSwitchState(reason=_UNREADABLE_STATE, since=since)
        return KillSwitchState(reason=reason, since=since)

    def engage(self, reason: str) -> bool:
        """Engage the switch. True when this call engaged it, False when it
        already was (the first reason and instant are kept)."""
        if reason not in KILL_SWITCH_REASONS:
            raise ValueError(f"unknown kill switch reason {reason!r}")
        document = json.dumps({"reason": reason, "since": self._now()})
        changed = bool(self._r.set(self._key, document, nx=True))
        SMS_SPEND_KILL_SWITCH_ENGAGED.set(1)
        if changed:
            SMS_SPEND_KILL_SWITCH_TRIPS_TOTAL.labels(reason=reason).inc()
            logger.warning("sms spend kill switch engaged reason=%s; no OTP SMS is sent", reason)
        return changed

    def release(self) -> bool:
        """Release the switch. True when it was engaged."""
        released = bool(self._r.delete(self._key))
        SMS_SPEND_KILL_SWITCH_ENGAGED.set(0)
        if released:
            logger.warning("sms spend kill switch released; OTP SMS sending resumes")
        return released


# --- the operator command -------------------------------------------------------------------

#: What each verb appends to the hash-chained audit log.
_AUDIT_ACTIONS: Final = {
    "engage": "sms.spend.kill_switch.engaged",
    "release": "sms.spend.kill_switch.released",
}


def _default_redis() -> redis.Redis:
    from intake_api.settings import ApiSettings

    return redis.Redis.from_url(ApiSettings.from_env().redis_url)


def _default_audit(action: str) -> None:
    """Append the operator's act to the API's own hash chain."""
    from intake_platform.audit import AuditChain
    from intake_platform.db.audit_store import SqlAlchemyAuditStore
    from sqlalchemy import create_engine

    from intake_api.settings import ApiSettings

    engine = create_engine(ApiSettings.from_env().audit_db_url)
    try:
        AuditChain(SqlAlchemyAuditStore(engine)).append(
            actor="operator:host",
            action=action,
            resource_ref="sms_spend:kill_switch",
            consent_scope_ref="scope:auth",
        )
    finally:
        engine.dispose()


def _describe(state: KillSwitchState | None) -> str:
    if state is None:
        return "sms spend kill switch: released (OTP SMS is sent)"
    since = datetime.fromtimestamp(state.since, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"sms spend kill switch: engaged reason={state.reason} since={since} (no OTP SMS is sent)"
    )


def _release_audited(switch: SpendKillSwitch, audit: Callable[[str], None], out: TextIO) -> bool:
    """Release an engaged switch only after its row is on the hash chain.

    The order is the control (security review, 28 Oct 2026): released first
    and audited after, a failed append left sending resumed with no record of
    who resumed it. A failed append leaves the switch engaged, and is named
    by its type only. A released switch writes no row. False when the release
    did not happen and the operator must act."""
    try:
        if switch.state() is None:
            return True
    except SpendStateUnreadable:
        print("sms spend kill switch: unreadable (the API refuses every send)", file=out)
        return False
    try:
        audit(_AUDIT_ACTIONS["release"])
    except Exception as exc:  # noqa: BLE001 — any failure to append must keep the switch on
        logger.warning(
            "kill switch release refused: the audit append failed (%s)", type(exc).__name__
        )
        print(
            "sms spend kill switch: the release could not be audited, so it stays engaged",
            file=out,
        )
        return False
    switch.release()
    return True


def main(
    argv: Sequence[str] | None = None,
    *,
    out: TextIO = sys.stdout,
    redis_factory: Callable[[], redis.Redis] = _default_redis,
    audit: Callable[[str], None] = _default_audit,
) -> int:
    """``python -m intake_api.sms_spend status|engage|release``, run inside the
    API container on the host (docs/runbooks/sms-abuse.md). Prints the state
    and nothing else; engage and release are appended to the audit chain."""
    parser = argparse.ArgumentParser(prog="intake_api.sms_spend", exit_on_error=False)
    parser.add_argument("verb")
    try:
        verb = parser.parse_args(list(argv) if argv is not None else None).verb
    except (argparse.ArgumentError, SystemExit):
        print("usage: python -m intake_api.sms_spend status|engage|release", file=out)
        return 2
    if verb not in ("status", "engage", "release"):
        print("usage: python -m intake_api.sms_spend status|engage|release", file=out)
        return 2
    switch = SpendKillSwitch(redis_factory())
    if verb == "engage":
        # stopping spend comes first; the row follows
        if switch.engage("manual"):
            audit(_AUDIT_ACTIONS["engage"])
    elif verb == "release" and not _release_audited(switch, audit, out):
        return 1
    try:
        print(_describe(switch.state()), file=out)
    except SpendStateUnreadable:
        print("sms spend kill switch: unreadable (the API refuses every send)", file=out)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
