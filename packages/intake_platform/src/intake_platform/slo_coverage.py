"""Monitoring coverage: every service, app, job and tier, or the reason it has none.

CLAUDE.md invariant 15 binds every *service* to an SLO file and a probe, and
files/10 §6 adds a golden-signal dashboard and a runbook on every alert. What
invariant 15 does not say is what happens to the things that are not a
``services/`` directory — the Next console, the mobile client, the
``python -m intake_platform.<job>`` entry points a scheduler runs, the
Langfuse and SIEM boundaries, and the ``workers`` tier the INT-021 acceptance
names but no directory holds. ``observability/slo_coverage.yaml`` answers that
per subject, and this module checks the answer (INT-021 close-out):

- subjects are **discovered** (:func:`discover_subjects`), so a new service,
  app or job without an entry is a failure rather than an omission;
- each entry states each facet exactly once — the SLO file, or a recorded
  ``exempt`` reason it needs none, or a recorded ``gap`` saying what is
  missing and why; the same for probe rows. A present service may carry
  neither an exemption nor a gap for its SLO: that is invariant 15;
- an entry that names an SLO file is held to its generated rule groups and
  its generated dashboard; named probe rows must be registry components and
  named alerts must be loaded by Prometheus;
- :func:`http_emitter_problems` holds every SLI written against
  ``http_requests_total{service="x"}`` to a ``mount_http_metrics(app, "x")``
  call in ``services/x`` — without one the SLO reads a series nobody serves
  and can never be breached (services/probes had exactly that).
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intake_platform.slo import SLOFile, load_slo_file
from intake_platform.slo_dashboards import DASHBOARD_DIR, dashboard_filename

__all__ = [
    "COVERAGE_PATH",
    "CoverageEntry",
    "CoverageManifest",
    "coverage_problems",
    "discover_subjects",
    "http_emitter_problems",
    "load_coverage",
    "mounted_http_services",
    "registry_components",
    "sli_http_services",
]

COVERAGE_PATH = "observability/slo_coverage.yaml"
RULES_REL = "infra/observability/prometheus-rules.yaml"
REGISTRY_REL = "observability/registry.yaml"
_JOBS_ROOT = ("packages", "intake_platform", "src", "intake_platform")
_SLO_PATH_RE = re.compile(r"^docs/slo/[a-z][a-z0-9-]*\.yaml$")
_HTTP_SLI_RE = re.compile(
    r"http_(?:requests_total|request_duration_seconds_(?:bucket|count|sum))"
    r'\{[^}]*service="([a-z0-9-]+)"'
)

Kind = Literal["service", "app", "job", "tier"]
Facet = Literal["slo", "probe"]
#: ``alert`` records an alert that exists but cannot fire yet (e.g. a one-shot
#: job's gauge that no Prometheus scrapes); it is reported, never required.
GapFacet = Literal["slo", "probe", "alert"]


class CoverageEntry(BaseModel):
    """One monitored subject and how each facet of invariant 15 is met."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    kind: Kind
    slo: str | None = None
    probes: list[str] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    exempt: dict[Facet, str] = Field(default_factory=dict)
    gaps: dict[GapFacet, str] = Field(default_factory=dict)
    awaiting: str | None = None

    @field_validator("slo")
    @classmethod
    def _slo_path(cls, value: str | None) -> str | None:
        if value is not None and _SLO_PATH_RE.match(value) is None:
            raise ValueError(f"slo must be docs/slo/<service>.yaml, got {value!r}")
        return value

    @field_validator("exempt", "gaps")
    @classmethod
    def _reasons(cls, value: dict[str, str]) -> dict[str, str]:
        for facet, reason in value.items():
            if not reason.strip():
                raise ValueError(f"the {facet} reason must not be blank")
        return value

    @model_validator(mode="after")
    def _each_facet_once(self) -> CoverageEntry:
        stated = {
            "slo": [self.slo is not None, "slo" in self.exempt, "slo" in self.gaps],
            "probe": [bool(self.probes), "probe" in self.exempt, "probe" in self.gaps],
        }
        for facet, ways in stated.items():
            if sum(ways) != 1:
                raise ValueError(
                    f"{self.subject}: state the {facet} facet exactly once — "
                    f"{'slo: <file>' if facet == 'slo' else 'probes: [...]'}, "
                    f"exempt.{facet} or gaps.{facet}"
                )
        if self.awaiting is not None and (not self.awaiting.strip() or not self.gaps):
            raise ValueError(f"{self.subject}: awaiting names who closes a gap; record the gap")
        return self


class CoverageManifest(BaseModel):
    """observability/slo_coverage.yaml."""

    model_config = ConfigDict(extra="forbid")

    subjects: list[CoverageEntry]

    @model_validator(mode="after")
    def _unique(self) -> CoverageManifest:
        seen: set[str] = set()
        for entry in self.subjects:
            if entry.subject in seen:
                raise ValueError(f"duplicate subject {entry.subject!r}")
            seen.add(entry.subject)
        return self


