"""The Model lanes governor's typed refusals (INT-428, ADR-035).

Each carries a machine-shaped ``code`` that reaches an HTTP body and echoes
no submitted value (invariant 6). Kept apart from the governor so the route
layer can map them without importing the rule.
"""

from __future__ import annotations

__all__ = [
    "ModelLanesActionMismatch",
    "ModelLanesChanged",
    "ModelLanesGovernanceRefused",
    "ModelLanesNothingToChange",
    "ModelLanesRoleIneligible",
    "SelfHostedNotHealthy",
]


class ModelLanesGovernanceRefused(Exception):
    """Base refusal; ``code`` is machine-shaped and reaches an HTTP body."""

    code = "model_lanes_refused"

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message or (code or self.code))
        if code is not None:
            self.code = code


class ModelLanesRoleIneligible(ModelLanesGovernanceRefused):
    code = "model_lanes_role_ineligible"


class ModelLanesNothingToChange(ModelLanesGovernanceRefused):
    code = "model_lanes_nothing_to_change"


class ModelLanesChanged(ModelLanesGovernanceRefused):
    code = "model_lanes_changed"


class ModelLanesActionMismatch(ModelLanesGovernanceRefused):
    code = "model_lanes_action_mismatch"


class SelfHostedNotHealthy(ModelLanesGovernanceRefused):
    code = "model_lanes_self_hosted_not_healthy"
