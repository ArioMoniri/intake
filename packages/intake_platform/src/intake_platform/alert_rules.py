"""Alert-rule audit: every rule Prometheus loads is runnable and actionable (INT-021).

files/10 §6 says ``docs/runbooks/`` is "linked from every alert"; CLAUDE.md
invariant 13 says every series is catalogued. INT-021 pinned both for the api
burn alerts only. This module is the machinery that holds them for every rule
in every file ``infra/observability/prometheus.yml`` loads — behind
tests/observability/test_alert_rules.py and ``make slo-report``:

- :func:`prometheus_rule_files` — the rule files Prometheus actually loads,
  mapped back from their mount point to ``infra/observability/``;
  :func:`unloaded_rule_files` names a rule file in that directory nobody loads
  (an alert that exists only in the repository);
- :func:`promql_series` — the series and recording rules an expression reads,
  **including bare names** (``sec_secret_rotation_due_days < 0``), which
  :func:`intake_platform.slo.metric_references` does not see because it only
  matches a name followed by a selector;
- :func:`markdown_anchors` / :func:`runbook_problem` — whether a runbook link
  resolves to an existing file under ``docs/runbooks/`` and to a heading in it
  (GitHub's slug rule; lines inside fenced code are not headings);
- :func:`rule_problems` — every defect across the loaded files: an
  uncatalogued series, a ``planned`` series (nothing emits it, so the rule can
  never fire), a recording rule nobody defines, and an alert whose runbook does
  not resolve.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from intake_platform.slo import MetricsCatalog

__all__ = [
    "RUNBOOK_ROOT",
    "alert_names",
    "github_slug",
    "iter_rules",
    "markdown_anchors",
    "prometheus_rule_files",
    "promql_series",
    "rule_problems",
    "runbook_problem",
    "unloaded_rule_files",
]

#: files/10 §6 — the one directory an alert's runbook link may point into.
RUNBOOK_ROOT = "docs/runbooks"

#: ``docs/runbooks/<file>.md#<anchor>``. The file part admits no ``/``, so a
#: link can neither leave the directory nor name a nested path.
_RUNBOOK_RE = re.compile(r"^docs/runbooks/([a-z0-9][a-z0-9._-]*)\.md#([a-z0-9_-]+)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`[^`]*`')
_SELECTOR_RE = re.compile(r"\{[^{}]*\}")
_RANGE_RE = re.compile(r"\[[^\[\]]*\]")
_GROUPING_RE = re.compile(
    r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^()]*\)", re.IGNORECASE
)
_OFFSET_RE = re.compile(r"\boffset\s+-?[0-9]+[a-z]+", re.IGNORECASE)
#: An identifier not preceded by a digit, ``.`` or ``$`` (so ``1e3`` and a
#: Grafana ``$variable`` are not series), with an optional ``(`` that marks it
#: as a function call.
_TOKEN_RE = re.compile(r"(?<![0-9.$A-Za-z_:])([A-Za-z_:][A-Za-z0-9_:]*)(\s*\()?")
_KEYWORDS = frozenset(
    {
        "and",
        "or",
        "unless",
        "by",
        "without",
        "on",
        "ignoring",
        "group_left",
        "group_right",
        "bool",
        "offset",
        "inf",
        "nan",
    }
)


# --- which files Prometheus loads -------------------------------------------------------


def prometheus_rule_files(prometheus_yml: Path) -> list[Path]:
    """The rule files ``prometheus.yml`` loads, as files beside it.

    The obs compose profile mounts ``infra/observability/<name>`` at
    ``/etc/prometheus/rules/<name>``; tests/observability/test_alert_rules.py
    holds every entry to that mount.
    """
    config = yaml.safe_load(prometheus_yml.read_text(encoding="utf-8"))
    entries = config.get("rule_files") or []
    return [prometheus_yml.parent / PurePosixPath(str(entry)).name for entry in entries]


def _is_rule_file(path: Path) -> bool:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return isinstance(loaded, dict) and isinstance(loaded.get("groups"), list)


def unloaded_rule_files(directory: Path, loaded: Sequence[Path]) -> list[Path]:
    """Rule files (a top-level ``groups`` list) in ``directory`` nobody loads."""
    wanted = {path.resolve() for path in loaded}
    return [
        path
        for path in sorted(directory.glob("*.yaml"))
        if path.resolve() not in wanted and _is_rule_file(path)
    ]


def iter_rules(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """``(group name, rule)`` for every rule in one Prometheus rule file."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for group in loaded.get("groups") or []:
        for rule in group.get("rules") or []:
            yield str(group.get("name")), rule


