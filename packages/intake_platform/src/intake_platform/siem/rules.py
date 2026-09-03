"""INT-205 — loaders for the committed rulesets and for ossec.conf.

Everything here is *config-level*: it decides whether the shipped detection
configuration holds without booting a manager, an indexer or a kernel driver.
That is the only half of this issue this host can exercise (HB-I1, HB-I2), and
it is also the half that would otherwise be checked by nobody until an incident.

The rulesets do double duty. They are what the manager and the agent load, and
they are also the **name catalogue the feed resolves against**: a rule name in
an alert payload is trustworthy only if it came from a file in this repository,
because Wazuh expands ``$(field)`` inside a rule description at alert time.
"""

from __future__ import annotations

# ElementTree over defusedxml deliberately: these are committed files in this
# repository, not input, and Python's ElementTree resolves no external entities
# at all. Adding a dependency to parse our own two files would be theatre.
import xml.etree.ElementTree as ET  # noqa: S405
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from intake_platform.siem.errors import SiemConfigError
from intake_platform.siem.models import Severity, Signal, is_rule_name_like

__all__ = [
    "FALCO_PRIORITY_SEVERITY",
    "FalcoRule",
    "FalcoRuleset",
    "LocalFile",
    "OssecConfig",
    "RuleCatalogue",
    "RuleEntry",
    "WAZUH_LEVEL_SEVERITY",
    "WazuhRule",
    "WazuhRuleset",
    "load_falco_ruleset",
    "load_ossec_config",
    "load_rule_catalogue",
    "load_wazuh_ruleset",
]

#: Wazuh reserves rule ids below 100000 for its own shipped ruleset; 100000 to
#: 119999 is the documented user range. Reusing a vendor id silently replaces a
#: vendor rule, which is a detection loss nobody would notice.
USER_RULE_RANGE = range(100000, 120000)

#: Group token -> the signal it declares. Closed: a rule whose groups name none
#: of these has no place in the console's Security module, and inventing a
#: fourth class for it would be worse than refusing the file.
_GROUP_SIGNAL = {
    "intake_auth_anomaly": Signal.AUTH_ANOMALY,
    "intake_k8s_audit": Signal.K8S_AUDIT,
    "intake_container_runtime": Signal.CONTAINER_RUNTIME,
}

#: Correlation directives. files/10 §7 names the signals — failed logins and
#: OTP anomalies per phone/IP/ASN, impossible travel, token reuse — and states
#: a number for none of them, so a `frequency`/`timeframe` pair here would be a
#: detection threshold nobody supplied (CLAUDE.md: never invent a value).
_BANNED_RULE_ELEMENTS = ("frequency", "timeframe", "ignore", "same_source_ip")

#: Wazuh's published level scale mapped onto the runbook's severity ladder.
#: Neither ladder is invented here: the levels are Wazuh's (15 "severe attack",
#: 12-14 high-importance security events, 7-11 warnings, 0-6 notifications and
#: user errors) and the SEV rungs are docs/security/incident-runbook.md's. This
#: table is the join between them, in one place, so the console and the pager
#: cannot disagree.
WAZUH_LEVEL_SEVERITY: dict[int, Severity] = {
    **{level: Severity.SEV4 for level in range(0, 7)},
    **{level: Severity.SEV3 for level in range(7, 12)},
    **{level: Severity.SEV2 for level in range(12, 15)},
    15: Severity.SEV1,
}

#: Falco writes a syslog priority. Same join, same reasoning.
FALCO_PRIORITY_SEVERITY: dict[str, Severity] = {
    "emergency": Severity.SEV1,
    "alert": Severity.SEV1,
    "critical": Severity.SEV2,
    "error": Severity.SEV2,
    "warning": Severity.SEV3,
    "notice": Severity.SEV3,
    "informational": Severity.SEV4,
    "info": Severity.SEV4,
    "debug": Severity.SEV4,
}


@dataclass(frozen=True, slots=True)
class WazuhRule:
    rule_id: int
    level: int
    name: str
    signal: Signal

    @property
    def severity(self) -> Severity:
        return WAZUH_LEVEL_SEVERITY[self.level]


@dataclass(frozen=True, slots=True)
class WazuhRuleset:
    path: Path
    rules: tuple[WazuhRule, ...]


@dataclass(frozen=True, slots=True)
class FalcoRule:
    name: str
    output: str
    priority: str
    signal: Signal

    @property
    def severity(self) -> Severity:
        return FALCO_PRIORITY_SEVERITY[self.priority.lower()]


@dataclass(frozen=True, slots=True)
class FalcoRuleset:
    path: Path
    rules: tuple[FalcoRule, ...]


