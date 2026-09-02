"""INT-206 — the one refusal the CI policy makes."""

from __future__ import annotations

__all__ = ["CiPolicyError"]


class CiPolicyError(ValueError):
    """A committed CI policy or runner-pool file does not hold.

    Raised at load time rather than reported as a finding, because a policy
    file that cannot be read is not a policy that passed — and a gate that
    degrades to "no rules" when its rules are unparseable is a gate that an
    editing mistake silently disables.
    """
