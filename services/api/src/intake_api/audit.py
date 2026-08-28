"""Async facade over the hash-chained audit log (INT-197; invariant 4).

The chain writer (`intake_platform.audit.AuditChain` over the store) is
synchronous by design; this facade serialises appends behind an asyncio lock
— the chain's running head must advance one entry at a time — and moves the
blocking work off the event loop. An audit failure propagates: a clinical
read that cannot be audited must not answer (fail closed).
"""

from __future__ import annotations

import asyncio

from intake_platform.audit import AuditChain, AuditStore

__all__ = ["AuditWriter"]


class AuditWriter:
    def __init__(self, store: AuditStore, *, actor_prefix: str = "") -> None:
        self._store = store
        self._prefix = actor_prefix
        self._chain: AuditChain | None = None
        self._lock = asyncio.Lock()

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None:
        async with self._lock:
            if self._chain is None:
                # first use resumes the persisted chain (reads the tail)
                self._chain = await asyncio.to_thread(AuditChain, self._store)
            await asyncio.to_thread(
                self._chain.append,
                actor=self._prefix + actor,
                action=action,
                resource_ref=resource_ref,
                consent_scope_ref=consent_scope,
            )

    async def healthy(self) -> bool:
        """Readiness: the store answers a read. Reported, never raised."""
        try:
            await asyncio.to_thread(self._store.last)
        except Exception:  # noqa: BLE001 — a readiness probe reports, never raises
            return False
        return True
