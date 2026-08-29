"""INT-223 — where the api gets a subject's age context from.

The rules engine (``intake_platform.consent.minors``) is pure: it needs an
:class:`~intake_platform.consent.minors.AgeContext` and a date. This module
is the seam that produces one for a live request, so ``ensure_consent`` can
run the age gate without knowing where a date of birth would come from.

Today it comes from nowhere, and that is a deliberate, recorded state rather
than a gap papered over:

- **no table holds a date of birth.** ``patients`` is pseudonym-only and
  tests/data/test_schema_shape.py fails the build on a ``date_of_birth`` or
  ``birth_date`` column anywhere in the model — identity lives in the
  tokenization vault, and whether we may collect and verify a DOB at all is
  the open ``dob_collection_mandatory`` policy row;
- so :class:`NoAgeRecordSource` truthfully reports ``DobAssurance.ABSENT``,
  which the engine maps to the ``no_dob_recorded`` row: the minor regime is
  not asserted and the consent ledger alone answers. It reports the absence;
  it never invents an adult.

When onboarding gains a verified DOB (INT-131 and the policy row above), a
source that reads it replaces this default on ``ApiState.age_context`` and
every gated route inherits the new behaviour with no route change — which is
the point of putting the gate inside the one enforcement point.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from intake_platform.consent.minors import AgeContext
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["AgeContextSource", "NoAgeRecordSource"]


class AgeContextSource(Protocol):
    """Resolve the age context of one patient inside an open tenant session."""

    async def resolve(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> AgeContext: ...


class NoAgeRecordSource:
    """The default: no verified date of birth is recorded anywhere, so the
    context is ``absent``. Stateless and allocation-cheap — it runs on every
    guarded request."""

    async def resolve(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
    ) -> AgeContext:
        return AgeContext.absent()