@dataclass(frozen=True, slots=True)
class LocalFile:
    location: str
    log_format: str


@dataclass(frozen=True, slots=True)
class OssecConfig:
    path: Path
    localfiles: tuple[LocalFile, ...]
    email_notification: bool
    vendor_reporting: bool
    log_retention_days: int | None


def _text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _groups_of(rule: ET.Element, parent: ET.Element) -> set[str]:
    tokens: set[str] = set()
    for source in (parent.get("name", ""), _text(rule.find("group"))):
        tokens |= {token.strip() for token in source.split(",") if token.strip()}
    return tokens


def load_wazuh_ruleset(path: Path) -> WazuhRuleset:
    """Parse the committed Wazuh ruleset, refusing anything it must not carry.

    A Wazuh rule file is an XML *fragment*: one ``<group>`` element per signal,
    all at the top level, with no document root. ElementTree wants exactly one
    root, so the text is wrapped before parsing. Wrapping rather than nesting
    the groups matters — Wazuh does not read nested ``<group>`` elements, and a
    file that parses here but not in the manager would be worse than useless.
    """
    try:
        text = path.read_text(encoding="utf-8")
        # nosec B314 — same call, same decision as the ruff suppression beside
        # it: `path` is a COMMITTED, version-controlled ruleset in this repo,
        # not attacker-supplied input. INT-019 added bandit, which reports the
        # rule ruff already had suppressed here; the two markers agree.
        root = ET.fromstring(f"<wazuh_ruleset>{text}</wazuh_ruleset>")  # noqa: S314 # nosec B314
    except (ET.ParseError, OSError) as exc:
        raise SiemConfigError(f"{path.name}: not parseable as a Wazuh ruleset: {exc}") from exc

    if "$(" in text:
        raise SiemConfigError(
            f"{path.name}: a description interpolates an event field with $(). "
            "That is how patient text reaches a rule name."
        )

    rules: list[WazuhRule] = []
    seen: set[int] = set()
    for parent in root.iter("group"):
        for rule in parent.findall("rule"):
            rules.append(_parse_wazuh_rule(path, parent, rule, seen))
    if not rules:
        raise SiemConfigError(f"{path.name}: holds no rules")
    return WazuhRuleset(path=path, rules=tuple(rules))


def _parse_wazuh_rule(
    path: Path, parent: ET.Element, rule: ET.Element, seen: set[int]
) -> WazuhRule:
    raw_id = rule.get("id", "")
    try:
        rule_id = int(raw_id)
    except ValueError as exc:
        raise SiemConfigError(f"{path.name}: rule id {raw_id!r} is not a number") from exc
    if rule_id not in USER_RULE_RANGE:
        raise SiemConfigError(
            f"{path.name}: rule {rule_id} is outside the Wazuh user range "
            f"{USER_RULE_RANGE.start}-{USER_RULE_RANGE.stop - 1}; it would replace a vendor rule"
        )
    if rule_id in seen:
        raise SiemConfigError(f"{path.name}: rule id {rule_id} appears twice")
    seen.add(rule_id)

    for banned in _BANNED_RULE_ELEMENTS:
        if rule.find(banned) is not None:
            raise SiemConfigError(
                f"{path.name}: rule {rule_id} sets <{banned}>, a correlation threshold "
                "files/10 §7 does not state. Never invent a value to unblock yourself."
            )

    try:
        level = int(rule.get("level", ""))
    except ValueError as exc:
        raise SiemConfigError(f"{path.name}: rule {rule_id} has no numeric level") from exc
    if level not in WAZUH_LEVEL_SEVERITY:
        raise SiemConfigError(f"{path.name}: rule {rule_id} level {level} is off the 0-15 scale")

    name = _text(rule.find("description"))
    if not is_rule_name_like(name):
        raise SiemConfigError(
            f"{path.name}: rule {rule_id} description is not identifier-shaped: {name!r}"
        )

    signals = {_GROUP_SIGNAL[token] for token in _groups_of(rule, parent) if token in _GROUP_SIGNAL}
    if len(signals) != 1:
        raise SiemConfigError(
            f"{path.name}: rule {rule_id} must declare exactly one signal group "
            f"({', '.join(sorted(_GROUP_SIGNAL))}); it declares {len(signals)}"
        )
    return WazuhRule(rule_id=rule_id, level=level, name=name, signal=signals.pop())


