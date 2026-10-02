"""Shared fixtures for the dev George clip route suites (INT-326).

A uniquely named module, like ``api_harness.py``, so both George suites import
it directly. Nothing here dials a network: the vendor is a counting fake, the
per-principal budget runs on fakeredis with an injected clock (docs/TDD.md
rule 6), and the scripted catalogue is either spelled by the test or read from
a bundle the REAL compiler wrote from the committed synthetic pack tree
(``tests/fixtures/protocols/compile``, the INT-041/INT-060 fixtures) — the
route is proven against the compiler's own manifest format, never a
re-derivation of it.
"""

from __future__ import annotations

from pathlib import Path

import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from intake_api.auth import require_principal
from intake_api.dev_fixture import PATIENT_ACCOUNT, DevAccount
from intake_api.dev_voice import GeorgeClipCache, GeorgeWiring, router
from intake_api.dev_voice_guard import ScriptedCatalogue
from intake_platform.security.rate_limit import TokenBucketLimiter
from protocols.bindings import load_opt
from protocols.cli import load_registry
from protocols.compile import compile_bundle, load_life_threat_set, write_bundle
from protocols.dsl import clip_text_hash
from voice_clips.audio import SynthesisedSpeech
from voice_clips.cache import CompiledClipManifest
from voice_clips.delivery import DeliveryProfile

REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPILE_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "protocols" / "compile"
_COMMITTED_OPT = REPO_ROOT / "packages" / "protocols" / "openehr" / "previsit_intake.v1.opt"
#: The synthetic pack the INT-060 clip-cache suite compiles (tests/voice/conftest.py).
FIXTURE_PACK_ID = "base.derlenebilir"


class CountingGateway:
    """Counts synthesise calls: ``calls == 0`` is the proof a refusal never
    reached the vendor."""

    def __init__(self) -> None:
        self.calls = 0
        self.seen: list[str] = []
        #: the delivery profile key of every call (INT-415)
        self.profiles: list[str] = []

    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
        self.calls += 1
        self.seen.append(text_tr)
        self.profiles.append(profile.key)
        return SynthesisedSpeech(
            pcm_s16le=b"\x01\x00\x02\x00\x03\x00", sample_rate_hz=24000, channels=1
        )


class FakeClock:
    """Deterministic clock for the token bucket (never the wall clock)."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def budget(
    *,
    capacity: int = 1000,
    refill_per_s: float = 1.0,
    clock: FakeClock | None = None,
    redis_client: fakeredis.FakeStrictRedis | None = None,
) -> TokenBucketLimiter:
    """A per-principal budget on fakeredis. The default is generous so suites
    that are not about the budget never trip it."""
    return TokenBucketLimiter(
        redis_client=redis_client if redis_client is not None else fakeredis.FakeStrictRedis(),
        capacity=capacity,
        refill_per_s=refill_per_s,
        now_fn=clock if clock is not None else FakeClock(),
        key_prefix="rl:george-test",
    )


def catalogue_of(*texts: str) -> ScriptedCatalogue:
    """A catalogue admitting exactly these scripted texts, keyed the way the
    compiled manifest keys them (``clip_text_hash``)."""
    return ScriptedCatalogue(text_hashes=frozenset(clip_text_hash(text) for text in texts))


def george_wiring_for(
    gateway: object,
    cache_dir: Path,
    *,
    catalogue: ScriptedCatalogue,
    limiter: TokenBucketLimiter | None = None,
) -> GeorgeWiring:
    return GeorgeWiring(
        cache=GeorgeClipCache(gateway=gateway, cache_dir=cache_dir),  # type: ignore[arg-type]
        catalogue=catalogue,
        budget=limiter if limiter is not None else budget(),
    )


def router_client(wiring: GeorgeWiring | None, account: DevAccount = PATIENT_ACCOUNT) -> TestClient:
    """The George router alone, with the principal resolved to ``account`` —
    for suites about what happens AFTER authentication. The authentication
    door itself is exercised through the real app (``api_harness``)."""
    app = FastAPI()
    app.state.george = wiring
    app.include_router(router)
    app.dependency_overrides[require_principal] = lambda: account
    return TestClient(app, raise_server_exceptions=False)


def compiled_dist(root: Path, *, voice: str) -> Path:
    """Compile the committed synthetic pack for ``voice`` and write the bundle
    exactly as ``make protocols-compile`` does; returns the dist root."""
    bundle = compile_bundle(
        pack_id=FIXTURE_PACK_ID,
        registry=load_registry(_COMPILE_FIXTURES / "tree"),
        life_threat=load_life_threat_set(_COMPILE_FIXTURES / "life_threat_signed.yaml"),
        template=load_opt(_COMMITTED_OPT),
        voice=voice,
    )
    dist = root / "dist"
    write_bundle(bundle, dist)
    return dist


def scripted_texts(dist: Path) -> list[str]:
    """Every ``text_tr`` the compiled manifests under ``dist`` carry, read with
    the clip cache's own manifest model."""
    texts: list[str] = []
    for path in sorted(dist.glob("*/clips.*.json")):
        manifest = CompiledClipManifest.model_validate_json(path.read_text(encoding="utf-8"))
        texts.extend(row.text_tr for row in manifest.entries)
    return texts
