"""The edge policy as a type (INT-203; files/10 §4 ``Edge:``).

``infra/security/edge/edge-policy.yaml`` is the only file a human edits; this
module is what refuses the shapes that would leave the edge armed in
appearance only. Three of those shapes are worth naming, because each has a
plausible-looking reason to be written:

* **an exclusion wider than one rule × one route × one parameter.** Every
  false positive arrives as "rule 942100 fires on our clinical field", and the
  smallest edit that makes it stop is ``SecRuleRemoveById 942100``. That edit
  removes SQL-injection detection from the entire service. The schema admits
  only the narrow form, with the approval that authorised it and a date it
  stops being true.
* **a threshold raised until the alerts stop.** CRS anomaly scoring blocks at
  5 by default; 100 is a WAF that has never blocked anything and never will.
  :data:`CRS_DEFAULT_INBOUND_THRESHOLD` is a ceiling, so the number may only
  go down — the same direction-of-travel rule CLAUDE.md invariant 8 applies to
  coverage.
* **``DetectionOnly``.** The correct mode for a tuning window on live traffic
  and the wrong mode to ship, differing by one word nobody re-reads.

The CrowdSec half carries invariant 6 rather than a detection question: a
bucket keyed on a request path writes ``/v1/patients/<id>`` into every alert
it raises, and an alert is shipped to the SIEM. Path- and query-shaped
expressions are refused in the filter and the group-by, and the Traefik access
log the parser reads is field-selected ``drop`` by default upstream of that.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "CRS_DEFAULT_INBOUND_THRESHOLD",
    "CrowdSecPolicy",
    "CrowdSecScenario",
    "EdgePolicy",
    "EdgePolicyError",
    "TlsPolicy",
    "WafPolicy",
    "WafRuleExclusion",
    "load_edge_policy",
]

#: OWASP CRS 4's own default inbound anomaly threshold. A ceiling, never a
#: target: the shipped policy may tighten below it and may never loosen past
#: it without changing this constant, which is a reviewed edit to code.
CRS_DEFAULT_INBOUND_THRESHOLD = 5

#: CRS rule ids live in 900000–999999. Anything outside it is either a local
#: rule (which this policy does not have) or a typo.
_CRS_ID_RANGE = range(900000, 1000000)

#: Expressions that would put a request path, a query string or a header value
#: into a CrowdSec bucket key or alert (invariant 6). Matched as substrings of
#: the scenario's own expressions, which are short and ours.
_PATH_SHAPED = (
    "RequestPath",
    "RequestAddr",
    "RequestLine",
    "RequestQuery",
    "RequestHeaders",
    "http_path",
    "uri",
    "query",
)

#: ACME directories that issue certificates no browser trusts. A resolver
#: pointed here renews happily forever and every dashboard shows "issued".
_STAGING_ACME = (
    "acme-staging-v02.api.letsencrypt.org",
    "acme-staging.api.letsencrypt.org",
    "pebble",
)


class EdgePolicyError(Exception):
    """The policy parses but violates something time- or repo-dependent."""


class WafRuleExclusion(BaseModel):
    """One CRS rule, switched off at one place, by a named human, until a date."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: int
    #: An exact route template. Not a prefix, not a glob, and never ``/``:
    #: "excluded on the API" is an exclusion nobody can bound.
    route: str = Field(min_length=2)
    #: A named variable inside a collection — ``ARGS:json.text_tr``, never the
    #: bare ``ARGS`` and never ``REQUEST_BODY``.
    target: str = Field(min_length=3)
    justification: str = Field(min_length=1)
    #: The recorded tier-2 approval (files/10 §8) that authorised it.
    approval_ref: str = Field(min_length=1)
    #: The day it stops being true. There is no "permanent" option, because a
    #: permanent exclusion is one nobody will ever revisit.
    expires_on: date

    @field_validator("rule_id")
    @classmethod
    def _crs_id(cls, value: int) -> int:
        if value not in _CRS_ID_RANGE:
            raise ValueError(
                f"{value} is not an OWASP CRS rule id (900000-999999); an exclusion "
                "names the rule it disables, not a category"
            )
        return value

    @field_validator("route")
    @classmethod
    def _one_route(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("route is a path template and starts with '/'")
        if "*" in value:
            raise ValueError("a glob route is an exclusion nobody can bound — name the one route")
        return value

    @field_validator("target")
    @classmethod
    def _one_target(cls, value: str) -> str:
        if ":" not in value:
            raise ValueError(
                f"'{value}' is a whole collection, not a target: an exclusion names one "
                "variable (ARGS:json.text_tr), because excluding ARGS excludes every "
                "parameter the rule would ever have caught"
            )
        collection, _, name = value.partition(":")
        if not name:
            raise ValueError("the variable after ':' is empty")
        if collection.upper() in {"REQUEST_BODY", "REQUEST_URI", "REQUEST_LINE"}:
            raise ValueError(f"'{collection}' is not a target, it is a surrender")
        return value


class WafPolicy(BaseModel):
    """What the Coraza middleware is configured to do with the OWASP CRS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: One value. ``DetectionOnly`` is reachable only by changing this type.
    engine: Literal["On"]
    paranoia_level: int = Field(ge=1, le=4)
    inbound_anomaly_threshold: int = Field(ge=1, le=CRS_DEFAULT_INBOUND_THRESHOLD)
    outbound_anomaly_threshold: int = Field(ge=1, le=CRS_DEFAULT_INBOUND_THRESHOLD)
    request_body_limit_bytes: int = Field(ge=1024, le=10_485_760)

    crs_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    plugin_version: str = Field(min_length=1)
    plugin_url: str = Field(pattern=r"^https://")
    plugin_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    wasm_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    licence: str = Field(min_length=1)
    licence_blob_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    licence_verified_at: date

    exclusions: list[WafRuleExclusion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_exclusion_per_rule_and_route(self) -> WafPolicy:
        seen: set[tuple[int, str, str]] = set()
        for exclusion in self.exclusions:
            key = (exclusion.rule_id, exclusion.route, exclusion.target)
            if key in seen:
                raise ValueError(f"duplicate exclusion {key}")
            seen.add(key)
        return self


class CrowdSecScenario(BaseModel):
    """One behavioural bucket, and the files/10 §7 signal it serves."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^intake/[a-z0-9-]+$")
    type: Literal["leaky", "trigger", "counter"]
    description: str = Field(min_length=1)
    filter: str = Field(min_length=1)
    groupby: str = Field(min_length=1)
    capacity: int = Field(ge=1)
    leakspeed: str = Field(pattern=r"^\d+[smh]$")
    blackhole: str = Field(pattern=r"^\d+[smh]$")
    #: A scenario with no remediation is a counter with a scary name.
    remediation: Literal[True]
    signal: str = Field(min_length=1)

    @field_validator("filter", "groupby")
    @classmethod
    def _no_path_or_query(cls, value: str) -> str:
        for token in _PATH_SHAPED:
            if token.lower() in value.lower():
                raise ValueError(
                    f"'{token}' would put a request path or query into the bucket key and "
                    "into every alert raised from it (CLAUDE.md invariant 6)"
                )
        return value


class CrowdSecPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    #: files/10 §1: shipping client addresses to a third-party reputation
    #: service is a transfer nobody consented to. One value.
    online_api: Literal[False]
    acquisition_path: str = Field(min_length=1)
    acquisition_type: Literal["traefik"]
    scenarios: list[CrowdSecScenario] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_names(self) -> CrowdSecPolicy:
        names = [scenario.name for scenario in self.scenarios]
        if len(set(names)) != len(names):
            raise ValueError("two scenarios share a name")
        return self


class TlsPolicy(BaseModel):
    """Certificate automation, stated once for both deployment shapes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resolver: str = Field(pattern=r"^[a-z0-9-]+$")
    ca_server: str = Field(pattern=r"^https://")
    challenge: Literal["tlsChallenge", "httpChallenge", "dnsChallenge"]
    storage: str = Field(min_length=1)
    key_algorithm: Literal["ECDSA-P256", "ECDSA-P384", "RSA-2048", "RSA-4096"]
    renew_before_days: int = Field(ge=30, le=60)
    account_email_env: str = Field(min_length=1)
    issuer_name: str = Field(pattern=r"^[a-z0-9-]+$")
    secret_name: str = Field(pattern=r"^[a-z0-9-]+$")
    #: May be empty — see the fail-closed note in the policy file. A rendered
    #: ``Certificate`` exists only when this list does.
    domains: list[str] = Field(default_factory=list)
    local_host: str = Field(pattern=r"^[a-z0-9.-]+\.test$")

    @field_validator("ca_server")
    @classmethod
    def _not_staging(cls, value: str) -> str:
        for marker in _STAGING_ACME:
            if marker in value:
                raise ValueError(
                    "a staging ACME directory issues certificates no browser trusts, and "
                    "renews them forever while the dashboard reads 'issued'"
                )
        return value

    @field_validator("domains")
    @classmethod
    def _public_names(cls, value: list[str]) -> list[str]:
        for domain in value:
            if domain.endswith((".test", ".local", ".internal", ".localhost")):
                raise ValueError(f"{domain!r} can never carry a publicly-trusted certificate")
            if "." not in domain.strip("."):
                raise ValueError(f"{domain!r} is not a fully-qualified name")
        return value


class EdgePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    waf: WafPolicy
    crowdsec: CrowdSecPolicy
    tls: TlsPolicy


def load_edge_policy(path: Path, *, today: date | None = None) -> EdgePolicy:
    """Load + validate the edge policy.

    Structural failures raise ``pydantic.ValidationError``; the one check that
    depends on the calendar rather than on the document — an exclusion past its
    expiry — raises :class:`EdgePolicyError`. Both stop a boot: an edge policy
    that will not load must not degrade into a permissive default.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    policy = EdgePolicy.model_validate(raw)
    now = today or date.today()
    for exclusion in policy.waf.exclusions:
        if exclusion.expires_on <= now:
            raise EdgePolicyError(
                f"WAF rule exclusion {exclusion.rule_id} on {exclusion.route} expired on "
                f"{exclusion.expires_on.isoformat()}; re-approve it or delete it — an "
                "exclusion nobody revisits is a rule nobody knows is off"
            )
    return policy


class RuleClass(StrEnum):
    """The CRS attack family a rule belongs to.

    Derived from the CRS file name, which is a constant of the ruleset, so an
    edge event can say *what kind of attack* without carrying a byte the
    attacker (or the patient) wrote. Used by :mod:`intake_platform.edge.logs`.
    """

    INITIALIZATION = "initialization"
    METHOD = "method"
    SCANNER = "scanner"
    PROTOCOL = "protocol"
    LFI = "lfi"
    RFI = "rfi"
    RCE = "rce"
    PHP = "php"
    GENERIC = "generic"
    XSS = "xss"
    SQLI = "sqli"
    SESSION_FIXATION = "session_fixation"
    JAVA = "java"
    BLOCKING = "blocking"
    DATA_LEAKAGE = "data_leakage"
    CORRELATION = "correlation"
    OTHER = "other"
