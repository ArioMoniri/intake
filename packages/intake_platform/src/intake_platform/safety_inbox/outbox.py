"""The in-process half of the inbox: the RED path puts, a worker writes (INT-406).

The clinician route on the RED path has a port with **no awaitable member**
(``intake_voice_runtime.talker.red_path.ClinicNotifier``): it runs first and
must not delay the stop it runs before. A network write to the shared store
would be exactly such a delay — a store that is slow or down would sit in
front of a RED. So the route **puts** the entry here, which is a list append
under a lock, and returns; the entry exists in this process at the instant of
the RED, stamped with that instant. A worker thread (:meth:`pump`) writes it
to the store, woken by the put.

**What "within 60 s" means here, and how it is watched.** files/02 §8.2 wants
the clinic inbox to have the RED within 60 s. The pump writes on the put and,
while the store refuses, retries every :data:`PUMP_INTERVAL` — far inside the
budget. What cannot be engineered away is a store that stays down, so the age
of the oldest waiting entry is exported as ``clinic_red_inbox_pending_age_s``,
computed when Prometheus scrapes (not when the pump last ran, so a dead pump
cannot freeze it at zero), and ``RedInboxEntryLate`` pages above 60 s.

**Nothing is dropped.** A failed write keeps the entry, in order — whatever
the store raised (INT-475: a fault other than ``SafetyInboxUnavailable`` used
to end the pump and lose the batch it had taken, with nothing paging). Shutting
the pump down drains first (:meth:`wait_until_empty`), and an entry the store
already holds is not written twice (the store's ``add`` is idempotent). An
entry a pass has taken but not yet written is still waiting: it counts in
:meth:`pending`, in the age that pages, and in :meth:`wait_until_empty`.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from intake_platform.safety_inbox.metrics import CLINIC_RED_INBOX_PENDING_AGE_S
from intake_platform.safety_inbox.model import InboxEntry
from intake_platform.safety_inbox.store import SafetyInboxStore, SafetyInboxUnavailable

__all__ = ["PUMP_INTERVAL", "FlushReport", "SafetyInboxOutbox"]

logger = logging.getLogger("intake_platform.safety_inbox")

#: The retry cadence while the store refuses. An engineering bound, not a
#: clinical value: one attempt a second puts a recovered store's write within
#: a second of recovery, far inside the 60 s budget, for the cost of one
#: refused connection a second while it is down.
PUMP_INTERVAL: Final = timedelta(seconds=1)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class FlushReport:
    written: tuple[str, ...]
    pending: int
    oldest_pending_age_s: float


class SafetyInboxOutbox:
    def __init__(self, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._pending: list[InboxEntry] = []
        #: The batch a flush has taken and is writing (INT-475).
        self._in_flight: list[InboxEntry] = []
        self._lock = threading.Lock()
        self._changed = threading.Condition(self._lock)
        self._wake = threading.Event()
        self._stopped = threading.Event()
        # computed at scrape time, so the page does not depend on the pump
        CLINIC_RED_INBOX_PENDING_AGE_S.set_function(self.oldest_pending_age_s)

    def put(self, entry: InboxEntry) -> None:
        """The RED path's call: an append and a wake-up, nothing that waits."""
        with self._lock:
            self._pending.append(entry)
        self._wake.set()

    def pending(self) -> tuple[InboxEntry, ...]:
        """Every entry not yet in the store, in order — the one being written too."""
        with self._lock:
            return (*self._in_flight, *self._pending)

    def oldest_pending_age_s(self) -> float:
        with self._lock:
            waiting = self._in_flight + self._pending
            if not waiting:
                return 0.0
            oldest = min(entry.created_at for entry in waiting)
        return max(0.0, (self._clock() - oldest).total_seconds())

    def flush(self, store: SafetyInboxStore) -> FlushReport:
        """Write every waiting entry; keep, in order, any the store refused."""
        with self._lock:
            batch, self._pending = self._pending, []
            self._in_flight = batch
        written: list[str] = []
        kept: list[InboxEntry] = []
        for entry in batch:
            if kept:
                # the store refused an earlier one: keep order, try next pass
                kept.append(entry)
                continue
            try:
                store.add(entry)
            except SafetyInboxUnavailable:
                kept.append(entry)
                continue
            except Exception as fault:  # noqa: BLE001 - any fault keeps the entry and the pump
                # the type only (invariant 6); the entry's age pages if it persists
                logger.error("safety inbox write failed", extra={"error": type(fault).__name__})
                kept.append(entry)
                continue
            written.append(entry.entry_id)
        with self._changed:
            self._pending = kept + self._pending
            self._in_flight = []
            self._changed.notify_all()
        return FlushReport(
            written=tuple(written),
            pending=len(self.pending()),
            oldest_pending_age_s=self.oldest_pending_age_s(),
        )

    def pump(self, store: SafetyInboxStore, *, interval: timedelta = PUMP_INTERVAL) -> None:
        """Run until :meth:`stop`: write on every put, retry on the interval.

        Draining on the way out is the caller's :meth:`wait_until_empty`; the
        pump's last pass runs after the stop so nothing put before it waits.
        """
        while True:
            self.flush(store)
            if self._stopped.is_set():
                return
            self._wake.wait(interval.total_seconds())
            self._wake.clear()

    def stop(self) -> None:
        self._stopped.set()
        self._wake.set()

    def wait_until_empty(self, timeout: float) -> bool:
        """True once nothing waits; False if the timeout passed first."""
        with self._changed:
            return self._changed.wait_for(
                lambda: not self._pending and not self._in_flight, timeout=timeout
            )
