"""INT-536 F5 — the satisfaction score's inventory basis is the basis its routes enforce.

Invariant 18: every data field carries ``{category, purpose, basis, retention,
recipients}``, and the basis has to be the ground the system actually relies
on. Both satisfaction routes require the ``satisfaction`` consent scope
(files/06 §2: açık rıza, off by default; ``intake_api.satisfaction``). The
storage said otherwise in three places:
- the ``events`` columns that hold the score were annotated
  ``KVKK m.5/2-c — processing necessary for the service contract``;
- the ``csat_texts`` key columns carried the same annotation;
- the ``satisfaction`` retention class gave it the same ground.

``docs/legal/COUNSEL_BRIEF.md`` §2.9 flagged this, and so did INT-529's F5.

``events`` holds more than one purpose: ``csat.v1`` and ``nps.v1`` are
satisfaction, ``wait.v1`` is operational. A column carries one annotation, so
its basis is now stated per ``event_type`` (:data:`inventory.EVENT_TYPE_BASES`).
This suite holds the annotations to the gates:
- the two event types the satisfaction routes write rest on the açık rıza basis;
- every ``Event(...)`` writer in the tree writes a type the map declares;
- ``csat_texts`` carries no contract ground at all;
- the retention class states the same ground.

Near misses: a contract-basis annotation on a satisfaction column is a finding,
and so is a writer of an undeclared event type.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest
import yaml
from fastapi.routing import APIRoute
from intake_api import satisfaction
from intake_api.consent_guard import ConsentGuard
from intake_platform import wait_times
from intake_platform.consent.registry import LegalBasis, resolve_scope
from intake_platform.db import inventory, models
from intake_platform.db.inventory import INVENTORY_KEY

REPO = Path(__file__).resolve().parents[2]
RETENTION_POLICY = (
    REPO / "packages/intake_platform/src/intake_platform/retention/retention_policy.yaml"
)
SATISFACTION_EVENT_TYPES = frozenset({"csat.v1", "nps.v1"})


def _basis(table: str, column: str) -> str:
    annotation: Mapping[str, str] = models.Base.metadata.tables[table].c[column].info[INVENTORY_KEY]
    return annotation["basis"]


def satisfaction_basis_findings(annotations: Iterable[tuple[str, str]]) -> list[str]:
    """``(where, basis)`` pairs for satisfaction data → what contradicts the gate."""
    return [
        f"{where}: {basis!r} is not the açık rıza ground its route enforces"
        for where, basis in annotations
        if basis == inventory.BASIS_CONTRACT or "açık rıza" not in basis
    ]


def test_both_satisfaction_routes_require_the_satisfaction_scope() -> None:
    routes = [route for route in satisfaction.router.routes if isinstance(route, APIRoute)]
    assert {route.path for route in routes} == {
        "/v1/sessions/{session_id}/csat",
        "/v1/feedback/nps",
    }
    for route in routes:
        guards = [
            dep.dependency for dep in route.dependencies if isinstance(dep.dependency, ConsentGuard)
        ]
        assert [guard.policy.enforced for guard in guards] == [(satisfaction.SATISFACTION_SCOPE,)]
    purpose = resolve_scope(satisfaction.SATISFACTION_SCOPE)
    assert purpose.legal_basis is LegalBasis.EXPLICIT_CONSENT
    assert purpose.default_granted is False


def test_the_satisfaction_event_types_rest_on_açık_rıza() -> None:
    for event_type in SATISFACTION_EVENT_TYPES:
        assert inventory.EVENT_TYPE_BASES[event_type] == inventory.BASIS_SATISFACTION_CONSENT
    assert "açık rıza" in inventory.BASIS_SATISFACTION_CONSENT
    assert satisfaction.SATISFACTION_SCOPE in inventory.BASIS_SATISFACTION_CONSENT


def test_every_events_column_states_the_basis_per_event_type() -> None:
    table = models.Base.metadata.tables["events"]
    for column in table.columns:
        assert _basis("events", column.name) == inventory.BASIS_EVENTS_BY_TYPE, column.name
    for event_type, basis in inventory.EVENT_TYPE_BASES.items():
        assert f"{event_type} — {basis}" in inventory.BASIS_EVENTS_BY_TYPE


def test_no_csat_texts_column_claims_the_contract() -> None:
    table = models.Base.metadata.tables["csat_texts"]
    pairs = [(f"csat_texts.{c.name}", _basis("csat_texts", c.name)) for c in table.columns]
    assert satisfaction_basis_findings(pairs) == []


def test_the_satisfaction_retention_class_states_the_same_ground() -> None:
    policy = yaml.safe_load(RETENTION_POLICY.read_text(encoding="utf-8"))
    rows = [row for row in policy["classes"] if row["data_class"] == "satisfaction"]
    assert len(rows) == 1
    assert satisfaction_basis_findings([("retention satisfaction", rows[0]["basis"])]) == []


@pytest.mark.parametrize(
    ("basis", "found"),
    [
        (inventory.BASIS_CONTRACT, True),
        ("KVKK m.5/2-f — legitimate interest", True),
        (inventory.BASIS_SATISFACTION_CONSENT, False),
        (inventory.BASIS_HEALTH_CONSENT, False),
    ],
)
def test_a_contract_ground_on_satisfaction_data_is_a_finding(basis: str, found: bool) -> None:
    assert bool(satisfaction_basis_findings([("forged", basis)])) is found


def _event_writers() -> list[tuple[str, ast.expr]]:
    """``(file, event_type expression)`` for every ``Event(...)`` in the source trees."""
    out: list[tuple[str, ast.expr]] = []
    for tree in sorted([*REPO.glob("packages/*/src"), *REPO.glob("services/*/src")]):
        for path in sorted(tree.rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(module):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Event"
                ):
                    for keyword in node.keywords:
                        if keyword.arg == "event_type":
                            out.append((path.relative_to(REPO).as_posix(), keyword.value))
    return out


def _resolved(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return expression.value
    if isinstance(expression, ast.Name) and expression.id == "WAIT_EVENT_TYPE":
        return wait_times.WAIT_EVENT_TYPE
    return None


def test_every_event_writer_writes_a_declared_type() -> None:
    writers = _event_writers()
    written = {(path, _resolved(expression)) for path, expression in writers}
    assert all(event_type is not None for _, event_type in written), written
    assert {event_type for _, event_type in written} == set(inventory.EVENT_TYPE_BASES)
    assert {
        event_type
        for path, event_type in written
        if path == "services/api/src/intake_api/satisfaction.py"
    } == SATISFACTION_EVENT_TYPES


def test_an_undeclared_event_type_is_not_resolved() -> None:
    """Near miss for the writer scan: a type the map does not declare stays
    visible as a mismatch rather than being folded into a known one."""
    forged = ast.parse('Event(event_type="lifecycle.v1")').body[0]
    assert isinstance(forged, ast.Expr) and isinstance(forged.value, ast.Call)
    assert _resolved(forged.value.keywords[0].value) not in inventory.EVENT_TYPE_BASES
