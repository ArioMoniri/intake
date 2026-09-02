"""INT-025 — metrics catalogue completeness + emission gate (inv. 13; files/08 §4).

Pinned here:
- files/08 §4 is the tracked-parameter map. Every metric id it names exists in
  observability/metrics_catalog.yaml with a Prometheus-shaped ``name`` (dots
  become underscores), the spec id preserved in ``id``, a ``unit``, an
  ``owner`` and — where 08 §4 states one — the ``target`` verbatim enough to
  grep. The parser below reads the section itself, so a spec edit that adds an
  id fails CI until the catalogue follows (no-silent-caps).
- Ids 08 §4 names for services that do not exist yet are catalogued with
  ``status: planned`` — present, never silently dropped. ``status`` is honest
  in both directions: a ``live`` entry must be observably emitted (static
  declaration or the served exposition), a ``planned`` entry must not be.
- The emit-without-catalogue gate, statically: every
  ``prometheus_client.Counter/Gauge/Histogram`` constructed under packages/ or
  services/ carries a family name the catalogue covers, or the build fails.
  The runtime direction (families actually served on /metrics) is asserted
  here too, mirroring tests/observability/test_slo_files.py.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

# Modules that register live families at import time must be imported here
# explicitly: the exposition check reads the default registry, and relying on
# pytest's collection order to have imported an emitter is luck, not a gate.
# Adding a live metric without listing its module fails
# test_live_entries_are_emitted_and_planned_entries_are_not, which points here.
import intake_platform.chaos  # noqa: F401  (vendor_*/chaos_* resilience families, INT-024)
import intake_platform.event_bus  # noqa: F401  (event_bus_* lag/retry/DLQ families)
import intake_platform.overlay.store  # noqa: F401  (overlay_facts_* families, INT-170)
import intake_platform.retention.engine  # noqa: F401  (retention_*_total)
import intake_platform.uploads  # noqa: F401  (document_upload_pipeline_total)
import intake_voice_runtime.metrics  # noqa: F401  (talker_/policyguard_/delivery_ families, INT-091)
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from intake_platform.health import mount_health
from intake_platform.metrics import mount_http_metrics
from intake_platform.slo import MetricDef, MetricsCatalog, load_metrics_catalog
from prometheus_client.parser import text_string_to_metric_families
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
CATALOG_PATH = REPO / "observability" / "metrics_catalog.yaml"
SPEC_PATH = REPO / "files" / "08_ADMIN_CONSOLE_AND_OBSERVABILITY.md"

#: Directories whose Python sources may construct Prometheus families.
SCAN_ROOTS = ("packages", "services")
SKIP_PARTS = frozenset({"tests", ".venv", "node_modules", "build", "dist", ".cache"})

#: files/08 §4 currently names exactly this many distinct metric ids. The pin
#: is the drift detector: an edit to §4 (or a parser regression) fails here,
#: forcing the catalogue to be reconciled instead of silently diverging.
EXPECTED_SPEC_ID_COUNT = 135

#: 08 §4 group B: "per turn, labels: profile, tenant, branch, vendor".
PER_TURN_LABELS = frozenset({"tenant", "profile", "branch", "vendor"})

#: Families registered by prometheus_client's default collectors (process /
#: gc / platform). They are served, not constructed in our sources, and the
#: process collector is platform-dependent (silent off Linux), so they are
#: exempt from the "live means observably emitted" proof.
DEFAULT_COLLECTOR_FAMILIES = frozenset(
    {
        "process_cpu_seconds_total",
        "process_resident_memory_bytes",
        "process_virtual_memory_bytes",
        "process_start_time_seconds",
        "process_open_fds",
        "process_max_fds",
        "python_gc_objects_collected_total",
        "python_gc_objects_uncollectable_total",
        "python_gc_collections_total",
        "python_info",
    }
)

#: Targets 08 §4 states, pinned as grep-able fragments the catalogue entry's
#: ``target`` must contain. Keys must be ids the spec parser finds.
SPEC_TARGET_FRAGMENTS: dict[str, str] = {
    "slo.api_availability": "99.9",
    "slo.voice_session_success": "99.5",
    "slo.note_ready_within_60s": "99",
    "slo.doctor_link_open_p95": "2 s",
    "voice.round_trip_ms": "02 §8",
    "voice.barge_in_stop_ms": "150",
    "voice.interruption_rate": "15",
    "voice.clip_cache_hit_ratio": "0.6",
    "work.latency_ms": "3 s",
    "delivery.insertion_wait_ms": "2 s",
    "delivery.duplicates": "0",
    "preempt.red_latency_ms": "300",
    "talker.tool_calls_total": "six",
    "note.acceptance_rate": "70",
    "protocol.must_ask_coverage": "95",
    "hallucination.audit_rate": "0.5",
    "triage.false_red_rate": "2",
    "crisis.path_completion": "100",
    "clinic.red_ack_latency_min": "4 business hours",
    "csat.score": "4.3",
    "session.completion_rate": "80",
    "session.duration_s": "4 min",
    "wait.time_to_first_question_s": "3 s",
    "wait.note_ready_after_wrapup_s": "60 s",
    "sec.egress_denied_total": "0",
    "client.crash_free_sessions": "99.5",
}

_SPEC_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)*$")
_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PROM_FAMILY_CLASSES = frozenset({"Counter", "Gauge", "Histogram"})


# --- files/08 §4 parsing ----------------------------------------------------------


def _spec_section_4() -> str:
    text = SPEC_PATH.read_text(encoding="utf-8")
    return text[text.index("\n## 4.") : text.index("\n## 5.")]


def spec_metric_ids() -> dict[str, frozenset[str]]:
    """08 §4 metric ids mapped to the label names its braces state (may be empty).

    A backticked token is a metric id when it is a dotted-or-plain lowercase
    identifier, optionally followed by ``{label,label}``. Section references
    (``02 §8``), paths and prose never match.
    """
    ids: dict[str, set[str]] = {}
    for token in re.findall(r"`([^`]+)`", _spec_section_4()):
        base, brace, tail = token.partition("{")
        labels: set[str] = set()
        if brace:
            if not tail.endswith("}"):
                continue
            labels = set(tail[:-1].split(","))
            if not all(_LABEL_RE.match(label) for label in labels):
                continue
        if _SPEC_ID_RE.match(base) is None:
            continue
        ids.setdefault(base, set()).update(labels)
    return {spec_id: frozenset(labels) for spec_id, labels in ids.items()}


# --- emission discovery -----------------------------------------------------------


def _python_sources() -> Iterator[Path]:
    for root in SCAN_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if SKIP_PARTS.isdisjoint(path.parts):
                yield path


def statically_declared_metrics() -> dict[str, str]:
    """Prometheus family name -> repo-relative file that constructs it.

    Finds every ``Counter``/``Gauge``/``Histogram`` call bound to
    prometheus_client (``from prometheus_client import Counter`` aliases and
    ``prometheus_client.Counter`` attribute calls) whose first argument is a
    string literal. ``collections.Counter`` and friends never match.
    """
    declared: dict[str, str] = {}
    for path in _python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        direct: set[str] = set()
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "prometheus_client":
                for alias in node.names:
                    if alias.name in _PROM_FAMILY_CLASSES:
                        direct.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "prometheus_client":
                        modules.add(alias.asname or alias.name)
        if not direct and not modules:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            called = (isinstance(func, ast.Name) and func.id in direct) or (
                isinstance(func, ast.Attribute)
                and func.attr in _PROM_FAMILY_CLASSES
                and isinstance(func.value, ast.Name)
                and func.value.id in modules
            )
            first = node.args[0]
            if called and isinstance(first, ast.Constant) and isinstance(first.value, str):
                declared[first.value] = str(path.relative_to(REPO))
    return declared


def _serve_exposition() -> str:
    app = FastAPI()
    mount_health(app)
    mount_http_metrics(app, "catalog_completeness_gate")
    return TestClient(app).get("/metrics").text


def served_family_names() -> frozenset[str]:
    """Every name a served family answers to (counters also as ``*_total``)."""
    names: set[str] = set()
    for family in text_string_to_metric_families(_serve_exposition()):
        names.add(family.name)
        if family.type == "counter":
            names.add(f"{family.name}_total")
    return frozenset(names)


def uncatalogued(catalog: MetricsCatalog, emitted: Iterable[str]) -> list[str]:
    return sorted(name for name in emitted if not catalog.covers(name))


def served_uncatalogued(catalog: MetricsCatalog) -> list[str]:
    offenders: list[str] = []
    for family in text_string_to_metric_families(_serve_exposition()):
        candidates = {family.name}
        if family.type == "counter":
            candidates.add(f"{family.name}_total")
        if not any(catalog.covers(name) for name in candidates):
            offenders.append(family.name)
    return sorted(offenders)


def _catalog() -> MetricsCatalog:
    return load_metrics_catalog(CATALOG_PATH)


def _by_spec_id(catalog: MetricsCatalog) -> dict[str, MetricDef]:
    return {metric.spec_id: metric for metric in catalog.metrics}


# --- the 08 §4 completeness gate --------------------------------------------------


def test_spec_parser_extracts_the_frozen_id_set() -> None:
    ids = spec_metric_ids()
    assert len(ids) == EXPECTED_SPEC_ID_COUNT, (
        "files/08 §4 changed (or the parser regressed): "
        f"{len(ids)} ids found, {EXPECTED_SPEC_ID_COUNT} pinned. Reconcile "
        "observability/metrics_catalog.yaml, then move the pin."
    )
    assert "voice.eou_delay_ms" in ids
    assert "worker_load" in ids  # plain LiveKit name, no dot
    assert "admin.four_eyes_self_approval_attempt_total" in ids
    assert ids["admin.pack_promoted_total"] == frozenset({"to"})
    assert ids["slo.burn_rate"] == frozenset({"window"})
    assert ids["admin.break_glass_opened_total"] == frozenset({"actor", "reason_class"})
    # section references, paths and prose never parse as ids
    assert not any("§" in spec_id or "/" in spec_id for spec_id in ids)


def test_every_08_4_id_is_catalogued_under_its_prometheus_name() -> None:
    by_spec = _by_spec_id(_catalog())
    ids = spec_metric_ids()
    missing = sorted(set(ids) - set(by_spec))
    assert missing == [], (
        "files/08 §4 names metric ids absent from observability/metrics_catalog.yaml "
        f"(inv. 13; no-silent-caps): {missing}"
    )
    for spec_id in ids:
        entry = by_spec[spec_id]
        assert entry.name == spec_id.replace(".", "_"), (
            f"{spec_id}: catalogued Prometheus name {entry.name!r} is not the "
            "dot-to-underscore normalisation of the spec id"
        )


def test_catalogued_spec_entries_declare_unit_owner_description() -> None:
    by_spec = _by_spec_id(_catalog())
    for spec_id in spec_metric_ids():
        entry = by_spec[spec_id]
        assert entry.unit.strip(), f"{spec_id}: empty unit"
        assert entry.owner.strip(), f"{spec_id}: empty owner"
        assert entry.description.strip(), f"{spec_id}: empty description"


def test_stated_labels_survive_into_the_catalogue() -> None:
    by_spec = _by_spec_id(_catalog())
    for spec_id, stated in spec_metric_ids().items():
        entry = by_spec[spec_id]
        assert stated <= set(entry.labels), (
            f"{spec_id}: 08 §4 states labels {sorted(stated)} but the catalogue "
            f"entry carries {entry.labels}"
        )
        if spec_id.startswith("voice."):
            assert PER_TURN_LABELS <= set(entry.labels), (
                f"{spec_id}: 08 §4 group B fixes per-turn labels "
                f"{sorted(PER_TURN_LABELS)}; entry carries {entry.labels}"
            )


def test_stated_targets_survive_into_the_catalogue() -> None:
    ids = spec_metric_ids()
    by_spec = _by_spec_id(_catalog())
    for spec_id, fragment in SPEC_TARGET_FRAGMENTS.items():
        assert spec_id in ids, f"target pinned for {spec_id}, which 08 §4 no longer names"
        entry = by_spec[spec_id]
        assert entry.target is not None, f"{spec_id}: 08 §4 states a target, entry has none"
        assert fragment in entry.target, (
            f"{spec_id}: target {entry.target!r} does not carry the 08 §4 fragment {fragment!r}"
        )


# --- inv. 13: emitting an uncatalogued metric fails -------------------------------


def test_every_statically_declared_metric_is_catalogued() -> None:
    catalog = _catalog()
    declared = statically_declared_metrics()
    # the scanner must keep finding the real emitters, or the gate is hollow
    assert "http_requests_total" in declared
    assert "http_request_duration_seconds" in declared
    offenders = {name: declared[name] for name in uncatalogued(catalog, declared)}
    assert offenders == {}, (
        "prometheus_client families constructed in code but absent from "
        f"observability/metrics_catalog.yaml (inv. 13): {offenders}"
    )


def test_every_served_family_is_catalogued() -> None:
    assert served_uncatalogued(_catalog()) == [], (
        "series served on /metrics but absent from observability/metrics_catalog.yaml (inv. 13)"
    )


def test_the_gate_reports_a_deliberately_uncatalogued_emission() -> None:
    """Near-miss negative control: remove one live entry, the gate names it."""
    catalog = _catalog()
    reduced = MetricsCatalog.model_validate(
        {
            "metrics": [
                metric.model_dump(exclude_none=True)
                for metric in catalog.metrics
                if metric.name != "http_requests_total"
            ]
        }
    )
    declared = statically_declared_metrics()
    assert "http_requests_total" in uncatalogued(reduced, declared)
    # the exposition parser reports counter families without the _total suffix
    assert "http_requests" in served_uncatalogued(reduced)
    assert uncatalogued(catalog, declared) == []


def test_live_entries_are_emitted_and_planned_entries_are_not() -> None:
    """``status`` is honest in both directions.

    A live entry nobody emits belongs in ``planned``; a planned entry that is
    actually emitted must be promoted to ``live``. Catalogued-but-planned is
    by design (08 §4 names services that do not exist yet), never a failure.
    """
    catalog = _catalog()
    observed = set(statically_declared_metrics()) | served_family_names()
    dishonest_live = sorted(
        metric.name
        for metric in catalog.metrics
        if metric.status == "live"
        and metric.name not in observed
        and metric.name not in DEFAULT_COLLECTOR_FAMILIES
    )
    assert dishonest_live == [], (
        f"catalogued as live but never emitted (mark planned or emit): {dishonest_live}"
    )
    emitted_planned = sorted(
        metric.name
        for metric in catalog.metrics
        if metric.status == "planned" and metric.name in observed
    )
    assert emitted_planned == [], (
        f"catalogued as planned but actually emitted (promote to live): {emitted_planned}"
    )


# --- schema: the fields INT-025 adds ----------------------------------------------


def _entry(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "voice_eou_delay_ms",
        "id": "voice.eou_delay_ms",
        "type": "histogram",
        "labels": ["tenant", "profile", "branch", "vendor"],
        "owner": "voice-runtime",
        "unit": "ms",
        "status": "planned",
        "description": "End-of-utterance delay per turn (LiveKit EOUMetrics).",
    }
    base.update(overrides)
    return base


def test_schema_accepts_a_planned_spec_entry() -> None:
    metric = MetricDef.model_validate(_entry(target="p50/p95 per files/02 §8"))
    assert metric.spec_id == "voice.eou_delay_ms"
    assert metric.status == "planned"
    assert metric.unit == "ms"


def test_schema_defaults_to_live_status_and_name_as_spec_id() -> None:
    payload = _entry(name="http_requests_total", type="counter", owner="platform", unit="count")
    del payload["id"]
    del payload["status"]
    metric = MetricDef.model_validate(payload)
    assert metric.status == "live"
    assert metric.id is None
    assert metric.spec_id == "http_requests_total"


def test_schema_requires_a_unit() -> None:
    payload = _entry()
    del payload["unit"]
    with pytest.raises(ValidationError, match="unit"):
        MetricDef.model_validate(payload)


def test_schema_rejects_a_blank_unit() -> None:
    with pytest.raises(ValidationError, match="unit"):
        MetricDef.model_validate(_entry(unit="   "))


def test_schema_rejects_a_blank_target() -> None:
    with pytest.raises(ValidationError, match="target"):
        MetricDef.model_validate(_entry(target="   "))


def test_schema_rejects_an_unknown_status() -> None:
    with pytest.raises(ValidationError):
        MetricDef.model_validate(_entry(status="someday"))


def test_schema_rejects_a_malformed_spec_id() -> None:
    with pytest.raises(ValidationError):
        MetricDef.model_validate(_entry(id="Voice.EOU-delay"))


def test_schema_rejects_an_id_that_does_not_normalise_to_the_name() -> None:
    with pytest.raises(ValidationError, match="normalis"):
        MetricDef.model_validate(_entry(id="voice.tts_ttfb_ms"))


def test_schema_still_rejects_a_dotted_prometheus_name() -> None:
    payload = _entry(name="voice.eou_delay_ms")
    del payload["id"]
    with pytest.raises(ValidationError):
        MetricDef.model_validate(payload)
