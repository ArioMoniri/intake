"""INT-038 — consent purposes, docs/legal text binding, grant/withdraw over
the INT-030 model, and the withdrawal-cascade contract (files/06 §2;
invariants 4, 6, 18). The api-side enforcement lives in
services/api intake_api.consent_guard; this package is the source of truth
it enforces."""

from __future__ import annotations

from intake_platform.consent.registry import (
    CHANNELS,
    CORE,
    PURPOSES,
    REMOVED_PURPOSES,
    LegalBasis,
    PurposeDef,
    UnknownPurposeError,
    dependents_of,
    purpose_ids,
    resolve_scope,
)
from intake_platform.consent.service import (
    OPT_OUT_VERSION,
    ConsentAudit,
    ConsentDecision,
    WithdrawalReport,
    consent_state,
    grant_consent,
    is_scope_allowed,
    sweep_withdrawals,
    withdraw_consent,
)
from intake_platform.consent.sweep import (
    SWEEP_INTERVAL,
    SWEEP_PASS_BUDGET,
    WITHDRAWAL_CASCADE_BUDGET,
    SweepSchedule,
)
from intake_platform.consent.texts import (
    ConsentText,
    ConsentTextCatalog,
    ConsentTextError,
    ConsentTextInvalidError,
    ConsentTextMissingError,
    text_filename,
)

__all__ = [
    "CHANNELS",
    "CORE",
    "OPT_OUT_VERSION",
    "PURPOSES",
    "REMOVED_PURPOSES",
    "SWEEP_INTERVAL",
    "SWEEP_PASS_BUDGET",
    "WITHDRAWAL_CASCADE_BUDGET",
    "ConsentAudit",
    "ConsentDecision",
    "ConsentText",
    "ConsentTextCatalog",
    "ConsentTextError",
    "ConsentTextInvalidError",
    "ConsentTextMissingError",
    "LegalBasis",
    "PurposeDef",
    "SweepSchedule",
    "UnknownPurposeError",
    "WithdrawalReport",
    "consent_state",
    "dependents_of",
    "grant_consent",
    "is_scope_allowed",
    "purpose_ids",
    "resolve_scope",
    "sweep_withdrawals",
    "text_filename",
    "withdraw_consent",
]
