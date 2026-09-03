"""One session's running totals, and the admission decision they support.

Three properties this class exists to hold, none of which is about arithmetic.

**It retains nothing a person could be recovered from.** The constructor takes
a session id and keeps only ``sha256`` of it (CLAUDE.md invariant 6, and the
same tokenisation ``ExtractSlotsHandler`` already applies to a span). Nothing
else patient-shaped ever enters: a charge is a number, not an utterance.

**It keeps totals, never a history.** CLAUDE.md invariant 3 forbids retaining
raw audio *and* forbids retaining a derived duration in a way that reconstructs
one — and a per-utterance list of audio-second charges is exactly the
turn-taking timeline of a recording nobody kept. So every field is a scalar per
component: a total, a charge count, a refusal count. There is no container a
history could occupy, and a test walks ``vars()`` to keep it that way.

**It never awaits anything.** Every method here is an ordinary function doing
O(1) integer work with no I/O, so a metered turn and an unmetered one take the
same time by construction (CLAUDE.md invariant 9). That is stronger than a
fast implementation: there is nothing on this object for the Talker to await
even by accident.

The admission rule, stated once:

============  ==================  =============================================
kind          obligatory charge   elective charge
============  ==================  =============================================
CAP           always admitted     admitted while ``total < limit``; refused
                                  once reached — and refused outright when no
                                  limit is declared (fail closed)
TARGET        always admitted     always admitted; an overrun is reported
ACCOUNTING    always admitted     always admitted; nothing to overrun
============  ==================  =============================================
"""

from __future__ import annotations

import enum
import hashlib
from collections.abc import Mapping

from clinical_schemas.common import FrozenModel

from intake_voice_runtime.metering.budgets import (
    PUBLISHED_BUDGETS,
    BudgetKind,
    SessionBudget,
)
from intake_voice_runtime.metering.components import ChargeClass, MeteredComponent

__all__ = ["Admission", "AdmissionReason", "SessionLedger"]


class AdmissionReason(enum.StrEnum):
    """Why this charge was admitted or refused. A closed set, and PHI-free."""

    #: Admitted because the patient is owed it. No budget outranks that.
    OBLIGATORY = "obligatory"
    #: Admitted: the component's budget is a target or accounting-only.
    NOT_CAPPED = "not_capped"
    #: Admitted: a cap is declared and the running total is inside it.
    WITHIN_CAP = "within_cap"
    #: Refused: a cap is declared and the running total has reached it.
    CAP_EXHAUSTED = "cap_exhausted"
    #: Refused: no cap is declared, so affordability is unknown (fail closed).
    CAP_UNDECLARED = "cap_undeclared"


class Admission(FrozenModel):
    """The decision, with the reason it can be explained by."""

    component: MeteredComponent
    charge_class: ChargeClass
    admitted: bool
    reason: AdmissionReason


class SessionLedger:
    """Running totals for one session. Scalars only; no history; no id."""

    def __init__(
        self,
        session_id: str,
        *,
        budgets: Mapping[MeteredComponent, SessionBudget] | None = None,
    ) -> None:
        if not session_id:
            raise ValueError("a ledger needs a session id to tokenise")
        self._session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        self._budgets: Mapping[MeteredComponent, SessionBudget] = dict(
            budgets if budgets is not None else PUBLISHED_BUDGETS
        )
        if set(self._budgets) != set(MeteredComponent):
            raise ValueError(
                "a budget policy must declare every component: a component with no "
                "declared kind has no defined behaviour at exhaustion"
            )
        self._totals: dict[MeteredComponent, float] = dict.fromkeys(MeteredComponent, 0.0)
        self._charges: dict[MeteredComponent, int] = dict.fromkeys(MeteredComponent, 0)
        self._refusals: dict[MeteredComponent, int] = dict.fromkeys(MeteredComponent, 0)

    # --- reads ---------------------------------------------------------------------

    @property
    def session_key(self) -> str:
        """``sha256`` of the session id. The id itself is never stored."""
        return self._session_key

    def budget(self, component: MeteredComponent) -> SessionBudget:
        return self._budgets[component]

    def total(self, component: MeteredComponent) -> float:
        return self._totals[component]

    def charges(self, component: MeteredComponent) -> int:
        return self._charges[component]

    def refusals(self, component: MeteredComponent) -> int:
        return self._refusals[component]

    def totals(self) -> Mapping[MeteredComponent, float]:
        return dict(self._totals)

    def over_budget(self, component: MeteredComponent) -> bool:
        """Whether a declared limit has been passed. Undeclared is never over."""
        limit = self._budgets[component].limit
        return limit is not None and self._totals[component] > limit

    def __repr__(self) -> str:
        return f"SessionLedger(session_key={self._session_key!r})"

    # --- the gate ------------------------------------------------------------------

    def admits(self, component: MeteredComponent, charge_class: ChargeClass) -> Admission:
        """May this work be done? A pure query — it records nothing.

        Called *before* the work, because tokens cannot be un-spent. The
        quantity is not an argument: a caller does not know it yet, and a gate
        that pretended to would be guessing.
        """
        budget = self._budgets[component]
        if charge_class is ChargeClass.OBLIGATORY:
            return self._decision(component, charge_class, True, AdmissionReason.OBLIGATORY)
        if budget.kind is not BudgetKind.CAP:
            return self._decision(component, charge_class, True, AdmissionReason.NOT_CAPPED)
        if budget.limit is None:
            return self._decision(component, charge_class, False, AdmissionReason.CAP_UNDECLARED)
        if self._totals[component] < budget.limit:
            return self._decision(component, charge_class, True, AdmissionReason.WITHIN_CAP)
        return self._decision(component, charge_class, False, AdmissionReason.CAP_EXHAUSTED)

    def _decision(
        self,
        component: MeteredComponent,
        charge_class: ChargeClass,
        admitted: bool,
        reason: AdmissionReason,
    ) -> Admission:
        if not admitted:
            self._refusals[component] += 1
        return Admission(
            component=component,
            charge_class=charge_class,
            admitted=admitted,
            reason=reason,
        )

    # --- the record ----------------------------------------------------------------

    def record(self, component: MeteredComponent, quantity: float) -> float:
        """Record what was actually spent, and return the new total.

        Deliberately separate from :meth:`admits` and deliberately unable to
        refuse: spend that has happened is a fact, and a ledger that could
        decline to write it down would be a ledger that under-reports exactly
        when it matters. An obligatory charge past a cap is recorded and shows
        up in :meth:`over_budget`.
        """
        if quantity < 0.0:
            raise ValueError(
                "a negative charge would net spend off against itself; a correction is "
                "a new session record, not a smaller total"
            )
        self._totals[component] += quantity
        self._charges[component] += 1
        return self._totals[component]
