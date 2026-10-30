"""Async facade over the hash-chained audit log (INT-197; invariant 4).

The chain writer (`intake_platform.audit.AuditChain` over the store) is
synchronous by design; this facade serialises every use of the chain behind
one asyncio lock — the chain's running head must advance one entry at a time,
and the INT-034 DocumentStore appends to the SAME chain — and moves the
blocking work off the event loop. An audit failure propagates: a clinical
read that cannot be audited must not answer (fail closed).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import TypeVar

from intake_platform.audit import AuditChain, AuditEntry, AuditStore

__all__ = ["AuditWriter"]

_T = TypeVar("_T")


class AuditWriter:
    def __init__(self, store: AuditStore) -> None:
        self._store = store
        self._chain: AuditChain | None = None
        self._lock = asyncio.Lock()

    async def run_locked(self, fn: Callable[[AuditChain], _T]) -> _T:
        """Run ``fn`` with the (lazily resumed) chain, serialised and off the
        event loop. Everything that appends to the chain goes through here —
        two concurrent writers with private heads would fork the chain."""
        async with self._lock:
            if self._chain is None:
                # first use resumes the persisted chain (reads the tail)
                self._chain = await asyncio.to_thread(AuditChain, self._store)
            chain = self._chain

            def caught_up(chain: AuditChain) -> _T:
                # INT-488: an operator's command beside the API appends to the
                # same chain; adopt its rows first, or this one would reuse its
                # seq (the primary key) and every audited route would fail
                chain.catch_up()
                return fn(chain)

            return await asyncio.to_thread(caught_up, chain)

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None:
        def _append(chain: AuditChain) -> None:
            chain.append(
                actor=actor,
                action=action,
                resource_ref=resource_ref,
                consent_scope_ref=consent_scope,
            )

        await self.run_locked(_append)

    async def entries(self) -> Sequence[AuditEntry]:
        """The whole chain, for a projection that must not miss a row.

        The patient-visible access log (INT-016) is built by narrowing this to
        the patient's OWN resource refs at the call site; reading the chain
        whole and filtering there is what makes "nothing silently dropped"
        checkable — a store-side filter would decide, invisibly, which of a
        patient's accesses they get to see.
        """
        return await asyncio.to_thread(self._store.entries)

    async def healthy(self) -> bool:
        """Readiness: the store answers a read. Reported, never raised."""
        try:
            await asyncio.to_thread(self._store.last)
        except Exception:  # noqa: BLE001 — a readiness probe reports, never raises
            return False
        return True
