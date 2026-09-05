"""The edge: WAF policy, CrowdSec scenarios, certificate automation (INT-203).

files/10 §4 ``Edge:``. Two modules, and the split is the point:
:mod:`~intake_platform.edge.policy` is what the edge is *configured* to do,
and :mod:`~intake_platform.edge.logs` is what the edge is allowed to *say* —
because a WAF that blocks a request and then writes the patient's sentence
into the log has traded an injection for a disclosure (invariant 6).
"""

from intake_platform.edge.logs import EdgeEvent, parse_coraza_line
from intake_platform.edge.policy import (
    CRS_DEFAULT_INBOUND_THRESHOLD,
    CrowdSecPolicy,
    CrowdSecScenario,
    EdgePolicy,
    EdgePolicyError,
    RuleClass,
    TlsPolicy,
    WafPolicy,
    WafRuleExclusion,
    load_edge_policy,
)

__all__ = [
    "CRS_DEFAULT_INBOUND_THRESHOLD",
    "CrowdSecPolicy",
    "CrowdSecScenario",
    "EdgeEvent",
    "EdgePolicy",
    "EdgePolicyError",
    "RuleClass",
    "TlsPolicy",
    "WafPolicy",
    "WafRuleExclusion",
    "load_edge_policy",
    "parse_coraza_line",
]
