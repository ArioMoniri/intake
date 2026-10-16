"""INT-428 / ADR-035 — hosted lanes belong to a deployment, not a tenant.

The AI/ML review's binding split, held structurally:

- **No PHI-closure code imports the hosted adapters.** Every Python source
  under ``packages/`` and ``services/`` other than the adapter package itself
  is parsed, and none imports ``intake_hosted_lanes``; the platform names the
  package only as a string it reaches for in the synthetic deployment.
- **No PHI-closure package depends on it**: only the workspace root lists it.
- **Only the synthetic image carries it**: ``infra/staging/Dockerfile.api``
  puts it on the path and bakes ``INTAKE_DEPLOYMENT_DATA_CLASS=synthetic``;
  the compose file sets neither, so no operator env can redeclare the host.
- **The wiring returns no hosted lanes** for a real-PHI declaration or an
  image without the package. Near miss: a synthetic declaration with the
  package present loads the provider (unlisted until its allow-list row lands).
"""

from __future__ import annotations

import ast
import importlib.util
import tomllib
from pathlib import Path

import pytest
from intake_platform.egress import load_allowlist
from intake_platform.model_lanes import HostedLanes, ProviderId
from intake_platform.model_lanes import wiring as lanes_wiring
from intake_platform.model_lanes.wiring import HOSTED_PACKAGE, load_hosted_lanes

REPO = Path(__file__).resolve().parents[2]
ADAPTER_ROOT = REPO / "packages" / "hosted-lanes"
ALLOWLIST = REPO / "infra" / "security" / "egress-allowlist.yaml"
SKIP = frozenset({".venv", "node_modules", "tests", "__pycache__"})


def _python_sources() -> list[Path]:
    out: list[Path] = []
    for root in (REPO / "packages", REPO / "services"):
        for path in root.rglob("*.py"):
            if ADAPTER_ROOT in path.parents or SKIP.intersection(path.parts):
                continue
            out.append(path)
    return out


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_phi_closure_source_imports_the_hosted_adapters() -> None:
    sources = _python_sources()
    assert len(sources) > 200, "the scan must walk the real tree"
    offenders = [
        str(path.relative_to(REPO))
        for path in sources
        if any(name.split(".")[0] == HOSTED_PACKAGE for name in _imports(path))
    ]
    assert offenders == []


def test_near_miss_the_scanner_catches_an_import() -> None:
    fake = ast.parse(f"from {HOSTED_PACKAGE}.plugin import hosted_lanes_from_env\n")
    names = {node.module for node in ast.walk(fake) if isinstance(node, ast.ImportFrom)}
    assert any(name and name.split(".")[0] == HOSTED_PACKAGE for name in names)


def test_no_package_on_the_phi_closure_depends_on_the_adapters() -> None:
    dependents = []
    for pyproject in [
        *REPO.glob("packages/*/pyproject.toml"),
        *REPO.glob("services/*/pyproject.toml"),
    ]:
        if pyproject.parent == ADAPTER_ROOT:
            continue
        deps = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"].get(
            "dependencies", []
        )
        if any(dep.startswith("intake-hosted-lanes") for dep in deps):
            dependents.append(str(pyproject.relative_to(REPO)))
    assert dependents == []


def test_only_the_synthetic_image_carries_the_adapters_and_bakes_the_class() -> None:
    dockerfile = (REPO / "infra" / "staging" / "Dockerfile.api").read_text(encoding="utf-8")
    assert "PYTHONPATH=/app/packages/hosted-lanes/src" in dockerfile
    assert "INTAKE_DEPLOYMENT_DATA_CLASS=synthetic" in dockerfile
    assert "synthetic patients only" in dockerfile.lower()
    compose = (REPO / "infra" / "staging" / "compose.yaml").read_text(encoding="utf-8")
    environment_lines = [line.split("#", 1)[0] for line in compose.splitlines()]
    assert not any("INTAKE_DEPLOYMENT_DATA_CLASS:" in line for line in environment_lines)
    assert not any("PYTHONPATH" in line for line in environment_lines)
    # no other image recipe in the tree puts the adapters on a path
    others = [
        path
        for path in REPO.glob("infra/**/Dockerfile*")
        if path.name != "Dockerfile.api.dockerignore"
        and path != REPO / "infra" / "staging" / "Dockerfile.api"
        and "hosted-lanes" in path.read_text(encoding="utf-8")
    ]
    assert others == []


@pytest.mark.parametrize("env", [{}, {"INTAKE_DEPLOYMENT_DATA_CLASS": "real_phi"}])
def test_a_phi_declaration_gets_no_hosted_lanes(env: dict[str, str]) -> None:
    lanes = load_hosted_lanes(env, keys=None, allowlist=load_allowlist(ALLOWLIST), root=REPO)
    assert lanes == HostedLanes.none()


def test_an_image_without_the_package_gets_no_hosted_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    real_find_spec = importlib.util.find_spec

    def absent(name: str, package: str | None = None):  # type: ignore[no-untyped-def]
        return None if name == HOSTED_PACKAGE else real_find_spec(name, package)

    monkeypatch.setattr(lanes_wiring.importlib.util, "find_spec", absent)
    lanes = load_hosted_lanes(
        {"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"},
        keys=None,
        allowlist=load_allowlist(ALLOWLIST),
        root=REPO,
    )
    assert lanes == HostedLanes.none()


def test_near_miss_the_synthetic_image_loads_the_provider_unlisted() -> None:
    lanes = load_hosted_lanes(
        {"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"},
        keys=None,
        allowlist=load_allowlist(ALLOWLIST),
        root=REPO,
    )
    info = lanes.info(ProviderId.OPENAI)
    assert info is not None and info.listed is False
    assert lanes.backends == {}  # no key store, nothing to call with


def test_every_provider_member_has_a_catalogue_row_and_dated_snapshots() -> None:
    lanes = load_hosted_lanes(
        {"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"},
        keys=None,
        allowlist=load_allowlist(ALLOWLIST),
        root=REPO,
    )
    assert set(lanes.providers) == set(ProviderId)
    for info in lanes.providers.values():
        for model in info.models:
            assert model.wire.endswith(model.version)
