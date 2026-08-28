"""INT-090 — audio_retention_guard: no audio write paths anywhere (invariant 3).

Three layers, complementing INT-036's policy-level guard
(tests/legal/test_retention_engine.py: audio is not a retention class and the
policy loader refuses one). This file guards the layers below the policy:

- **code**: a static AST scan over every Python source under packages/ and
  services/ (the INT-025 metrics-gate house style). No source may import an
  audio-file library, carry a string literal ending in an audio file
  extension (a filename or object key someone could write to), or carry an
  ``audio/*`` content-type literal (an object-store put). The allow-list
  below is empty; extending it requires an invariant-3 justification in the
  PR and CODEOWNER review.
- **livekit config**: infra/livekit/livekit-dev.yaml keeps recording
  structurally impossible, not merely off — no redis block (egress/ingress
  workers register over the redis bus; without it a recording request has
  nothing to reach), no ingress/webhook block, ephemeral rooms.
- **compose**: the livekit service is profile-gated, tag-pinned, loopback
  only, mounts nothing writable (no volume to record onto), and the dev tier
  ships no egress/ingress/recorder companion service.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "infra" / "livekit" / "livekit-dev.yaml"
COMPOSE_PATH = REPO / "infra" / "docker-compose.dev.yml"

SCAN_ROOTS = ("packages", "services")
SKIP_PARTS = frozenset({"tests", ".venv", "node_modules", "build", "dist", ".cache"})

#: File extensions that mark a literal as an audio artefact name. A string
#: literal ending in one of these inside production code is a place audio
#: could be written to (or read back from — equally forbidden: invariant 3
#: says never *reachable*, not only never written).
AUDIO_EXTENSIONS = (
    ".wav",
    ".mp3",
    ".ogg",
    ".oga",
    ".opus",
    ".flac",
    ".m4a",
    ".aac",
    ".pcm",
    ".amr",
    ".aiff",
    ".aif",
    ".wma",
    ".webm",
    ".mka",
    ".caf",
)

#: Libraries whose purpose is audio file I/O (or raw capture). Importing one
#: under packages/ or services/ is a finding: the voice runtime consumes
#: WebRTC frames in memory (invariant 3 buffers) and never touches audio
#: files. ``scipy.io.wavfile`` is matched as a dotted prefix.
AUDIO_IO_MODULES = frozenset(
    {
        "wave",
        "aifc",
        "sunau",
        "soundfile",
        "pydub",
        "audiofile",
        "audioread",
        "torchaudio",
        "librosa",
        "pyaudio",
        "sounddevice",
        "scipy.io.wavfile",
    }
)

#: repo-relative path -> literals it is allowed to carry. Empty by design;
#: any entry needs an invariant-3 justification and CODEOWNER review, and the
#: clip cache (agent-voice TTS output, files/03 §4.2) is the only anticipated
#: candidate.
ALLOWED_AUDIO_LITERALS: dict[str, frozenset[str]] = {}


def _module_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Every dotted module name an import statement binds or reads from."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    module = node.module or ""
    names = [module] if module else []
    names += [f"{module}.{alias.name}" if module else alias.name for alias in node.names]
    return names


def _is_forbidden_module(name: str) -> bool:
    parts = name.split(".")
    prefixes = {".".join(parts[: i + 1]) for i in range(len(parts))}
    return not prefixes.isdisjoint(AUDIO_IO_MODULES)


def audio_findings(label: str, source: str) -> list[str]:
    """Every audio write/read path a Python source exposes, as strings."""
    findings: list[str] = []
    allowed = ALLOWED_AUDIO_LITERALS.get(label, frozenset())
    tree = ast.parse(source, filename=label)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            for name in _module_names(node):
                if _is_forbidden_module(name):
                    findings.append(f"{label}:{node.lineno}: audio I/O import {name!r}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in allowed:
                continue
            lowered = node.value.lower()
            if lowered.endswith(AUDIO_EXTENSIONS):
                findings.append(f"{label}:{node.lineno}: audio-typed literal {node.value!r}")
            if lowered.startswith("audio/"):
                findings.append(f"{label}:{node.lineno}: audio content type {node.value!r}")
    return findings


def _python_sources() -> list[Path]:
    sources: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO / root
        if not base.is_dir():
            continue
        sources += [
            path for path in sorted(base.rglob("*.py")) if SKIP_PARTS.isdisjoint(path.parts)
        ]
    return sources


class TestNoAudioWritePathInCode:
    def test_the_scan_walks_a_real_corpus(self) -> None:
        """The gate is hollow if the walker finds nothing to scan."""
        sources = _python_sources()
        assert len(sources) >= 10
        assert any(path.name == "uploads.py" for path in sources)

    def test_no_source_under_packages_or_services_touches_audio(self) -> None:
        findings: list[str] = []
        for path in _python_sources():
            label = str(path.relative_to(REPO))
            findings += audio_findings(label, path.read_text(encoding="utf-8"))
        assert findings == [], (
            "audio write/read paths in production code (invariant 3 — raw audio "
            f"is never written anywhere): {findings}"
        )

    def test_no_audio_file_exists_in_the_tree(self) -> None:
        offenders = [
            str(path.relative_to(REPO))
            for root in (*SCAN_ROOTS, "infra")
            if (REPO / root).is_dir()
            for path in sorted((REPO / root).rglob("*"))
            if path.suffix.lower() in AUDIO_EXTENSIONS
        ]
        assert offenders == []

    def test_the_allow_list_is_empty(self) -> None:
        """Growing it is a reviewed decision, never a drive-by."""
        assert ALLOWED_AUDIO_LITERALS == {}

    # --- near-miss negative controls: the scanner itself is under test -------------

    def test_the_scanner_reports_each_kind_of_offender(self) -> None:
        offending = (
            "import wave\n"
            "from scipy.io import wavfile\n"
            "import torchaudio as ta\n"
            'HANDLE = open("call.wav", "wb")\n'
            'CONTENT_TYPE = "audio/ogg"\n'
        )
        findings = audio_findings("synthetic.py", offending)
        assert len(findings) == 5
        assert any("'wave'" in finding for finding in findings)
        assert any("scipy.io.wavfile" in finding for finding in findings)
        assert any("torchaudio" in finding for finding in findings)
        assert any("call.wav" in finding for finding in findings)
        assert any("audio/ogg" in finding for finding in findings)

    def test_the_scanner_ignores_near_misses(self) -> None:
        benign = (
            "from scipy import stats\n"
            "import waveforms_math\n"
            'METRIC = "voice_round_trip_ms"\n'
            'LEVEL = "audio_level"\n'
            'NOTE = "the wavelength.txt report"\n'
            'DOC = "report.pdf"\n'
        )
        assert audio_findings("synthetic.py", benign) == []

    def test_the_allow_list_is_honoured_per_file_only(self) -> None:
        source = 'CLIP = "clip.opus"\n'
        try:
            ALLOWED_AUDIO_LITERALS["packages/x/clips.py"] = frozenset({"clip.opus"})
            assert audio_findings("packages/x/clips.py", source) == []
            assert audio_findings("packages/y/other.py", source) != []
        finally:
            del ALLOWED_AUDIO_LITERALS["packages/x/clips.py"]


def _config() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return loaded


class TestLiveKitConfigHasNoRecordingSurface:
    def test_recording_egress_ingress_are_structurally_absent(self) -> None:
        config = _config()
        forbidden = {"redis", "ingress", "egress", "recording", "webhook"}
        present = forbidden & set(config)
        assert present == set(), (
            f"livekit-dev.yaml carries {sorted(present)} — with a redis bus or "
            "ingress/webhook config, recording stops being structurally impossible"
        )

    def test_rooms_are_ephemeral(self) -> None:
        room = _config()["room"]
        assert room["auto_create"] is True
        assert 0 < room["empty_timeout"] <= 600
        assert 0 < room["departure_timeout"] <= 60
        assert 0 < room["max_participants"] <= 8

    def test_the_room_is_audio_only(self) -> None:
        mimes = [codec["mime"] for codec in _config()["room"]["enabled_codecs"]]
        assert mimes == ["audio/opus"], "a video codec widens the eavesdropping surface"

    def test_no_keys_live_in_the_committed_config(self) -> None:
        assert "keys" not in _config(), "API keys arrive via LIVEKIT_KEYS from env (inv. 14)"
        assert "key_file" not in _config()

    def test_turn_is_embedded_udp_only_dev_tier(self) -> None:
        turn = _config()["turn"]
        assert turn["enabled"] is True
        assert turn["udp_port"] == 3478
        # TLS/TCP relay needs certs and puts TCP head-of-line blocking on the
        # media path (files/03 §4.4b treats it as a degradation trigger, and
        # production runs coturn in the same PoP instead — see the runbook).
        assert "tls_port" not in turn
        assert "cert_file" not in turn
        assert "key_file" not in turn

    def test_rtc_stays_on_the_host_it_is_started_on(self) -> None:
        rtc = _config()["rtc"]
        assert rtc["use_external_ip"] is False
        assert 0 < rtc["port_range_end"] - rtc["port_range_start"] <= 50


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return loaded


def _services() -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = _compose()["services"]
    return services


class TestComposeDevTier:
    def test_livekit_is_profile_gated_like_clamav(self) -> None:
        assert _services()["livekit"]["profiles"] == ["livekit"]

    def test_image_is_tag_pinned(self) -> None:
        image = str(_services()["livekit"]["image"])
        repository, _, tag = image.partition(":")
        assert repository == "livekit/livekit-server"
        assert tag.startswith("v") and tag not in {"v", "latest"}, f"floating tag: {image}"

    def test_all_published_ports_bind_loopback(self) -> None:
        for port in _services()["livekit"]["ports"]:
            assert str(port).startswith("127.0.0.1:"), f"livekit publishes {port}"

    def test_keys_come_from_env_with_a_dev_only_default(self) -> None:
        keys = str(_services()["livekit"]["environment"]["LIVEKIT_KEYS"])
        assert keys.startswith("${LIVEKIT_API_KEY:-"), "keys must be env-overridable"
        assert "${LIVEKIT_API_SECRET:-" in keys
        assert "dev-only" in keys, "the baked-in default must be labelled dev-only"

    def test_livekit_has_a_healthcheck(self) -> None:
        healthcheck = _services()["livekit"].get("healthcheck")
        assert healthcheck and healthcheck.get("test")

    def test_livekit_mounts_nothing_writable(self) -> None:
        volumes = [str(volume) for volume in _services()["livekit"].get("volumes", [])]
        assert len(volumes) == 1, "exactly the config file — no volume to record onto"
        assert volumes[0].endswith(":ro")
        source = volumes[0].split(":", 1)[0]
        assert source.startswith("./"), "no named volume for livekit"
        assert (REPO / "infra" / source[2:]) == CONFIG_PATH

    def test_the_mounted_config_is_the_file_this_suite_parses(self) -> None:
        command = str(_services()["livekit"]["command"])
        assert "--config" in command
        assert CONFIG_PATH.exists()

    def test_no_egress_ingress_or_recorder_service_exists(self) -> None:
        for name, service in _services().items():
            haystack = f"{name} {service.get('image', '')}".lower()
            for token in ("egress", "ingress", "recorder"):
                assert token not in haystack, f"{name} looks like a recording service"

    def test_no_volume_anywhere_smells_of_recordings(self) -> None:
        for name, service in _services().items():
            for volume in service.get("volumes", []):
                lowered = str(volume).lower()
                for token in ("record", "audio", "media"):
                    assert token not in lowered, f"{name} mounts {volume}"
