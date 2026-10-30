"""Concrete destroyers over the INT-030 models and the INT-034 object store.

:func:`sqlalchemy_destroyers` returns the routes a :class:`RoutingExecutor`
takes for the classes this package holds stores for today:

- ``telemetry`` / ``satisfaction`` → Event rows (both live on the events
  table; the split is a policy fact — different 06 §3 rows, different
  clocks — not a storage fact);
- ``consent_records_hospital_tenant`` → Consent rows at the 10-year mark;
- ``clinical_record`` → the whole session tree on the DSAR path: document
  objects first (via the injected remover), then, in one transaction, the
  previsit output rows, document rows, the Doctor Link rows and then the
  share rows they hang off, note and slot rows, the telemetry de-link, and
  the session row itself, children before parents throughout. Object removal
  precedes the row transaction on purpose: if the run dies in between, rows
  point at nothing — the failure direction that favours erasure, which is the
  right bias for a KVKK m.7/m.11 destruction (the reverse would strand PHI
  bytes behind a deleted index).

  Every foreign key to ``sessions.id`` is handled by name (INT-392;
  tests/data/test_session_delete_contract.py holds the declaration). The
  previsit output (INT-317) is the note's frozen projection on the same
  record clock and goes first, like the DSAR executor's; its key keeps NO
  ACTION so a path that forgets it fails rather than dropping it unseen.
  Telemetry is de-linked rather than destroyed — it has its own 06 §3 clock
  and is PHI-free by construction, the ``intake_api.dsar.shred`` reasoning —
  and ``csat_texts`` goes with the session through its ON DELETE CASCADE.

  One level down (INT-393): a Doctor Link row (INT-150) is annotated
  ``RET_SHARE``, "grant row retained with the record", so it follows this
  class and goes before its share. ``doctor_links.share_id`` keeps NO ACTION
  for the same fail-closed reason. That test file now declares what an
  erasure does to every key reachable from ``patients`` and ``sessions``.

Classes whose stores live outside this package today — ``traffic_logs_5651``
(ingress infra) and ``doctor_link_tokens`` (the share-token service,
INT-131; the Doctor Link grant row itself follows ``clinical_record``, above)
— register their destroyers with the same :class:`RoutingExecutor`
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
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

from sqlalchemy import Engine, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from intake_platform.db.models import (
    Consent as ConsentRow,
)
from intake_platform.db.models import (
    DoctorLink,
    Document,
    Event,
    IntakeSession,
    Note,
    PatientPasskey,
    PreVisitOutputRow,
    RecordEmbedding,
    Share,
    Slot,
)
from intake_platform.records.index import document_ref_of
from intake_platform.retention.engine import Destroyer
from intake_platform.retention.planner import InventoryItem
from intake_platform.retention.policy import DestroyableClass

__all__ = [
    "DocumentObjectDestroyer",
    "ObjectRemover",
    "UnknownBucketError",
    "WormBundleProtectedError",
    "recovered_passkey_inventory",
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


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def recovered_passkey_inventory(engine: Engine, *, cooloff: timedelta) -> list[InventoryItem]:
    """INT-582 (legal B4): every passkey with a recovery running, as an
    event-clock item due when its cool-off ends. The cool-off is the API's
    (``intake_api.passkey.service.RECOVERY_COOLOFF_S``) and comes in as an
    argument; a cancelled recovery has no ``recovery_requested_at`` and is not
    listed at all. Ids only (invariant 6)."""
    with Session(engine) as session:
        rows = session.execute(
            select(
                PatientPasskey.id,
                PatientPasskey.patient_id,
                PatientPasskey.recovery_requested_at,
            ).where(PatientPasskey.recovery_requested_at.is_not(None))
        ).all()
    items: list[InventoryItem] = []
    for passkey_id, patient_id, requested in rows:
        started = _aware(requested)
        items.append(
            InventoryItem(
                data_class=DestroyableClass.RECOVERED_PASSKEYS,
                item_ref=str(passkey_id),
                clock_start=started,
                expires_at=started + cooloff,
                subject_ref=f"patient:{patient_id}",
            )
        )
    return items


def sqlalchemy_destroyers(
    engine: Engine,
    *,
    remove_object: Callable[[str], None],
    record_passkey_recovery: Callable[[str], None] | None = None,
) -> dict[DestroyableClass, Destroyer]:
    """Destroyers for the classes whose stores are the INT-030 tables.
    ``remove_object`` receives each document's ``object_ref`` — wire a
    :class:`DocumentObjectDestroyer` there in anything beyond the unit lane.

    ``record_passkey_recovery`` (INT-582) audits each destroyed recovered
    passkey as ``passkey.recovery.complete`` by its id. Without it the class is
    not routed, so a due passkey refuses loudly (NoExecutorRegisteredError)
    rather than disappearing unaudited."""

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
            # INT-123: the vectors indexed from a destroyed document go with it.
            # The index writer refuses any source box that is not
            # doc:<documents.id>, so this finds every row a document produced.
            document_refs = [
                document_ref_of(document_id)
                for document_id in session.scalars(
                    select(Document.id).where(Document.session_id.in_(session_ids))
                ).all()
            ]
            if document_refs:
                session.execute(
                    delete(RecordEmbedding).where(RecordEmbedding.document_ref.in_(document_refs))
                )
            session.execute(delete(Document).where(Document.session_id.in_(session_ids)))
            if note_ids:
                shares = select(Share.id).where(Share.note_id.in_(note_ids))
                session.execute(delete(DoctorLink).where(DoctorLink.share_id.in_(shares)))
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

    def destroy_recovered_passkeys(refs: Sequence[str]) -> int:
        if record_passkey_recovery is None:  # pragma: no cover — never routed without it
            raise ValueError("a recovered passkey is destroyed only where it can be audited")
        ids = _as_uuids("passkey", refs)
        with Session(engine) as session, session.begin():
            gone = session.scalars(
                delete(PatientPasskey)
                .where(
                    PatientPasskey.id.in_(ids),
                    # only a passkey whose recovery is still running is this
                    # class's: a cancelled one survives even if listed earlier
                    PatientPasskey.recovery_requested_at.is_not(None),
                )
                .returning(PatientPasskey.id)
            ).all()
        for passkey_id in gone:
            record_passkey_recovery(str(passkey_id))
        return len(gone)

    routes: dict[DestroyableClass, Destroyer] = {
        DestroyableClass.TELEMETRY: destroy_events,
        DestroyableClass.SATISFACTION: destroy_events,
        DestroyableClass.CONSENT_RECORDS_HOSPITAL_TENANT: destroy_consents,
        DestroyableClass.CLINICAL_RECORD: destroy_clinical,
    }
    if record_passkey_recovery is not None:
        routes[DestroyableClass.RECOVERED_PASSKEYS] = destroy_recovered_passkeys
    return routes
