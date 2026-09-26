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
    "AWAITING_HUMAN",
    "GOLDEN_SIGNALS",
    "PHI_RISK_LABEL_NAMES",
    "SLO",
    "AwaitingHumanSource",
    "BurnRateAlert",
    "BurnRateAlerts",
    "MetricDef",
    "MetricsCatalog",
    "SLOFile",
    "SpecSource",
    "alert_rule_name",
    "dashboard_filename",
    "dashboard_uid",
    "error_budget",
    "grafana_dashboard",
    "load_metrics_catalog",
    "load_slo_file",
    "metric_references",
    "prometheus_rule_groups",
    "recording_rule_name",
    "render_prometheus_rules",
    "runbook_anchor",
    "sli_service_labels",
    "window_seconds",
]

#: The objective of an SLO no human has set. An error budget is a commitment,
#: so the schema takes either a quoted blueprint sentence or this literal —
#: never a plausible number chosen by whoever wrote the file. An SLO carrying
#: it generates recording rules and no alert: nothing pages against a budget
#: nobody set (CLAUDE.md, "never invent a value to unblock yourself").
AWAITING_HUMAN = "awaiting-human"

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
#: ``service="voice-runtime"`` inside a label selector — the pin that says which
#: service is supposed to be emitting the series an SLI reads.
_SERVICE_LABEL_RE = re.compile(r'\bservice\s*=\s*"([a-z][a-z0-9-]*)"')
#: A files/HUMAN_BLOCKERS.md row id (HB-C1, HB-L17, HB-O5…).
_BLOCKER_RE = re.compile(r"^HB-[A-Z]+[0-9]+[a-z]?$")
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


def sli_service_labels(expr: str) -> frozenset[str]:
    """The ``service="..."`` label values an SLI pins.

    The catalogue check proves the series FAMILY exists; this is what lets a
    caller prove the LABEL VALUE is emitted. docs/slo/probes.yaml declared an
    availability budget over ``http_requests_total{service="probes"}`` while
    services/probes never mounted the HTTP middleware — a catalogued family, a
    label value nobody wrote, and an error budget that could never burn.
    """
    return frozenset(_SERVICE_LABEL_RE.findall(expr))


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


class SpecSource(BaseModel):
    """Where a numeric objective comes from: a blueprint sentence, quoted.

    ``quote`` is checked **verbatim** against ``file`` by
    tests/observability/test_slo_provenance.py, and the objective's own digits
    must appear inside the quote. That is the whole mechanism: an objective
    cannot be written unless the sentence stating it already exists in the
    spec.
    """

    model_config = ConfigDict(extra="forbid")

    cite: str
    file: str
    quote: str

    @field_validator("cite", "file", "quote")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cite, file and quote must all be non-blank")
        return value


class AwaitingHumanSource(BaseModel):
    """No objective yet: the blocker row, the named human, the one question."""

    model_config = ConfigDict(extra="forbid")

    blocker: str
    human: str
    ask: str

    @field_validator("blocker")
    @classmethod
    def _blocker_shape(cls, value: str) -> str:
        if _BLOCKER_RE.match(value) is None:
            raise ValueError(f"not a HUMAN_BLOCKERS.md row id: {value!r}")
        return value

    @field_validator("human", "ask")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("an awaiting-human source names a human and an ask")
        return value


