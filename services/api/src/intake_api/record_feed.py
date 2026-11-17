"""Where a document's extraction is read from, and what the patient said (INT-138).

INT-121 built the extraction half of files/03 §10 and the confirm gate;
INT-124 built the model in front of it. Neither reaches a patient: nothing in
this API publishes an :class:`~intake_platform.records.DocumentExtraction`.
This module is the server side of that transport, in two parts.

**The seam** — :class:`ExtractionSource`. The route asks it one question
(*what has been read out of this document?*) and gets one of three answers.
:class:`NoExtractionSource` is the production answer and it is always
*unread*: every producer on the path is shut today — ``NoLayout`` and
``NoOcr`` behind the open parser-sandbox ADR (files/10 §4), and row 9 of
files/03 §4.9.1 refusing on the PHI path until a host serves it (INT-381).
Answering anything else would be inventing a feed. A producer plugs in here
without a route changing, the same way ``LayoutExtractor`` and
``TerminologyBinder`` do on the platform side.

**The ledger** — :class:`RecordDecisions`. A patient's verdict on one item is
recorded here, and a *confirmed* item goes through
:func:`~clinical_schemas.record_extraction.confirm_record_item` into INT-121's
:class:`~intake_platform.records.ConfirmedRecordStore` — the one store whose
``admit`` takes a :class:`~clinical_schemas.record_extraction.ConfirmedRecordItem`
and nothing else. A declined item is recorded as declined and admitted
nowhere: a patient who disagrees produces a refusal, never an edited value.

The store is INT-121's, and it holds in process memory. That is a property
of the store rather than a choice made here: writing confirmed lab values to
a table is a decision to persist a structured copy of patient health data,
which needs its invariant-18 annotation and a human's yes (CLAUDE.md, *when
to stop and ask*). It fails in the safe direction — a verdict lost to a
restart leaves the item *pending*, and a pending item reaches no note.

Nothing here logs, and no key or error carries anything but ids (invariant 6).
"""

from __future__ import annotations

import asyncio
import enum
import uuid
from dataclasses import dataclass, field
from typing import Final, Protocol

from clinical_schemas.record_extraction import ConfirmedRecordItem
from intake_platform.records import ConfirmedRecordStore, DocumentExtraction

__all__ = [
    "DOCUMENT_REF_PREFIX",
    "Decision",
    "ExtractionPhase",
    "ExtractionReading",
    "ExtractionSource",
    "NoExtractionSource",
    "RecordDecisions",
    "document_ref_for",
]

#: What every source box on a document's items must name. It is the same
#: ``doc:<id>`` the audit chain already writes for a document, so the
#: confirmation's ``source_ref`` (derived from the box) and the audit entry
#: point at one artefact.
DOCUMENT_REF_PREFIX: Final = "doc:"


def document_ref_for(document_id: uuid.UUID) -> str:
    return f"{DOCUMENT_REF_PREFIX}{document_id}"


class ExtractionPhase(enum.StrEnum):
    """What a source can say about one document. Closed."""

    READ = "read"
    READING = "reading"
    UNREAD = "unread"


class Decision(enum.StrEnum):
    """What a patient may say about one item. Two members, and the missing
    third is the design: there is no *edited* verdict, because
    ``confirm_record_item`` carries the observation over unchanged."""

    CONFIRMED = "confirmed"
    DECLINED = "declined"


@dataclass(frozen=True, slots=True)
class ExtractionReading:
    """One answer from a source. ``extraction`` is present exactly when read."""

    phase: ExtractionPhase
    extraction: DocumentExtraction | None = None

    def __post_init__(self) -> None:
        if (self.phase is ExtractionPhase.READ) != (self.extraction is not None):
            raise ValueError("an extraction accompanies the read phase, and only that phase")


class ExtractionSource(Protocol):
    """Where the route reads a document's extraction from."""

    async def read(self, *, tenant_id: uuid.UUID, document_id: uuid.UUID) -> ExtractionReading: ...


@dataclass(frozen=True, slots=True)
class NoExtractionSource:
    """The production source: nothing has been read, for any document.

    Every producer is shut (see the module docstring), so *unread* is the
    true answer rather than a stand-in for one. It is the same fail-closed
    shape as ``NoLayout``, ``NoOcr`` and ``NoTerminology``.
    """

    async def read(self, *, tenant_id: uuid.UUID, document_id: uuid.UUID) -> ExtractionReading:
        return ExtractionReading(ExtractionPhase.UNREAD)


_ItemKey = tuple[uuid.UUID, uuid.UUID, str]
_PatientKey = tuple[uuid.UUID, uuid.UUID]


@dataclass
class RecordDecisions:
    """The patient's verdicts, and the confirmed items they admitted.

    Keys are ids only: a tenant, a document and an item id, which is a digest
    of the item's position and box and never of its text. ``lock`` serialises
    one decision end to end — check, audit, record — so two taps on one card
    cannot both pass the check and admit the item twice.
    """

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _decided: dict[_ItemKey, Decision] = field(default_factory=dict)
    _stores: dict[_PatientKey, ConfirmedRecordStore] = field(default_factory=dict)

    def decision(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID, item_id: str
    ) -> Decision | None:
        return self._decided.get((tenant_id, document_id, item_id))

    def record_declined(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID, item_id: str
    ) -> None:
        self._decided[(tenant_id, document_id, item_id)] = Decision.DECLINED

    def record_confirmed(
        self,
        *,
        tenant_id: uuid.UUID,
        patient_id: uuid.UUID,
        document_id: uuid.UUID,
        item_id: str,
        item: ConfirmedRecordItem,
    ) -> None:
        store = self._stores.setdefault((tenant_id, patient_id), ConfirmedRecordStore())
        store.admit(item)
        self._decided[(tenant_id, document_id, item_id)] = Decision.CONFIRMED

    def admitted(
        self, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> tuple[ConfirmedRecordItem, ...]:
        store = self._stores.get((tenant_id, patient_id))
        return store.admitted if store is not None else ()
