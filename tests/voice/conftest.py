"""Shared fixtures for the INT-060 clip-cache suite.

The compiled bundle comes from the same committed synthetic pack tree the
INT-041 compiler suite uses (``tests/fixtures/protocols/compile``): the clip
cache is built *from* a compiled manifest, so re-deriving a manifest here
would be testing a second implementation instead of the one that ships.
Everything is synthetic (files/04 §7).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from protocols.bindings import OperationalTemplate, load_opt
from protocols.cli import load_registry
from protocols.compile import CompiledBundle, LifeThreatSet, compile_bundle, load_life_threat_set
from protocols.loader import PackRegistry
from protocols.locale_text import DEFAULT_LOCALE

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "protocols" / "compile"
SIGNED_LIFE_THREAT = FIXTURES / "life_threat_signed.yaml"
PACK_TREE = FIXTURES / "tree"
REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_OPT = REPO_ROOT / "packages" / "protocols" / "openehr" / "previsit_intake.v1.opt"

PACK_ID = "base.derlenebilir"
VOICE = "sentetik-ses"
#: The clip cache keys on (locale, voice) since INT-297. Taken from the registry
#: rather than spelled again, so the fixtures cannot drift from what compiles.
LOCALE = DEFAULT_LOCALE


@pytest.fixture
def registry() -> PackRegistry:
    return load_registry(PACK_TREE)


@pytest.fixture
def template() -> OperationalTemplate:
    return load_opt(COMMITTED_OPT)


@pytest.fixture
def life_threat() -> LifeThreatSet:
    return load_life_threat_set(SIGNED_LIFE_THREAT)


@pytest.fixture
def bundle(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> CompiledBundle:
    return compile_bundle(
        pack_id=PACK_ID,
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
