"""INT-443 — the hosted ElevenLabs TTS lane, against a recorded vendor.

The adapter speaks to ``httpx.MockTransport`` behind the REAL egress guard
(a fake resolver answers with a documentation address), so the allow-list
decides every call exactly as it does on the host. CI never reaches the
vendor. The vendor host here is a reserved ``.example`` name on a test copy
of the allow-list: the adapter reads its host off the row, so nothing needs
the real hostname (``scripts/ci/assert_no_vendor_calls.sh`` scans tests).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from intake_hosted_lanes.clip_lane import hosted_clip_tts_from_env
from intake_hosted_lanes.elevenlabs import (
    ELEVENLABS_EGRESS_ROW,
    ElevenLabsHostedTts,
    HostedTtsRefused,
    HostedTtsUnavailable,
    elevenlabs_row,
)
from intake_hosted_lanes.plugin import HostedLanesRefused
from intake_platform.egress import (
    AllowlistEntry,
    EgressAllowlist,
    EgressPolicy,
    EgressPurpose,
    load_allowlist,
)
from intake_platform.model_lanes.keys import KeyVaultUnavailable, ProviderApiKey, ProviderKeyNotSet
from model_lanes_kit import TEST_KEY
from voice_clips.delivery import delivery_profile
from voice_clips.gateway import DeliveryProfileMismatchError, NumeralInScriptError, TtsError

REPO = Path(__file__).resolve().parents[2]
SHIPPED_ALLOWLIST = REPO / "infra" / "security" / "egress-allowlist.yaml"
VENDOR_HOST = "tts.vendor.example"
PUBLIC_TEST_ADDR = "203.0.113.10"
VOICE = "JBFqnCBsd6RMkjVDRZzb"
SCRIPTED = "Şikâyetiniz ne zaman başladı?"
PCM = b"\x01\x00\x02\x00\x03\x00\x04\x00"


def _allowlist(**overrides: Any) -> EgressAllowlist:
    shipped = load_allowlist(SHIPPED_ALLOWLIST)
    fields: dict[str, Any] = {
        "name": ELEVENLABS_EGRESS_ROW,
        "host": VENDOR_HOST,
        "port": 443,
        "protocol": "https",
        "purpose_id": EgressPurpose.HOSTED_MODEL_INFERENCE,
        "purpose": "hosted TTS of scripted text, synthetic only (test copy)",
        "basis": "no-personal-data; synthetic deployment only",
    }
    fields.update(overrides)
    row = AllowlistEntry(**fields)
    return EgressAllowlist(
        version=shipped.version,
        tiers=shipped.tiers.model_copy(update={"dev": [*shipped.tiers.dev, row]}),
    )


class Vendor:
    def __init__(self, response: httpx.Response | None = None) -> None:
        self.response = response if response is not None else httpx.Response(200, content=PCM)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response


def _lane(
    vendor: Vendor,
    *,
    allowlist: EgressAllowlist | None = None,
    key: Callable[[], ProviderApiKey] = lambda: ProviderApiKey(TEST_KEY),
    admits: Callable[[str], bool] = lambda text: text == SCRIPTED,
) -> ElevenLabsHostedTts:
    allow = allowlist if allowlist is not None else _allowlist()
    return ElevenLabsHostedTts(
        host=VENDOR_HOST,
        key=key,
        policy=EgressPolicy.for_tier(allow, "dev", resolver=lambda host, port: (PUBLIC_TEST_ADDR,)),
        admits=admits,
        inner=httpx.MockTransport(vendor),
    )


def test_a_catalogue_text_is_one_request_in_the_clip_gen_shape() -> None:
    vendor = Vendor()
    profile = delivery_profile("routine")
    speech = _lane(vendor).synthesise(text_tr=SCRIPTED, voice_id=VOICE, profile=profile)
    assert speech.pcm_s16le == PCM and speech.sample_rate_hz == 24000 and speech.channels == 1
    (request,) = vendor.requests
    # the guard resolved and pinned the row's host; the name rides in Host
    assert request.headers["host"] == VENDOR_HOST
    assert request.url.host == PUBLIC_TEST_ADDR
    assert request.url.path == f"/v1/text-to-speech/{VOICE}"
    assert request.url.params["output_format"] == "pcm_24000"
    assert request.headers["xi-api-key"] == TEST_KEY
    body = json.loads(request.content)
    assert body == {
        "text": SCRIPTED,
        "model_id": "eleven_multilingual_v2",
        "apply_text_normalization": "off",
        "voice_settings": profile.voice_settings.as_request(),
    }


@pytest.mark.parametrize(
    ("text", "context", "error", "code"),
    [
        ("Başka bir metin?", "routine", HostedTtsRefused, "hosted_tts_not_in_catalogue"),
        (SCRIPTED, "red", HostedTtsRefused, "red_not_on_demand"),
    ],
)
def test_off_catalogue_and_red_are_refused_before_the_wire(
    text: str, context: str, error: type[TtsError], code: str
) -> None:
    vendor = Vendor()
    with pytest.raises(error) as refused:
        _lane(vendor, admits=lambda t: True if context == "red" else t == SCRIPTED).synthesise(
            text_tr=text,
            voice_id=VOICE,
            profile=delivery_profile(context),  # type: ignore[arg-type]
        )
    assert str(refused.value) == code
    assert vendor.requests == []


def test_a_numeral_is_refused_even_on_the_catalogue() -> None:
    # the near miss of the first test: catalogued, but carrying a digit
    vendor = Vendor()
    with pytest.raises(NumeralInScriptError):
        _lane(vendor, admits=lambda t: True).synthesise(
            text_tr="Ağrınız 5 gündür mü?", voice_id=VOICE, profile=delivery_profile("routine")
        )
    assert vendor.requests == []


def test_a_profile_for_another_model_and_a_bad_voice_id_are_refused() -> None:
    vendor = Vendor()
    lane = _lane(vendor)
    other = ElevenLabsHostedTts(
        host=lane.host, key=lane.key, policy=lane.policy, admits=lane.admits, model_id="eleven_v3"
    )
    with pytest.raises(DeliveryProfileMismatchError):
        other.synthesise(text_tr=SCRIPTED, voice_id=VOICE, profile=delivery_profile("routine"))
    with pytest.raises(HostedTtsRefused, match="hosted_tts_voice_refused"):
        lane.synthesise(text_tr=SCRIPTED, voice_id="../voices", profile=delivery_profile("routine"))
    assert vendor.requests == []


def _raise(exc: Exception) -> Callable[[], ProviderApiKey]:
    def key() -> ProviderApiKey:
        raise exc

    return key


@pytest.mark.parametrize(
    ("key", "code"),
    [
        (_raise(ProviderKeyNotSet("none")), "hosted_key_not_set"),
        (_raise(KeyVaultUnavailable()), "model_lanes_key_store_unavailable"),
    ],
)
def test_a_missing_key_is_a_code_and_no_call(key: Callable[[], ProviderApiKey], code: str) -> None:
    vendor = Vendor()
    with pytest.raises(HostedTtsUnavailable) as unavailable:
        _lane(vendor, key=key).synthesise(
            text_tr=SCRIPTED, voice_id=VOICE, profile=delivery_profile("routine")
        )
    assert unavailable.value.code == code
    assert vendor.requests == []


def test_the_allow_list_decides_the_call_in_process() -> None:
    # the same row serving another purpose: the guard refuses before any byte
    vendor = Vendor()
    lane = _lane(vendor, allowlist=_allowlist(purpose_id=EgressPurpose.PACKAGE_REGISTRY))
    with pytest.raises(HostedTtsUnavailable) as denied:
        lane.synthesise(text_tr=SCRIPTED, voice_id=VOICE, profile=delivery_profile("routine"))
    assert denied.value.code == "hosted_lane_egress_denied"
    assert vendor.requests == []


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(401, json={"detail": SCRIPTED}), "hosted_lane_key_rejected"),
        (httpx.Response(500, text=SCRIPTED), "hosted_lane_http_500"),
        (httpx.Response(200, content=b""), "hosted_lane_bad_response"),
        (httpx.Response(200, content=b"\x01\x00\x02"), "hosted_lane_bad_response"),
    ],
)
def test_a_vendor_failure_is_a_code_that_echoes_nothing(
    response: httpx.Response, code: str
) -> None:
    # unavailable, not refused: the caller may fall back to another lane
    with pytest.raises(HostedTtsUnavailable) as refused:
        _lane(Vendor(response)).synthesise(
            text_tr=SCRIPTED, voice_id=VOICE, profile=delivery_profile("routine")
        )
    assert refused.value.code == code
    assert SCRIPTED not in str(refused.value) and TEST_KEY not in str(refused.value)
    assert refused.value.__cause__ is None and refused.value.__context__ is None


def test_an_unreachable_vendor_never_chains_the_request() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    lane = _lane(Vendor())
    lane = ElevenLabsHostedTts(
        host=lane.host,
        key=lane.key,
        policy=lane.policy,
        admits=lane.admits,
        inner=httpx.MockTransport(down),
    )
    with pytest.raises(HostedTtsUnavailable) as unavailable:
        lane.synthesise(text_tr=SCRIPTED, voice_id=VOICE, profile=delivery_profile("routine"))
    assert unavailable.value.code == "hosted_lane_unreachable"
    assert unavailable.value.__cause__ is None and unavailable.value.__context__ is None


# --- the row and the factory -----------------------------------------------------------


def test_the_row_binds_the_host_the_adapter_dials() -> None:
    row = elevenlabs_row(_allowlist())
    assert row is not None and row.host == VENDOR_HOST


@pytest.mark.parametrize(
    "override",
    [
        {"glob": True, "host": "*.vendor.example"},
        {"phi_allowed": True, "phi_exception_approval": "D-test"},
        {"purpose_id": EgressPurpose.PACKAGE_REGISTRY},
        {"port": 8443},
    ],
)
def test_a_mis_bound_row_stops_the_wiring(override: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        elevenlabs_row(_allowlist(**override))


class _Vault:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def key_for_call(self, provider: Any) -> ProviderApiKey:
        self.asked.append(str(provider))
        return ProviderApiKey(TEST_KEY)


SYNTHETIC = {"INTAKE_DEPLOYMENT_DATA_CLASS": "synthetic"}


@pytest.mark.parametrize("env", [{}, {"INTAKE_DEPLOYMENT_DATA_CLASS": "real_phi"}])
def test_the_factory_refuses_outside_the_synthetic_deployment(env: dict[str, str]) -> None:
    vault = _Vault()
    with pytest.raises(HostedLanesRefused):
        hosted_clip_tts_from_env(env, keys=vault, allowlist=_allowlist(), admits=bool)  # type: ignore[arg-type]
    assert vault.asked == []


def test_the_factory_builds_from_the_row_and_the_proxy() -> None:
    env = {**SYNTHETIC, "INTAKE_EGRESS_PROXY_URL": "http://egress-proxy:3128"}
    vault = _Vault()
    lane = hosted_clip_tts_from_env(env, keys=vault, allowlist=_allowlist(), admits=bool)  # type: ignore[arg-type]
    assert lane is not None
    assert lane.host == VENDOR_HOST and lane.proxy == "http://egress-proxy:3128"
    assert vault.asked == [], "the key is read per call, not at wiring"
    assert lane.key().reveal() == TEST_KEY
    assert vault.asked == ["elevenlabs"]


def test_the_factory_answers_none_without_the_row() -> None:
    shipped = load_allowlist(SHIPPED_ALLOWLIST)
    without = EgressAllowlist(
        version=shipped.version,
        tiers=shipped.tiers.model_copy(
            update={"dev": [e for e in shipped.tiers.dev if e.name != ELEVENLABS_EGRESS_ROW]}
        ),
    )
    assert (
        hosted_clip_tts_from_env(SYNTHETIC, keys=_Vault(), allowlist=without, admits=bool) is None
    )  # type: ignore[arg-type]
