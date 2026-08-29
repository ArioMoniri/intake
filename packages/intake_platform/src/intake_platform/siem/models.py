"""INT-205 — the alert type, and why it has no field patient text can occupy.

A security monitor reads everything on the box: every log line, every file
name, every command line. That makes the *alert payload* the most likely place
for PHI to leave the PHI path — files/10 §9 `incident-response` names it
directly ("[I] PHI pasted into tickets or chat during the response"), and the
alert is what gets pasted.

So the control is the type, not the normaliser's diligence. :class:`SecurityAlert`
carries ids, a scrubbed path, a rule reference and two closed enumerations. It
has no ``full_log``, no ``output``, no ``cmdline``, no ``user``. Every string
field is bounded, ASCII, and unchanged by :func:`intake_platform.redaction.redact_text`
— a Turkish symptom sentence fails all three, a TC Kimlik number fails the
third. A caller who constructs one of these by hand hits the same wall the
normaliser does.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from intake_platform.redaction import redact_text

__all__ = [
    "AlertSource",
    "ScrubbedPath",
    "SecurityAlert",
    "Severity",
    "Signal",
    "is_identifier_like",
    "is_rule_name_like",
]


class AlertSource(StrEnum):
    """Which detector produced the alert (files/10 §7 stack)."""

    FALCO = "falco"
    WAZUH = "wazuh"


class Signal(StrEnum):
    """The three classes INT-205's acceptance names, plus the honest fourth.

    ``unclassified`` is what a vendor rule outside our committed rulesets maps
    to. Guessing a class for it would be worse than saying we do not know.
    """

    AUTH_ANOMALY = "auth_anomaly"
    K8S_AUDIT = "k8s_audit"
    CONTAINER_RUNTIME = "container_runtime"
    UNCLASSIFIED = "unclassified"


class Severity(StrEnum):
    """The severity ladder docs/security/incident-runbook.md states.

    Both detectors have a scale of their own; neither is ours. The console and
    the pager read this one, so both vendor scales are mapped onto it once, in
    :mod:`intake_platform.siem.normalise`, rather than at every reading site.
    """

    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


#: An identifier field: no spaces at all, ASCII, bounded. Host names, container
#: ids, agent ids, rule references and timestamps all fit; narrative does not.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,63}$")

#: A rule name may carry spaces because that is how both products write them
#: ("intake: repeated authentication failure"). The charset is still closed and
#: still ASCII, which is what a Turkish symptom sentence fails.
_RULE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 :_./()-]{0,95}$")

#: One component of a filesystem path that is safe to keep verbatim.
SAFE_PATH_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,63}$")


def is_identifier_like(value: str) -> bool:
    """True when ``value`` is an identifier we are willing to put in an alert.

    Three independent gates, because each catches what the others miss:
    the closed charset stops narrative and non-ASCII, the length bound stops a
    pasted document, and re-running redaction stops a TC Kimlik number, an IBAN
    or a phone number that happens to be spelled out of digits and dashes.
    """
    return bool(_IDENTIFIER_RE.match(value)) and redact_text(value) == value


def is_rule_name_like(value: str) -> bool:
    """True when ``value`` is shaped like a rule name rather than a sentence."""
    return bool(_RULE_NAME_RE.match(value)) and redact_text(value) == value


class ScrubbedPath(BaseModel):
    """A filesystem path reduced to the part that is safe to show.

    INT-205 must carry paths — a container-runtime alert without one is not
    actionable — and a path is also the easiest place to smuggle patient text:
    ``/data/uploads/Ayse-Yilmaz-göğüs-ağrısı-anamnez.txt`` is a filename, not a
    log line, and a "reject anything with a space" guard would let it through.

    So the path is kept component by component for as long as each component is
    an identifier, and truncated at the first one that is not. ``digest`` is the
    sha256 of the *whole* original path, which is what lets a responder
    correlate two alerts about the same file without ever seeing its name.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: the longest leading run of safe components ("" when none survived)
    safe_prefix: str
    #: how many components the original path had — a number, so always safe
    depth: int = Field(ge=0)
    #: whether anything was dropped
    truncated: bool
    #: sha256 of the original path, present only when something was dropped
    digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _prefix_holds_only_safe_components(self) -> Self:
        for component in self.safe_prefix.split("/"):
            if component in ("", ".", ".."):
                continue
            if not SAFE_PATH_COMPONENT_RE.match(component):
                raise ValueError(f"path component is not an identifier: {component!r}")
        if self.truncated and self.digest is None:
            raise ValueError("a truncated path must carry the digest of the original")
        return self


class SecurityAlert(BaseModel):
    """One detection, in the only shape allowed to leave the SIEM tier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: stable per detection, so the console can de-duplicate and acknowledge
    alert_id: str
    source: AlertSource
    #: the vendor's handle for the rule: a Wazuh rule id, or a digest of a
    #: Falco rule name. Never the rule's prose.
    rule_ref: str
    #: resolved from a committed ruleset by ``rule_ref`` — never from the event.
    #: Wazuh expands ``$(field)`` inside a rule description, which is exactly
    #: how event data would arrive wearing a rule name.
    rule_name: str | None = None
    signal: Signal
    severity: Severity
    observed_at: str
    host_id: str | None = None
    container_id: str | None = None
    agent_id: str | None = None
    path: ScrubbedPath | None = None

    @model_validator(mode="after")
    def _every_string_field_is_an_identifier(self) -> Self:
        for name in ("alert_id", "rule_ref", "observed_at", "host_id", "container_id", "agent_id"):
            value = getattr(self, name)
            if value is not None and not is_identifier_like(value):
                raise ValueError(f"{name} is not an identifier: refusing to carry it in an alert")
        if self.rule_name is not None and not is_rule_name_like(self.rule_name):
            raise ValueError("rule_name is not an identifier: refusing to carry it in an alert")
        return self
