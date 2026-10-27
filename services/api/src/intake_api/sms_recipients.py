"""INT-528 — who the OTP tier may send an SMS to.

Owner order, 16 Oct 2026: SMS is real on the synthetic host, so there the API
sends a code, and starts an OTP login, only for a number on the owner's test
allow-list. The list is the SSM SecureString
``/intake/staging/sms_test_allowlist``, synced by
``infra/staging/netgsm_secrets.sh`` into OpenBao ``secret/api/netgsm`` as the
field ``test_allowlist``: Turkish mobiles in E.164, separated by commas,
semicolons, spaces or newlines.

It fails closed. An absent, empty or unreadable list, or one with a single
malformed entry, admits nobody: a typo must never quietly narrow the list to
something nobody checked. The numbers never reach a ``repr``, a log line or a
metric label (invariant 6); only their count is ever reported.

Outside the synthetic deployment there is no list: :data:`ADMIT_ALL` is the
gate, and the vendor's own reach (Turkish mobiles only) is the bound.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Protocol, final

__all__ = [
    "ADMIT_ALL",
    "SYNTHETIC_ENVIRONMENTS",
    "AdmitAll",
    "RecipientGate",
    "SmsTestAllowlist",
]

#: The deployments where SMS reaches only the owner's test numbers.
SYNTHETIC_ENVIRONMENTS: Final = frozenset({"staging"})

_TR_MOBILE_E164 = re.compile(r"\+905[0-9]{9}")
_SEPARATORS = re.compile(r"[\s,;]+")


class RecipientGate(Protocol):
    """Whether a code may be sent to this number (E.164)."""

    def admits(self, phone_e164: str) -> bool: ...


@final
@dataclass(frozen=True)
class AdmitAll:
    """No test list: every number the vendor can reach."""

    def admits(self, phone_e164: str) -> bool:
        del phone_e164
        return True


ADMIT_ALL: Final = AdmitAll()


@final
@dataclass(frozen=True)
class SmsTestAllowlist:
    """The synthetic host's test numbers. Shown only as a count."""

    numbers: frozenset[str] = field(repr=False)

    @property
    def count(self) -> int:
        return len(self.numbers)

    def admits(self, phone_e164: str) -> bool:
        return phone_e164 in self.numbers

    def __str__(self) -> str:
        return f"SmsTestAllowlist({self.count} numbers)"

    @classmethod
    def parse(cls, raw: object) -> SmsTestAllowlist:
        """The listed numbers, or none at all when anything is wrong."""
        if not isinstance(raw, str):
            return cls(frozenset())
        tokens = [token for token in _SEPARATORS.split(raw.strip()) if token]
        if not tokens or not all(_TR_MOBILE_E164.fullmatch(token) for token in tokens):
            return cls(frozenset())
        return cls(frozenset(tokens))