class SLO(BaseModel):
    """One objective: an error-ratio SLI over a rolling window.

    ``objective`` is a percentage **or** the literal :data:`AWAITING_HUMAN`.
    Either way ``source`` says where it came from, and the two must agree: a
    number needs a :class:`SpecSource`, an absent objective needs an
    :class:`AwaitingHumanSource`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    sli: str
    objective: float | Literal["awaiting-human"]
    source: SpecSource | AwaitingHumanSource
    window: str
    burn_rate_alerts: BurnRateAlerts

    @property
    def error_budget(self) -> float | None:
        """The budget ratio, or ``None`` when no human has set the objective."""
        if isinstance(self.objective, str):
            return None
        return error_budget(self.objective)

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

    @field_validator("objective")
    @classmethod
    def _objective_bounds(cls, value: float | str) -> float | str:
        if isinstance(value, str):
            return value
        if not 0.0 < value < 100.0:
            raise ValueError(f"objective must be a percentage strictly inside (0, 100): {value}")
        return value

    @field_validator("window")
    @classmethod
    def _window_shape(cls, value: str) -> str:
        window_seconds(value)
        return value

    @model_validator(mode="after")
    def _objective_matches_its_source(self) -> SLO:
        if isinstance(self.objective, str):
            if not isinstance(self.source, AwaitingHumanSource):
                raise ValueError(
                    f"objective {AWAITING_HUMAN!r} needs a source naming a blocker, a human "
                    "and the one sentence they must answer — not a spec citation"
                )
        elif not isinstance(self.source, SpecSource):
            raise ValueError(
                f"objective {self.objective} is a commitment and must quote the blueprint "
                f"sentence that states it; use {AWAITING_HUMAN!r} when no sentence does"
            )
        return self


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

    Fails closed on an unset objective: an SLO whose ``objective`` is
    :data:`AWAITING_HUMAN` still gets its recording rules — measuring an SLI is
    how the number eventually gets chosen from data rather than from an
    agent's intuition — and gets **no alerting rule**, because a burn-rate
    threshold is ``factor x budget`` and there is no budget to multiply.
    """
    recording: list[dict[str, object]] = []
    alerting: list[dict[str, object]] = []
    for slo in slo_file.slos:
        budget = slo.error_budget
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
        if budget is None:
            continue
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
    """Serialise the derived rule groups for every given SLO file as YAML.

    A group with no rules is dropped: every SLO whose objective is
    :data:`AWAITING_HUMAN` produces an empty alerting group, and a rules file
    is configuration for Prometheus rather than a place to document absence —
    the header and files/HUMAN_BLOCKERS.md carry that.
    """
    groups: list[dict[str, object]] = []
    for slo_file in slo_files:
        groups.extend(
            group
            for group in prometheus_rule_groups(slo_file, runbook_path)["groups"]
            if group["rules"]
        )
    rendered: str = yaml.safe_dump({"groups": groups}, sort_keys=False, width=4096)
    return rendered


# --- dashboards as code -----------------------------------------------------------

_DATASOURCE = {"type": "prometheus", "uid": "prometheus"}
#: files/10 §6 wants the four golden signals per service. Three of them are
#: emitted per service by intake_platform.metrics; saturation is not, because
#: the prometheus_client process collector carries no ``service`` label, and the
#: panel says so rather than pretending otherwise.
GOLDEN_SIGNALS = ("traffic", "errors", "latency", "saturation")


def dashboard_uid(service: str) -> str:
    return f"intake-{service}-slo"


def dashboard_filename(service: str) -> str:
    return f"{service}-slo-dashboard.json"


def _stat_panel(
    panel_id: int, title: str, description: str, expr: str, x: int, y: int
) -> dict[str, object]:
    return {
        "id": panel_id,
        "type": "stat",
        "title": title,
        "description": description,
        "datasource": _DATASOURCE,
        "gridPos": {"h": 6, "w": 6, "x": x, "y": y},
        "fieldConfig": {
            "defaults": {
                "unit": "none",
                "thresholds": {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green", "value": None},
                        {"color": "yellow", "value": 1},
                        {"color": "orange", "value": 6},
                        {"color": "red", "value": 14.4},
                    ],
                },
            },
            "overrides": [],
        },
        "targets": [{"refId": "A", "expr": expr}],
    }


def _timeseries_panel(
    panel_id: int,
    title: str,
    description: str,
    expr: str,
    unit: str,
    x: int,
    y: int,
) -> dict[str, object]:
    return {
        "id": panel_id,
        "type": "timeseries",
        "title": title,
        "description": description,
        "datasource": _DATASOURCE,
        "gridPos": {"h": 8, "w": 12, "x": x, "y": y},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "targets": [{"refId": "A", "expr": expr}],
    }


