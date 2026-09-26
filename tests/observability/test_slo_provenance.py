"""INT-021 — an SLO objective is a commitment, so it must be quoted or absent.

CLAUDE.md's standing rule is "never invent a value to unblock yourself", and an
error-budget target is the shape of invented value that survives longest: it
reads as authoritative, it is a single number with no units to check, and it
ends up in a tender. files/10 §6 states exactly one — *"API availability
99.9 %"* — and files/08 §4 A states three more that are session objectives over
series no service emits yet. Every other objective in docs/slo/ was chosen by
whoever wrote the file.

So the schema now takes provenance, not just a number:

- ``source: {cite, file, quote}`` — a numeric objective must quote the sentence
  that states it, and this file greps the cited blueprint for that quote
  **verbatim**. You cannot write a number the spec does not contain.
- ``objective: awaiting-human`` with ``source: {blocker, human, ask}`` — no
  number, a HUMAN_BLOCKERS.md row, the named human and the one sentence they
  must answer.

And it fails closed: :func:`intake_platform.slo.prometheus_rule_groups` emits
recording rules for an ``awaiting-human`` SLO (measuring costs nothing and is
how the number eventually gets chosen from data) and **no alerting rule at
all**. Nothing can page against a budget nobody set.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.slo import (
    AWAITING_HUMAN,
    AwaitingHumanSource,
    SLOFile,
    SpecSource,
    load_slo_file,
    prometheus_rule_groups,
)
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
SLO_DIR = REPO / "docs" / "slo"
RULES_PATH = REPO / "infra" / "observability" / "prometheus-rules.yaml"
BLOCKERS_PATH = REPO / "files" / "HUMAN_BLOCKERS.md"

_WS_RE = re.compile(r"\s+")


def _slo_paths() -> list[Path]:
    paths = sorted(SLO_DIR.glob("*.yaml"))
    assert paths, "docs/slo/ must hold at least the api SLO file"
    return paths


def _flat(text: str) -> str:
    """Collapse whitespace so a quote survives the blueprint's line wrapping."""
    return _WS_RE.sub(" ", text)


def _slo_doc(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "service": "api",
        "owner": "platform",
        "slos": [
            {
                "name": "availability",
                "sli": 'sum(rate(http_requests_total{service="api",status=~"5.."}[5m]))'
                ' / sum(rate(http_requests_total{service="api"}[5m]))',
                "objective": 99.9,
                "source": {
                    "cite": "files/10 §6",
                    "file": "files/10_SECURITY_AND_TECHNICAL_MONITORING.md",
                    "quote": "API availability 99.9 %",
                },
                "window": "28d",
                "burn_rate_alerts": {
                    "fast": {
                        "factor": 14.4,
                        "long_window": "1h",
                        "short_window": "5m",
                        "for_duration": "2m",
                        "severity": "page",
                    },
                    "slow": {
                        "factor": 6.0,
                        "long_window": "6h",
                        "short_window": "30m",
                        "for_duration": "15m",
                        "severity": "page",
                    },
                },
            }
        ],
    }
    base.update(overrides)
    return base


def _awaiting_source() -> dict[str, str]:
    return {
        "blocker": "HB-O5",
        "human": "owner",
        "ask": "What share of good events over 28 days is this SLI's commitment?",
    }


# --- every committed objective is quoted or absent --------------------------------


def test_every_slo_declares_a_source() -> None:
    for path in _slo_paths():
        for slo in load_slo_file(path).slos:
            assert slo.source is not None, f"{path.name}:{slo.name} has no source"


def test_every_numeric_objective_is_quoted_verbatim_from_its_cited_file() -> None:
    for path in _slo_paths():
        for slo in load_slo_file(path).slos:
            if slo.objective == AWAITING_HUMAN:
                continue
            source = slo.source
            assert isinstance(source, SpecSource), (
                f"{path.name}:{slo.name} states a number without citing a blueprint"
            )
            cited = REPO / source.file
            assert cited.is_file(), f"{path.name}:{slo.name} cites a missing file {source.file}"
            haystack = _flat(cited.read_text(encoding="utf-8"))
            assert _flat(source.quote) in haystack, (
                f"{path.name}:{slo.name} quotes {source.quote!r}, which does not appear in "
                f"{source.file} — an objective is only as real as the sentence that states it"
            )


def test_every_numeric_objective_appears_inside_its_own_quote() -> None:
    """The quote must contain the number, or the citation proves nothing."""
    for path in _slo_paths():
        for slo in load_slo_file(path).slos:
            if slo.objective == AWAITING_HUMAN:
                continue
            assert isinstance(slo.source, SpecSource)
            digits = f"{slo.objective:g}"
            assert digits in slo.source.quote, (
                f"{path.name}:{slo.name} objective {digits} is absent from its own quote "
                f"{slo.source.quote!r}"
            )


