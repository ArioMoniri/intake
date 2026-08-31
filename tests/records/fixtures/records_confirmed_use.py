"""The POSITIVE control for INT-121's type-level confirmation gate.

A conforming specimen: an extraction is confirmed by a patient and by a
clinician, admitted to the store, projected onto the note and mapped to FHIR.
``mypy --strict`` must find nothing here, or the negative control beside it
separates nothing.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from clinical_schemas.mappers import record_item_to_r4
from clinical_schemas.overlay import Confirmer
from clinical_schemas.record_extraction import (
    ConfirmedRecordItem,
    SourceBox,
    UnconfirmedRecordItem,
    confirm_record_item,
)
from clinical_schemas.records import RecordItemKind
from intake_platform.records_extraction import ConfirmedRecordStore

AT = dt.datetime(2026, 8, 20, 9, 30, tzinfo=dt.UTC)

BOX = SourceBox(
    document_ref="document:doc-1",
    page=2,
    bbox=(0.12, 0.40, 0.48, 0.44),
    start=40,
    end=52,
)

OBSERVATION = UnconfirmedRecordItem(
    kind=RecordItemKind.LAB,
    summary="Üre 45 mg/dL",
    box=BOX,
    observed_at=AT,
    value_magnitude=Decimal("45"),
    unit="mg/dL",
    date=dt.date(2026, 8, 20),
)


def patient_confirms_then_the_store_admits(store: ConfirmedRecordStore) -> ConfirmedRecordItem:
    confirmed = confirm_record_item(OBSERVATION, by=Confirmer.PATIENT, actor_ref="hasta-17", at=AT)
    store.admit(confirmed)
    return confirmed


def clinician_confirms_and_it_reaches_the_note_and_fhir() -> str:
    confirmed = confirm_record_item(OBSERVATION, by=Confirmer.CLINICIAN, actor_ref="hekim-2", at=AT)
    attributed = confirmed.as_imported_objective()
    resource = record_item_to_r4(confirmed.as_record_item(), subject_ref="Patient/p-1")
    return f"{attributed.value.provenance}:{type(resource).__name__}"