def grafana_dashboard(slo_file: SLOFile) -> dict[str, object]:
    """Derive one service's SLO + golden-signal dashboard from its SLO file.

    Every panel reads either a ``slo:`` recording rule this module also
    generates or a series in observability/metrics_catalog.yaml;
    tests/observability/test_slo_generator.py holds both true and holds the
    committed JSON equal to this derivation.

    An SLO whose objective is :data:`AWAITING_HUMAN` gets its error-ratio
    timeseries and **no burn-rate stat**: a burn rate is the ratio divided by
    the budget, and dividing by a number nobody set would put an invented
    figure on a wall where it reads as measured.
    """
    service = slo_file.service
    panels: list[dict[str, object]] = []
    panel_id = 0
    row_y = 0

    for index, slo in enumerate(slo_file.slos):
        budget = slo.error_budget
        hour_rule = recording_rule_name(service, slo.name, "1h")
        panel_id += 1
        if budget is None:
            source = slo.source
            blocker = source.blocker if isinstance(source, AwaitingHumanSource) else "unset"
            panels.append(
                _stat_panel(
                    panel_id,
                    f"{slo.name} error ratio (1h)",
                    (
                        f"{hour_rule}. No burn rate is shown: the objective is "
                        f"{AWAITING_HUMAN} ({blocker}), so there is no budget to divide by "
                        "and a number here would read as measured."
                    ),
                    hour_rule,
                    x=(index % 4) * 6,
                    y=row_y,
                )
            )
        else:
            panels.append(
                _stat_panel(
                    panel_id,
                    f"{slo.name} burn rate (1h, multiples of budget)",
                    (
                        f"{hour_rule} divided by the {slo.objective:g} % budget ({budget:g}). "
                        "Pages at 14.4, tickets at 1 — see docs/runbooks/slo-burn.md."
                    ),
                    f"{hour_rule} / {budget!r}",
                    x=(index % 4) * 6,
                    y=row_y,
                )
            )
    row_y += 6

    for slo in slo_file.slos:
        panel_id += 1
        window_rule = recording_rule_name(service, slo.name, slo.burn_rate_alerts.fast.long_window)
        panels.append(
            _timeseries_panel(
                panel_id,
                f"{slo.name} error ratio over {slo.burn_rate_alerts.fast.long_window}",
                f"{window_rule} — the SLI itself, whether or not an objective is set.",
                window_rule,
                unit="percentunit",
                x=0,
                y=row_y,
            )
        )
        row_y += 8

    selector = f'{{service="{service}"}}'
    error_selector = f'{{service="{service}",status=~"5.."}}'
    panel_id += 1
    panels.append(
        _timeseries_panel(
            panel_id,
            "Traffic — requests per second",
            "Golden signal 1 of 4 (files/10 §6).",
            f"sum(rate(http_requests_total{selector}[5m]))",
            unit="reqps",
            x=0,
            y=row_y,
        )
    )
    panel_id += 1
    panels.append(
        _timeseries_panel(
            panel_id,
            "Errors — 5xx share of requests",
            "Golden signal 2 of 4 (files/10 §6).",
            f"sum(rate(http_requests_total{error_selector}[5m])) "
            f"/ sum(rate(http_requests_total{selector}[5m]))",
            unit="percentunit",
            x=12,
            y=row_y,
        )
    )
    row_y += 8
    panel_id += 1
    panels.append(
        _timeseries_panel(
            panel_id,
            "Latency — p95 request duration",
            "Golden signal 3 of 4 (files/10 §6).",
            "histogram_quantile(0.95, sum by (le) "
            f"(rate(http_request_duration_seconds_bucket{selector}[5m])))",
            unit="s",
            x=0,
            y=row_y,
        )
    )
    panel_id += 1
    panels.append(
        _timeseries_panel(
            panel_id,
            "Saturation — open file descriptors against the process limit",
            (
                "Golden signal 4 of 4 (files/10 §6). PROCESS-WIDE, not per service: the "
                "prometheus_client process collector emits no service label, so this panel "
                "cannot be scoped the way the three above are. Scoping it needs a collector "
                "-side label (INT-023); until then the panel says what it is."
            ),
            "process_open_fds / process_max_fds",
            unit="percentunit",
            x=12,
            y=row_y,
        )
    )

    return {
        "__comment": (
            f"infra/observability/grafana/dashboards/{dashboard_filename(service)} — GENERATED "
            f"docs/slo/{service}.yaml by intake_platform.slo.grafana_dashboard (INT-021). "
            "Do not hand-edit: tests/observability/test_slo_generator.py fails on drift. "
            "Re-emit with `uv run python scripts/observability/slo_report.py "
            "--emit-dashboards infra/observability/grafana/dashboards`."
        ),
        "uid": dashboard_uid(service),
        "title": f"{service} — SLOs, burn rate and golden signals",
        "tags": ["slo", service, "intake"],
        "timezone": "utc",
        "schemaVersion": 39,
        "version": 1,
        "editable": False,
        "time": {"from": "now-24h", "to": "now"},
        "templating": {"list": []},
        "annotations": {"list": []},
        "panels": panels,
    }