def alert_names(paths: Sequence[Path]) -> frozenset[str]:
    """Every alert name across the given rule files."""
    return frozenset(
        str(rule["alert"]) for path in paths for _, rule in iter_rules(path) if "alert" in rule
    )


# --- what an expression reads -----------------------------------------------------------


def promql_series(expr: str) -> frozenset[str]:
    """Series names and recording rules (``a:b:c``) a PromQL expression reads.

    Label matchers, range and subquery brackets, grouping clauses, offsets and
    string literals are removed first; what remains is operators, numbers,
    function calls, keywords and names. A name followed by ``(`` is a function.
    """
    text = _STRING_RE.sub('""', expr)
    text = _SELECTOR_RE.sub(" ", text)
    text = _RANGE_RE.sub(" ", text)
    text = _GROUPING_RE.sub(" ", text)
    text = _OFFSET_RE.sub(" ", text)
    found: set[str] = set()
    for match in _TOKEN_RE.finditer(text):
        name, call = match.group(1), match.group(2)
        if call is not None or name.lower() in _KEYWORDS:
            continue
        found.add(name)
    return frozenset(found)


# --- runbooks -------------------------------------------------------------------------------


def github_slug(heading: str) -> str:
    """GitHub's heading anchor: lower-case, punctuation dropped, spaces to ``-``.

    Underscores and hyphens survive, so ``trace_emission`` stays one word.
    """
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def markdown_anchors(text: str) -> frozenset[str]:
    """Every heading anchor in a Markdown document (fenced code excluded)."""
    anchors: set[str] = set()
    fenced = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = _HEADING_RE.match(line)
        if match is not None:
            anchors.add(github_slug(match.group(2)))
    return frozenset(anchors)


def runbook_problem(link: object, repo: Path) -> str | None:
    """Why a runbook annotation does not resolve, or ``None`` when it does."""
    if not isinstance(link, str) or not link.strip():
        return "no runbook annotation (files/10 §6: a runbook is linked from every alert)"
    match = _RUNBOOK_RE.match(link)
    if match is None:
        return f"runbook {link!r} is not a {RUNBOOK_ROOT}/<file>.md#<anchor> link"
    path = repo / RUNBOOK_ROOT / f"{match.group(1)}.md"
    if not path.is_file():
        return f"runbook file {RUNBOOK_ROOT}/{path.name} does not exist"
    anchor = match.group(2)
    if anchor not in markdown_anchors(path.read_text(encoding="utf-8")):
        return f"{RUNBOOK_ROOT}/{path.name} has no heading that slugs to #{anchor}"
    return None


# --- the whole audit ------------------------------------------------------------------------


def _series_problem(reference: str, catalog: MetricsCatalog, records: frozenset[str]) -> str | None:
    if ":" in reference:
        if reference in records:
            return None
        return f"reads recording rule {reference!r}, which no loaded rule file defines"
    family = catalog.family(reference)
    if family is None:
        return f"reads {reference!r}, which observability/metrics_catalog.yaml does not list"
    if family.status != "live":
        return (
            f"reads {reference!r}, which is catalogued as planned — nothing emits it, "
            "so the rule can never fire"
        )
    return None


def rule_problems(paths: Sequence[Path], catalog: MetricsCatalog, repo: Path) -> list[str]:
    """Every defect across the given rule files, as sentences; empty when clean."""
    records = frozenset(
        str(rule["record"]) for path in paths for _, rule in iter_rules(path) if "record" in rule
    )
    problems: list[str] = []
    for path in paths:
        for group, rule in iter_rules(path):
            name = rule.get("alert") or rule.get("record") or "<unnamed>"
            where = f"{path.name}:{group}:{name}"
            for reference in sorted(promql_series(str(rule.get("expr", "")))):
                problem = _series_problem(reference, catalog, records)
                if problem is not None:
                    problems.append(f"{where} {problem}")
            if "alert" in rule:
                annotations = rule.get("annotations") or {}
                problem = runbook_problem(annotations.get("runbook"), repo)
                if problem is not None:
                    problems.append(f"{where} {problem}")
    return problems
