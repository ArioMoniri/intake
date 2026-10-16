"""INT-443 — ElevenLabs as the synthetic host's hosted TTS, through the George route.

What is held here, each with its near miss:

- **Where the route exists.** Mounted in dev (INT-326) and on the synthetic
  deployment that declares its hosted clip lane; never in production, never
  on a PHI deployment that sets the lane name, never on a synthetic one that
  does not.
- **Where the wiring comes from.** The synthetic lane reads its key from the
  key store, its host from the allow-list row, its cache from its own
  variable; a PHI deployment never touches the key store.
- **What the route serves.** A catalogue text in the v4 profile of its
  context (the cast voice E04 on eleven_v3, D20), cached by
  ``delivery.<context>@v4``; a hit is free and never dials;
  RED is refused; a vendor failure falls back to the self-hosted lane when one
  is configured, recorded in ``X-Clip-Lane``, the cache path and the metric.
- **The app's catalogue.** The committed file loads and admits what the app
  speaks; a file a human edited into an unsafe shape is refused whole.

The vendor is ``httpx.MockTransport`` behind the real egress guard. Nothing
dials a network.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from george_harness import CountingGateway, budget, catalogue_of, router_client
from intake_api.consent_guard import dev_voice_scripted_routes
from intake_api.dev_voice import (
    CLIP_LANE_TOTAL,
    GEORGE_CLIP_PATH,
    GeorgeClipCache,
    GeorgeWiring,
    george_wiring_from_env,
)
from intake_api.dev_voice_guard import (
    APP_CATALOGUE_DEFAULT,
    ENV_APP_CATALOGUE,
    ENV_GEORGE_CLIP_DIST,
    ENV_HOSTED_TTS,
    AppCatalogueError,
    george_route_mountable,
    hosted_clip_lane_declared,
    load_app_catalogue,
    scripted_catalogue_from_env,
)
from intake_api.hosted_clip_lane import ENV_HOSTED_TTS_CACHE_DIR, hosted_clip_lane
from intake_hosted_lanes.elevenlabs import ELEVENLABS_EGRESS_ROW, ElevenLabsHostedTts
from intake_platform.egress import (
    AllowlistEntry,
    EgressAllowlist,
    EgressPolicy,
    EgressPurpose,
    load_allowlist,
)
from intake_platform.model_lanes.keys import ProviderApiKey
from protocols.dsl import clip_text_hash
from voice_clips.audio import SynthesisedSpeech
from voice_clips.delivery import CLIPGEN_VOICE_ID, DeliveryProfile, delivery_profile

REPO = Path(__file__).resolve().parents[2]
SHIPPED_ALLOWLIST = REPO / "infra" / "security" / "egress-allowlist.yaml"
APP_CATALOGUE = REPO / APP_CATALOGUE_DEFAULT
VENDOR_HOST = "tts.vendor.example"
TEST_ADDR = "203.0.113.10"
TEST_KEY = "xi-test-unit-lane-" + "k" * 24 + "WXYZ"
PCM = b"\x01\x00\x02\x00\x03\x00\x04\x00"
SCRIPTED = "Şikâyetiniz ne zaman başladı?"
SCRIPTED_TWO = "Ağrınız nereye yayılıyor?"
SYNTHETIC = {"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic", ENV_HOSTED_TTS: "elevenlabs"}


# --- where the route exists -------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "mounted"),
    [
        ({}, True),  # dev, INT-326's lane
        ({"INTAKE_ENV": "dev"}, True),
        ({"INTAKE_ENV": "staging", **SYNTHETIC}, True),
        # near misses: one fact short each
        ({"INTAKE_ENV": "staging", "INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}, False),
        ({"INTAKE_ENV": "staging", ENV_HOSTED_TTS: "elevenlabs"}, False),  # a PHI deployment
        (
            {
                "INTAKE_ENV": "staging",
                "INTAKE_DEPLOYMENT_DATA_CLASS": "real_phi",
                ENV_HOSTED_TTS: "elevenlabs",
            },
            False,
        ),
        ({"INTAKE_ENV": "staging", **SYNTHETIC, ENV_HOSTED_TTS: "ElevenLabs"}, False),
        ({"INTAKE_ENV": "prod", **SYNTHETIC}, False),
        ({"INTAKE_ENV": "production"}, False),
    ],
)
def test_the_route_is_mountable_exactly_where_it_may_be(env: dict[str, str], mounted: bool) -> None:
    assert george_route_mountable(env) is mounted


@pytest.fixture
def staging_harness(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[ApiHarness]:
    monkeypatch.setenv("INTAKE_ENV", "staging")
    for name, value in request.param.items():
        monkeypatch.setenv(name, value)
    yield from build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN)


@pytest.mark.parametrize(
    ("staging_harness", "routes"),
    [
        (SYNTHETIC, [f"POST {GEORGE_CLIP_PATH}"]),
        ({ENV_HOSTED_TTS: "elevenlabs"}, []),  # PHI: never, whatever it declares
    ],
    indirect=["staging_harness"],
)
def test_the_real_app_mounts_it_on_the_synthetic_host_only(
    staging_harness: ApiHarness, routes: list[str]
) -> None:
    assert dev_voice_scripted_routes(staging_harness.client.app) == routes  # type: ignore[arg-type]


# --- where the wiring comes from --------------------------------------------------------


def _allowlist(with_row: bool = True) -> EgressAllowlist:
    shipped = load_allowlist(SHIPPED_ALLOWLIST)
    rows = [e for e in shipped.tiers.dev if e.name != ELEVENLABS_EGRESS_ROW]
    if with_row:
        rows.append(
            AllowlistEntry(
                name=ELEVENLABS_EGRESS_ROW,
                host=VENDOR_HOST,
                port=443,
                protocol="https",
                purpose_id=EgressPurpose.HOSTED_MODEL_INFERENCE,
                purpose="hosted TTS of scripted text, synthetic only (test copy)",
                basis="no-personal-data; synthetic deployment only",
            )
        )
    return EgressAllowlist(
        version=shipped.version, tiers=shipped.tiers.model_copy(update={"dev": rows})
    )


class _Kv:
    def __init__(self) -> None:
        self.opened = 0

    def __call__(self) -> _Kv:
        self.opened += 1
        return self

    def get_kv(self, path: str) -> dict[str, Any]:
        assert path == "model-lanes/providers/elevenlabs"
        return {"api_key": TEST_KEY}


def _write_allowlist(tmp_path: Path, allowlist: EgressAllowlist) -> Path:
    path = tmp_path / "egress-allowlist.yaml"
    path.write_text(json.dumps(allowlist.model_dump(mode="json")), encoding="utf-8")
    return path


def _lane_env(tmp_path: Path, *, with_row: bool = True) -> dict[str, str]:
    return {
        **SYNTHETIC,
        "INTAKE_EGRESS_ALLOWLIST_PATH": str(_write_allowlist(tmp_path, _allowlist(with_row))),
        ENV_HOSTED_TTS_CACHE_DIR: str(tmp_path / "clips"),
    }


def test_the_synthetic_lane_is_the_vendor_behind_the_row_and_the_key(tmp_path: Path) -> None:
    kv = _Kv()
    lane = hosted_clip_lane(_lane_env(tmp_path), kv=kv, admits=bool)  # type: ignore[arg-type]
    assert lane is not None
    assert isinstance(lane.primary, ElevenLabsHostedTts)
    assert lane.primary.host == VENDOR_HOST
    assert lane.cache_dir == tmp_path / "clips"
    assert lane.fallback is None, "no self-hosted endpoint configured, no fallback"
    assert lane.primary.key().reveal() == TEST_KEY


@pytest.mark.parametrize(
    "change",
    [
        {"INTAKE_DEPLOYMENT_DATA_CLASS": "real_phi"},
        {ENV_HOSTED_TTS: ""},
        {ENV_HOSTED_TTS_CACHE_DIR: ""},
    ],
)
def test_one_fact_short_is_no_lane_and_no_key_read(tmp_path: Path, change: dict[str, str]) -> None:
    kv = _Kv()
    env = {**_lane_env(tmp_path), **change}
    assert hosted_clip_lane(env, kv=kv, admits=bool) is None  # type: ignore[arg-type]
    assert kv.opened == 0


def test_no_allow_list_row_is_no_lane(tmp_path: Path) -> None:
    # the owner's row is absent: hosted_egress_not_listed, the route answers 503
    assert hosted_clip_lane(_lane_env(tmp_path, with_row=False), kv=_Kv(), admits=bool) is None  # type: ignore[arg-type]


def test_the_fallback_needs_its_own_voice(tmp_path: Path) -> None:
    env = {**_lane_env(tmp_path), "INTAKE_TTS_ENDPOINT": "http://tts.internal.example:8080"}
    assert hosted_clip_lane(env, kv=_Kv(), admits=bool).fallback is None  # type: ignore[arg-type,union-attr]
    env["INTAKE_HOSTED_TTS_FALLBACK_VOICE"] = "freya"
    lane = hosted_clip_lane(env, kv=_Kv(), admits=bool)  # type: ignore[arg-type]
    assert lane is not None and lane.fallback is not None and lane.fallback_voice_id == "freya"


def test_the_george_wiring_on_the_synthetic_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in _lane_env(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("INTAKE_ENV", "staging")
    monkeypatch.setenv(ENV_GEORGE_CLIP_DIST, str(tmp_path / "no-dist"))
    wiring = george_wiring_from_env(kv=_Kv())  # type: ignore[arg-type]
    assert wiring is not None
    assert isinstance(wiring.cache.gateway, ElevenLabsHostedTts)
    assert wiring.catalogue.admits(json.loads(APP_CATALOGUE.read_text())["rows"][0]["text_tr"])
    # near miss: the same host as a PHI deployment builds nothing
    monkeypatch.setenv("INTAKE_DEPLOYMENT_DATA_CLASS", "real_phi")
    assert george_wiring_from_env(kv=_Kv()) is None  # type: ignore[arg-type]


# --- what the route serves --------------------------------------------------------------


class Vendor:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, content=PCM if self.status == 200 else b"")


def _hosted(vendor: Vendor, *texts: str) -> ElevenLabsHostedTts:
    return ElevenLabsHostedTts(
        host=VENDOR_HOST,
        key=lambda: ProviderApiKey(TEST_KEY),
        policy=EgressPolicy.for_tier(_allowlist(), "dev", resolver=lambda h, p: (TEST_ADDR,)),
        admits=lambda text: text in texts,
        inner=httpx.MockTransport(vendor),
    )


def _wiring(
    tmp_path: Path,
    vendor: Vendor,
    *,
    fallback: CountingGateway | None = None,
    capacity: int = 1000,
) -> GeorgeWiring:
    texts = (SCRIPTED, SCRIPTED_TWO)
    return GeorgeWiring(
        cache=GeorgeClipCache(
            gateway=_hosted(vendor, *texts),
            cache_dir=tmp_path / "clips",
            fallback=fallback,
            fallback_voice_id="freya" if fallback is not None else None,
        ),
        catalogue=catalogue_of(*texts),
        budget=budget(capacity=capacity, refill_per_s=0.001),
    )


def _count(lane: str, cache: str) -> float:
    return CLIP_LANE_TOTAL.labels(lane=lane, cache=cache)._value.get()  # type: ignore[no-any-return]


def test_a_catalogue_text_is_served_by_elevenlabs_in_its_v4_profile(tmp_path: Path) -> None:
    vendor = Vendor()
    client = router_client(_wiring(tmp_path, vendor))
    before = _count("elevenlabs", "miss")
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED})
    assert res.status_code == 200
    assert res.headers["x-clip-lane"] == "elevenlabs"
    assert res.headers["x-george-cache"] == "miss"
    assert _count("elevenlabs", "miss") == before + 1
    (request,) = vendor.requests
    body = json.loads(request.content)
    routine = delivery_profile("routine")
    assert routine.key == "delivery.routine@v4"
    assert body["model_id"] == "eleven_v3"
    assert body["voice_settings"] == routine.voice_settings.as_request()
    assert request.url.path == f"/v1/text-to-speech/{CLIPGEN_VOICE_ID}"
    assert (tmp_path / "clips" / routine.key).is_dir(), "cache keyed by profile@version"
    assert body["text"] == "[calm] " + SCRIPTED, "the routine row's tag, on the wire only"


@pytest.mark.parametrize(
    ("context", "prefix"),
    [
        ("welcome", "[warmly] "),
        ("sensitive", "[softly] [reassuring] "),
        ("acknowledgement", "[gently] "),
        ("closing", "[warmly] "),
    ],
)
def test_the_named_context_puts_its_own_tags_on_the_wire(
    tmp_path: Path, context: str, prefix: str
) -> None:
    vendor = Vendor()
    client = router_client(_wiring(tmp_path, vendor))
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED, "delivery_context": context})
    assert res.status_code == 200
    (request,) = vendor.requests
    assert json.loads(request.content)["text"] == prefix + SCRIPTED
    key = f"delivery.{context}@v4"
    assert (tmp_path / "clips" / key / clip_text_hash(SCRIPTED)).is_file()


@pytest.mark.parametrize(
    "body",
    [
        {"text_tr": "[warmly] " + SCRIPTED},  # a client's tag inside the text
        {"text_tr": "[calm] " + SCRIPTED},  # the row's own prefix, sent early
        {"text_tr": SCRIPTED, "tags": ["[warmly]"]},  # a tag field
        {"text_tr": SCRIPTED, "wire_prefix": "[warmly] "},
        {"text_tr": SCRIPTED, "voice_settings": {"stability": 0.1}},
    ],
)
def test_a_client_never_supplies_a_tag_or_a_setting(tmp_path: Path, body: dict[str, Any]) -> None:
    vendor = Vendor()
    res = router_client(_wiring(tmp_path, vendor)).post(GEORGE_CLIP_PATH, json=body)
    assert res.status_code == 422
    assert vendor.requests == []


def test_a_v2_era_clip_on_the_volume_is_never_served(tmp_path: Path) -> None:
    # a George clip baked under the INT-424 table, at the address v2 used
    stale = tmp_path / "clips" / "delivery.routine@v2" / clip_text_hash(SCRIPTED)
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"george-v2-era")
    vendor = Vendor()
    res = router_client(_wiring(tmp_path, vendor)).post(
        GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED}
    )
    assert res.status_code == 200 and res.headers["x-george-cache"] == "miss"
    assert res.content != b"george-v2-era" and len(vendor.requests) == 1
    assert (tmp_path / "clips" / "delivery.routine@v4" / clip_text_hash(SCRIPTED)).is_file()


def test_a_v4_clip_on_the_volume_is_served_without_a_dial(tmp_path: Path) -> None:
    # near miss of the v2 case: the same text at the v4 address is a hit
    baked = tmp_path / "clips" / "delivery.routine@v4" / clip_text_hash(SCRIPTED)
    baked.parent.mkdir(parents=True)
    baked.write_bytes(b"e04-v4")
    vendor = Vendor()
    res = router_client(_wiring(tmp_path, vendor)).post(
        GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED}
    )
    assert res.status_code == 200 and res.headers["x-george-cache"] == "hit"
    assert res.content == b"e04-v4" and vendor.requests == []
    assert os.listdir(tmp_path / "clips") == ["delivery.routine@v4"]


def test_a_hit_dials_nothing_and_costs_nothing(tmp_path: Path) -> None:
    vendor = Vendor()
    client = router_client(_wiring(tmp_path, vendor, capacity=1))
    assert client.post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED}).status_code == 200
    for _ in range(3):  # the bucket is empty, and hits still serve
        hit = client.post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED})
        assert hit.status_code == 200 and hit.headers["x-george-cache"] == "hit"
    assert len(vendor.requests) == 1
    # near miss: a second, uncached text is a miss and the bucket is empty
    assert client.post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED_TWO}).status_code == 429
    assert len(vendor.requests) == 1


def test_red_is_never_fetched(tmp_path: Path) -> None:
    vendor = Vendor()
    client = router_client(_wiring(tmp_path, vendor))
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED, "delivery_context": "red"})
    assert res.status_code == 422 and res.json() == {"error": "red_not_on_demand"}
    assert vendor.requests == []


def test_a_vendor_failure_falls_back_to_self_hosted_and_says_so(tmp_path: Path) -> None:
    vendor = Vendor(status=503)
    fallback = CountingGateway()
    client = router_client(_wiring(tmp_path, vendor, fallback=fallback))
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED})
    assert res.status_code == 200
    assert res.headers["x-clip-lane"] == "self_hosted"
    assert fallback.calls == 1
    routine = delivery_profile("routine")
    assert (tmp_path / "clips" / "self_hosted" / routine.key).is_dir()
    assert not (tmp_path / "clips" / routine.key).exists(), "the vendor's path stays empty"
    # the vendor is tried again on the next request; once it answers, it serves
    vendor.status = 200
    again = client.post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED})
    assert again.headers["x-clip-lane"] == "elevenlabs" and len(vendor.requests) == 2


def test_without_a_fallback_a_vendor_failure_is_502(tmp_path: Path) -> None:
    client = router_client(_wiring(tmp_path, Vendor(status=503)))
    res = client.post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED})
    assert res.status_code == 502 and res.json() == {"error": "george_unavailable"}


class _Refusing:
    def synthesise(
        self, *, text_tr: str, voice_id: str, profile: DeliveryProfile
    ) -> SynthesisedSpeech:
        from intake_hosted_lanes.elevenlabs import HostedTtsRefused

        raise HostedTtsRefused("hosted_tts_not_in_catalogue")


def test_a_refusal_never_falls_back(tmp_path: Path) -> None:
    fallback = CountingGateway()
    wiring = GeorgeWiring(
        cache=GeorgeClipCache(
            gateway=_Refusing(),  # type: ignore[arg-type]
            cache_dir=tmp_path / "clips",
            fallback=fallback,
            fallback_voice_id="freya",
        ),
        catalogue=catalogue_of(SCRIPTED),
        budget=budget(),
    )
    res = router_client(wiring).post(GEORGE_CLIP_PATH, json={"text_tr": SCRIPTED})
    assert res.status_code == 502
    assert fallback.calls == 0


# --- the app's catalogue ----------------------------------------------------------------


def test_the_committed_app_catalogue_loads_and_is_never_red() -> None:
    rows = load_app_catalogue(APP_CATALOGUE)
    assert len(rows) > 50
    assert {row.delivery_context for row in rows} <= {"routine", "instrument"}


def test_the_merged_catalogue_admits_the_app_texts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_GEORGE_CLIP_DIST, str(tmp_path / "no-dist"))
    catalogue = scripted_catalogue_from_env({ENV_APP_CATALOGUE: str(APP_CATALOGUE)})
    assert catalogue is not None
    first = json.loads(APP_CATALOGUE.read_text(encoding="utf-8"))["rows"][0]["text_tr"]
    assert catalogue.admits(first)
    assert not catalogue.admits("Bu cümleyi benim için seslendirin lütfen")


def _doc(**row: str) -> dict[str, Any]:
    base = {"subject": "question.x", "text_tr": SCRIPTED, "delivery_context": "routine"}
    return {"version": 1, "locale": "tr", "source": "test", "rows": [{**base, **row}]}


@pytest.mark.parametrize(
    "doc",
    [
        _doc(text_tr="Ağrınız 5 gündür mü?"),  # a numeral
        _doc(text_tr="Durun [whispers] lütfen"),  # an audio tag
        _doc(delivery_context="red"),
        _doc(delivery_context="shouting"),
        {**_doc(), "extra": 1},
        {**_doc(), "locale": "en"},
        {**_doc(), "rows": _doc()["rows"] * 2},  # a text listed twice
    ],
)
def test_an_unsafe_app_catalogue_is_refused_whole(tmp_path: Path, doc: dict[str, Any]) -> None:
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(AppCatalogueError):
        load_app_catalogue(path)


def test_a_safe_app_catalogue_loads(tmp_path: Path) -> None:
    # near miss of the refusals above
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(_doc()), encoding="utf-8")
    assert [row.text_tr for row in load_app_catalogue(path)] == [SCRIPTED]


def test_the_lane_is_declared_only_by_the_exact_pair() -> None:
    assert hosted_clip_lane_declared(SYNTHETIC)
    assert not hosted_clip_lane_declared({**SYNTHETIC, "INTAKE_DEPLOYMENT_DATA_CLASS": "Synthetic"})
