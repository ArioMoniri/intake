"""The database privileges the DSAR erasure run exercises (INT-395).

Which role runs erasure is an open owner decision, INT-394 (a dedicated
``erasure_rw`` role, or narrow grants to ``app_rw``). Until it is made, the
executor must not guess: it asks postgres for every privilege below before it
touches the object store or a row, and a role that lacks any of them gets a
typed, audited refusal naming each one, instead of a transaction that dies on
the first ``permission denied`` half-way through a subject.

Declared as data, statement by statement, so the grants test can read the
same set against the migrations (tests/legal/test_dsar_flows.py). Today
``app_rw`` lacks exactly three: DELETE on ``notification_preferences`` (0007)
and on ``patient_overlays`` (0010), and UPDATE on ``events.session_id``
(0001 keeps events append-only for the app). This module grants nothing —
granting is INT-394's decision, not this one's.

UPDATEs are declared per column. They are the narrowest grant that lets the
statement run, and it is what INT-394's option (b) would grant for
``events.session_id``. ``has_column_privilege`` is true for a table-level
grant too, so the check does not care which of the two the owner chooses.

A foreign-key cascade needs no grant on the child (postgres runs referential
actions as the table owner), so ``csat_texts`` is read, never deleted, here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, Literal

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "ERASURE_PRIVILEGES",
    "ERASURE_ROLE_DECISION",
    "Privilege",
    "PrivilegeProbe",
    "missing_privileges",
]

#: The backlog decision that owns every grant the erasure role lacks.
ERASURE_ROLE_DECISION: Final = "INT-394"


@dataclass(frozen=True, order=True)
class Privilege:
    """One privilege on one table, or on one column of it."""

    table: str
    privilege: Literal["SELECT", "UPDATE", "DELETE"]
    column: str | None = None

    @property
    def target(self) -> str:
        return self.table if self.column is None else f"{self.table}.{self.column}"

    @property
    def ref(self) -> str:
        """The id-shaped audit reference for this privilege."""
        return f"db-grant:{self.target}/{self.privilege}"

    def describe(self) -> str:
        return f"role lacks {self.privilege} on {self.target} ({ERASURE_ROLE_DECISION})"


def _select(*tables: str) -> frozenset[Privilege]:
    return frozenset(Privilege(table, "SELECT") for table in tables)


def _delete(*tables: str) -> frozenset[Privilege]:
    return frozenset(Privilege(table, "DELETE") for table in tables)


#: Every privilege ``intake_api.dsar.shred.execute_due_shreds`` exercises.
ERASURE_PRIVILEGES: Final[frozenset[Privilege]] = (
    # the due requests, and the subject sweep (``dsar.store.subject_record``)
    _select(
        "dsar_requests",
        "sessions",
        "slots",
        "notes",
        "previsit_outputs",
        "shares",
        "doctor_links",
        "documents",
        "consents",
        "dsar_rectifications",
        "overlay_facts",
        "patient_overlays",
        "csat_texts",
        "notification_preferences",
        "guardian_links",
        "events",
    )
    # the crypto-shred of every envelope, and the request's own close
    | frozenset(
        {
            Privilege("notes", "UPDATE", "payload"),
            Privilege("dsar_rectifications", "UPDATE", "payload"),
            Privilege("slots", "UPDATE", "value"),
            Privilege("overlay_facts", "UPDATE", "payload"),
            Privilege("previsit_outputs", "UPDATE", "payload"),
            Privilege("doctor_links", "UPDATE", "recipient"),
            Privilege("dsar_requests", "UPDATE", "status"),
            Privilege("dsar_requests", "UPDATE", "completed_at"),
            # the telemetry de-link (INT-392 §8)
            Privilege("events", "UPDATE", "session_id"),
        }
    )
    # the row removals, children first
    | _delete(
        "previsit_outputs",
        "doctor_links",
        "shares",
        "documents",
        "dsar_rectifications",
        "notes",
        "overlay_facts",
        "patient_overlays",
        "notification_preferences",
        "slots",
        "sessions",
    )
)

#: Answers which of the needed privileges the session's role lacks.
PrivilegeProbe = Callable[[AsyncSession], Awaitable[tuple[Privilege, ...]]]


async def missing_privileges(session: AsyncSession) -> tuple[Privilege, ...]:
    """The privileges in :data:`ERASURE_PRIVILEGES` the current role lacks,
    in a stable order, from one round trip.

    Postgres only. SQLite, which carries the unit lane, has no privilege
    system at all: every statement is permitted there, so nothing is missing.
    """
    connection = await session.connection()
    if connection.dialect.name != "postgresql":
        return ()
    needed = sorted(ERASURE_PRIVILEGES)
    # Every argument cast to text: both functions are overloaded on oid and
    # (for the column) smallint, and an untyped parameter must not be left
    # for the server to resolve.
    checks = [
        func.has_table_privilege(cast(need.table, Text), cast(need.privilege, Text))
        if need.column is None
        else func.has_column_privilege(
            cast(need.table, Text), cast(need.column, Text), cast(need.privilege, Text)
        )
        for need in needed
    ]
    held = (await session.execute(select(*checks))).one()
    return tuple(need for need, ok in zip(needed, held, strict=True) if not ok)
