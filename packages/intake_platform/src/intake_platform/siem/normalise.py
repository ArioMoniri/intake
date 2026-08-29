"""INT-205 — the scrub boundary: vendor alert in, :class:`SecurityAlert` out.

This module is the whole PHI control, and its shape matters more than its
contents: it reads a **closed list of keys** out of the vendor payload and
ignores everything else. It does not walk the event, it does not copy unknown
fields "for context", and it does not fall back to the raw line when a key is
missing. Whatever a detector decides to put in ``output``, ``full_log``,
``proc.cmdline`` or ``data`` is therefore unreachable by construction rather
than by filtering — a filter can be outrun, a key that is never read cannot.

Two fields are worth naming because they look harmless and are not:

* **the rule's prose.** Wazuh expands ``$(field)`` inside a rule description at
  alert time, so ``rule.description`` is event data wearing a rule name. Names
  come from :mod:`intake_platform.siem.rules` by id, or not at all.
* **the file path.** A container-runtime alert is useless without one, and
  ``/data/uploads/Ayse-göğüs-ağrısı-anamnez.txt`` is a filename rather than a
  log line. :func:`intake_platform.siem.scrub.scrub_path` keeps the shape and
  digests the rest.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from intake_platform.siem.errors import AlertRefused
from intake_platform.siem.metrics import ALERTS_INGESTED, ALERTS_REFUSED, FIELDS_DROPPED
from intake_platform.siem.models import (
    AlertSource,
    ScrubbedPath,
    SecurityAlert,
    Signal,
    is_identifier_like,
)
from intake_platform.siem.rules import (
    FALCO_PRIORITY_SEVERITY,
    WAZUH_LEVEL_SEVERITY,
    RuleCatalogue,
)
from intake_platform.siem.scrub import scrub_path

__all__ = ["normalise_alert", "normalise_falco", "normalise_wazuh"]

#: The only Falco keys read. `output`, `output_fields.proc.cmdline`,
#: `output_fields.evt.args` and `output_fields.container.name` are deliberately
#: absent: the first three are narrative and the fourth is operator-chosen text.
_FALCO_KEYS = ("rule", "priority", "hostname", "time", "output_fields")

#: The only Falco output_fields read.
_FALCO_FIELD_KEYS = ("container.id", "fd.name")

#: The only Wazuh keys read. `full_log`, `previous_output` and `data` are
#: absent: `data` is the decoded application log line, which is where our own
#: services' fields live, and a service that ever logged narrative would hand
#: it straight to the console through this door.
_WAZUH_KEYS = ("rule", "agent", "timestamp", "id", "syscheck")


def _closed(event: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Project a payload onto a closed key set.

    Written as a projection rather than as a series of ``event.get`` calls so
    the claim "these keys and no others" is executable: a later edit that reads
    a sixth key has to add it to the tuple above, next to the comment saying
    why the omitted ones are omitted.
    """
    return {key: event.get(key) for key in keys}


def _identifier_or_none(source: AlertSource, field: str, value: Any) -> str | None:
    """Keep ``value`` only if it is an identifier; count it when it is not."""
    if value is None:
        return None
    text = str(value)
    if is_identifier_like(text):
        return text
    FIELDS_DROPPED.labels(source=source.value, field=field).inc()
    return None