def load_coverage(path: Path) -> CoverageManifest:
    return CoverageManifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def registry_components(path: Path) -> frozenset[str]:
    """Component names in observability/registry.yaml (validated by services/probes)."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return frozenset(str(row["component"]) for row in loaded.get("components") or [])


def discover_subjects(repo: Path) -> dict[str, Kind]:
    """Every service, app and job in the tree, by name."""
    found: dict[str, Kind] = {}
    for pyproject in sorted((repo / "services").glob("*/pyproject.toml")):
        found[pyproject.parent.name] = "service"
    for package in sorted((repo / "apps").glob("*/package.json")):
        found[package.parent.name] = "app"
    for main in sorted(repo.joinpath(*_JOBS_ROOT).glob("*/__main__.py")):
        found[f"intake_platform.{main.parent.name}"] = "job"
    return found


def _slo_problems(
    subject: str, slo: str, repo: Path, rules: Mapping[str, Any], dashboards: Path
) -> list[str]:
    path = repo / slo
    if not path.is_file():
        return [f"{subject}: {slo} does not exist"]
    service = load_slo_file(path).service
    problems: list[str] = []
    groups = {str(group.get("name")) for group in rules.get("groups") or []}
    for suffix in ("recording", "alerts"):
        if f"slo-{service}-{suffix}" not in groups:
            problems.append(f"{subject}: {slo} has no slo-{service}-{suffix} group in {RULES_REL}")
    if not (dashboards / dashboard_filename(service)).is_file():
        problems.append(f"{subject}: no dashboard {DASHBOARD_DIR}/{dashboard_filename(service)}")
    return problems


def coverage_problems(
    manifest: CoverageManifest,
    repo: Path,
    *,
    registry: frozenset[str],
    alerts: frozenset[str],
    rules: Mapping[str, Any],
    dashboards: Path,
) -> list[str]:
    """Every coverage defect, as sentences; empty when the manifest is true."""
    problems: list[str] = []
    discovered = discover_subjects(repo)
    entries = {entry.subject: entry for entry in manifest.subjects}
    for name, kind in sorted(discovered.items()):
        if name not in entries:
            problems.append(f"{name} ({kind}) has no entry in {COVERAGE_PATH}")
        elif entries[name].kind != kind:
            problems.append(f"{name}: entry says {entries[name].kind}, the tree says {kind}")
    referenced = {entry.slo for entry in manifest.subjects if entry.slo is not None}
    for slo_path in sorted((repo / "docs" / "slo").glob("*.yaml")):
        rel = f"docs/slo/{slo_path.name}"
        if rel not in referenced:
            problems.append(f"{rel} is not referenced by any entry in {COVERAGE_PATH}")
    for entry in manifest.subjects:
        present = entry.subject in discovered
        if entry.kind != "tier" and not present and "slo" not in entry.gaps:
            problems.append(
                f"{entry.subject}: no such {entry.kind} in the tree — an absent subject can only "
                "record a gap"
            )
        if entry.kind == "service" and present and entry.slo != f"docs/slo/{entry.subject}.yaml":
            problems.append(
                f"{entry.subject}: a present service declares docs/slo/{entry.subject}.yaml "
                "(inv. 15) — no exemption, no gap"
            )
        if entry.slo is not None:
            problems.extend(_slo_problems(entry.subject, entry.slo, repo, rules, dashboards))
        for component in entry.probes:
            if component not in registry:
                problems.append(
                    f"{entry.subject}: probe row {component!r} is not in {REGISTRY_REL}"
                )
        for alert in entry.alerts:
            if alert not in alerts:
                problems.append(f"{entry.subject}: alert {alert!r} is not in any loaded rule file")
    return problems


# --- SLI emitters -------------------------------------------------------------------------------


def sli_http_services(slo_file: SLOFile) -> frozenset[str]:
    """Services whose HTTP request series this file's SLIs select."""
    return frozenset(name for slo in slo_file.slos for name in _HTTP_SLI_RE.findall(slo.sli))


def _string_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value
    return constants


def mounted_http_services(service_dir: Path) -> frozenset[str]:
    """``service`` arguments of every ``mount_http_metrics(app, service)`` call.

    A string literal, or a module-level name bound to one, resolves; anything
    else does not count as an emitter.
    """
    found: set[str] = set()
    for source in sorted(service_dir.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        constants = _string_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name != "mount_http_metrics":
                continue
            arg = node.args[1]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.add(arg.value)
            elif isinstance(arg, ast.Name) and arg.id in constants:
                found.add(constants[arg.id])
    return frozenset(found)


def http_emitter_problems(slo_files: Sequence[SLOFile], services_root: Path) -> list[str]:
    """Every HTTP SLI whose service directory never mounts the request metrics."""
    problems: list[str] = []
    for slo_file in slo_files:
        for service in sorted(sli_http_services(slo_file)):
            service_dir = services_root / service
            if service_dir.is_dir() and service in mounted_http_services(service_dir):
                continue
            problems.append(
                f'docs/slo/{slo_file.service}.yaml reads http_requests_total{{service="{service}"}}'
                f" but services/{service} never calls "
                f'mount_http_metrics(app, "{service}") — an SLO nothing can breach'
            )
    return problems
