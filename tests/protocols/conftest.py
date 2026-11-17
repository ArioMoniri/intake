"""Shared fixtures for the INT-041 compiler suite.

Everything here is synthetic (files/04 §7: packs and goldens carry synthetic
data only). The life-threat variants are derived from the one committed
fixture by patching its YAML, so there is a single place where the sign-off
shape is written down.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.bindings import OperationalTemplate, load_opt
from protocols.cli import load_registry
from protocols.compile import LifeThreatSet, load_life_threat_set
from protocols.loader import PackRegistry

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "protocols" / "compile"
SIGNED_LIFE_THREAT = FIXTURES / "life_threat_signed.yaml"
PACK_TREE = FIXTURES / "tree"
REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_OPT = REPO_ROOT / "packages" / "protocols" / "openehr" / "previsit_intake.v1.opt"


@pytest.fixture
def pack_tree() -> Path:
    return PACK_TREE


@pytest.fixture
def registry() -> PackRegistry:
    return load_registry(PACK_TREE)


@pytest.fixture
def template() -> OperationalTemplate:
    return load_opt(COMMITTED_OPT)


@pytest.fixture
def life_threat() -> LifeThreatSet:
    return load_life_threat_set(SIGNED_LIFE_THREAT, allow_fixture_snapshots=True)


@pytest.fixture
def patched_life_threat(tmp_path: Path) -> Callable[[Mapping[str, Any]], LifeThreatSet]:
    """Load the committed signed fixture with top-level keys replaced."""

    def _patch(overrides: Mapping[str, Any]) -> LifeThreatSet:
        raw: dict[str, Any] = yaml.safe_load(SIGNED_LIFE_THREAT.read_text(encoding="utf-8"))
        for key, value in overrides.items():
            raw[key] = value
        path = tmp_path / "life_threat_patched.yaml"
        path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=True), encoding="utf-8")
        return load_life_threat_set(path, allow_fixture_snapshots=True)

    return _patch
