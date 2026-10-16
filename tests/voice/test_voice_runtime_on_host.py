"""INT-515 — the voice runtime as the synthetic host runs it.

Issue #877: *"Add voice-runtime … to the staging compose. Point it at the
hosted lanes once #751 merges … catalogued metrics, /healthz /readyz /metrics
/version, an SLO file and a synthetic probe (invariant 15). Raw audio is never
written (invariant 3)."* Tests: *"the probe completes a scripted synthetic
turn"*. The orchestrator's brief adds the fail-closed half: *"config keyed on
the lane registry, failing closed with a clear readiness reason if a lane is
missing"*.

What this file pins, and against what:

- **readiness keyed on the lane registry.** The registry is
  ``intake_platform.model_lanes`` (INT-428, PR #751, not on main). Its seam is
  ``ModelResolver.resolve(role, *, tenant_id) -> ModelAssignment`` with
  ``available`` and ``reason``; the gate is written against that shape and is
  exercised here with a stand-in resolver of the same shape, and with a stand-in
  ``wiring`` module mirroring #751's ``model_lanes_from_env`` signature, because
  the real one is not importable on this tree. Without the package every lane
  is not ready and the reason says so;
- **process hardening (invariant 3)**: core dumps off, not dumpable, memory
  locked — each a readiness check, each reported rather than assumed;
- **the deployment's environment** (``serve.wiring_from_env``): what the staging
  compose sets binds, and nothing is guessed when it is absent;
- **the synthetic turn** against recorded fixtures under
  ``tests/fixtures/voice/synthetic_turn`` — no vendor and no socket.
"""

from __future__ import annotations

