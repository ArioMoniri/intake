"""Load a ``scripts/dev/record_*_fixture.py`` recorder as a module (INT-565).

The fixture-parity tests call a recorder's ``build_payload`` and compare it
with the committed fixture, so a fixture that is not the route's own builder
fails the Python lane. The recorders resolve paths from the repository root,
so callers ``chdir`` there first.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[2]


def recorder(name: str) -> ModuleType:
    path = REPO / "scripts" / "dev" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
