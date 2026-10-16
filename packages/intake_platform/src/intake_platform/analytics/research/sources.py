"""INT-490 — the release, computed server-side from what is already stored.

**What is live.** Two view kinds have a source today, and both read row
METADATA only — never a content column:

- ``funnel`` — a session row is a visit opened for the person (invited); a
  start instant, an uploaded document or a note means the intake began
  (started); a completion instant or a note means it produced a note
  (finished); a share of that note means the patient sent it (shared). Each
  is judged **as of the end of the week**: a share made after the week closed
  does not move the week, so two reads of a closed week agree;
- ``locale`` — ``sessions.locale``, a registry code (INT-296).

**What is not, and why** (each reported on the page with its reason class):

- ``triage`` — ``triage_level_not_recorded``. The rules-engine level exists
  only inside the envelope-encrypted previsit document. Decrypting patient
  documents so a staff read can count them would open a second read path to
  patient content, which files/10 §9 gives to break-glass alone. A
  content-free record of the level, written where the rules engine runs, is
  the source this view needs.
- ``platform`` and every per-question view —
  :meth:`~.retention.AnalyticsRetention.raw_telemetry_reason`. Nothing stored
  holds a question's outcome, answer mode, time, repeats or recognition band,
  or the device platform; recording them is per-person raw telemetry whose
  retention LD-06 leaves to the owner, and record-level improvement data needs
  the owner's consent-scope decision too (LD-06 ``consent_scope``).

**Who is counted.** One tenant at a time, inside that tenant's RLS session,
every query carrying its ``tenant_id`` predicate as well. A patient whose
latest decision on ``learning:service_improvement`` is a withdrawal is not
counted — LD-06 keeps that opt-out "as a courtesy" — decided by the same
platform evaluator every route uses (invariant 4: a read of clinical data
checks a consent scope). A person counts once per protocol version per week;
their latest session in it speaks for them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Final

from clinical_schemas.consent import ConsentPurpose
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_platform.analytics.k_anonymity import _ID_SHAPE
from intake_platform.analytics.research.catalogue import (
    QUESTION_VIEW_KINDS,
    Period,
    Stage,
    ViewKind,
)
from intake_platform.analytics.research.records import SubjectRecord
from intake_platform.analytics.research.retention import AnalyticsRetention
from intake_platform.consent import ConsentTextCatalog, is_scope_allowed
from intake_platform.db.models import Document, IntakeSession, Note, Share
from intake_platform.locale.registry import LOCALE_REGISTRY

__all__ = [
    "AGGREGATION_SCOPE",
    "LIVE_VIEW_KINDS",
    "SourceUnreadable",
    "family_records",
    "not_collected_reasons",
]

#: files/06 §2: the de-identified-aggregate purpose; its opt-out is honoured.
AGGREGATION_SCOPE: Final = ConsentPurpose.LEARNING_SERVICE_IMPROVEMENT.value

LIVE_VIEW_KINDS: Final = frozenset({ViewKind.FUNNEL, ViewKind.LOCALE})


class SourceUnreadable(Exception):
    """A stored row could not be counted as it stands; the read refuses rather
    than miscounting. ``code`` is a class, never the row's value."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def not_collected_reasons(retention: AnalyticsRetention) -> dict[ViewKind, str]:
    raw = retention.raw_telemetry_reason()
    reasons = {kind: raw for kind in QUESTION_VIEW_KINDS}
    reasons[ViewKind.PLATFORM] = raw
    reasons[ViewKind.TRIAGE] = "triage_level_not_recorded"
    return reasons


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _before(value: datetime | None, end: datetime) -> bool:
    instant = _aware(value)
    return instant is not None and instant < end


async def family_records(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    period: Period,
    catalog: ConsentTextCatalog,
) -> list[SubjectRecord]:
    """One :class:`SubjectRecord` per counted person per protocol version."""
    start, end = period.start, period.end
    visits = (
        await session.execute(
            select(
                IntakeSession.id,
                IntakeSession.patient_id,
                IntakeSession.protocol_id,
                IntakeSession.protocol_version,
                IntakeSession.locale,
                IntakeSession.started_at,
                IntakeSession.completed_at,
                IntakeSession.created_at,
            ).where(
                IntakeSession.tenant_id == tenant_id,
                IntakeSession.created_at >= start,
                IntakeSession.created_at < end,
            )
        )
    ).all()
    if not visits:
        return []
    ids = [visit.id for visit in visits]

    notes = (
        await session.execute(
            select(Note.id, Note.session_id).where(
                Note.tenant_id == tenant_id, Note.session_id.in_(ids), Note.created_at < end
            )
        )
    ).all()
    noted = {note.session_id for note in notes}
    note_session = {note.id: note.session_id for note in notes}
    shared: set[uuid.UUID] = set()
    if note_session:
        shares = await session.execute(
            select(Share.note_id).where(
                Share.tenant_id == tenant_id,
                Share.note_id.in_(list(note_session)),
                Share.created_at < end,
            )
        )
        shared = {note_session[note_id] for note_id in shares.scalars()}
    documented = set(
        (
            await session.execute(
                select(Document.session_id).where(
                    Document.tenant_id == tenant_id,
                    Document.session_id.in_(ids),
                    Document.created_at < end,
                )
            )
        ).scalars()
    )

    allowed: dict[uuid.UUID, bool] = {}
    latest: dict[tuple[uuid.UUID, str, str], tuple[datetime, str, SubjectRecord]] = {}
    for visit in visits:
        if visit.patient_id not in allowed:
            allowed[visit.patient_id] = await is_scope_allowed(
                session,
                tenant_id=tenant_id,
                patient_id=visit.patient_id,
                scope=AGGREGATION_SCOPE,
                catalog=catalog,
            )
        if not allowed[visit.patient_id]:
            continue
        if any(_ID_SHAPE.match(v) is None for v in (visit.protocol_id, visit.protocol_version)):
            raise SourceUnreadable("dimension_not_id_shaped")
        if visit.locale not in LOCALE_REGISTRY:
            raise SourceUnreadable("locale_outside_registry")
        if visit.id in shared:
            stage = Stage.SHARED
        elif visit.id in noted or _before(visit.completed_at, end):
            stage = Stage.FINISHED
        elif visit.id in documented or _before(visit.started_at, end):
            stage = Stage.STARTED
        else:
            stage = Stage.INVITED
        record = SubjectRecord(
            subject=visit.patient_id,
            tenant=tenant_id,
            protocol=visit.protocol_id,
            protocol_version=visit.protocol_version,
            stage=stage,
            locale=visit.locale,
        )
        key = (visit.patient_id, visit.protocol_id, visit.protocol_version)
        order = (_aware(visit.created_at) or start, str(visit.id), record)
        if key not in latest or order[:2] > latest[key][:2]:
            latest[key] = order
    return [entry[2] for entry in latest.values()]
