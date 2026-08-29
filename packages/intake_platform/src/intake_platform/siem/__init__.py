"""INT-205 — Wazuh + Falco: the tier, its rules, and the console feed.

Three pieces, in the order an alert travels through them:

1. **the tier** (infra/docker-compose.siem.yml, infra/security/wazuh,
   infra/security/falco) — a Wazuh manager and indexer, and a Falco agent that
   writes JSON into a volume the manager reads. No dashboard: files/10 §7 puts
   the dashboards in the console's Security module, and a second web console
   over the alert store would be the parallel authorization plane files/08 §0b
   F1 names.
2. **the rules** (:mod:`intake_platform.siem.rules`) — loaded and validated
   here as well as by the manager, because this is the half a laptop can check.
   They are also the name catalogue the feed resolves against.
3. **the feed** (:mod:`intake_platform.siem.feed`) — vendor alert in,
   :class:`SecurityAlert` out, with a scrub boundary
   (:mod:`intake_platform.siem.normalise`) that reads a closed key set and
   nothing else.

The scrub boundary is the reason this package exists in ``intake_platform``
rather than in ``infra/``. A SIEM is the one component with permission to read
every log, every file name and every command line on the PHI path; the alert it
emits is the shortest path from that permission to a ticket, a chat message or a
screen. Invariant 6 has to be enforced on our side of the vendor, so it is.
"""

from __future__ import annotations

from intake_platform.siem.deploy import (
    MIN_CONTAINER_MEMORY_BYTES,
    MIN_FREE_DISK_BYTES,
    RETENTION_ASK,
    RETENTION_ENV,
    DeployBlocked,
    DeployStep,
    host_preflight,
    plan_siem_deploy,
)
from intake_platform.siem.errors import (
    AlertRefused,
    RetentionNotConfiguredError,
    SiemConfigError,
)
from intake_platform.siem.feed import (
    ALERTS_PATH_ENV,
    ConsoleFeed,
    FeedCounts,
    default_alerts_path,
    load_console_feed,
)
from intake_platform.siem.models import (
    AlertSource,
    ScrubbedPath,
    SecurityAlert,
    Severity,
    Signal,
    is_identifier_like,
    is_rule_name_like,
)
from intake_platform.siem.normalise import normalise_alert, normalise_falco, normalise_wazuh
from intake_platform.siem.rules import (
    FALCO_PRIORITY_SEVERITY,
    USER_RULE_RANGE,
    WAZUH_LEVEL_SEVERITY,
    FalcoRule,
    FalcoRuleset,
    LocalFile,
    OssecConfig,
    RuleCatalogue,
    RuleEntry,
    WazuhRule,
    WazuhRuleset,
    load_falco_ruleset,
    load_ossec_config,
    load_rule_catalogue,
    load_wazuh_ruleset,
)
from intake_platform.siem.scrub import scrub_path

__all__ = [
    "ALERTS_PATH_ENV",
    "FALCO_PRIORITY_SEVERITY",
    "MIN_CONTAINER_MEMORY_BYTES",
    "MIN_FREE_DISK_BYTES",
    "RETENTION_ASK",
    "RETENTION_ENV",
    "USER_RULE_RANGE",
    "WAZUH_LEVEL_SEVERITY",
    "AlertRefused",
    "AlertSource",
    "ConsoleFeed",
    "DeployBlocked",
    "DeployStep",
    "FalcoRule",
    "FalcoRuleset",
    "FeedCounts",
    "LocalFile",
    "OssecConfig",
    "RetentionNotConfiguredError",
    "RuleCatalogue",
    "RuleEntry",
    "ScrubbedPath",
    "SecurityAlert",
    "Severity",
    "SiemConfigError",
    "Signal",
    "WazuhRule",
    "WazuhRuleset",
    "default_alerts_path",
    "host_preflight",
    "is_identifier_like",
    "is_rule_name_like",
    "load_console_feed",
    "load_falco_ruleset",
    "load_ossec_config",
    "load_rule_catalogue",
    "load_wazuh_ruleset",
    "normalise_alert",
    "normalise_falco",
    "normalise_wazuh",
    "plan_siem_deploy",
    "scrub_path",
]
