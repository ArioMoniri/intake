"""The console's only route to the audit record (INT-180; invariant 4).

**There is one audit path and this is not a second one.** INT-121 refused to
build a second data-boundary fence on the grounds that a security control
implemented twice diverges, and the argument is stronger here: the console is
the largest privilege in the system, so a private admin log would be the log
an insider edits. Every console action therefore lands in the INT-016
hash-chained record through :class:`AdminAuditSink`, whose entire surface is
``record`` — the sink can append and can do nothing else.

That narrowness is the point HB-I12 turns on. A hash chain detects an attacker
who edits a row and stops; it does not detect one who recomputes forward or
truncates the tail, which is why the head is published hourly **outside the
platform_admin blast radius**. The console sits inside that radius, so it must
not be able to read the head, export a bundle, or hold a chain object. It
holds an append-only sink, and ``tests/admin/test_admin_audit.py`` walks these
sources for any mention of a chain symbol.

**Write-ahead is the ordering rule** (files/08 §8.1): the intent row is
appended before the mutation runs, and a second row records the outcome. A
mutation that succeeds and then crashes before logging is the failure that
matters, and this is the only ordering that survives it.

**What travels.** The chain's field set is closed and id-shaped, so the §8.1
detail block — justification free text, the controller-instruction reference,
the actor's authenticator — cannot ride in it and must not. What rides is a
content digest over the id-shaped part of that block, in ``resource_ref``, so
a detail record that is later edited no longer matches the row that authorised
it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from types import TracebackType
from typing import Protocol

from intake_platform.admin.metrics import SEC_ADMIN_ACTIONS_TOTAL

__all__ = [
    "ADMIN_BASIS_REF",
    "AdminAuditSink",
    "AdminActionRecord",
    "admin_resource_ref",
    "detail_digest",
]

#: files/06 §1 / files/08 §2.6: an administrative action is not a patient
#: consent scope, so the row cites the obligation it is discharged under —
#: the same shape ``NOTIFICATION_BASIS_REF`` uses for İYS.
ADMIN_BASIS_REF = "basis:KVKK-12"


class AdminAuditSink(Protocol):
    """Append, and nothing else. ``intake_api.audit.AuditWriter`` satisfies
    this structurally, which is how the console reaches the one chain without
    ever holding it."""

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None: ...


def detail_digest(detail: Mapping[str, str]) -> str:
    """SHA-256 over the canonical form of the id-shaped detail block.

    Deliberately boring and fully specified — sorted keys, no whitespace,
    ASCII-only — so an auditor holding the detail record can recompute the
    digest that the chain row carries.
    """
    canonical = json.dumps(dict(detail), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def admin_resource_ref(correlation: str, digest: str) -> str:
    """``admin_action:<correlation>:<digest>`` — 110 characters, inside the
    chain's 128-character id shape. The correlation id joins the intent row to
    its outcome row; the digest binds both to the detail block."""
    return f"admin_action:{correlation}:{digest}"


class AdminActionRecord:
    """Write-ahead audit around one console action.

    Used as an async context manager: entering appends the intent row (and
    counts the action), leaving appends the outcome row — success when the
    body returned, failure when it raised or refused. Both paths append, so
    "audited" is a property of the control flow rather than of every author
    remembering to call something on the way out.
    """

    def __init__(
        self,
        sink: AdminAuditSink,
        *,
        actor: str,
        action: str,
        detail: Mapping[str, str],
    ) -> None:
        self._sink = sink
        self._actor = actor
        self._action = action
        self._resource_ref = admin_resource_ref(uuid.uuid4().hex, detail_digest(detail))
        self._failed = False

    @property
    def resource_ref(self) -> str:
        return self._resource_ref

    def mark_failed(self) -> None:
        """Record a refusal that the handler turns into a response rather
        than an exception."""
        self._failed = True

    async def __aenter__(self) -> AdminActionRecord:
        await self._sink.record(
            actor=self._actor,
            action=f"{self._action}.intent",
            resource_ref=self._resource_ref,
            consent_scope=ADMIN_BASIS_REF,
        )
        SEC_ADMIN_ACTIONS_TOTAL.inc()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        outcome = "failure" if (exc_type is not None or self._failed) else "success"
        await self._sink.record(
            actor=self._actor,
            action=f"{self._action}.{outcome}",
            resource_ref=self._resource_ref,
            consent_scope=ADMIN_BASIS_REF,
        )
