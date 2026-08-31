"""The POSITIVE control for INT-170's type-level confirmation gate.

Everything here is the intended shape: an observation is confirmed by a named
patient or clinician, and only the resulting :class:`ConfirmedFact` is handed
to the store. ``mypy --strict`` must find nothing wrong with this file — if it
did, the negative control beside it would prove nothing, because a checker that
rejects everything separates nothing.

Nothing here is imported by production code; both files are specimens for the
type checker.
"""

from __future__ import annotations

from datetime import UTC, datetime

from clinical_schemas.overlay import (
    ConfirmedFact,
    Confirmer,
    LearnedFactSource,
    UnconfirmedObservation,
    confirm,
)
from intake_api.audit import AuditWriter
from intake_api.overlay_store import OverlayAuditSink, PatientOverlayStore

OBSERVED_AT = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
CONFIRMED_AT = datetime(2026, 1, 5, 9, 1, tzinfo=UTC)

OBSERVATION = UnconfirmedObservation(
    key="ilac.ilac_kullanimi",
    value=False,
    observed_ref="oturum-91",
    observed_at=OBSERVED_AT,
)


def patient_confirmed() -> ConfirmedFact:
    """The patient said so, in their own review step."""
    return confirm(
        OBSERVATION,
        by=Confirmer.PATIENT,
        actor_ref="hasta-17",
        at=CONFIRMED_AT,
        source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
        source_ref="oturum-91",
        confidence=1.0,
    )


def clinician_confirmed() -> ConfirmedFact:
    """A clinician accepted it into the note. A different asserter, and the
    type keeps them apart: ``Confirmer`` has two members and no third."""
    return confirm(
        OBSERVATION,
        by=Confirmer.CLINICIAN,
        actor_ref="hekim-4",
        at=CONFIRMED_AT,
        source=LearnedFactSource.CLINICIAN_ACCEPTED_NOTE,
        source_ref="not-33",
        confidence=1.0,
    )


async def commit_both(store: PatientOverlayStore) -> None:
    for fact in (patient_confirmed(), clinician_confirmed()):
        await store.commit(
            tenant_ref="kiracı-1",
            patient_ref="hasta-17",
            fact=fact,
            actor="hasta-17",
        )


def the_audit_writer_is_a_sink(writer: AuditWriter) -> OverlayAuditSink:
    """The production audit chain satisfies the store's narrow sink protocol,
    so the seam the tests fill with an in-process double is the same seam the
    API wires (invariant 4)."""
    return writer
