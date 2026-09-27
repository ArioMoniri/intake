"""Concrete destroyers over the INT-030 models and the INT-034 object store.

:func:`sqlalchemy_destroyers` returns the routes a :class:`RoutingExecutor`
takes for the classes this package holds stores for today:

- ``telemetry`` / ``satisfaction`` → Event rows (both live on the events
  table; the split is a policy fact — different 06 §3 rows, different
  clocks — not a storage fact);
- ``consent_records_hospital_tenant`` → Consent rows at the 10-year mark;
- ``clinical_record`` → the whole session tree on the DSAR path: document
  objects first (via the injected remover), then, in one transaction, the
  previsit output rows, document/share/note/slot rows, the telemetry de-link,
  and the session row itself. Object removal precedes the row transaction on
  purpose: if the run dies in between, rows point at nothing — the failure
  direction that favours erasure, which is the right bias for a KVKK
  m.7/m.11 destruction (the reverse would strand PHI bytes behind a deleted
  index).

  Every foreign key to ``sessions.id`` is handled by name (INT-392;
  tests/data/test_session_delete_contract.py holds the declaration). The
  previsit output (INT-317) is the note's frozen projection on the same
  record clock and goes first, like the DSAR executor's; its key keeps NO
  ACTION so a path that forgets it fails rather than dropping it unseen.
  Telemetry is de-linked rather than destroyed — it has its own 06 §3 clock
  and is PHI-free by construction, the ``intake_api.dsar.shred`` reasoning —
  and ``csat_texts`` goes with the session through its ON DELETE CASCADE.

Classes whose stores live outside this package today — ``traffic_logs_5651``
(ingress infra) and ``doctor_link_tokens`` (the share-token service,
INT-131) — register their destroyers with the same :class:`RoutingExecutor`
when those services land; until then an inventory naming them fails closed in
the router (:class:`NoExecutorRegisteredError`), never silently.

:class:`DocumentObjectDestroyer` is the INT-034 seam with the WORM boundary
built in: it deletes only from the documents bucket and refuses the audit
bucket by type (:class:`WormBundleProtectedError`) — the destruction log and
the audit bundles are not this engine's to destroy.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from typing import Any, Protocol, cast

from sqlalchemy import Engine, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from intake_platform.db.models import (
    Consent as ConsentRow,
)
from intake_platform.db.models import (
    Document,
    Event,
    IntakeSession,
    Note,
    PreVisitOutputRow,
    Share,
    Slot,
)
from intake_platform.retention.engine import Destroyer
from intake_platform.retention.policy import DestroyableClass

__all__ = [
    "DocumentObjectDestroyer",
    "ObjectRemover",
    "UnknownBucketError",
    "WormBundleProtectedError",
    "sqlalchemy_destroyers",
]


class WormBundleProtectedError(Exception):
    """An attempt to remove an object from the WORM audit bucket."""


class UnknownBucketError(Exception):
    """An object ref outside the documents bucket — refused, never guessed."""


class ObjectRemover(Protocol):
    """The one slice of the INT-034 ObjectStorageClient this module needs."""

    def remove_object(
        self, bucket_name: str, object_name: str, version_id: str | None = None
    ) -> None: ...


class DocumentObjectDestroyer:
    """Removes document objects by their stored ``object_ref`` (the INT-030
    ``documents.object_ref`` format, ``bucket/key``), inside the WORM
    boundary: only the documents bucket is destroyable."""

    def __init__(self, client: ObjectRemover, *, bucket_docs: str, bucket_audit: str) -> None:
        self._client = client
        self._bucket_docs = bucket_docs
        self._bucket_audit = bucket_audit

    def __call__(self, object_ref: str) -> None:
        bucket, sep, key = object_ref.partition("/")
        if not sep or not key:
            raise UnknownBucketError(
                "object_ref must be 'bucket/key' (INT-030 documents.object_ref); "
                "a ref without a bucket cannot be checked against the WORM boundary"
            )
        if bucket == self._bucket_audit:
            raise WormBundleProtectedError(
                f"bucket {bucket!r} holds the WORM audit bundles (10-year retention, "
                "06 §3): destruction evidence is not destroyable by this engine"
            )
        if bucket != self._bucket_docs:
            raise UnknownBucketError(
                f"bucket {bucket!r} is not the documents bucket: this destroyer "
                "deletes only what INT-034 stores for patients"
            )
        self._client.remove_object(bucket, key)


def _as_uuids(field_name: str, refs: Sequence[str]) -> list[uuid.UUID]:
    try:
        return [uuid.UUID(ref) for ref in refs]
    except ValueError as err:
        raise ValueError(
            f"{field_name} refs must be UUIDs (INT-030 primary keys); a ref that "
            "does not parse is refused rather than skipped"
        ) from err


def _as_ints(field_name: str, refs: Sequence[str]) -> list[int]:
    try:
        return [int(ref) for ref in refs]
    except ValueError as err:
        raise ValueError(
            f"{field_name} refs must be integer event ids; a ref that does not "
            "parse is refused rather than skipped"
        ) from err


def sqlalchemy_destroyers(
    engine: Engine, *, remove_object: Callable[[str], None]
) -> dict[DestroyableClass, Destroyer]:
    """Destroyers for the classes whose stores are the INT-030 tables.
    ``remove_object`` receives each document's ``object_ref`` — wire a
    :class:`DocumentObjectDestroyer` there in anything beyond the unit lane."""

    def destroy_events(refs: Sequence[str]) -> int:
        ids = _as_ints("event", refs)
        with Session(engine) as session, session.begin():
            result = cast(
                "CursorResult[Any]",
                session.execute(delete(Event).where(Event.id.in_(ids))),
            )
            return int(result.rowcount)

    def destroy_consents(refs: Sequence[str]) -> int:
        ids = _as_uuids("consent", refs)
        with Session(engine) as session, session.begin():
            result = cast(
                "CursorResult[Any]",
                session.execute(delete(ConsentRow).where(ConsentRow.id.in_(ids))),
            )
            return int(result.rowcount)

    def destroy_clinical(refs: Sequence[str]) -> int:
        session_ids = _as_uuids("session", refs)
        # Objects first — see the module docstring for why this order.
        with Session(engine) as session:
            object_refs = session.scalars(
                select(Document.object_ref).where(Document.session_id.in_(session_ids))
            ).all()
        for object_ref in object_refs:
            remove_object(object_ref)
        with Session(engine) as session, session.begin():
            note_ids = session.scalars(
                select(Note.id).where(Note.session_id.in_(session_ids))
            ).all()
            session.execute(
                delete(PreVisitOutputRow).where(PreVisitOutputRow.session_id.in_(session_ids))
            )
            session.execute(delete(Document).where(Document.session_id.in_(session_ids)))
            if note_ids:
                session.execute(delete(Share).where(Share.note_id.in_(note_ids)))
            session.execute(delete(Note).where(Note.session_id.in_(session_ids)))
            session.execute(delete(Slot).where(Slot.session_id.in_(session_ids)))
            session.execute(
                update(Event).where(Event.session_id.in_(session_ids)).values(session_id=None)
            )
            result = cast(
                "CursorResult[Any]",
                session.execute(delete(IntakeSession).where(IntakeSession.id.in_(session_ids))),
            )
            return int(result.rowcount)

    return {
        DestroyableClass.TELEMETRY: destroy_events,
        DestroyableClass.SATISFACTION: destroy_events,
        DestroyableClass.CONSENT_RECORDS_HOSPITAL_TENANT: destroy_consents,
        DestroyableClass.CLINICAL_RECORD: destroy_clinical,
    }