def _digest16(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _scrubbed(source: AlertSource, field: str, raw: Any) -> ScrubbedPath | None:
    if raw is None:
        return None
    try:
        scrubbed = scrub_path(str(raw))
    except AlertRefused:
        FIELDS_DROPPED.labels(source=source.value, field=field).inc()
        return None
    if scrubbed.truncated:
        FIELDS_DROPPED.labels(source=source.value, field=field).inc()
    return scrubbed


def _refuse(source: AlertSource, reason: str, message: str) -> AlertRefused:
    ALERTS_REFUSED.labels(source=source.value, reason=reason).inc()
    return AlertRefused(message)


def _admit(alert: SecurityAlert) -> SecurityAlert:
    ALERTS_INGESTED.labels(
        source=alert.source.value, signal=alert.signal.value, severity=alert.severity.value
    ).inc()
    return alert


def normalise_falco(event: Mapping[str, Any], catalogue: RuleCatalogue) -> SecurityAlert:
    """Reduce one Falco JSON alert to a :class:`SecurityAlert`."""
    source = AlertSource.FALCO
    read = _closed(event, _FALCO_KEYS)
    priority = str(read["priority"] or "").lower()
    if priority not in FALCO_PRIORITY_SEVERITY:
        raise _refuse(
            source,
            "unknown_priority",
            f"falco priority {read['priority']!r} is not a priority",
        )

    rule = str(read["rule"] or "")
    if not rule:
        raise _refuse(source, "no_rule", "falco alert names no rule")
    entry = catalogue.for_falco(rule)

    observed_at = _identifier_or_none(source, "time", read["time"])
    if observed_at is None:
        raise _refuse(source, "no_timestamp", "falco alert carries no usable timestamp")

    raw_fields = read["output_fields"]
    fields = _closed(raw_fields, _FALCO_FIELD_KEYS) if isinstance(raw_fields, Mapping) else {}
    container_id = _identifier_or_none(source, "container.id", fields.get("container.id"))
    path = _scrubbed(source, "fd.name", fields.get("fd.name"))

    rule_ref = _digest16(rule)
    return _admit(
        SecurityAlert(
            alert_id=_digest16(f"falco:{rule_ref}:{observed_at}:{container_id}"),
            source=source,
            rule_ref=rule_ref,
            rule_name=entry.name if entry is not None else None,
            # Falco only ever reports host and container runtime behaviour, so
            # an unrecognised rule is still a container-runtime signal — unlike
            # Wazuh, where the vendor ruleset spans everything.
            signal=entry.signal if entry is not None else Signal.CONTAINER_RUNTIME,
            severity=FALCO_PRIORITY_SEVERITY[priority],
            observed_at=observed_at,
            host_id=_identifier_or_none(source, "hostname", read["hostname"]),
            container_id=container_id,
            agent_id=None,
            path=path,
        )
    )


def normalise_wazuh(event: Mapping[str, Any], catalogue: RuleCatalogue) -> SecurityAlert:
    """Reduce one Wazuh alert (a line of alerts.json) to a :class:`SecurityAlert`."""
    source = AlertSource.WAZUH
    read = _closed(event, _WAZUH_KEYS)
    rule = read["rule"]
    if not isinstance(rule, Mapping):
        raise _refuse(source, "no_rule", "wazuh alert carries no rule block")

    raw_id = str(rule.get("id", ""))
    if not raw_id.isdigit() or len(raw_id) > 7:
        raise _refuse(source, "no_rule", f"wazuh rule id {raw_id!r} is not a rule id")

    level = rule.get("level")
    if not isinstance(level, int) or level not in WAZUH_LEVEL_SEVERITY:
        raise _refuse(source, "unknown_level", f"wazuh rule level {level!r} is off the 0-15 scale")

    observed_at = _identifier_or_none(source, "timestamp", read["timestamp"])
    if observed_at is None:
        raise _refuse(source, "no_timestamp", "wazuh alert carries no usable timestamp")

    entry = catalogue.for_wazuh(int(raw_id))
    agent = read["agent"] if isinstance(read["agent"], Mapping) else {}
    syscheck = read["syscheck"] if isinstance(read["syscheck"], Mapping) else {}

    alert_id = _identifier_or_none(source, "id", read["id"])
    return _admit(
        SecurityAlert(
            alert_id=alert_id or _digest16(f"wazuh:{raw_id}:{observed_at}"),
            source=source,
            rule_ref=raw_id,
            rule_name=entry.name if entry is not None else None,
            # A Wazuh rule we did not write could be about anything the vendor
            # ruleset covers. Saying "unclassified" is the honest answer; the
            # console groups it and the responder reads the id.
            signal=entry.signal if entry is not None else Signal.UNCLASSIFIED,
            severity=WAZUH_LEVEL_SEVERITY[level],
            observed_at=observed_at,
            host_id=_identifier_or_none(source, "agent.name", agent.get("name")),
            container_id=None,
            agent_id=_identifier_or_none(source, "agent.id", agent.get("id")),
            path=_scrubbed(source, "syscheck.path", syscheck.get("path")),
        )
    )


def normalise_alert(event: Mapping[str, Any], catalogue: RuleCatalogue) -> SecurityAlert:
    """Dispatch on the shape of the payload rather than on a self-declared type.

    Wazuh's ``rule`` is an object, Falco's is the rule's name. Trusting a
    ``source`` field the producer sets would let a compromised producer pick
    which normaliser runs.
    """
    rule = event.get("rule")
    if isinstance(rule, Mapping):
        return normalise_wazuh(event, catalogue)
    if isinstance(rule, str):
        return normalise_falco(event, catalogue)
    raise AlertRefused("payload is neither a Wazuh alert nor a Falco alert")
