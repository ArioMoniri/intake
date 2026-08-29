"""INT-133 — profiles, companions, guardian flows, proxy acknowledgement.

The FLOW layer over INT-223's rules engine (``intake_platform.consent.
minors`` / ``.guardian``). It consumes that engine's decisions and softens
none of them: every value HB-L20 left with counsel stays refused, and a flow
that cannot proceed without one fails closed while naming the question.

Three modules:

- :mod:`~intake_platform.profiles.attribution` — the three files/02 §3
  attribution values, derived from a declared role + speaker, plus the
  files/06 §6 ``proxy_reported`` flag and the files/13 §13 third-party
  regime;
- :mod:`~intake_platform.profiles.flow` — the next step for a session, with
  the HB-L20 rows that block it;
- :mod:`~intake_platform.profiles.sections` — the adolescent-private section
  per files/06 §6.
"""

from __future__ import annotations

from intake_platform.profiles.attribution import (
    PROXY_ACK_REQUIRED,
    Attribution,
    AttributionDecision,
    ProxyAcknowledgement,
    SensitiveDelivery,
    Speaker,
    SubjectRole,
    resolve_attribution,
)
from intake_platform.profiles.flow import (
    ProfileFlowOutcome,
    ProfileFlowStep,
    blocking_policy_rows,
    resolve_profile_flow,
)
from intake_platform.profiles.sections import (
    ADOLESCENT_PRIVATE_SECTION,
    SectionRelease,
    release_adolescent_private_section,
)

__all__ = [
    "ADOLESCENT_PRIVATE_SECTION",
    "PROXY_ACK_REQUIRED",
    "Attribution",
    "AttributionDecision",
    "ProfileFlowOutcome",
    "ProfileFlowStep",
    "ProxyAcknowledgement",
    "SectionRelease",
    "SensitiveDelivery",
    "Speaker",
    "SubjectRole",
    "blocking_policy_rows",
    "release_adolescent_private_section",
    "resolve_attribution",
    "resolve_profile_flow",
]
