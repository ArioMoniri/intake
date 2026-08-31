"""The NEGATIVE control for INT-121's type-level confirmation gate.

Acceptance: *"patient confirms before use"*. INT-170 made that distinction
type-level for ``PatientOverlay`` facts; this file holds six separate attempts
to put an unconfirmed extraction to clinical use, and
``tests/records/test_extraction_eval.py`` asserts ``mypy --strict`` reports
every one of them by line.

The six attempts, in order:

1. build an item with no source box at all — the acceptance's "source boxes";
2. admit the raw observation to the store, which takes the confirmed type only;
3. build a ``ConfirmedRecordItem`` with no confirmation;
4. build one with a boolean "yes it's confirmed" flag, which is the design
   *(type-level)* exists to rule out;
5. project an unconfirmed observation onto the note;
6. re-point a confirmed item's confirmation afterwards.

This module is expected to fail type-checking, and nothing imports it.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from clinical_schemas.note import ImportedObjectiveItem
from clinical_schemas.overlay import Confirmation, Confirmer, LearnedFactSource
from clinical_schemas.provenance import Attributed
from clinical_schemas.record_extraction import (
    ConfirmedRecordItem,
    SourceBox,
    UnconfirmedRecordItem,
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
    summary="Üre 45 mg/dL",
    box=BOX,
    observed_at=AT,
    value_magnitude=Decimal("45"),
    unit="mg/dL",
)


def attempt_one_a_value_with_no_source_box() -> UnconfirmedRecordItem:
    """1 — every extracted value names where on the page it came from."""
    return UnconfirmedRecordItem(
        kind=RecordItemKind.LAB,
        summary="Üre 45 mg/dL",
        observed_at=AT,
        value_magnitude=Decimal("45"),
        unit="mg/dL",
    )


def attempt_two_admit_the_observation(store: ConfirmedRecordStore) -> None:
    """2 — the store takes the confirmed type and nothing else."""
    store.admit(OBSERVATION)


def attempt_three_a_confirmed_item_without_a_confirmation() -> ConfirmedRecordItem:
    """3 — there is no confirmed item that nobody confirmed."""
    return ConfirmedRecordItem(observation=OBSERVATION)


def attempt_four_a_boolean_flag() -> ConfirmedRecordItem:
    """4 — a flag any caller could set is exactly what (type-level) refuses."""
    return ConfirmedRecordItem(observation=OBSERVATION, confirmed=True)


def attempt_five_project_an_unconfirmed_value_onto_the_note() -> Attributed[ImportedObjectiveItem]:
    """5 — an unconfirmed extraction may not reach a note."""
    return OBSERVATION.as_imported_objective()


def attempt_six_repoint_the_confirmation(item: ConfirmedRecordItem) -> ConfirmedRecordItem:
    """6 — the record is frozen; a new confirmation is a new record."""
    item.confirmation = Confirmation(
        by=Confirmer.PATIENT,
        actor_ref="hasta-17",
        at=AT,
        source=LearnedFactSource.CONFIRMED_IMPORTED_RECORD,
        source_ref="document:doc-1",
    )
    return item
