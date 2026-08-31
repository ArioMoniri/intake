"""The NEGATIVE control for INT-170's type-level confirmation gate.

CLAUDE.md invariant 12: *"``PatientOverlay`` facts require patient or clinician
confirmation (type-level)."* A claim like that is worth exactly what its
negative control is worth, so this file holds five separate attempts to commit
something nobody confirmed, and ``tests/learning/test_overlay_provenance.py``
asserts ``mypy --strict`` reports every one of them by line.

The five attempts, in order:

1. hand the store the raw observation — the shape extraction actually produces;
2. build a ``ConfirmedFact`` with no confirmation at all;
3. build one with a boolean "yes it's confirmed" flag, which is the design the
   acceptance's *(type-level)* exists to rule out;
4. name a confirmer that is neither the patient nor a clinician (a model);
5. re-point a committed fact's confirmation afterwards.

This module is expected to fail type-checking, and nothing imports it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from clinical_schemas.overlay import (
    Confirmation,
    ConfirmedFact,
    Confirmer,
    LearnedFactSource,
    UnconfirmedObservation,
)
from intake_api.overlay_store import PatientOverlayStore

AT = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)

OBSERVATION = UnconfirmedObservation(
    key="ilac.ilac_kullanimi",
    value=False,
    observed_ref="oturum-91",
    observed_at=AT,
)


async def attempt_one_commit_the_observation(store: PatientOverlayStore) -> None:
    """1 — the store takes the confirmed type and nothing else."""
    await store.commit(
        tenant_ref="kiracı-1",
        patient_ref="hasta-17",
        fact=OBSERVATION,
        actor="hasta-17",
    )


def attempt_two_a_fact_without_a_confirmation() -> ConfirmedFact:
    """2 — there is no ``ConfirmedFact`` that nobody confirmed."""
    return ConfirmedFact(key="ilac.ilac_kullanimi", value=False, confidence=1.0)


def attempt_three_a_boolean_flag() -> ConfirmedFact:
    """3 — a flag any caller could set is exactly what (type-level) refuses."""
    return ConfirmedFact(
        key="ilac.ilac_kullanimi",
        value=False,
        confidence=1.0,
        confirmed=True,
    )


def attempt_four_a_model_confirmed_it() -> Confirmation:
    """4 — ``Confirmer`` has two members: the patient and the clinician."""
    return Confirmation(
        by=Confirmer.MODEL,
        actor_ref="çıkarım-1",
        at=AT,
        source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
        source_ref="oturum-91",
    )


def attempt_five_repoint_the_confirmation(fact: ConfirmedFact) -> ConfirmedFact:
    """5 — the record is frozen; a new value is a new confirmation."""
    fact.confirmation = Confirmation(
        by=Confirmer.PATIENT,
        actor_ref="hasta-17",
        at=AT,
        source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
        source_ref="oturum-91",
    )
    return fact
