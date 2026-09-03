"""INT-101 — session budgets and cost metering per component and profile.

sec_row: `llm-boundary` (docs/security/threat-model.md). files/10 §5 LLM10,
*"unbounded consumption"*. files/08 §4 group J, *"cost"*.

Read :mod:`intake_voice_runtime.metering.budgets` first: it decides what kind
of object each budget is, which is the question the acceptance line leaves
open and the one everything else here follows from.

Two things this package does **not** do, both deliberate and both recorded
where they are decided:

* it emits no ``cost.per_session`` (:mod:`intake_voice_runtime.metering.cost` —
  there is no price, and a plausible one is worse than none);
* it emits no series for Backend extraction tokens (files/08 §4 states that row
  without an id; :mod:`intake_voice_runtime.metering.meter` says why an id is
  not minted here).
"""

from __future__ import annotations

from intake_voice_runtime.metering.adapters import (
    ElectiveWorkRefused,
    MeteredExtractionGateway,
    MeteredSpeechSynthesizer,
)
from intake_voice_runtime.metering.budgets import (
    PUBLISHED_BUDGETS,
    BudgetKind,
    SessionBudget,
    budget_for,
    published_budgets,
)
from intake_voice_runtime.metering.components import (
    UNIT_OF,
    ChargeClass,
    MeteredComponent,
    MeterUnit,
)
from intake_voice_runtime.metering.cost import (
    CostNotPriced,
    PriceBook,
    Unpriced,
    priced_cost,
)
from intake_voice_runtime.metering.ledger import Admission, AdmissionReason, SessionLedger
from intake_voice_runtime.metering.meter import SELF_HOSTED, SessionMeter, TurnLabels

__all__ = [
    "PUBLISHED_BUDGETS",
    "SELF_HOSTED",
    "UNIT_OF",
    "Admission",
    "AdmissionReason",
    "BudgetKind",
    "ChargeClass",
    "CostNotPriced",
    "ElectiveWorkRefused",
    "MeterUnit",
    "MeteredComponent",
    "MeteredExtractionGateway",
    "MeteredSpeechSynthesizer",
    "PriceBook",
    "SessionBudget",
    "SessionLedger",
    "SessionMeter",
    "TurnLabels",
    "Unpriced",
    "budget_for",
    "priced_cost",
    "published_budgets",
]