import base64
import builtins
import hashlib
import io
import json
import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient
from intake_platform.egress import VENDOR_LLM_DOMAINS
from intake_platform.safety_inbox import RedisSafetyInboxStore
from intake_platform.voice_control import RedisVoiceControlStore
from intake_voice_runtime.adapters.asr import RecordedTranscriber
from intake_voice_runtime.adapters.speech import RecordedSpeechSynthesizer
from intake_voice_runtime.app import VoiceRuntimeWiring, create_app
from intake_voice_runtime.extraction.gateway import RecordedExtractionGateway
from intake_voice_runtime.hardening import (
    MCL_CURRENT,
    MCL_FUTURE,
    PR_SET_DUMPABLE,
    ProcessHardening,
    harden_process,
)
from intake_voice_runtime.lanes import (
    MODEL_LANES_PACKAGE,
    MODEL_LANES_WIRING,
    REASON_READY,
    REASON_REFUSED,
    REASON_REGISTRY_ABSENT,
    REASON_REGISTRY_UNLOADABLE,
    REASON_REGISTRY_UNREACHABLE,
    REASON_STORE_UNCONFIGURED,
    LaneGate,
    SpeechLane,
    lane_gate_from_env,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.serve import (
    ENV_LIVEKIT_URL,
    ENV_PROBE_VOICE_ID,
    wiring_from_env,
)
from intake_voice_runtime.synthetic_turn import (
    PROBE_ANSWER_TR,
    PROBE_QUESTION_TR,
    PROBE_SLOT_REF,
    TurnStage,
    probe_extraction_call,
)
from intake_voice_runtime.talker.speech import assert_no_numeral
from prometheus_client import REGISTRY
from talker_harness import RecordedClipStore, RecordingSynthesizer

REPO = Path(__file__).resolve().parents[2]
TURN_FIXTURES = REPO / "tests" / "fixtures" / "voice" / "synthetic_turn"
PROBE_VOICE = "sentetik-ses"
LIVEKIT_KEY = "a" * 64
LIVEKIT_SECRET = "b" * 64

HARDENED = ProcessHardening(core_dumps_off=True, not_dumpable=True, memory_locked=True)


# --- doubles ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Assignment:
    """The two fields of #751's ``ModelAssignment`` the gate reads."""

    available: bool
    reason: str


@dataclass
class Resolver:
    """A ``ModelResolver``-shaped stand-in: role → assignment."""

    refused: Mapping[str, str] = field(default_factory=dict)
    raises: Exception | None = None
    asked: list[tuple[str, str | None]] = field(default_factory=list)

    def resolve(self, role: str, *, tenant_id: str | None) -> Assignment:
        self.asked.append((role, tenant_id))
        if self.raises is not None:
            raise self.raises
        if role in self.refused:
            return Assignment(available=False, reason=self.refused[role])
        return Assignment(available=True, reason="")


@dataclass
class Sfu:
    """The SFU's liveness, as the readiness check reads it."""

    up: bool = True

    async def ping(self) -> bool:
        return self.up


def _ready(**overrides: Any) -> VoiceRuntimeWiring:
    fields: dict[str, Any] = {
        "clip_store": RecordedClipStore(),
        "synthesizer": RecordingSynthesizer(),
        "room_token_source": lambda session_id: "token",
        "voice_controls": RedisVoiceControlStore(fakeredis.FakeRedis()),
        "safety_inbox": RedisSafetyInboxStore(fakeredis.FakeRedis()),
        "lanes": LaneGate(Resolver()),
        "hardening": HARDENED,
        "sfu": Sfu(),
    }
    fields.update(overrides)
    return VoiceRuntimeWiring(**fields)


def _readyz(wiring: VoiceRuntimeWiring) -> tuple[int, dict[str, str]]:
    response = TestClient(create_app(wiring), raise_server_exceptions=False).get("/readyz")
    return response.status_code, response.json()["checks"]


def _lane_gauge(lane: str, reason: str) -> float | None:
    return REGISTRY.get_sample_value("voice_lane_ready", {"lane": lane, "reason": reason})


# --- readiness, keyed on the lane registry ---------------------------------------------


def test_a_fully_wired_runtime_is_ready() -> None:
    status, checks = _readyz(_ready())
    assert status == 200
    assert set(checks.values()) == {"ok"}
    for lane in ("asr", "tts", "llm"):
        assert checks[f"lane_{lane}"] == "ok"


@pytest.mark.parametrize("lane", ["asr", "tts", "llm"])
def test_readiness_fails_closed_naming_the_missing_lane(lane: str) -> None:
    resolver = Resolver(refused={lane: "hosted_key_not_set"})
    status, checks = _readyz(_ready(lanes=LaneGate(resolver)))
    assert status == 503
    assert checks[f"lane_{lane}"] == "error"
    assert [name for name, state in checks.items() if state != "ok"] == [f"lane_{lane}"]
    # the reason is the registry's own code, readable without the logs
    assert _lane_gauge(lane, "hosted_key_not_set") == 0.0


def test_a_ready_lane_reports_ready_as_its_reason() -> None:
    _readyz(_ready())
    assert _lane_gauge("tts", REASON_READY) == 1.0


def test_without_the_lane_registry_every_lane_fails_closed_and_says_why() -> None:
    imported: list[str] = []

    def find_spec(name: str) -> object | None:
        assert name == MODEL_LANES_PACKAGE
        return None

    def import_module(name: str) -> ModuleType:
        imported.append(name)
        raise AssertionError("an absent registry is never imported")

    gate = lane_gate_from_env({}, find_spec=find_spec, import_module=import_module)
    for lane in SpeechLane:
        status = gate.status(lane)
        assert (status.ready, status.reason) == (False, REASON_REGISTRY_ABSENT)
    assert imported == []
    code, checks = _readyz(_ready(lanes=gate))
    assert code == 503
    assert {checks[f"lane_{lane.value}"] for lane in SpeechLane} == {"error"}
    assert _lane_gauge("asr", REASON_REGISTRY_ABSENT) == 0.0


def _wiring_module(answer: Callable[..., object]) -> Callable[[str], ModuleType]:
    module = ModuleType(MODEL_LANES_WIRING)
    module.model_lanes_from_env = answer  # type: ignore[attr-defined]

    def import_module(name: str) -> ModuleType:
        assert name == MODEL_LANES_WIRING
        return module

    return import_module


def test_the_registry_is_read_through_the_model_lanes_builder() -> None:
    """#751's one builder, ``model_lanes_from_env(env, *, kv, root)``: the
    runtime passes its environment and no key store of its own, so a hosted
    route it cannot authenticate reports the registry's own refusal."""
    seen: dict[str, Any] = {}
    resolver = Resolver(refused={"tts": "hosted_key_store_unconfigured"})

    @dataclass
    class Wiring:
        router: Resolver

    def model_lanes_from_env(env: Mapping[str, str], *, kv: object, root: Path) -> Wiring:
        seen.update(env=dict(env), kv=kv, root=root)
        return Wiring(router=resolver)

    env = {"INTAKE_MODEL_LANES_REDIS_URL": "redis://redis:6379/0"}
    gate = lane_gate_from_env(
        env, find_spec=lambda name: object(), import_module=_wiring_module(model_lanes_from_env)
    )
    assert seen == {"env": env, "kv": None, "root": Path()}
    assert gate.status(SpeechLane.ASR).ready is True
    tts = gate.status(SpeechLane.TTS)
    assert (tts.ready, tts.reason) == (False, "hosted_key_store_unconfigured")
    # asked with no tenant: readiness is the deployment's, not one tenant's
    assert ("asr", None) in resolver.asked


def test_a_registry_with_no_control_store_is_unconfigured() -> None:
    gate = lane_gate_from_env(
        {}, find_spec=lambda name: object(), import_module=_wiring_module(lambda env, **kw: None)
    )
    assert gate.status(SpeechLane.LLM).reason == REASON_STORE_UNCONFIGURED


def test_a_registry_that_cannot_load_is_unloadable_not_ready() -> None:
    def boom(env: Mapping[str, str], **kw: object) -> object:
        raise FileNotFoundError("infra/model-lanes/self-hosted.yaml")

    gate = lane_gate_from_env(
        {}, find_spec=lambda name: object(), import_module=_wiring_module(boom)
    )
    status = gate.status(SpeechLane.ASR)
    assert (status.ready, status.reason) == (False, REASON_REGISTRY_UNLOADABLE)


def test_a_resolver_that_raises_is_unreachable_not_ready() -> None:
    gate = LaneGate(Resolver(raises=ConnectionError("redis down")))
    status = gate.status(SpeechLane.LLM)
    assert (status.ready, status.reason) == (False, REASON_REGISTRY_UNREACHABLE)


@pytest.mark.parametrize(
    "reason",
    ["Bearer sk-abc", "hasta adı Ayşe", "x" * 200, "", "UPPER_CASE"],
)
def test_a_reason_that_is_not_an_id_never_becomes_a_label(reason: str) -> None:
    """Invariant 6: a refusal code becomes a metric label only if it is an id."""
    gate = LaneGate(Resolver(refused={"asr": reason}))
    assert gate.status(SpeechLane.ASR).reason == REASON_REFUSED


def test_near_miss_an_id_shaped_reason_passes_through() -> None:
    gate = LaneGate(Resolver(refused={"asr": "identity_mismatch"}))
    assert gate.status(SpeechLane.ASR).reason == "identity_mismatch"


def test_a_typed_worker_needs_only_the_extraction_lane() -> None:
    resolver = Resolver(refused={"asr": "unconfigured", "tts": "unconfigured"})
    status, checks = _readyz(
        _ready(
            profile=VoiceProfile.TYPED,
            lanes=LaneGate(resolver),
            clip_store=None,
            synthesizer=None,
            room_token_source=None,
            voice_controls=None,
            sfu=None,
        )
    )
    assert status == 200, checks
    # near miss: the same worker with its one lane refused is not ready
    status, checks = _readyz(
        _ready(profile=VoiceProfile.TYPED, lanes=LaneGate(Resolver(refused={"llm": "x_y"})))
    )
    assert (status, checks["lane_llm"]) == (503, "error")


def test_an_unwired_gate_is_not_ready() -> None:
    status, checks = _readyz(_ready(lanes=None))
    assert status == 503
    assert {checks["lane_asr"], checks["lane_tts"], checks["lane_llm"]} == {"error"}


def test_an_sfu_that_does_not_answer_is_not_ready() -> None:
    status, checks = _readyz(_ready(sfu=Sfu(up=False)))
    assert (status, checks["sfu"]) == (503, "error")
    status, checks = _readyz(_ready(sfu=None))
    assert (status, checks["sfu"]) == (503, "error")


# --- process hardening (invariant 3) ---------------------------------------------------


@dataclass
class Libc:
    """``prctl`` and ``mlockall`` as ctypes exposes them: 0 or -1."""

    prctl_rc: int = 0
    mlockall_rc: int = 0
    calls: list[tuple[str, tuple[int, ...]]] = field(default_factory=list)

    def prctl(self, *args: int) -> int:
        self.calls.append(("prctl", args))
        return self.prctl_rc

    def mlockall(self, *args: int) -> int:
        self.calls.append(("mlockall", args))
        return self.mlockall_rc


def test_hardening_turns_core_dumps_off_and_locks_memory() -> None:
    import resource

    libc = Libc()
    limits: list[tuple[int, tuple[int, int]]] = []
    hardening = harden_process(
        libc=libc,
        setrlimit=lambda which, value: limits.append((which, value)),
        platform="linux",
    )
    assert hardening == ProcessHardening(core_dumps_off=True, not_dumpable=True, memory_locked=True)
    assert limits == [(resource.RLIMIT_CORE, (0, 0))]
    assert ("prctl", (PR_SET_DUMPABLE, 0, 0, 0, 0)) in libc.calls
    assert ("mlockall", (MCL_CURRENT | MCL_FUTURE,)) in libc.calls


def test_a_refused_mlock_is_reported_and_fails_readiness() -> None:
    hardening = harden_process(
        libc=Libc(mlockall_rc=-1), setrlimit=lambda which, value: None, platform="linux"
    )
    assert hardening.memory_locked is False
    status, checks = _readyz(_ready(hardening=hardening))
    assert (status, checks["memory_locked"], checks["core_dumps_off"]) == (503, "error", "ok")


def test_a_refused_core_limit_or_prctl_fails_readiness() -> None:
    def refuse(which: int, value: tuple[int, int]) -> None:
        raise OSError("not permitted")

    hardening = harden_process(libc=Libc(prctl_rc=-1), setrlimit=refuse, platform="linux")
    assert (hardening.core_dumps_off, hardening.not_dumpable) == (False, False)
    status, checks = _readyz(_ready(hardening=hardening))
    assert (status, checks["core_dumps_off"]) == (503, "error")


def test_off_linux_nothing_claims_to_be_locked() -> None:
    hardening = harden_process(libc=Libc(), setrlimit=lambda which, value: None, platform="darwin")
    assert (hardening.not_dumpable, hardening.memory_locked) == (False, False)


def test_a_linux_host_without_a_findable_libc_claims_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ctypes.util

    monkeypatch.setattr(ctypes.util, "find_library", lambda name: None)
    hardening = harden_process(setrlimit=lambda which, value: None, platform="linux")
    assert hardening == ProcessHardening(
        core_dumps_off=True, not_dumpable=False, memory_locked=False
    )


def test_readiness_fails_closed_without_a_hardening_report() -> None:
    status, checks = _readyz(_ready(hardening=None))
    assert (status, checks["core_dumps_off"], checks["memory_locked"]) == (503, "error", "error")


def test_a_typed_worker_holds_no_audio_so_its_memory_need_not_be_locked() -> None:
    unlocked = ProcessHardening(core_dumps_off=True, not_dumpable=True, memory_locked=False)
    status, checks = _readyz(_ready(profile=VoiceProfile.TYPED, hardening=unlocked))
    assert (status, checks["memory_locked"], checks["core_dumps_off"]) == (200, "ok", "ok")


# --- serve: the deployment's environment -----------------------------------------------


def test_an_empty_environment_binds_nothing_and_readiness_names_it_all() -> None:
    wiring = wiring_from_env({}, hardening=HARDENED, lane_gate=LaneGate(None))
    assert wiring.voice_controls is None
    assert wiring.safety_inbox is None
    assert wiring.room_token_source is None
    assert wiring.sfu is None
    assert wiring.synthesizer is None
    assert wiring.transcriber is None
    assert wiring.extraction is None
    assert wiring.clip_store is None
    status, checks = _readyz(wiring)
    assert status == 503
    assert {name for name, state in checks.items() if state != "ok"} == {
        "clip_store",
        "speech_synthesizer",
        "room_token",
        "voice_controls",
        "safety_inbox",
        "sfu",
        "lane_asr",
        "lane_tts",
        "lane_llm",
    }


def _staging_env(**extra: str) -> dict[str, str]:
    return {
        "INTAKE_VOICE_CONTROL_REDIS_URL": "redis://:pw@redis:6379/0",
        "INTAKE_SAFETY_INBOX_REDIS_URL": "redis://:pw@redis:6379/0",
        ENV_LIVEKIT_URL: "http://livekit:7880",
        "LIVEKIT_API_KEY": LIVEKIT_KEY,
        "LIVEKIT_API_SECRET": LIVEKIT_SECRET,
        **extra,
    }


def _claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def test_the_staging_environment_binds_the_stores_the_sfu_and_the_agent_token() -> None:
    wiring = wiring_from_env(_staging_env(), hardening=HARDENED, lane_gate=LaneGate(None))
    assert wiring.voice_controls is not None
    assert wiring.safety_inbox is not None
    assert wiring.sfu is not None
    assert wiring.room_token_source is not None
    session = "0b6f8f9e-1c8e-4c55-9d9f-1d1c4b0a6b11"
    claims = _claims(wiring.room_token_source(session))
    assert claims["sub"] == "agent"
    video = claims["video"]
    assert video["room"] == f"intake-{session}"
    # the agent never publishes data: a RED reaches the device through the
    # SFU's server API (intake_voice_runtime.sfu), not from the agent's peer
    assert video["canPublishData"] is False
    assert claims["exp"] - claims["iat"] <= 600


def test_a_half_configured_sfu_is_unbound_not_guessed() -> None:
    env = _staging_env()
    del env["LIVEKIT_API_SECRET"]
    wiring = wiring_from_env(env, hardening=HARDENED, lane_gate=LaneGate(None))
    assert (wiring.sfu, wiring.room_token_source) == (None, None)
    env = _staging_env()
    del env[ENV_LIVEKIT_URL]
    wiring = wiring_from_env(env, hardening=HARDENED, lane_gate=LaneGate(None))
    assert (wiring.sfu, wiring.room_token_source) == (None, None)


def test_a_malformed_store_url_is_unbound_not_guessed() -> None:
    env = _staging_env(INTAKE_VOICE_CONTROL_REDIS_URL="http://redis:6379")
    wiring = wiring_from_env(env, hardening=HARDENED, lane_gate=LaneGate(None))
    assert wiring.voice_controls is None
    assert wiring.safety_inbox is not None


def test_a_public_speech_endpoint_is_refused_at_boot() -> None:
    """The adapters' own refusal (INT-095) holds when the environment names a
    public host: the binding stays empty and readiness says so."""
    env = _staging_env(INTAKE_TTS_ENDPOINT="https://speech.example.com")
    wiring = wiring_from_env(env, hardening=HARDENED, lane_gate=LaneGate(None))
    assert wiring.synthesizer is None


@pytest.mark.parametrize(
    "url",
    ["livekit:7880", "ftp://livekit:7880", "http://livekit:7880/rtc", "http://livekit:7880/?x=1"],
)
def test_an_sfu_url_that_is_not_a_bare_http_origin_is_unbound(url: str) -> None:
    wiring = wiring_from_env(
        _staging_env(**{ENV_LIVEKIT_URL: url}), hardening=HARDENED, lane_gate=LaneGate(None)
    )
    assert (wiring.sfu, wiring.room_token_source) == (None, None)


def test_public_asr_and_extraction_endpoints_are_refused_at_boot() -> None:
    env = _staging_env(
        INTAKE_ASR_ENDPOINT="https://asr.example.com",
        # a vendor host, derived from the egress module rather than spelled here
        INTAKE_EXTRACTION_ENDPOINT=f"https://api.{min(VENDOR_LLM_DOMAINS)}",
    )
    wiring = wiring_from_env(env, hardening=HARDENED, lane_gate=LaneGate(None))
    assert (wiring.transcriber, wiring.extraction) == (None, None)


def test_a_malformed_inbox_url_is_unbound_not_guessed() -> None:
    env = _staging_env(INTAKE_SAFETY_INBOX_REDIS_URL="inbox.local")
    wiring = wiring_from_env(env, hardening=HARDENED, lane_gate=LaneGate(None))
    assert wiring.safety_inbox is None
    assert wiring.voice_controls is not None


def test_the_factory_hardens_before_it_binds(monkeypatch: pytest.MonkeyPatch) -> None:
    import intake_voice_runtime.serve as serve

    order: list[str] = []

    def harden() -> ProcessHardening:
        order.append("harden")
        return HARDENED

    def bind(env: Mapping[str, str], *, hardening: ProcessHardening) -> VoiceRuntimeWiring:
        order.append("bind")
        assert hardening is HARDENED
        return VoiceRuntimeWiring(hardening=hardening, lanes=LaneGate(None))

    monkeypatch.setattr(serve, "harden_process", harden)
    monkeypatch.setattr(serve, "wiring_from_env", bind)
    app = serve.app_from_env()
    assert order == ["harden", "bind"]
    assert TestClient(app).get("/healthz").status_code == 200


def test_the_probe_voice_comes_from_the_environment_only() -> None:
    wiring = wiring_from_env(
        _staging_env(**{ENV_PROBE_VOICE_ID: PROBE_VOICE}),
        hardening=HARDENED,
        lane_gate=LaneGate(None),
    )
    assert wiring.probe_voice_id == PROBE_VOICE
    assert wiring_from_env({}, hardening=HARDENED, lane_gate=LaneGate(None)).probe_voice_id is None


# --- the synthetic turn, against recorded fixtures -------------------------------------


def _recorded(**overrides: Any) -> VoiceRuntimeWiring:
    fields: dict[str, Any] = {
        "synthesizer": RecordedSpeechSynthesizer(root=TURN_FIXTURES / "tts"),
        "transcriber": RecordedTranscriber(TURN_FIXTURES / "asr"),
        "extraction": RecordedExtractionGateway(TURN_FIXTURES / "extraction"),
        "probe_voice_id": PROBE_VOICE,
    }
    fields.update(overrides)
    return VoiceRuntimeWiring(**fields)


def _turn(wiring: VoiceRuntimeWiring) -> tuple[int, dict[str, Any]]:
    response = TestClient(create_app(wiring), raise_server_exceptions=False).post(
        "/probe/synthetic-turn"
    )
    return response.status_code, response.json()


def test_the_probe_completes_a_scripted_synthetic_turn_against_fixtures() -> None:
    status, report = _turn(_recorded())
    assert status == 200, report
    assert report["completed"] is True
    assert [stage["stage"] for stage in report["stages"]] == [stage.value for stage in TurnStage]
    assert all(stage["ok"] for stage in report["stages"])
    assert all(isinstance(stage["latency_ms"], float) for stage in report["stages"])
    # the extraction stage reports the one synthetic slot it bound, by id
    assert report["bound_slots"] == [PROBE_SLOT_REF]


def test_the_report_carries_ids_and_timings_only() -> None:
    _, report = _turn(_recorded())
    body = json.dumps(report, ensure_ascii=False)
    for word in (*PROBE_QUESTION_TR.split(), *PROBE_ANSWER_TR.split()):
        assert word.strip("?,.:") not in body, word
    assert set(report) == {"completed", "stages", "bound_slots"}


def test_a_lane_that_is_not_bound_stops_the_turn_at_its_stage() -> None:
    status, report = _turn(_recorded(transcriber=None))
    assert status == 503
    assert report["completed"] is False
    failed = [stage for stage in report["stages"] if not stage["ok"]]
    assert [(stage["stage"], stage["code"]) for stage in failed] == [
        (TurnStage.TRANSCRIBE.value, "unbound")
    ]
    # nothing after the failed stage ran
    assert report["stages"][-1]["stage"] == TurnStage.TRANSCRIBE.value


def test_no_probe_voice_stops_the_turn_before_any_speech() -> None:
    status, report = _turn(_recorded(probe_voice_id=None))
    assert status == 503
    assert [(s["stage"], s["code"]) for s in report["stages"]] == [
        (TurnStage.AGENT_SPEECH.value, "voice_unconfigured")
    ]


def test_a_failing_lane_is_named_by_class_never_by_message(tmp_path: Path) -> None:
    status, report = _turn(_recorded(transcriber=RecordedTranscriber(tmp_path)))
    assert status == 503
    failed = report["stages"][-1]
    assert (failed["stage"], failed["code"]) == (
        TurnStage.TRANSCRIBE.value,
        "RecordedTranscriptMissing",
    )
    assert str(tmp_path) not in json.dumps(report)


def test_a_turn_that_binds_nothing_is_not_completed(tmp_path: Path) -> None:
    """Near miss: every lane answered, the extraction bound no slot."""
    recording = tmp_path / "extraction"
    recording.mkdir()
    call = probe_extraction_call(_transcript_text())
    (recording / f"{call.recording_key}.json").write_text(
        json.dumps(
            {
                "schema_id": "intake.extraction.slots.v1",
                "prompt_version": "extraction.v1",
                "data_sha256": call.data.sha256,
                "completion": json.dumps(
                    {"slots": {}, "candidate_flags": [], "clarification_needed": True}
                ),
            }
        ),
        encoding="utf-8",
    )
    status, report = _turn(_recorded(extraction=RecordedExtractionGateway(recording)))
    assert status == 503
    assert (report["stages"][-1]["stage"], report["stages"][-1]["code"]) == (
        TurnStage.EXTRACT.value,
        "nothing_bound",
    )


@dataclass
class _Silent:
    """Lanes that answer with nothing: an empty synthesis, an empty transcript."""

    def synthesize(self, text_tr: str, voice_id: str) -> bytes:
        return b""

    def transcribe(self, audio: bytes) -> Any:
        from intake_voice_runtime.adapters.asr import Transcription

        return Transcription(text="   ", model="silent")


def test_an_empty_synthesis_is_not_speech() -> None:
    status, report = _turn(_recorded(synthesizer=_Silent()))
    assert status == 503
    assert [(s["stage"], s["code"]) for s in report["stages"]] == [
        (TurnStage.AGENT_SPEECH.value, "empty")
    ]


def test_an_empty_transcript_is_not_a_turn() -> None:
    status, report = _turn(_recorded(transcriber=_Silent()))
    assert status == 503
    assert (report["stages"][-1]["stage"], report["stages"][-1]["code"]) == (
        TurnStage.TRANSCRIBE.value,
        "empty",
    )


@pytest.mark.parametrize(
    ("missing", "stage"),
    [("synthesizer", TurnStage.AGENT_SPEECH), ("extraction", TurnStage.EXTRACT)],
)
def test_each_unbound_lane_stops_the_turn_at_its_own_stage(missing: str, stage: TurnStage) -> None:
    status, report = _turn(_recorded(**{missing: None}))
    assert status == 503
    assert (report["stages"][-1]["stage"], report["stages"][-1]["code"]) == (
        stage.value,
        "unbound",
    )


def _transcript_text() -> str:
    recordings = sorted((TURN_FIXTURES / "asr").glob("*.json"))
    assert len(recordings) == 1
    return str(json.loads(recordings[0].read_text(encoding="utf-8"))["text"])


def test_the_probe_is_rate_limited_so_it_cannot_run_up_a_vendor_bill() -> None:
    client = TestClient(create_app(_recorded()), raise_server_exceptions=False)
    first = client.post("/probe/synthetic-turn")
    second = client.post("/probe/synthetic-turn")
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json() == {"code": "probe_rate_limited"}


@pytest.fixture()
def opened_for_write(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Every file the process opens for writing while the turn runs."""
    written: list[str] = []
    real_open = builtins.open
    real_os_open = os.open

    def watched_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(flag in mode for flag in "wax+"):
            written.append(str(file))
        return real_open(file, mode, *args, **kwargs)

    def watched_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            written.append(str(path))
        return real_os_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watched_open)
    monkeypatch.setattr(io, "open", watched_open)
    monkeypatch.setattr(os, "open", watched_os_open)
    yield written


def test_the_turn_never_writes_audio(opened_for_write: list[str]) -> None:
    """Invariant 3: the synthetic patient's audio exists in memory for the
    length of one call and is written nowhere — no file, no temp file."""
    status, _ = _turn(_recorded())
    assert status == 200
    assert opened_for_write == []


def test_the_script_is_numeral_free_synthetic_siz_register_and_one_question() -> None:
    """Never patient-facing (no session reaches it), and written to the rules
    that would apply if it were: no numeral (invariant 22), one question,
    ``siz`` (CLAUDE.md patient copy)."""
    for text in (PROBE_QUESTION_TR, PROBE_ANSWER_TR):
        assert_no_numeral(text)
    assert PROBE_QUESTION_TR.count("?") == 1
    assert "sentetik" in PROBE_QUESTION_TR.lower()
    assert "musunuz" in PROBE_QUESTION_TR


def test_the_fixtures_are_recordings_of_this_script() -> None:
    """The recordings are addressed by the script itself: edit the script and
    the turn stops finding them, rather than replaying a stale answer."""
    tts = TURN_FIXTURES / "tts"
    for text in (PROBE_QUESTION_TR, PROBE_ANSWER_TR):
        key = hashlib.sha256(f"{text}\x00{PROBE_VOICE}".encode()).hexdigest()
        assert (tts / f"{key}.json").is_file(), text
    answer = json.loads(
        (
            tts
            / f"{hashlib.sha256(f'{PROBE_ANSWER_TR}\x00{PROBE_VOICE}'.encode()).hexdigest()}.json"
        ).read_text(encoding="utf-8")
    )
    frames = base64.b64decode(answer["body_base64"])
    assert (TURN_FIXTURES / "asr" / f"{hashlib.sha256(frames).hexdigest()}.json").is_file()
    call = probe_extraction_call(_transcript_text())
    assert (TURN_FIXTURES / "extraction" / f"{call.recording_key}.json").is_file()
