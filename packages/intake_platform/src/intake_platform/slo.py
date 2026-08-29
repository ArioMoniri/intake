"""SLO-as-code: schema, catalogue membership and rule generation (INT-021).

CLAUDE.md inv. 13/15 and files/10 §6 make two artefacts load-bearing:

- ``observability/metrics_catalog.yaml`` — the closed registry of Prometheus
  series the platform emits. A series served on ``/metrics`` but absent here
  fails CI, and a label name that could carry PHI is rejected at the schema
  (inv. 6 — identifiers only, never free text).
- ``docs/slo/<service>.yaml`` — one file per service directory: SLIs written
  against catalogued series, objectives over a rolling window, and the
  multiwindow multi-burn-rate alert policy (Google SRE workbook shape; the
  numbers are pinned by files/10 §6: page at 14.4x/1h and 6x/6h, ticket at
  1x/3d).

``prometheus_rule_groups`` derives the recording and alerting rules from an
SLO file; tests/observability/test_slo_generator.py holds the committed
infra/observability/prometheus-rules.yaml equal to that derivation, so the
rules cannot drift from the SLO file. Convention: every SLI is the ERROR
RATIO (bad over total) written over a ``[5m]`` rate; recording rules re-range
the same expression per alert window.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "PHI_RISK_LABEL_NAMES",
    "SLO",
    "BurnRateAlert",
    "BurnRateAlerts",
    "MetricDef",
    "MetricsCatalog",
    "SLOFile",
    "alert_rule_name",
    "error_budget",
    "load_metrics_catalog",
    "load_slo_file",
    "metric_references",
    "prometheus_rule_groups",
    "recording_rule_name",
    "render_prometheus_rules",
    "runbook_anchor",
    "window_seconds",
]

#: Label names that could carry patient data. Metric labels hold enumerable
#: identifiers (route template, status class, tenant id); a label that names a
#: person, a phone, an address or free text is rejected at the schema. This
#: set may grow, never shrink (inv. 6).
PHI_RISK_LABEL_NAMES = frozenset(
    {
        "address",
        "birth_date",
        "body",
        "dob",
        "email",
        "first_name",
        "free_text",
        "full_name",
        "last_name",
        "message",
        "msisdn",
        "name",
        "national_id",
        "patient_name",
        "phone",
        "phone_number",
        "query",
        "tckn",
        "text",
        "transcript",
        "utterance",
    }
)

_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
#: files/08 §4 writes ids in OTel dotted form (``voice.eou_delay_ms``); the
#: Prometheus ``name`` is that id with dots turned into underscores.
_SPEC_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*$")
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_WINDOW_RE = re.compile(r"^([0-9]+)([smhd])$")
_WINDOW_UNIT_S = {"s": 1, "m": 60, "h": 3600, "d": 86400}
#: A metric reference is an identifier immediately followed by a label
#: selector or a range selector — the only two forms our expressions use.
_REFERENCE_RE = re.compile(r"\b([a-z_][a-z0-9_]*)(?=[{\[])")
_HISTOGRAM_SUFFIXES = ("_bucket", "_count", "_sum")
#: Every SLI is written over this base rate window; rules re-range it.
BASE_RANGE = "[5m]"


def window_seconds(window: str) -> int:
    """Duration of a Prometheus window string (``5m``/``1h``/``3d``) in seconds."""
    match = _WINDOW_RE.match(window)
    if match is None:
        raise ValueError(f"not a window (digits + s/m/h/d): {window!r}")
    return int(match.group(1)) * _WINDOW_UNIT_S[match.group(2)]


def error_budget(objective: float) -> float:
    """The error-budget ratio for an objective in percent (99.9 -> 0.001)."""
    return round((100.0 - objective) / 100.0, 10)


def metric_references(expr: str) -> frozenset[str]:
    """Series names a PromQL expression selects (identifier before ``{`` or ``[``)."""
    return frozenset(_REFERENCE_RE.findall(expr))


class MetricDef(BaseModel):
    """One catalogued Prometheus series family.

    INT-025 fields (files/08 §4 completeness):

    - ``id`` — the 08 §4 / OTel dotted id when it differs from ``name``; its
      dot-to-underscore normalisation must equal ``name``.
    - ``unit`` — required; what one observation measures (``ms``, ``count``…).
    - ``target`` — the objective 08 §4 states, verbatim enough to grep; absent
      when the spec states none.
    - ``status`` — ``live`` (something emits it today) or ``planned`` (08 §4
      names it, the emitting service has not landed). Both directions are
      enforced by tests/observability/test_metrics_catalog.py.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["counter", "gauge", "histogram"]
    labels: list[str]
    owner: str
    unit: str
    description: str
    id: str | None = None
    target: str | None = None
    status: Literal["live", "planned"] = "live"

    @property
    def spec_id(self) -> str:
        """The files/08 §4 id this entry answers to (``name`` when undotted)."""
        return self.id if self.id is not None else self.name

    @field_validator("name")
    @classmethod
    def _name_shape(cls, value: str) -> str:
        if _NAME_RE.match(value) is None:
            raise ValueError(f"not a Prometheus series name: {value!r}")
        return value

    @field_validator("unit")
    @classmethod
    def _unit_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("unit must not be blank")
        return value

    @field_validator("target")
    @classmethod
    def _target_nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("target must not be blank (omit it instead)")
        return value

    @field_validator("id")
    @classmethod
    def _id_shape(cls, value: str | None) -> str | None:
        if value is not None and _SPEC_ID_RE.match(value) is None:
            raise ValueError(f"not an OTel dotted metric id: {value!r}")
        return value

    @model_validator(mode="after")
    def _id_normalises_to_name(self) -> MetricDef:
        if self.id is not None and self.id.replace(".", "_") != self.name:
            raise ValueError(
                f"id {self.id!r} does not normalise to name {self.name!r} "
                "(dots become underscores, nothing else changes)"
            )
        return self

    @field_validator("labels")
    @classmethod
    def _labels_safe(cls, value: list[str]) -> list[str]:
        for label in value:
            if _NAME_RE.match(label) is None:
                raise ValueError(f"not a Prometheus label name: {label!r}")
            if label in PHI_RISK_LABEL_NAMES:
                raise ValueError(f"PHI-risk label name {label!r} is forbidden (inv. 6)")
        if len(set(value)) != len(value):
            raise ValueError(f"duplicate label names: {value}")
        return value


class MetricsCatalog(BaseModel):
    """The closed registry: every emitted series exists here (inv. 13)."""

    model_config = ConfigDict(extra="forbid")

    metrics: list[MetricDef] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_names(self) -> MetricsCatalog:
        seen: set[str] = set()
        for metric in self.metrics:
            if metric.name in seen:
                raise ValueError(f"duplicate metric name: {metric.name!r}")
            seen.add(metric.name)
        return self

    @property
    def names(self) -> frozenset[str]:
        return frozenset(metric.name for metric in self.metrics)

    def covers(self, reference: str) -> bool:
        """True when a PromQL series reference resolves to a catalogued family.

        A histogram family covers its ``_bucket``/``_count``/``_sum`` series.
        """
        by_name = {metric.name: metric for metric in self.metrics}
        if reference in by_name:
            return True
        for suffix in _HISTOGRAM_SUFFIXES:
            if reference.endswith(suffix):
                base = by_name.get(reference[: -len(suffix)])
                if base is not None and base.type == "histogram":
                    return True
        return False

    def unknown_references(self, expr: str) -> frozenset[str]:
        return frozenset(ref for ref in metric_references(expr) if not self.covers(ref))


class BurnRateAlert(BaseModel):
    """One multiwindow burn-rate condition: both windows above factor x budget."""

    model_config = ConfigDict(extra="forbid")

    factor: float = Field(gt=0)
    long_window: str
    short_window: str
    for_duration: str
    severity: Literal["page", "ticket"]

    @field_validator("long_window", "short_window", "for_duration")
    @classmethod
    def _window_shape(cls, value: str) -> str:
        window_seconds(value)
        return value

    @model_validator(mode="after")
    def _short_before_long(self) -> BurnRateAlert:
        if window_seconds(self.short_window) >= window_seconds(self.long_window):
            raise ValueError(
                f"short window {self.short_window} must be shorter than {self.long_window}"
            )
        return self


class BurnRateAlerts(BaseModel):
    """files/10 §6 policy: fast and slow both page; the ticket lane files work."""

    model_config = ConfigDict(extra="forbid")

    fast: BurnRateAlert
    slow: BurnRateAlert
    ticket: BurnRateAlert | None = None

    @model_validator(mode="after")
    def _severities(self) -> BurnRateAlerts:
        if self.fast.severity != "page" or self.slow.severity != "page":
            raise ValueError("fast and slow burn alerts must page")
        if self.ticket is not None and self.ticket.severity != "ticket":
            raise ValueError("the ticket lane must carry severity ticket")
        return self

    def named_alerts(self) -> list[tuple[str, BurnRateAlert]]:
        out: list[tuple[str, BurnRateAlert]] = [("fast", self.fast), ("slow", self.slow)]
        if self.ticket is not None:
            out.append(("ticket", self.ticket))
        return out


class SLO(BaseModel):
    """One objective: an error-ratio SLI over a rolling window."""

    model_config = ConfigDict(extra="forbid")

    name: str
    sli: str
    objective: float = Field(gt=0, lt=100)
    window: str
    burn_rate_alerts: BurnRateAlerts

    @field_validator("name")
    @classmethod
    def _name_shape(cls, value: str) -> str:
        if _NAME_RE.match(value) is None:
            raise ValueError(f"not an SLO name: {value!r}")
        return value

    @field_validator("sli")
    @classmethod
    def _sli_base_range(cls, value: str) -> str:
        if BASE_RANGE not in value:
            raise ValueError(f"SLI must be written over the {BASE_RANGE} base rate window")
        return value

    @field_validator("window")
    @classmethod
    def _window_shape(cls, value: str) -> str:
        window_seconds(value)
        return value


class SLOFile(BaseModel):
    """docs/slo/<service>.yaml — one per directory under services/ (inv. 15)."""

    model_config = ConfigDict(extra="forbid")

    service: str
    owner: str
    slos: list[SLO] = Field(min_length=1)

    @field_validator("service")
    @classmethod
    def _service_shape(cls, value: str) -> str:
        if _SERVICE_RE.match(value) is None:
            raise ValueError(f"not a service name: {value!r}")
        return value

    @model_validator(mode="after")
    def _unique_slo_names(self) -> SLOFile:
        names = [slo.name for slo in self.slos]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate SLO names: {names}")
        return self


def load_metrics_catalog(path: Path) -> MetricsCatalog:
    return MetricsCatalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_slo_file(path: Path) -> SLOFile:
    return SLOFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _slug(service: str) -> str:
    return service.replace("-", "_")


def _camel(text: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[-_]", text) if part)


def recording_rule_name(service: str, slo_name: str, window: str) -> str:
    return f"slo:{_slug(service)}_{slo_name}:error_ratio_rate{window}"


def alert_rule_name(service: str, slo_name: str, kind: str) -> str:
    return f"{_camel(service)}{_camel(slo_name)}{_camel(kind)}Burn"


def runbook_anchor(service: str, slo_name: str, kind: str) -> str:
    return f"{service}-{slo_name}-{kind}-burn"


def _normalize(expr: str) -> str:
    return " ".join(expr.split())


def prometheus_rule_groups(
    slo_file: SLOFile, runbook_path: str = "docs/runbooks/slo-burn.md"
) -> dict[str, list[dict[str, object]]]:
    """Derive the Prometheus recording + alerting groups for one SLO file.

    The committed infra/observability/prometheus-rules.yaml is held equal to
    this derivation by tests/observability/test_slo_generator.py.
    """
    recording: list[dict[str, object]] = []
    alerting: list[dict[str, object]] = []
    for slo in slo_file.slos:
        budget = error_budget(slo.objective)
        windows = sorted(
            {
                window
                for _, alert in slo.burn_rate_alerts.named_alerts()
                for window in (alert.long_window, alert.short_window)
            },
            key=window_seconds,
        )
        for window in windows:
            recording.append(
                {
                    "record": recording_rule_name(slo_file.service, slo.name, window),
                    "expr": _normalize(slo.sli).replace(BASE_RANGE, f"[{window}]"),
                    "labels": {"service": slo_file.service, "slo": slo.name},
                }
            )
        for kind, alert in slo.burn_rate_alerts.named_alerts():
            long_rule = recording_rule_name(slo_file.service, slo.name, alert.long_window)
            short_rule = recording_rule_name(slo_file.service, slo.name, alert.short_window)
            threshold = f"({alert.factor!r} * {budget!r})"
            alerting.append(
                {
                    "alert": alert_rule_name(slo_file.service, slo.name, kind),
                    "expr": f"{long_rule} > {threshold} and {short_rule} > {threshold}",
                    "for": alert.for_duration,
                    "labels": {
                        "severity": alert.severity,
                        "service": slo_file.service,
                        "slo": slo.name,
                    },
                    "annotations": {
                        "summary": (
                            f"{slo_file.service} {slo.name}: error budget burning at "
                            f">= {alert.factor:g}x over {alert.long_window} "
                            f"and {alert.short_window}"
                        ),
                        "runbook": (
                            f"{runbook_path}#{runbook_anchor(slo_file.service, slo.name, kind)}"
                        ),
                    },
                }
            )
    return {
        "groups": [
            {"name": f"slo-{slo_file.service}-recording", "rules": recording},
            {"name": f"slo-{slo_file.service}-alerts", "rules": alerting},
        ]
    }


def render_prometheus_rules(
    slo_files: list[SLOFile], runbook_path: str = "docs/runbooks/slo-burn.md"
) -> str:
    """Serialise the derived rule groups for every given SLO file as YAML."""
    groups: list[dict[str, object]] = []
    for slo_file in slo_files:
        groups.extend(prometheus_rule_groups(slo_file, runbook_path)["groups"])
    rendered: str = yaml.safe_dump({"groups": groups}, sort_keys=False, width=4096)
    return rendered
