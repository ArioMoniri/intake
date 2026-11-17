"""Shared fakes for the INT-428 model-lane suites. Tests only (invariant 17).

Nothing here reaches a network: the KV store is a dict, the hosted backend
records its calls and answers from what the test hands it, and a self-hosted
endpoint's identity is whatever the test's probe returns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from intake_platform.egress import DataClass
from intake_platform.model_lanes import (
    HostedChat,
    HostedLanes,
    HostedModel,
    HostedProviderInfo,
    HostedSpeech,
    HostedTranscript,
    HostedUsage,
    InMemoryModelLanesStore,
    Lane,
    LaneRouter,
    ModelCatalogue,
    ModelLanesControl,
    ModelRef,
    ProviderApiKey,
    ProviderId,
    ProviderKeyVault,
    QualificationRegistry,
    SelfHostedHealth,
    SelfHostedModel,
    ServedIdentity,
    TenantDataClass,
)
from intake_platform.model_lanes.qualifications import EvalRun, EvalStatus, Qualification

#: Fake, test-only weights manifest: 64-hex values that are no file's digest.
WEIGHTS = {"model.safetensors": "a" * 64}
REVISION = "b" * 40
OTHER_REVISION = "c" * 40

LLM_SNAPSHOT = HostedModel(
    id="gpt-4o-mini", version="2024-07-18", wire="gpt-4o-mini-2024-07-18", lanes=(Lane.LLM,)
)
ASR_SNAPSHOT = HostedModel(
    id="gpt-4o-mini-transcribe",
    version="2025-12-15",
    wire="gpt-4o-mini-transcribe-2025-12-15",
    lanes=(Lane.ASR,),
)
TTS_SNAPSHOT = HostedModel(
    id="gpt-4o-mini-tts",
    version="2025-12-15",
    wire="gpt-4o-mini-tts-2025-12-15",
    lanes=(Lane.TTS,),
)
HOSTED_MODELS = (LLM_SNAPSHOT, ASR_SNAPSHOT, TTS_SNAPSHOT)
DEFAULTS = {
    Lane.LLM: "gpt-4o-mini",
    Lane.ASR: "gpt-4o-mini-transcribe",
    Lane.TTS: "gpt-4o-mini-tts",
}


def self_hosted_row(
    lane: Lane,
    *,
    component: str = "gpu-model",
    model_id: str = "org/model",
    revision: str = REVISION,
    jurisdiction: str | None = "TR",
    phi_path: bool = True,
    weights: Mapping[str, str] | None = None,
) -> SelfHostedModel:
    return SelfHostedModel(
        lane=lane,
        component=component,
        model_id=model_id,
        revision=revision,
        weights=dict(WEIGHTS if weights is None else weights),
        jurisdiction=jurisdiction,
        phi_path=phi_path,
    )


def identity_of(row: SelfHostedModel) -> ServedIdentity:
    ref = row.ref()
    assert ref is not None and ref.sha256 is not None
    return ServedIdentity(ref.model_id, ref.version, ref.sha256)


class FakeKv:
    """OpenBao KV v2 as a dict, answering a missing path with a 404 the way
    ``SecretsProvider`` raises it."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}
        self.destroyed: list[str] = []
        self.reachable = True

    def _check(self) -> None:
        if not self.reachable:
            raise httpx.ConnectError("openbao down")

    @staticmethod
    def _missing(path: str) -> httpx.HTTPStatusError:
        request = httpx.Request("GET", f"http://openbao.invalid/v1/secret/data/{path}")
        return httpx.HTTPStatusError(
            "not found", request=request, response=httpx.Response(404, request=request)
        )

    def put_kv(self, path: str, data: dict[str, Any]) -> None:
        self._check()
        self.data[path] = dict(data)

    def get_kv(self, path: str) -> dict[str, Any]:
        self._check()
        if path not in self.data:
            raise self._missing(path)
        return dict(self.data[path])

    def destroy_kv(self, path: str) -> None:
        self._check()
        if path not in self.data:
            raise self._missing(path)
        del self.data[path]
        self.destroyed.append(path)

    def list_kv(self, path: str) -> list[str]:
        self._check()
        return [key.removeprefix(path) for key in self.data if key.startswith(path)]


#: A test-only key: shaped like a provider key, valid for nothing.
TEST_KEY = "sk-test-unit-lane-" + "k" * 24 + "WXYZ"


