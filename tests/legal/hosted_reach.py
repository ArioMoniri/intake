"""Scanners for the INT-529 vendor tripwire: how the synthetic host could reach
a hosted vendor with a patient's data, read from the tree rather than assumed.

Each scanner returns a set of ``(file, what)`` pairs or module names. The
tripwire (``test_synthetic_vendor_tripwire.py``) holds each set exactly to the
one the texts were verified against. A new member is a new path to verify
before the texts may keep saying that no outside company receives the data.

The paths:
- **Compose.** The services, the networks that lead off the host, and the
  api's command.
- **Dispatchers.** The modules that import ``model_lanes.dispatch``.
- **Hosted-backend call sites.** These are calls of ``chat_json``,
  ``transcribe`` or ``speech``, or those names as strings (a ``getattr``),
  reads of ``.hosted.backends``, and the names ``HostedBackend`` and
  ``HostedLanes``. The scan covers every first-party tree except the adapters
  themselves and the model-lanes package that defines the seam.
- **Routed references.** These are string constants naming
  ``intake_hosted_lanes`` or ``intake_voice_runtime`` (an ``importlib``
  literal), outside those packages themselves.
- **The API's reach.** This is the first-party import closure of
  ``intake_api``, transitive, checked for any gateway module.

Helpers only; no test lives here (the legal_harness precedent).
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping
from functools import cache, lru_cache
from pathlib import Path
from types import MappingProxyType

import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "infra" / "staging" / "compose.yaml"
DOCKERFILE = REPO / "infra" / "staging" / "Dockerfile.api"

_ADAPTERS = "packages/hosted-lanes/"
_LANES_PACKAGE = "packages/intake_platform/src/intake_platform/model_lanes/"
_VOICE_RUNTIME = "services/voice-runtime/"
BACKEND_METHODS = frozenset({"chat_json", "transcribe", "speech"})
HOSTED_NAMES = frozenset({"HostedBackend", "HostedLanes"})
ROUTED_PREFIXES = ("intake_hosted_lanes", "intake_voice_runtime")
_DISPATCH_MODULE = "intake_platform.model_lanes.dispatch"
_LANES_MODULE = "intake_platform.model_lanes"


# --- the tree -------------------------------------------------------------------------


def _src_roots() -> list[Path]:
    return sorted([*REPO.glob("packages/*/src"), *REPO.glob("services/*/src")])


@lru_cache(maxsize=1)
def python_sources() -> Mapping[str, str]:
    """``{repo-relative path: source}`` for every first-party Python file that
    can ship: the package and service trees, scripts and infra. Read once per
    session; callers that change a file work on a copy."""
    paths: list[Path] = [p for root in _src_roots() for p in root.rglob("*.py")]
    paths += [*(REPO / "scripts").rglob("*.py"), *(REPO / "infra").rglob("*.py")]
    return MappingProxyType(
        {p.relative_to(REPO).as_posix(): p.read_text(encoding="utf-8") for p in sorted(paths)}
    )


@cache
def _parse(source: str) -> ast.Module:
    """One parse per distinct source; the scanners only read the tree."""
    return ast.parse(source)


def _imports(tree: ast.AST) -> list[tuple[str, tuple[str, ...], int]]:
    """``(module, names, level)`` for every import statement."""
    found: list[tuple[str, tuple[str, ...], int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.append((node.module or "", tuple(a.name for a in node.names), node.level))
        elif isinstance(node, ast.Import):
            found.extend((alias.name, (), 0) for alias in node.names)
    return found


# --- compose ---------------------------------------------------------------------------


def compose_facts() -> dict[str, object]:
    """The services, who sits on the two networks that lead off the host, and
    the api's command (none in compose, so the image's own CMD runs)."""
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services: dict[str, dict[str, object]] = compose["services"]

    def on(network: str) -> frozenset[str]:
        return frozenset(
            name for name, spec in services.items() if network in (spec.get("networks") or [])
        )

    api = services.get("api", {})
    cmd = [
        line
        for line in DOCKERFILE.read_text(encoding="utf-8").splitlines()
        if line.startswith("CMD")
    ]
    return {
        "services": frozenset(services),
        "outbound": on("outbound"),
        "vendor": on("vendor"),
        "api_command": (api.get("command"), api.get("entrypoint"), cmd[-1] if cmd else None),
    }


# --- dispatchers, call sites, references ----------------------------------------------


def dispatchers(sources: Mapping[str, str]) -> frozenset[str]:
    out: set[str] = set()
    for path, source in sources.items():
        if path.startswith(_LANES_PACKAGE):
            continue
        for module, names, _ in _imports(_parse(source)):
            if module == _DISPATCH_MODULE or (module == _LANES_MODULE and "dispatch" in names):
                out.add(path)
    return frozenset(out)


def hosted_call_sites(sources: Mapping[str, str]) -> frozenset[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path, source in sources.items():
        if path.startswith((_ADAPTERS, _LANES_PACKAGE)):
            continue
        for node in ast.walk(_parse(source)):
            if isinstance(node, ast.Attribute) and node.attr in BACKEND_METHODS:
                found.add((path, node.attr))
            elif isinstance(node, ast.Constant) and node.value in BACKEND_METHODS:
                found.add((path, f"{node.value} (string)"))
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "backends"
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "hosted"
            ):
                found.add((path, "hosted.backends"))
            if isinstance(node, ast.Name) and node.id in HOSTED_NAMES:
                found.add((path, node.id))
            if isinstance(node, ast.alias) and node.name in HOSTED_NAMES:
                found.add((path, node.name))
    return frozenset(found)


def routed_references(sources: Mapping[str, str]) -> frozenset[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path, source in sources.items():
        if path.startswith((_ADAPTERS, _VOICE_RUNTIME)):
            continue
        for node in ast.walk(_parse(source)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith(ROUTED_PREFIXES):
                    found.add((path, node.value))
    return frozenset(found)


# --- the API's import closure -----------------------------------------------------------


def _module_name(relative: str) -> str:
    inside = Path(relative.split("/src/", 1)[1]).with_suffix("")
    parts = inside.parts[:-1] if inside.name == "__init__" else inside.parts
    return ".".join(parts)


def import_graph(sources: Mapping[str, str]) -> dict[str, frozenset[str]]:
    """First-party module → the first-party modules it imports (parents included)."""
    modules = {
        _module_name(path): path for path in sources if "/src/" in path and path.endswith(".py")
    }
    graph: dict[str, frozenset[str]] = {}
    for module, path in modules.items():
        package = module if path.endswith("__init__.py") else module.rpartition(".")[0]
        targets: set[str] = set()
        for name, names, level in _imports(_parse(sources[path])):
            if level:
                base_parts = package.split(".")[: len(package.split(".")) - (level - 1)]
                name = ".".join([*base_parts, name] if name else base_parts)
            for candidate in (name, *(f"{name}.{n}" for n in names)):
                parts = candidate.split(".")
                targets.update(
                    ".".join(parts[:i])
                    for i in range(1, len(parts) + 1)
                    if ".".join(parts[:i]) in modules
                )
        graph[module] = frozenset(targets - {module})
    return graph


def closure(graph: Mapping[str, Iterable[str]], roots: Iterable[str]) -> frozenset[str]:
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        module = stack.pop()
        if module in seen:
            continue
        seen.add(module)
        stack.extend(graph.get(module, ()))
    return frozenset(seen)


def api_reach(graph: Mapping[str, Iterable[str]], gateways: frozenset[str]) -> frozenset[str]:
    """Gateway modules in the transitive first-party import closure of
    ``intake_api``. A gateway is a dispatcher, anything under
    ``intake_voice_runtime`` and anything under ``intake_hosted_lanes``."""
    reached = closure(graph, [m for m in graph if m == "intake_api" or m.startswith("intake_api.")])
    return frozenset(m for m in reached if m in gateways or m.startswith(ROUTED_PREFIXES))


def gateway_modules(dispatcher_paths: Iterable[str]) -> frozenset[str]:
    return frozenset(_module_name(path) for path in dispatcher_paths)