def test_every_awaiting_human_objective_names_a_real_blocker_row() -> None:
    blockers = BLOCKERS_PATH.read_text(encoding="utf-8")
    seen = 0
    for path in _slo_paths():
        for slo in load_slo_file(path).slos:
            if slo.objective != AWAITING_HUMAN:
                continue
            seen += 1
            source = slo.source
            assert isinstance(source, AwaitingHumanSource)
            assert f"{source.blocker}" in blockers, (
                f"{path.name}:{slo.name} is awaiting-human on {source.blocker}, which has no "
                "row in files/HUMAN_BLOCKERS.md"
            )
            assert source.human.strip(), f"{path.name}:{slo.name} names no human"
            assert source.ask.strip().endswith("?"), (
                f"{path.name}:{slo.name} ask is not a question the human can answer: {source.ask!r}"
            )
    assert seen, "no SLO is awaiting-human — has the provenance gate been bypassed?"


# --- the schema itself ------------------------------------------------------------


def test_schema_rejects_a_number_without_a_spec_source() -> None:
    bad = _slo_doc()
    bad["slos"][0]["source"] = _awaiting_source()
    with pytest.raises(ValidationError, match="awaiting-human"):
        SLOFile.model_validate(bad)


def test_schema_rejects_awaiting_human_with_a_spec_source() -> None:
    bad = _slo_doc()
    bad["slos"][0]["objective"] = AWAITING_HUMAN
    with pytest.raises(ValidationError, match="blocker"):
        SLOFile.model_validate(bad)


def test_schema_rejects_a_missing_source() -> None:
    bad = _slo_doc()
    del bad["slos"][0]["source"]
    with pytest.raises(ValidationError):
        SLOFile.model_validate(bad)


def test_schema_rejects_a_blank_quote() -> None:
    bad = _slo_doc()
    bad["slos"][0]["source"]["quote"] = "   "
    with pytest.raises(ValidationError):
        SLOFile.model_validate(bad)


def test_schema_accepts_awaiting_human_with_a_blocker() -> None:
    doc = _slo_doc()
    doc["slos"][0]["objective"] = AWAITING_HUMAN
    doc["slos"][0]["source"] = _awaiting_source()
    parsed = SLOFile.model_validate(doc)
    assert parsed.slos[0].objective == AWAITING_HUMAN
    assert parsed.slos[0].error_budget is None


# --- fail closed: no objective, no alert ------------------------------------------


def test_an_awaiting_human_slo_generates_recording_rules_and_no_alert() -> None:
    doc = _slo_doc()
    doc["slos"][0]["objective"] = AWAITING_HUMAN
    doc["slos"][0]["source"] = _awaiting_source()
    groups = prometheus_rule_groups(SLOFile.model_validate(doc))
    by_name = {group["name"]: group["rules"] for group in groups["groups"]}
    assert by_name["slo-api-recording"], "an unset objective must still be measured"
    assert by_name["slo-api-alerts"] == [], (
        "an SLO with no objective must generate no alerting rule — a page needs a budget"
    )


def test_a_sourced_slo_still_generates_its_three_burn_alerts() -> None:
    doc = _slo_doc()
    doc["slos"][0]["burn_rate_alerts"]["ticket"] = {
        "factor": 1.0,
        "long_window": "3d",
        "short_window": "6h",
        "for_duration": "1h",
        "severity": "ticket",
    }
    groups = prometheus_rule_groups(SLOFile.model_validate(doc))
    alerts = [r["alert"] for g in groups["groups"] for r in g["rules"] if "alert" in r]
    assert alerts == [
        "ApiAvailabilityFastBurn",
        "ApiAvailabilitySlowBurn",
        "ApiAvailabilityTicketBurn",
    ]


def test_no_committed_alert_belongs_to_an_objectiveless_slo() -> None:
    """The committed rules file must not page on a budget nobody set."""
    unset = {
        f"{slo_file.service}/{slo.name}"
        for path in _slo_paths()
        for slo_file in [load_slo_file(path)]
        for slo in slo_file.slos
        if slo.objective == AWAITING_HUMAN
    }
    rules: dict[str, Any] = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))
    for group in rules["groups"]:
        for rule in group["rules"]:
            if "alert" not in rule:
                continue
            key = f"{rule['labels']['service']}/{rule['labels']['slo']}"
            assert key not in unset, f"{rule['alert']} pages on {key}, whose objective is unset"
