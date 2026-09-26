"""INT-326 — the dev George clip route is not an open paid proxy (audit F05).

Before this issue ``POST /dev/voice/george-clip`` synthesised ANY <=600-char
text through the ElevenLabs key for ANY caller: no principal (the consent-guard
declaration is a marker, not a check), "scripted text only" enforced only by
the mobile client, no budget, and nothing stopping it in production. On a
public host that is cost abuse plus arbitrary — possibly PHI — text reaching a
US vendor, against invariant 19.

Four doors, each proven here with the vendor a counting fake that must stay at
zero calls whenever a door refuses (never a live dial — ADR-028, CLAUDE.md
"Never call paid/live APIs in tests"):

(a) an authenticated patient principal — through the REAL app and the REAL
    dev-bearer door (``api_harness``), not a stubbed dependency;
(b) the server-side catalogue — ``text_tr`` is admitted only when
    ``clip_text_hash(text_tr)`` is a row of a compiled clip manifest, proven
    against a bundle the real compiler wrote, with near-miss negative controls;
(c) a per-principal token bucket (the INT-012 Redis limiter) — refusals cost
    budget, principals do not share one, an unreachable store fails closed;
(d) production — the route is not mounted and no wiring is built, whatever
    the dev flags say.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path

import fakeredis
import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from george_harness import (
    CountingGateway,
    FakeClock,
    budget,
    catalogue_of,
    compiled_dist,
    george_wiring_for,
    router_client,
    scripted_texts,
)
from intake_api.consent_guard import dev_voice_scripted_routes
from intake_api.dev_fixture import DEV_TENANT_ID, PATIENT_ACCOUNT, DevAccount
from intake_api.dev_voice import (
    ENV_DEV_GEORGE,
    ENV_GEORGE_CACHE_DIR,
    GEORGE_CLIP_PATH,
    george_wiring_from_env,
)
from intake_api.dev_voice_guard import (
    ENV_GEORGE_CLIP_DIST,
    intake_env_is_prod,
    load_scripted_catalogue,
)
from protocols.dsl import clip_text_hash
from voice_clips import ManifestTamperedError
from voice_clips.gateway import ENV_ELEVENLABS_BASE, ENV_ELEVENLABS_KEY

#: The synthetic voice the INT-060 clip suite compiles for (tests/voice/conftest.py).
VOICE = "sentetik-ses"

# Scripted-shaped Turkish with no numeral (invariant 22), standing in for
# catalogue rows where a test spells its own catalogue.
_SCRIPTED = "Şikayetiniz nedir?"
_SCRIPTED_TWO = "Ne zamandır sürüyor?"
_SCRIPTED_THREE = "Başka bir şey eklemek ister misiniz?"
#: What an abuser would send: free text that is no compiled row.
_FREE_TEXT = "Bu cümleyi benim için seslendirin lütfen"

_SECRET = "sk-do-not-log-me"  # noqa: S105 - a fake key for the env fixture


def _patient_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {PATIENT_TOKEN}"}


def _mount(harness: ApiHarness, wiring: object) -> None:
    """Hand the real app a George wiring (the harness builds it without one)."""
    harness.client.app.state.george = wiring  # type: ignore[attr-defined]


def _george_routes(harness: ApiHarness) -> list[str]:
    """The consent scan's own walker, which descends into included routers (a
    flat ``app.routes`` scan sees none of them and would pass vacuously)."""
    return dev_voice_scripted_routes(harness.client.app)  # type: ignore[arg-type]


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    return compiled_dist(tmp_path, voice=VOICE)


# (a) an authenticated principal ------------------------------------------------


def test_no_credentials_is_401_and_the_vendor_is_never_dialled(
    harness: ApiHarness, tmp_path: Path
) -> None:
    gateway = CountingGateway()
    _mount(harness, george_wiring_for(gateway, tmp_path / "c", catalogue=catalogue_of(_SCRIPTED)))
    res = harness.client.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED})
    assert res.status_code == 401
    assert res.json()["error"] == "unauthorized"
    assert gateway.calls == 0


def test_a_wrong_bearer_is_401_and_the_vendor_is_never_dialled(
    harness: ApiHarness, tmp_path: Path
) -> None:
    gateway = CountingGateway()
    _mount(harness, george_wiring_for(gateway, tmp_path / "c", catalogue=catalogue_of(_SCRIPTED)))
    res = harness.client.post(
        GEORGE_CLIP_PATH,
        json={"text_tr": _SCRIPTED},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert res.status_code == 401
    assert gateway.calls == 0


def test_authentication_is_checked_before_the_lane_reports_its_configuration(
    harness: ApiHarness,
) -> None:
    # an anonymous caller learns nothing about the lane — not even that it is off
    _mount(harness, None)
    res = harness.client.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED})
    assert res.status_code == 401


def test_an_authenticated_patient_is_served(harness: ApiHarness, tmp_path: Path) -> None:
    # positive control for the door: the same request WITH the patient token
    gateway = CountingGateway()
    _mount(harness, george_wiring_for(gateway, tmp_path / "c", catalogue=catalogue_of(_SCRIPTED)))
    res = harness.client.post(
        GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED}, headers=_patient_headers()
    )
    assert res.status_code == 200
    assert res.content[:4] == b"RIFF"
    assert gateway.calls == 1


def test_a_clinic_admin_principal_is_403(harness: ApiHarness, tmp_path: Path) -> None:
    # the caller is the patient's own device; a console token has no business here
    gateway = CountingGateway()
    _mount(harness, george_wiring_for(gateway, tmp_path / "c", catalogue=catalogue_of(_SCRIPTED)))
    res = harness.client.post(
        GEORGE_CLIP_PATH,
        json={"text_tr": _SCRIPTED},
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
    )
    assert res.status_code == 403
    assert gateway.calls == 0


# (b) the compiled catalogue is the allow-list ---------------------------------


def test_the_catalogue_is_every_row_of_the_compiled_manifest(dist: Path) -> None:
    texts = scripted_texts(dist)
    assert texts, "the synthetic pack must compile clippable lines for this proof to mean anything"
    catalogue = load_scripted_catalogue(dist)
    assert catalogue.text_hashes == frozenset(clip_text_hash(text) for text in texts)
    assert all(catalogue.admits(text) for text in texts)


def test_compiled_text_is_served_and_reaches_the_vendor_verbatim(
    dist: Path, tmp_path: Path
) -> None:
    gateway = CountingGateway()
    text = scripted_texts(dist)[0]
    client = router_client(
        george_wiring_for(gateway, tmp_path / "c", catalogue=load_scripted_catalogue(dist))
    )
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": text})
    assert res.status_code == 200
    assert gateway.seen == [text]  # invariant 10: the compiled text, byte for byte


def test_free_text_is_422_never_echoed_and_never_reaches_the_vendor(
    dist: Path, tmp_path: Path
) -> None:
    gateway = CountingGateway()
    cache_dir = tmp_path / "c"
    client = router_client(
        george_wiring_for(gateway, cache_dir, catalogue=load_scripted_catalogue(dist))
    )
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": _FREE_TEXT})
    assert res.status_code == 422
    assert res.json() == {"error": "not_in_catalogue"}
    assert _FREE_TEXT not in res.text  # invariant 6: a refusal never carries the text
    assert gateway.calls == 0
    assert not cache_dir.exists()


@pytest.mark.parametrize(
    "near_miss",
    [
        pytest.param(lambda text: text + " ", id="trailing-space"),
        pytest.param(lambda text: text[:-1], id="last-character-dropped"),
        pytest.param(lambda text: text.upper(), id="case-changed"),
        pytest.param(lambda text: text + " Ve şunu da söyleyin", id="suffix-appended"),
        pytest.param(lambda text: "Lütfen dinleyin. " + text, id="prefix-prepended"),
    ],
)
def test_a_near_miss_of_a_compiled_row_is_refused(
    dist: Path, tmp_path: Path, near_miss: object
) -> None:
    # the negative control: one character away from an admitted row is not admitted
    text = scripted_texts(dist)[0]
    candidate = near_miss(text)  # type: ignore[operator]
    assert candidate != text
    gateway = CountingGateway()
    client = router_client(
        george_wiring_for(gateway, tmp_path / "c", catalogue=load_scripted_catalogue(dist))
    )
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": candidate})
    assert res.status_code == 422
    assert res.json()["error"] == "not_in_catalogue"
    assert gateway.calls == 0


def test_the_numeral_refusal_still_answers_first(tmp_path: Path) -> None:
    # invariant 22 keeps its own, more specific refusal (the pre-INT-326 contract)
    gateway = CountingGateway()
    client = router_client(george_wiring_for(gateway, tmp_path / "c", catalogue=catalogue_of()))
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": "2 gün önce başladı."})
    assert res.status_code == 422
    assert res.json()["error"] == "not_speakable"
    assert gateway.calls == 0


# (c) a per-principal budget ------------------------------------------------------


def test_an_exhausted_budget_is_429_with_retry_after_and_no_vendor_call(tmp_path: Path) -> None:
    clock = FakeClock()
    gateway = CountingGateway()
    client = router_client(
        george_wiring_for(
            gateway,
            tmp_path / "c",
            catalogue=catalogue_of(_SCRIPTED, _SCRIPTED_TWO, _SCRIPTED_THREE),
            limiter=budget(capacity=2, refill_per_s=0.1, clock=clock),
        )
    )
    assert client.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED}).status_code == 200
    assert client.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED_TWO}).status_code == 200
    third = client.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED_THREE})
    assert third.status_code == 429
    assert third.json() == {"error": "george_rate_limited"}
    assert int(third.headers["retry-after"]) >= 1
    assert gateway.calls == 2  # the refused, uncached text never reached the vendor

    clock.now += 10.0  # 0.1 token/s x 10 s = one token back
    assert client.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED_THREE}).status_code == 200
    assert gateway.calls == 3


def test_refused_requests_spend_the_budget_too(tmp_path: Path) -> None:
    # hammering off-catalogue text is not free: the budget is charged at the door
    gateway = CountingGateway()
    client = router_client(
        george_wiring_for(
            gateway,
            tmp_path / "c",
            catalogue=catalogue_of(_SCRIPTED),
            limiter=budget(capacity=2, refill_per_s=0.001),
        )
    )
    assert client.post(GEORGE_CLIP_PATH, json={"text_tr": _FREE_TEXT}).status_code == 422
    assert client.post(GEORGE_CLIP_PATH, json={"text_tr": _FREE_TEXT}).status_code == 422
    assert client.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED}).status_code == 429
    assert gateway.calls == 0


def test_principals_do_not_share_a_budget(tmp_path: Path) -> None:
    shared = budget(capacity=1, refill_per_s=0.001)
    gateway = CountingGateway()
    wiring = george_wiring_for(
        gateway, tmp_path / "c", catalogue=catalogue_of(_SCRIPTED), limiter=shared
    )
    other = DevAccount(
        account_id="another-patient",
        role="patient",
        tenant_id=DEV_TENANT_ID,
        patient_id=uuid.uuid4(),
    )
    first = router_client(wiring, PATIENT_ACCOUNT)
    second = router_client(wiring, other)
    assert first.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED}).status_code == 200
    assert first.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED}).status_code == 429
    assert second.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED}).status_code == 200


def test_an_unreachable_budget_store_fails_closed_503(tmp_path: Path) -> None:
    server = fakeredis.FakeServer()
    server.connected = False
    gateway = CountingGateway()
    client = router_client(
        george_wiring_for(
            gateway,
            tmp_path / "c",
            catalogue=catalogue_of(_SCRIPTED),
            limiter=budget(redis_client=fakeredis.FakeStrictRedis(server=server)),
        )
    )
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED})
    assert res.status_code == 503
    assert res.json() == {"error": "george_budget_unavailable"}
    assert gateway.calls == 0


# (d) absent in production ---------------------------------------------------------


@pytest.fixture(params=["prod", "production", "PROD"])
def prod_harness(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ApiHarness]:
    monkeypatch.setenv("INTAKE_ENV", request.param)
    yield from build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN)


def test_prod_does_not_mount_the_route_even_with_a_wiring(
    prod_harness: ApiHarness, tmp_path: Path
) -> None:
    gateway = CountingGateway()
    _mount(
        prod_harness,
        george_wiring_for(gateway, tmp_path / "c", catalogue=catalogue_of(_SCRIPTED)),
    )
    assert _george_routes(prod_harness) == []
    res = prod_harness.client.post(
        GEORGE_CLIP_PATH, json={"text_tr": _SCRIPTED}, headers=_patient_headers()
    )
    assert res.status_code == 404
    assert gateway.calls == 0


def test_dev_mounts_the_route(harness: ApiHarness) -> None:
    # positive control for the prod test above: same app factory, dev env
    assert _george_routes(harness) == [f"POST {GEORGE_CLIP_PATH}"]


@pytest.mark.parametrize(
    ("value", "is_prod"),
    [("prod", True), ("production", True), ("PROD", True), ("dev", False), ("staging", False)],
)
def test_prod_detection_follows_the_platform_convention(
    monkeypatch: pytest.MonkeyPatch, value: str, is_prod: bool
) -> None:
    monkeypatch.setenv("INTAKE_ENV", value)
    assert intake_env_is_prod() is is_prod


def test_unset_intake_env_is_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    assert intake_env_is_prod() is False


def _arm_every_flag(monkeypatch: pytest.MonkeyPatch, dist_root: Path, cache_dir: Path) -> None:
    monkeypatch.setenv(ENV_DEV_GEORGE, "explicit-yes")
    monkeypatch.setenv(ENV_ELEVENLABS_BASE, "https://tts.example.invalid")
    monkeypatch.setenv(ENV_ELEVENLABS_KEY, _SECRET)
    monkeypatch.setenv(ENV_GEORGE_CLIP_DIST, str(dist_root))
    monkeypatch.setenv(ENV_GEORGE_CACHE_DIR, str(cache_dir))


def test_prod_builds_no_wiring_whatever_the_flags_say(
    monkeypatch: pytest.MonkeyPatch, dist: Path, tmp_path: Path
) -> None:
    _arm_every_flag(monkeypatch, dist, tmp_path / "c")
    monkeypatch.setenv("INTAKE_ENV", "prod")
    assert george_wiring_from_env() is None


def test_dev_with_every_flag_and_a_compiled_catalogue_builds_the_wiring(
    monkeypatch: pytest.MonkeyPatch, dist: Path, tmp_path: Path
) -> None:
    # positive control for the prod refusal: the same env, minus prod
    _arm_every_flag(monkeypatch, dist, tmp_path / "c")
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    wiring = george_wiring_from_env()
    assert wiring is not None
    assert wiring.catalogue == load_scripted_catalogue(dist)


def test_no_compiled_catalogue_leaves_the_lane_unconfigured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "dist"
    empty.mkdir()
    _arm_every_flag(monkeypatch, empty, tmp_path / "c")
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    assert george_wiring_from_env() is None


def test_a_tampered_manifest_leaves_the_lane_unconfigured(
    monkeypatch: pytest.MonkeyPatch, dist: Path, tmp_path: Path
) -> None:
    # a row whose text no longer hashes to its key is a pack edited after
    # compile — the catalogue is refused whole rather than read around
    manifest = next(dist.glob("*/clips.*.json"))
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    doc["entries"][0]["text_tr"] = _FREE_TEXT
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ManifestTamperedError):
        load_scripted_catalogue(dist)
    _arm_every_flag(monkeypatch, dist, tmp_path / "c")
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    assert george_wiring_from_env() is None