def load_falco_ruleset(path: Path) -> FalcoRuleset:
    """Parse the committed Falco ruleset (a YAML list of rules/macros/lists)."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        raise SiemConfigError(f"{path.name}: not parseable as a Falco ruleset: {exc}") from exc
    if not isinstance(raw, list):
        raise SiemConfigError(f"{path.name}: a Falco ruleset is a list of entries")

    rules: list[FalcoRule] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict) or "rule" not in entry:
            continue
        rules.append(_parse_falco_rule(path, entry, seen))
    if not rules:
        raise SiemConfigError(f"{path.name}: holds no rules")
    return FalcoRuleset(path=path, rules=tuple(rules))


def _parse_falco_rule(path: Path, entry: dict[str, Any], seen: set[str]) -> FalcoRule:
    name = str(entry["rule"])
    if not is_rule_name_like(name):
        raise SiemConfigError(f"{path.name}: rule name is not identifier-shaped: {name!r}")
    if name in seen:
        raise SiemConfigError(f"{path.name}: rule {name!r} appears twice")
    seen.add(name)

    priority = entry.get("priority")
    if priority is None:
        raise SiemConfigError(f"{path.name}: rule {name!r} states no priority")
    if str(priority).lower() not in FALCO_PRIORITY_SEVERITY:
        raise SiemConfigError(
            f"{path.name}: rule {name!r} priority {priority!r} is not a Falco priority"
        )

    tags = {str(tag) for tag in entry.get("tags", [])}
    if "intake_container_runtime" not in tags:
        raise SiemConfigError(f"{path.name}: rule {name!r} must be tagged intake_container_runtime")
    return FalcoRule(
        name=name,
        output=str(entry.get("output", "")),
        priority=str(priority),
        signal=Signal.CONTAINER_RUNTIME,
    )


def load_ossec_config(path: Path) -> OssecConfig:
    """Parse the committed manager configuration and hold it to §7 and §8."""
    try:
        # nosec B314 — see load_wazuh_ruleset: a committed, version-controlled
        # manager configuration, not attacker-supplied input.
        root = ET.parse(path).getroot()  # noqa: S314 # nosec B314
    except (ET.ParseError, OSError) as exc:
        raise SiemConfigError(f"{path.name}: not parseable as an ossec.conf: {exc}") from exc

    localfiles: list[LocalFile] = []
    for element in root.iter("localfile"):
        location = _text(element.find("location"))
        log_format = _text(element.find("log_format"))
        if log_format != "json":
            raise SiemConfigError(
                f"{path.name}: {location} is ingested as {log_format!r}. Every source this "
                "manager reads is json, so fields are decoded rather than regex-scraped out "
                "of a line that may hold patient text."
            )
        localfiles.append(LocalFile(location=location, log_format=log_format))
    if not localfiles:
        raise SiemConfigError(f"{path.name}: ingests nothing")

    email = _text(root.find(".//global/email_notification")).lower() == "yes"
    if email:
        raise SiemConfigError(
            f"{path.name}: email_notification is on. A mail relay is an egress path out of "
            "the PHI network and there is no allow-list entry for one (files/10 §4)."
        )

    update_check = _text(root.find(".//global/update_check")).lower() == "yes"
    vuln_detection = _text(root.find(".//vulnerability-detection/enabled")).lower() == "yes"

    rotation = root.find(".//logging/rotation")
    retention: int | None = None
    if rotation is not None:
        max_age = _text(rotation.find("max_age"))
        retention = int(max_age) if max_age.isdigit() else None

    return OssecConfig(
        path=path,
        localfiles=tuple(localfiles),
        email_notification=email,
        vendor_reporting=update_check or vuln_detection,
        log_retention_days=retention,
    )


@dataclass(frozen=True, slots=True)
class RuleEntry:
    """What the feed is allowed to say about a rule, resolved from a file."""

    name: str
    signal: Signal


@dataclass(frozen=True, slots=True)
class RuleCatalogue:
    wazuh_ids: dict[int, RuleEntry]
    falco_names: dict[str, RuleEntry]

    def for_wazuh(self, rule_id: int) -> RuleEntry | None:
        return self.wazuh_ids.get(rule_id)

    def for_falco(self, name: str) -> RuleEntry | None:
        return self.falco_names.get(name)


def load_rule_catalogue(wazuh_path: Path, falco_path: Path) -> RuleCatalogue:
    """Build the name catalogue from the two rulesets that are actually loaded."""
    wazuh = load_wazuh_ruleset(wazuh_path)
    falco = load_falco_ruleset(falco_path)
    return RuleCatalogue(
        wazuh_ids={
            rule.rule_id: RuleEntry(name=rule.name, signal=rule.signal) for rule in wazuh.rules
        },
        falco_names={
            rule.name: RuleEntry(name=rule.name, signal=rule.signal) for rule in falco.rules
        },
    )
