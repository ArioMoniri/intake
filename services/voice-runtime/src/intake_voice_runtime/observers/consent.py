"""Per-lane consent — KVKK-6, files/06 §2 (INT-038's closed purpose list).

files/03 §4.7: *"Each lane is a separate consent purpose and can be disabled
per tenant or patient without affecting intake."* The rule this module encodes
is the strict reading of that: **a lane with no consent scope does not run**,
and the scope has to be one the closed files/06 §2 registry already knows.

Three of the five lanes therefore behave differently, and each difference is
the blueprint's, not this module's:

- ``affect`` and ``linguistic`` have purposes — ``lane:affect`` and
  ``lane:linguistic`` — and run when they are granted;
- ``acoustic`` has **no scope at all, deliberately**. files/06 §2.4 removed it
  from the purpose list on 25 Aug 2026 and made it an investigational-device
  informed-consent form: *"a device you may not place on the market is not
  made lawful by a toggle."* Asking for it here is refused by name, and the
  lane's gate is :mod:`intake_voice_runtime.observers.study` instead;
- ``asr_quality`` and ``engagement`` have **no purpose any human has
  decided**. files/03 §4.7 says every lane is its own consent purpose and
  files/06 §2 lists two; the two files disagree, and the disagreement is a
  legal question, not an engineering one. The framework refuses to invent a
  scope to unblock itself (CLAUDE.md), so those two lanes cannot be
  registered. The mechanism is built, the gate is wired, it fails closed, and
  the content is empty — the ask is recorded in docs/evidence/INT-110.md.

The consent *store* is not reachable from here. The lane framework takes a
:class:`ConsentProbe`, which the worker satisfies from
``intake_platform.consent``; a lane package that imported the consent service
would import a database session, and invariant 13 says lanes hold no such
capability. The probe is synchronous for the same reason ``WorkSubmitter`` is:
it is read on the frame-offer path, and an awaitable there would be a way for
a consent check to delay speech.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel
from clinical_schemas.observers import Lane
from pydantic import Field

__all__ = [
    "LANE_CONSENT_SCOPES",
    "REFUSED_CONSENT_SCOPES",
    "UNDECLARED_CONSENT_LANES",
    "ConsentProbe",
    "ConsentReading",
    "LaneConsentError",
    "LaneConsentScopeRefusedError",
    "LaneConsentUndeclaredError",
    "consent_scope_for",
]

#: The lane purposes files/06 §2 actually lists. Not extended here: the list
#: is closed, and INT-038's registry is where it lives.
LANE_CONSENT_SCOPES: Final[Mapping[Lane, str]] = MappingProxyType(
    {
        Lane.AFFECT: "lane:affect",
        Lane.LINGUISTIC: "lane:linguistic",
    }
)

#: Scopes that must never be asked for. ``lane:acoustic`` is in INT-038's
#: ``REMOVED_PURPOSES`` for the files/06 §2.4 reason; refusing it a second
#: time here means a lane cannot even form the request.
REFUSED_CONSENT_SCOPES: Final[Mapping[Lane, str]] = MappingProxyType(
    {Lane.ACOUSTIC: "lane:acoustic"}
)

#: Lanes files/03 §4.7 says need a purpose and files/06 §2 does not give one.
UNDECLARED_CONSENT_LANES: Final[frozenset[Lane]] = frozenset(
    set(Lane) - set(LANE_CONSENT_SCOPES) - set(REFUSED_CONSENT_SCOPES)
)


class LaneConsentError(RuntimeError):
    """A lane cannot be run because of its consent scope."""


class LaneConsentUndeclaredError(LaneConsentError):
    """No human has decided this lane's consent purpose. Fail closed."""


class LaneConsentScopeRefusedError(LaneConsentError):
    """The scope is refused by name: it is an ICF, not a toggle (files/06 §2.4)."""


class ConsentReading(FrozenModel):
    """One granted scope, at the version whose text the patient was shown.

    The version travels with every lane read because files/03 §4.8 makes
    ``consent_version`` a recorded field on the signal — a signal you cannot
    attribute to a consent version is a signal you cannot defend at an audit.
    """

    scope: str = Field(min_length=1)
    version: str = Field(min_length=1)


@runtime_checkable
class ConsentProbe(Protocol):
    """The consent state, as the lane framework needs it. **Not awaitable.**"""

    def granted(self, scope: str) -> ConsentReading | None: ...


def consent_scope_for(lane: Lane) -> str:
    """The consent scope this lane must hold, or a refusal saying why not."""
    refused = REFUSED_CONSENT_SCOPES.get(lane)
    if refused is not None:
        raise LaneConsentScopeRefusedError(
            f"{refused} is not a consent purpose: files/06 §2.4 makes the acoustic "
            "module an investigational-device informed-consent form, and a device "
            "you may not place on the market is not made lawful by a toggle"
        )
    scope = LANE_CONSENT_SCOPES.get(lane)
    if scope is None:
        raise LaneConsentUndeclaredError(
            f"the {lane.value} lane has no consent purpose in the closed files/06 §2 "
            "list, so it cannot be run. files/03 §4.7 says every lane is its own "
            "purpose and files/06 §2 names two; reconciling them is a legal "
            "decision (docs/evidence/INT-110.md)"
        )
    return scope