@dataclass
class FakeHostedBackend:
    """A hosted provider that records its calls. ``served`` overrides the model
    name it claims to have answered with (the per-call identity check)."""

    provider: ProviderId = ProviderId.OPENAI
    text: str = '{"slots": []}'
    served: str | None = None
    fail: str | None = None
    probe_ok: bool = True
    calls: list[tuple[str, str, DataClass]] = field(default_factory=list)

    @property
    def provider_id(self) -> ProviderId:
        return self.provider

    def _maybe_fail(self) -> None:
        if self.fail is not None:
            from intake_platform.model_lanes import HostedLaneUnavailable

            raise HostedLaneUnavailable(self.fail)

    def chat_json(
        self,
        *,
        instructions: str,
        data_block: str,
        schema_name: str,
        json_schema: Mapping[str, Any],
        data_class: DataClass,
        model: str,
    ) -> HostedChat:
        self.calls.append(("chat", model, data_class))
        self._maybe_fail()
        return HostedChat(
            text=self.text,
            model=self.served if self.served is not None else model,
            usage=HostedUsage(input_tokens=7, output_tokens=3),
        )

    def transcribe(
        self, audio: bytes, *, audio_format: str, data_class: DataClass, model: str
    ) -> HostedTranscript:
        self.calls.append(("asr", model, data_class))
        self._maybe_fail()
        return HostedTranscript(text="sentetik", model=model, usage=HostedUsage(input_tokens=5))

    def speech(self, text_tr: str, *, data_class: DataClass, model: str) -> HostedSpeech:
        self.calls.append(("tts", model, data_class))
        self._maybe_fail()
        return HostedSpeech(
            pcm_s16le=b"\x00\x00" * 8,
            sample_rate_hz=24000,
            channels=1,
            model=model,
            usage=HostedUsage(characters=len(text_tr)),
        )

    def probe(self, model: str) -> bool:
        self.calls.append(("probe", model, DataClass.NON_PERSONAL))
        return self.probe_ok


def hosted_lanes(backend: FakeHostedBackend | None, *, listed: bool = True) -> HostedLanes:
    info = HostedProviderInfo(
        provider=ProviderId.OPENAI,
        egress_row="openai-api",
        listed=listed,
        models=HOSTED_MODELS,
        defaults=DEFAULTS,
    )
    backends = {ProviderId.OPENAI: backend} if backend is not None else {}
    return HostedLanes(providers={ProviderId.OPENAI: info}, backends=backends)


def catalogue(
    hosted: HostedLanes, self_hosted: Mapping[Lane, tuple[SelfHostedModel, ...]]
) -> ModelCatalogue:
    return ModelCatalogue(
        hosted={p: info.models for p, info in hosted.providers.items()},
        hosted_defaults={p: dict(info.defaults) for p, info in hosted.providers.items()},
        self_hosted=dict(self_hosted),
    )


def green(lane: Lane, ref: ModelRef, *, run: str = "rf-goldens-run-1") -> Qualification:
    """A qualification row with both runs green (test data, not an eval)."""
    from datetime import date

    return Qualification(
        lane=lane,
        provider=ref.provider,
        model_id=ref.model_id,
        version=ref.version,
        sha256=ref.sha256,
        rf_extraction_goldens=EvalRun(
            status=EvalStatus.GREEN, run_id=run, run_on=date(2026, 10, 2)
        ),
        negation_set=EvalRun(
            status=EvalStatus.GREEN, run_id=f"{run}-neg", run_on=date(2026, 10, 2)
        ),
    )


@dataclass
class Lanes:
    """One composed router and the handles a test pokes."""

    router: LaneRouter
    store: InMemoryModelLanesStore
    kv: FakeKv
    keys: ProviderKeyVault
    backend: FakeHostedBackend
    identities: dict[Lane, ServedIdentity | None]
    rows: dict[Lane, SelfHostedModel]


def build_lanes(
    *,
    declared: TenantDataClass = TenantDataClass.SYNTHETIC,
    control: ModelLanesControl | None = None,
    key_set: bool = True,
    listed: bool = True,
    in_image: bool = True,
    qualifications: QualificationRegistry | None = None,
    served: bool = True,
    kill_switch: Any = None,
) -> Lanes:
    rows = {lane: self_hosted_row(lane, component=f"gpu-{lane.value}") for lane in Lane}
    identities: dict[Lane, ServedIdentity | None] = {
        lane: (identity_of(row) if served else None) for lane, row in rows.items()
    }
    endpoints = {lane: f"http://gpu-{lane.value}.internal.invalid" for lane in Lane}
    by_url = {endpoints[lane]: lane for lane in Lane}
    health = SelfHostedHealth(endpoints, probe=lambda url: identities[by_url[url]])
    kv = FakeKv()
    keys = ProviderKeyVault(kv)
    if key_set:
        kv.put_kv(
            "model-lanes/providers/openai",
            {"api_key": ProviderApiKey(TEST_KEY).reveal(), "last4": "WXYZ", "set_at": "t"},
        )
    backend = FakeHostedBackend()
    hosted = hosted_lanes(backend, listed=listed) if in_image else HostedLanes.none()
    store = InMemoryModelLanesStore(control)
    router = LaneRouter(
        store=store,
        hosted=hosted,
        models=catalogue(hosted, {lane: (row,) for lane, row in rows.items()}),
        keys=keys,
        qualifications=qualifications
        if qualifications is not None
        else QualificationRegistry.gating(Lane.LLM, Lane.ASR),
        declared=declared,
        health=health,
        kill_switch=kill_switch,
    )
    return Lanes(router, store, kv, keys, backend, identities, rows)
