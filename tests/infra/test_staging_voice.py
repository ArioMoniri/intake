"""INT-515 — voice-runtime and a pinned LiveKit SFU on the synthetic host.

Issue #877: *"Add voice-runtime and a pinned LiveKit SFU (with TURN on
443/TLS) to the staging compose."* The orchestrator's brief adds: behind the
existing Caddy; images pinned by digest; the licence from the raw LICENSE blob
recorded in the registry; raw audio never written (tmpfs, no volumes for media,
core dumps off, memory lockable); the RED trigger over the data channel only.

No container runtime exists where this suite runs (CLAUDE.md, memory "no
container runtime anywhere"), so, like ``test_staging_compose.py``, this file
pins what is decidable without booting anything:

- the compose project admits exactly the services it names, the two new ones
  included, and the SFU's media path is the one TLS port Caddy already holds;
- the SFU's configuration is strict-parse-clean against the keys LiveKit
  v1.13.10 declares (an unknown key stops ``livekit-server`` at boot), makes
  recording structurally impossible, and relays only to itself;
- Caddy's layer-4 listener wrapper sends ``turn.<host>`` to the SFU's TURN port
  with the client address in a PROXY header and every other name to the HTTP
  server, and the custom build is pinned to a module checksum;
- the host scripts build, stamp and smoke the new images the way INT-352 does
  the api's;
- ``turn_probe.py`` speaks STUN over TLS correctly (against a local socket).

The host-side run belongs to the merge queue (*"Do NOT deploy"*); nothing here
claims it ran.
"""

from __future__ import annotations

import importlib.util
import json
import re
import socket
import struct
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from intake_probes.registry import ProbeId, load_registry
from test_staging_compose import (
    DEPLOY,
    INIT,
    LIB,
    PINNED,
    REQUIRED_INTERPOLATION,
    SERVICES,
    SHIM_COMMIT,
    SHIM_IMAGE_ID,
    SHIM_SPDX,
    SMOKE,
    _bash,
    _code,
    _compose,
    _docker_calls,
    _env_template,
    _environment,
    _release_dir,
    _run_release,
    _sbom_host,
    _service,
    _sha256,
    _text,
)

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
CADDYFILE = STAGING / "Caddyfile"
LIVEKIT_CONFIG = STAGING / "livekit" / "livekit.yaml"
VOICE_DOCKERFILE = STAGING / "Dockerfile.voice-runtime"
VOICE_DOCKERIGNORE = STAGING / "Dockerfile.voice-runtime.dockerignore"
CADDY_DOCKERFILE = STAGING / "Dockerfile.caddy"
CADDY_DOCKERIGNORE = STAGING / "Dockerfile.caddy.dockerignore"
TURN_PROBE = STAGING / "turn_probe.py"
REGISTRY = REPO / "observability" / "registry.yaml"
RUNBOOK = REPO / "docs" / "runbooks" / "staging.md"

#: The two services this issue adds, beside the INT-345/INT-421 backend.
VOICE_SERVICES = {"voice-runtime", "livekit"}

#: LiveKit v1.13.10, pinned by the index digest resolved from Docker Hub's v2
#: API on 16 Oct 2026 (docs/evidence/INT-515.md). Assembled from its parts.
_LIVEKIT_REPOSITORY = "livekit/livekit-server"
_LIVEKIT_TAG = "v1.13.10"
_LIVEKIT_DIGEST = "sha256:89ca9ce0791e18d6e03bf6e2c49ceb27e1c754eae8bd50c989386c1a5963791a"
LIVEKIT_IMAGE = f"{_LIVEKIT_REPOSITORY}:{_LIVEKIT_TAG}@{_LIVEKIT_DIGEST}"

#: The caddy image staging ran before this issue (INT-345), now the runtime
#: stage of Dockerfile.caddy. Assembled from its parts like the image above, so
#: this file holds no whole reference for Renovate to own.
_CADDY_RUNTIME_REPOSITORY = "caddy"
_CADDY_TAG = "2.11.4-alpine"
_CADDY_RUNTIME_DIGEST = "sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b"

#: The SFU's fixed address on the media network, and Caddy's: the TURN relay
#: may reach only the first, and only the second may send a PROXY header.
MEDIA_SUBNET = "10.47.115.0/24"
LIVEKIT_ADDRESS = "10.47.115.10"
CADDY_ADDRESS = "10.47.115.20"

#: The caddy-l4 module, by version and go.sum checksum (sum.golang.org,
#: read 16 Oct 2026). The build refuses a binary that does not carry exactly
#: this line in its build info.
CADDY_L4_MODULE = "github.com/mholt/caddy-l4"
CADDY_L4_VERSION = "v0.1.2"
CADDY_L4_SUM = "h1:23rhxVar8F5Sl7sYKDgEReI1yT//+e8J7EtMwO2yJpU="

#: Every key LiveKit v1.13.10 declares at the levels this config uses, read
#: from pkg/config/config.go and mediatransportutil's rtcconfig at the commit
#: v1.13.10 pins. ``livekit-server`` decodes with KnownFields(true): a key
#: outside these sets refuses to start.
LIVEKIT_TOP_LEVEL = {
    "port", "bind_addresses", "prometheus_port", "prometheus", "debug_handler", "webtransport",
    "rtc", "redis", "audio", "video", "room", "turn", "ingress", "sip", "webhook",
    "node_selector", "key_file", "keys", "region", "signal_relay", "psrpc", "log_level",
    "logging", "limit", "agents", "development", "metric", "trace", "node_stats",
    "enable_data_tracks", "enable_participant_data_blob", "api",
}  # fmt: skip
LIVEKIT_RTC_KEYS = {
    "udp_port", "tcp_port", "port_range_start", "port_range_end", "use_stun_port_as_ice",
    "node_ip", "stun_servers", "use_external_ip", "require_ipv4", "skip_external_ip_validation",
    "advertise_internal_ip", "use_ice_lite", "interfaces", "ips", "enable_loopback_candidate",
    "use_mdns", "external_ip_only", "batch_io", "turn_servers", "enable_warp",
    "packet_buffer_size", "packet_buffer_size_video", "packet_buffer_size_audio",
    "pli_throttle", "congestion_control", "allow_tcp_fallback", "tcp_fallback_rtt_threshold",
    "allow_udp_unstable_fallback",
}  # fmt: skip
LIVEKIT_ROOM_KEYS = {
    "auto_create", "enabled_codecs", "max_participants", "empty_timeout", "departure_timeout",
}  # fmt: skip
LIVEKIT_TURN_KEYS = {
    "enabled", "domain", "cert_file", "key_file", "tls_port", "udp_port", "relay_range_start",
    "relay_range_end", "external_tls", "bind_addresses", "proxy_protocol",
    "proxy_protocol_trusted_cidrs", "per_user_relay_allocation_limit", "ttl_seconds",
    "allow_restricted_peer_cidrs", "deny_peer_cidrs",
}  # fmt: skip

#: The voice runtime's SBOM stamp: its own image, its own SBOM (INT-352's rule).
VOICE_SBOM_STAMP = "INTAKE_VOICE_RUNTIME_SBOM_DIGEST"


def _livekit_images(services: dict[str, Any]) -> list[str]:
    return [
        str(service.get("image", ""))
        for service in services.values()
        if str(service.get("image", "")).startswith("livekit/")
    ]


def _livekit_config() -> dict[str, Any]:
    loaded = yaml.safe_load(_text(LIVEKIT_CONFIG))
    assert isinstance(loaded, dict)
    return loaded


def _site(host: str) -> str:
    text = _text(CADDYFILE)
    assert f"\n{host} {{" in text, host
    return text.split(f"\n{host} {{", 1)[1].split("\n}", 1)[0]


def _global_options() -> str:
    text = _text(CADDYFILE)
    start = text.index("\n{\n")
    return text[start : text.index("\n}\n", start)]


def _load_turn_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("turn_probe", TURN_PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["turn_probe"] = module
    spec.loader.exec_module(module)
    return module


def _dockerfile(path: Path) -> list[tuple[str, str]]:
    joined: list[str] = []
    buffer = ""
    for line in _text(path).splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or (not buffer and not stripped):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        joined.append(buffer + stripped)
        buffer = ""
    return [(s.partition(" ")[0].upper(), s.partition(" ")[2].strip()) for s in joined]


# --- the services set ------------------------------------------------------------------


class TestServicesSet:
    def test_the_compose_admits_exactly_these_services(self) -> None:
        """Issue #877's first test. The set is the INT-345/INT-421 backend plus
        the two this issue adds, and nothing else: no egress, ingress, recorder
        or agent-dispatch service rides in with the SFU."""
        assert VOICE_SERVICES <= SERVICES
        assert set(_compose()["services"]) == SERVICES

    def test_near_miss_a_recorder_would_be_refused_by_the_same_check(self) -> None:
        widened = {*SERVICES, "egress"}
        assert widened != set(_compose()["services"])

    def test_no_service_records_or_ingests_media(self) -> None:
        """LiveKit's egress (recording), ingress and SIP workers are separate
        images; the only LiveKit image here is the server. (INT-442's
        `egress-proxy` is a forward proxy for API calls, not a media worker.)"""
        assert _livekit_images(_compose()["services"]) == [LIVEKIT_IMAGE]

    @pytest.mark.parametrize("worker", ["livekit/egress", "livekit/ingress", "livekit/sip"])
    def test_near_miss_a_recording_worker_is_caught(self, worker: str) -> None:
        services = {**_compose()["services"], "recorder": {"image": f"{worker}:v1.0.0"}}
        assert _livekit_images(services) != [LIVEKIT_IMAGE]


# --- the SFU ------------------------------------------------------------------------------


class TestSfuService:
    def test_runs_the_pinned_image(self) -> None:
        livekit = _service("livekit")
        assert livekit["image"] == LIVEKIT_IMAGE
        assert PINNED.match(livekit["image"])
        assert "build" not in livekit

    def test_runs_the_committed_config_read_only(self) -> None:
        livekit = _service("livekit")
        assert livekit["command"] == ["--config", "/etc/livekit/livekit.yaml"]
        assert livekit["volumes"] == ["./livekit/livekit.yaml:/etc/livekit/livekit.yaml:ro"]

    def test_mounts_nothing_writable_and_no_named_volume(self) -> None:
        """Invariant 3: there is nowhere for the SFU to write a media frame."""
        livekit = _service("livekit")
        for volume in livekit["volumes"]:
            assert str(volume).endswith(":ro"), volume
            assert str(volume).startswith("./"), "no named volume"
        assert livekit["read_only"] is True
        assert livekit["tmpfs"] == ["/tmp:noexec,nosuid,size=8m"]  # noqa: S108 — a mount spec

    def test_is_unprivileged_with_core_dumps_off(self) -> None:
        livekit = _service("livekit")
        assert livekit["user"] == "65534:65534"
        assert livekit["cap_drop"] == ["ALL"]
        assert "cap_add" not in livekit
        assert "no-new-privileges:true" in livekit["security_opt"]
        assert livekit["ulimits"]["core"] == 0

    def test_publishes_no_port_and_sits_on_the_internal_media_network_only(self) -> None:
        livekit = _service("livekit")
        assert "ports" not in livekit
        networks = _compose()["networks"]
        assert set(livekit["networks"]) == {"media"}
        assert livekit["networks"]["media"]["ipv4_address"] == LIVEKIT_ADDRESS
        media = networks["media"]
        assert media["internal"] is True
        assert media["ipam"]["config"] == [{"subnet": MEDIA_SUBNET, "ip_range": "10.47.115.128/25"}]

    def test_keys_are_required_host_secrets_never_a_default(self) -> None:
        keys = _environment(_service("livekit"))["LIVEKIT_KEYS"]
        assert keys == "${LIVEKIT_API_KEY:?run init.sh}: ${LIVEKIT_API_SECRET:?run init.sh}"
        template = _env_template()
        assert template["LIVEKIT_API_KEY"] == "" and template["LIVEKIT_API_SECRET"] == ""

    def test_the_turn_domain_is_the_hosts_turn_name(self) -> None:
        env = _environment(_service("livekit"))
        assert env["LIVEKIT_TURN_DOMAIN"] == "turn.${STAGING_HOSTNAME:?run init.sh}"

    def test_has_a_healthcheck_on_its_own_listener(self) -> None:
        check = _service("livekit")["healthcheck"]["test"]
        assert check == ["CMD", "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:7880/"]


class TestSfuConfig:
    def test_every_key_is_one_livekit_declares(self) -> None:
        """LiveKit decodes strictly: an unknown key is a server that never starts."""
        config = _livekit_config()
        assert set(config) <= LIVEKIT_TOP_LEVEL
        assert set(config["rtc"]) <= LIVEKIT_RTC_KEYS
        assert set(config["room"]) <= LIVEKIT_ROOM_KEYS
        assert set(config["turn"]) <= LIVEKIT_TURN_KEYS

    def test_near_miss_a_misspelt_key_is_caught(self) -> None:
        assert "external_tls_termination" not in LIVEKIT_TURN_KEYS
        assert "tls-port" not in LIVEKIT_TURN_KEYS

    def test_recording_ingress_and_webhooks_are_structurally_absent(self) -> None:
        """No redis bus means no egress or ingress worker can register; no
        webhook means no event leaves the SFU (invariant 3, as INT-090's dev tier)."""
        config = _livekit_config()
        for key in (
            "redis",
            "ingress",
            "webhook",
            "sip",
            "psrpc",
            "signal_relay",
            "keys",
            "key_file",
        ):
            assert key not in config, key

    def test_the_room_is_audio_only_ephemeral_and_small(self) -> None:
        room = _livekit_config()["room"]
        assert room["enabled_codecs"] == [{"mime": "audio/opus"}]
        assert room["max_participants"] == 4
        assert room["empty_timeout"] == 300 and room["departure_timeout"] == 20

    def test_media_reaches_the_sfu_only_through_turn_over_tls(self) -> None:
        """Only Caddy publishes ports, and only 80/443 TCP (the security group
        admits nothing else). ICE-over-TCP is off, UDP TURN is off, and the SFU
        never advertises a public address it does not have."""
        config = _livekit_config()
        rtc = config["rtc"]
        assert rtc["tcp_port"] == 0
        assert rtc["udp_port"] == 7882
        assert rtc["use_external_ip"] is False
        assert rtc["node_ip"] == LIVEKIT_ADDRESS
        turn = config["turn"]
        assert turn["enabled"] is True
        assert turn["udp_port"] == 0
        assert turn["tls_port"] == 5349
        assert turn["external_tls"] is True

    def test_the_relay_reaches_the_sfu_and_nothing_else(self) -> None:
        """LiveKit denies relays to private addresses unless allowed; the one
        allowed peer is the SFU itself (and v1.13.10 further limits a relay to
        this host to its media ports, #4992)."""
        turn = _livekit_config()["turn"]
        assert turn["allow_restricted_peer_cidrs"] == [f"{LIVEKIT_ADDRESS}/32"]
        assert 0 < turn["relay_range_end"] - turn["relay_range_start"] <= 64

    def test_only_caddy_may_state_the_client_address(self) -> None:
        turn = _livekit_config()["turn"]
        assert turn["proxy_protocol"] is True
        assert turn["proxy_protocol_trusted_cidrs"] == [f"{CADDY_ADDRESS}/32"]

    def test_the_sfu_logs_no_client_network_details(self) -> None:
        """Invariant 6: info-level join lines carry the client's address."""
        assert _livekit_config()["logging"] == {"level": "warn"}

    def test_the_relay_range_is_not_published(self) -> None:
        for name, service in _compose()["services"].items():
            for mapping in service.get("ports", []):
                assert "3000" not in str(mapping), (name, mapping)


# --- the edge -----------------------------------------------------------------------------


class TestEdge:
    def test_caddy_is_built_from_the_pinned_base_with_the_layer4_module(self) -> None:
        caddy = _service("caddy")
        assert caddy["image"] == "intake-staging/caddy:${INTAKE_GIT_SHA:?set by deploy.sh}"
        assert caddy["build"] == {
            "context": "../..",
            "dockerfile": "infra/staging/Dockerfile.caddy",
        }
        froms = [
            args for instruction, args in _dockerfile(CADDY_DOCKERFILE) if instruction == "FROM"
        ]
        assert len(froms) == 2
        builder, runtime = froms
        assert builder.startswith("caddy:2.11.4-builder-alpine@sha256:") and builder.endswith(
            " AS build"
        )
        assert PINNED.match(builder.split()[0])
        # the runtime is the very image staging ran before this issue
        assert runtime == f"{_CADDY_RUNTIME_REPOSITORY}:{_CADDY_TAG}@{_CADDY_RUNTIME_DIGEST}"

    def test_the_module_is_pinned_and_its_checksum_is_verified_in_the_build(self) -> None:
        runs = " ".join(
            args for instruction, args in _dockerfile(CADDY_DOCKERFILE) if instruction == "RUN"
        )
        assert f"--with {CADDY_L4_MODULE}@{CADDY_L4_VERSION}" in runs
        assert "xcaddy build v2.11.4" in runs
        assert CADDY_L4_SUM in runs, "the build refuses a binary without this exact go.sum line"
        assert "build-info" in runs

    def test_the_build_context_is_empty(self) -> None:
        assert _text(CADDY_DOCKERIGNORE).strip().splitlines()[-1] == "*"
        assert not [line for line in _text(CADDY_DOCKERIGNORE).splitlines() if line.startswith("!")]

    def test_caddy_holds_a_fixed_address_on_the_media_network(self) -> None:
        caddy = _service("caddy")
        assert caddy["networks"]["media"] == {"ipv4_address": CADDY_ADDRESS}
        assert {"public", "edge"} <= set(caddy["networks"])

    def test_turn_rides_the_https_port_through_the_layer4_wrapper(self) -> None:
        options = _global_options()
        assert "servers :443 {" in options
        assert "protocols h1 h2" in options, "no HTTP/3: 443/udp is not published"
        wrappers = options.split("listener_wrappers {", 1)[1]
        assert re.search(r"@turn tls sni turn\.\{\$STAGING_HOSTNAME\}", wrappers)
        route = wrappers.split("route @turn {", 1)[1].split("\n\t\t\t\t}", 1)[0]
        lines = [line.strip() for line in route.splitlines() if line.strip()]
        # TLS ends at Caddy with the turn name's own certificate …
        assert lines[0] == "tls"
        # … and the plain TURN stream goes to the SFU with the client address
        assert "proxy_protocol v2" in lines
        assert "upstream tcp/livekit:5349" in lines
        # every other name falls through to the HTTP server's own TLS
        assert re.search(r"\n\t\t\ttls\n\t\t\}", options), "the tls wrapper follows layer4"

    def test_near_miss_an_unqualified_servers_block_would_shadow_the_wrapper(self) -> None:
        """Caddy applies the first ``servers`` block that matches a listener, so
        an unqualified one before ``:443`` would silently drop the wrapper."""
        assert "\tservers {" not in _global_options()

    def test_the_turn_name_gets_a_certificate_and_serves_nothing_over_http(self) -> None:
        site = _site("turn.{$STAGING_HOSTNAME}")
        assert "disable_tlsalpn_challenge" in site
        assert "respond 404" in site
        assert "reverse_proxy" not in site

    def test_the_signalling_host_routes_only_the_rtc_paths(self) -> None:
        site = _site("rtc.{$STAGING_HOSTNAME}")
        assert 'X-Intake-Environment "staging-synthetic-only"' in site
        # the auth site's shape: refuse what is not public, proxy the rest.
        # (respond sorts before reverse_proxy in Caddy's directive order, so an
        # unmatched `respond 404` would answer every request)
        assert re.search(r"@not_signal not path /rtc /rtc/\*\n", site)
        assert "respond @not_signal 404" in site
        assert re.findall(r"reverse_proxy (\S+)", site) == ["livekit:7880"]
        assert not re.search(r"^\s*respond 404\s*$", site, re.M), (
            "an unmatched respond shadows the proxy"
        )
        assert "/twirp" not in site

    def test_no_new_port_is_published(self) -> None:
        published = {str(mapping) for mapping in _service("caddy")["ports"]}
        assert published == {"80:80", "443:443"}
        for name in VOICE_SERVICES:
            assert "ports" not in _service(name), name


# --- the voice runtime --------------------------------------------------------------------


class TestVoiceRuntimeService:
    def test_runs_the_image_built_from_this_commit(self) -> None:
        voice = _service("voice-runtime")
        assert voice["image"] == "intake-staging/voice-runtime:${INTAKE_GIT_SHA:?set by deploy.sh}"
        assert voice["build"]["dockerfile"] == "infra/staging/Dockerfile.voice-runtime"
        assert voice["build"]["args"] == {
            "GIT_SHA": "${INTAKE_GIT_SHA:?set by deploy.sh}",
            "BUILT_AT": "${INTAKE_BUILT_AT:?set by deploy.sh}",
        }

    def test_raw_audio_has_nowhere_to_land(self) -> None:
        """Invariant 3 at deploy time: a read-only root, a small noexec tmpfs,
        no volume of any kind, core dumps off and memory lockable."""
        voice = _service("voice-runtime")
        assert "volumes" not in voice
        assert voice["read_only"] is True
        assert voice["tmpfs"] == ["/tmp:noexec,nosuid,size=16m"]  # noqa: S108 — a mount spec
        assert voice["ulimits"] == {"core": 0, "memlock": -1}
        assert voice["cap_drop"] == ["ALL"]
        assert "cap_add" not in voice
        assert "no-new-privileges:true" in voice["security_opt"]

    def test_reaches_redis_and_the_sfu_only(self) -> None:
        voice = _service("voice-runtime")
        assert set(voice["networks"]) == {"backend", "media"}
        networks = _compose()["networks"]
        for network in voice["networks"]:
            assert networks[network]["internal"] is True, network
        assert "ports" not in voice

    def test_staging_posture_and_stores(self) -> None:
        env = _environment(_service("voice-runtime"))
        assert env["INTAKE_ENV"] == "staging"
        assert env["INTAKE_LIVEKIT_URL"] == "http://livekit:7880"
        for key in (
            "INTAKE_VOICE_CONTROL_REDIS_URL",
            "INTAKE_SAFETY_INBOX_REDIS_URL",
            "INTAKE_MODEL_LANES_REDIS_URL",
        ):
            assert env[key] == "redis://:${REDIS_PASSWORD:?run init.sh}@redis:6379/0", key
        for key in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
            assert REQUIRED_INTERPOLATION.match(env[key]), key

    def test_no_vendor_lane_and_no_proxy_is_configured_here(self) -> None:
        """The hosted lanes arrive with #751/#774/#775 and their egress change is
        the owner's patch (owner-515-egress.patch), never this file. Until then
        nothing here names a speech endpoint, a proxy or a recorded fixture."""
        env = _environment(_service("voice-runtime"))
        for key in env:
            assert not key.startswith(("INTAKE_TTS_", "INTAKE_ASR_", "INTAKE_EXTRACTION_")), key
            assert "PROXY" not in key and "RECORDED" not in key, key
        assert "outbound" not in _service("voice-runtime")["networks"]

    def test_the_sbom_stamp_is_its_own_required_digest(self) -> None:
        env = _environment(_service("voice-runtime"))
        assert (
            env["INTAKE_SBOM_DIGEST"]
            == "${INTAKE_VOICE_RUNTIME_SBOM_DIGEST:?set by deploy.sh from the release SBOM}"
        )
        assert VOICE_SBOM_STAMP not in _env_template()

    def test_starts_after_the_store_and_the_sfu_are_healthy(self) -> None:
        depends = _service("voice-runtime")["depends_on"]
        assert depends == {
            "redis": {"condition": "service_healthy"},
            "livekit": {"condition": "service_healthy"},
        }

    def test_the_api_reads_the_inbox_the_runtime_writes_and_mints_room_tokens(self) -> None:
        env = _environment(_service("api"))
        assert (
            env["INTAKE_SAFETY_INBOX_REDIS_URL"]
            == "redis://:${REDIS_PASSWORD:?run init.sh}@redis:6379/0"
        )
        assert env["INTAKE_LIVEKIT_PUBLIC_URL"] == "wss://rtc.${STAGING_HOSTNAME:?run init.sh}"
        for key in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
            assert REQUIRED_INTERPOLATION.match(env[key]), key


class TestVoiceRuntimeImage:
    def test_bases_are_pinned_and_the_lock_is_frozen(self) -> None:
        instructions = _dockerfile(VOICE_DOCKERFILE)
        aliases = {args.split()[-1] for i, args in instructions if i == "FROM" and " AS " in args}
        for instruction, args in instructions:
            if instruction == "FROM":
                assert PINNED.match(args.split()[0]), args
            if instruction == "COPY" and "--from=" in args:
                source = re.search(r"--from=(\S+)", args)
                assert source and (source.group(1) in aliases or PINNED.match(source.group(1)))
        runs = " ".join(args for i, args in instructions if i == "RUN")
        assert "uv sync --frozen --no-dev --package intake-voice-runtime" in runs
        assert "--require-hashes" in runs

    def test_the_process_is_the_serve_factory_as_a_non_root_user(self) -> None:
        instructions = _dockerfile(VOICE_DOCKERFILE)
        users = [args for i, args in instructions if i == "USER"]
        assert users == ["10001:10001"]
        (cmd,) = [args for i, args in instructions if i == "CMD"]
        assert json.loads(cmd) == [
            "uvicorn",
            "intake_voice_runtime.serve:app_from_env",
            "--factory",
            "--host",
            "0.0.0.0",  # noqa: S104 — the container's own interfaces; no port is published
            "--port",
            "8100",
            "--no-server-header",
        ]

    def test_a_build_without_real_stamps_is_refused(self) -> None:
        runs = " ".join(args for i, args in _dockerfile(VOICE_DOCKERFILE) if i == "RUN")
        assert 'if [ -z "$GIT_SHA" ] || [ "$GIT_SHA" = "dev" ]' in runs

    def test_the_build_context_denies_by_default_and_never_sends_a_secret(self) -> None:
        lines = _text(VOICE_DOCKERIGNORE).splitlines()
        assert lines[[line.strip() for line in lines].index("*")] == "*"
        for denied in ("**/.env", "**/.env.*", "**/.git"):
            assert denied in lines, denied


# --- the host scripts ---------------------------------------------------------------------


class TestHostScripts:
    def test_deploy_and_init_build_and_stamp_the_runtime_before_any_compose_call(self) -> None:
        for script in (INIT, DEPLOY):
            code = _code(script)
            order = [
                code.index(step)
                for step in (
                    "build_api_image",
                    "build_voice_runtime_image",
                    "stamp_sbom",
                    "stamp_voice_runtime_sbom",
                )
            ]
            assert order == sorted(order), script.name
            assert order[-1] < code.index("compose "), script.name

    def test_deploy_builds_the_edge_before_it_recreates_it(self) -> None:
        code = _code(DEPLOY)
        assert code.index("build_caddy_image") < code.index("compose up -d --no-build")

    def test_every_compose_build_carries_both_build_time_values(self) -> None:
        builds = [
            line.strip()
            for path in (LIB,)
            for line in _code(path).splitlines()
            if re.search(r"\bcompose build\b", line)
        ]
        assert len(builds) == 5
        for build in builds:
            assert 'INTAKE_VOICE_RUNTIME_SBOM_DIGEST="$SBOM_DIGEST_DURING_BUILD"' in build, build

    def test_smoke_stamps_from_disk_and_checks_the_voice_tier(self) -> None:
        code = _code(SMOKE)
        assert code.index("stamp_voice_runtime_sbom_from_disk") < code.index("compose ")
        for needle in (
            "turn_probe.py",
            "/rtc/validate",
            "/twirp/livekit.RoomService/ListParticipants",
            "/probe/synthetic-turn",
            "voice-runtime",
        ):
            assert needle in code, needle

    def test_the_runbook_has_the_voice_section(self) -> None:
        text = _text(RUNBOOK)
        section = text.split("## Voice runtime and SFU (INT-515)", 1)[1].split("\n## ", 1)[0]
        for needle in ("./init.sh", "turn.", "rtc.", "443", "LIVEKIT_API_KEY", "owner-515"):
            assert needle in section, needle


class TestVoiceRuntimeSbom:
    def test_stamp_writes_the_runtime_sbom_beside_the_apis(self, tmp_path: Path) -> None:
        bin_dir = _sbom_host(tmp_path)
        result = _run_release(
            tmp_path,
            bin_dir,
            "stamp_voice_runtime_sbom; "
            'printf "%s\\n%s\\n" "$INTAKE_VOICE_RUNTIME_SBOM_DIGEST" "$VOICE_RUNTIME_SBOM_FILE"',
        )
        assert result.returncode == 0, result.stderr
        digest, sbom_file = result.stdout.split()
        sbom = Path(sbom_file)
        hex_id = SHIM_IMAGE_ID.removeprefix("sha256:")
        assert sbom == _release_dir(tmp_path) / f"voice-runtime-{hex_id}.spdx.json"
        assert sbom.read_text(encoding="utf-8") == SHIM_SPDX
        assert digest == _sha256(sbom)
        saves = [s for s in _docker_calls(tmp_path, "image") if s.startswith("image save ")]
        assert saves[-1].endswith(f"intake-staging/voice-runtime:{SHIM_COMMIT}")

    def test_no_runtime_sbom_refuses_the_release(self, tmp_path: Path) -> None:
        bin_dir = _sbom_host(tmp_path, "fail")
        result = _run_release(tmp_path, bin_dir, "stamp_voice_runtime_sbom")
        assert result.returncode != 0
        assert "refusing" in result.stderr

    def test_smoke_reads_the_runtime_sbom_and_never_writes_one(self, tmp_path: Path) -> None:
        bin_dir = _sbom_host(tmp_path)
        assert _run_release(tmp_path, bin_dir, "stamp_voice_runtime_sbom").returncode == 0
        (tmp_path / "syft-mode").write_text("fail", encoding="utf-8")
        result = _run_release(
            tmp_path,
            bin_dir,
            'stamp_voice_runtime_sbom_from_disk; printf "%s" "$INTAKE_VOICE_RUNTIME_SBOM_DIGEST"',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith("sha256:")
        assert len(_docker_calls(tmp_path, "run")) == 1

    def test_the_api_sbom_path_is_unchanged(self, tmp_path: Path) -> None:
        bin_dir = _sbom_host(tmp_path)
        result = _run_release(tmp_path, bin_dir, 'stamp_sbom; printf "%s" "$SBOM_FILE"')
        assert result.returncode == 0, result.stderr
        assert Path(result.stdout).name == f"api-{SHIM_IMAGE_ID.removeprefix('sha256:')}.spdx.json"

    def test_the_build_value_never_outlives_the_build(self, tmp_path: Path) -> None:
        bin_dir = _sbom_host(tmp_path)
        result = _run_release(
            tmp_path,
            bin_dir,
            'build_voice_runtime_image; printf "[%s]" "${INTAKE_VOICE_RUNTIME_SBOM_DIGEST-unset}"',
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == "[unset]"
        (build,) = _docker_calls(tmp_path, "compose")
        assert build.endswith(" build voice-runtime")

    def test_the_caddy_build_is_one_compose_build(self, tmp_path: Path) -> None:
        bin_dir = _sbom_host(tmp_path)
        assert _run_release(tmp_path, bin_dir, "build_caddy_image").returncode == 0
        (build,) = _docker_calls(tmp_path, "compose")
        assert build.endswith(" build caddy")


# --- the TURN probe smoke.sh runs from the host --------------------------------------------


class TestTurnProbe:
    def test_a_binding_request_is_a_well_formed_stun_header(self) -> None:
        probe = _load_turn_probe()
        transaction = bytes(range(12))
        request = probe.binding_request(transaction)
        assert len(request) == 20
        kind, length, cookie = struct.unpack("!HHI", request[:8])
        assert (kind, length, cookie) == (0x0001, 0, 0x2112A442)
        assert request[8:] == transaction

    def test_a_success_response_with_the_same_transaction_is_accepted(self) -> None:
        probe = _load_turn_probe()
        transaction = bytes(range(12))
        response = struct.pack("!HHI", 0x0101, 0, 0x2112A442) + transaction
        assert probe.is_binding_success(response, transaction) is True

    @pytest.mark.parametrize(
        "response",
        [
            struct.pack("!HHI", 0x0111, 0, 0x2112A442) + bytes(range(12)),  # error response
            struct.pack("!HHI", 0x0101, 0, 0x2112A442) + bytes(12),  # another transaction
            struct.pack("!HHI", 0x0101, 0, 0xDEADBEEF) + bytes(range(12)),  # no magic cookie
            b"HTTP/1.1 400 Bad Request\r\n\r\n",  # an HTTP server answered instead
            b"",
        ],
    )
    def test_anything_else_is_refused(self, response: bytes) -> None:
        probe = _load_turn_probe()
        assert probe.is_binding_success(response, bytes(range(12))) is False

    def test_the_exchange_runs_over_a_stream(self) -> None:
        """Against a local socket standing in for the SFU behind Caddy: the
        probe writes one Binding request and reads one success."""
        probe = _load_turn_probe()
        server, client = socket.socketpair()

        def sfu() -> None:
            request = server.recv(20)
            server.sendall(struct.pack("!HHI", 0x0101, 0, 0x2112A442) + request[8:20])
            server.close()

        thread = threading.Thread(target=sfu)
        thread.start()
        try:
            assert probe.stun_binding(client, transaction=bytes(range(12))) is True
        finally:
            client.close()
            thread.join(timeout=5)

    def test_main_reports_a_refused_connection_without_raising(self) -> None:
        probe = _load_turn_probe()
        with socket.socket() as unused:
            unused.bind(("127.0.0.1", 0))
            port = unused.getsockname()[1]
        assert (
            probe.main(
                ["--connect", "127.0.0.1", "--port", str(port), "--sni", "turn.example.test"]
            )
            == 1
        )


# --- the in-container probe smoke.sh runs ---------------------------------------------------


VOICE_PROBE = STAGING / "voice_probe.py"


def _load_voice_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("voice_probe", VOICE_PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["voice_probe"] = module
    spec.loader.exec_module(module)
    return module


class _Answer:
    def __init__(self, status: int, body: object) -> None:
        self.status = status
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _opener(status: int, body: object, seen: list[tuple[str, str]] | None = None) -> Any:
    import urllib.error

    def open_(request: Any, timeout: float) -> _Answer:
        if seen is not None:
            seen.append((request.get_method(), request.full_url))
        if status >= 400:
            raise urllib.error.HTTPError(
                request.full_url,
                status,
                "refused",
                {},
                _Answer(status, body),  # type: ignore[arg-type]
            )
        return _Answer(status, body)

    return open_


class TestVoiceProbe:
    def test_it_asks_the_runtime_on_loopback_only(self) -> None:
        probe = _load_voice_probe()
        seen: list[tuple[str, str]] = []
        probe.main(["turn"], _opener(200, {"completed": True, "stages": []}, seen))
        probe.main(["readyz"], _opener(200, {"checks": {"sfu": "ok"}}, seen))
        assert seen == [
            ("POST", "http://127.0.0.1:8100/probe/synthetic-turn"),
            ("GET", "http://127.0.0.1:8100/readyz"),
        ]

    def test_readyz_names_only_the_failing_checks(self, capsys: pytest.CaptureFixture[str]) -> None:
        probe = _load_voice_probe()
        body = {"checks": {"sfu": "ok", "lane_asr": "error", "lane_tts": "error"}}
        assert probe.main(["readyz"], _opener(503, body)) == 1
        assert capsys.readouterr().out.strip() == "not ready: lane_asr, lane_tts"
        assert probe.main(["readyz"], _opener(200, {"checks": {"sfu": "ok"}})) == 0

    def test_a_completed_turn_passes_and_a_stopped_one_names_its_stage(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        probe = _load_voice_probe()
        done = {"completed": True, "stages": [{"stage": "extract", "ok": True, "latency_ms": 9.5}]}
        assert probe.main(["turn"], _opener(200, done)) == 0
        stopped = {
            "completed": False,
            "stages": [{"stage": "transcribe", "ok": False, "latency_ms": 1.0, "code": "unbound"}],
        }
        assert probe.main(["turn"], _opener(503, stopped)) == 1
        assert capsys.readouterr().out.splitlines()[-1] == "turn stopped at transcribe: unbound"

    def test_the_rate_limit_is_its_own_exit_code(self) -> None:
        probe = _load_voice_probe()
        assert probe.main(["turn"], _opener(429, {"code": "probe_rate_limited"})) == 2

    def test_healthz_and_an_unknown_command(self) -> None:
        probe = _load_voice_probe()
        assert probe.main(["healthz"], _opener(200, {"status": "alive"})) == 0
        assert probe.main(["healthz"], _opener(503, {})) == 1
        assert probe.main(["nonsense"], _opener(200, {})) == 64


# --- the registry rows --------------------------------------------------------------------


class TestRegistry:
    def test_the_sfu_row_records_the_raw_licence_blob_and_the_image(self) -> None:
        row = next(
            entry for entry in load_registry(REGISTRY) if entry.component == "livekit-server"
        )
        assert row.image == LIVEKIT_IMAGE
        assert row.license == "Apache-2.0"
        assert row.licence_blob_url == (
            "https://raw.githubusercontent.com/livekit/livekit/"
            "e5655ac20267fa5005dccaf3f0e3bfc3ea688c07/LICENSE"
        )
        assert row.licence_blob_sha256 == (
            "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
        )
        assert row.licence_verified_at is not None
        assert row.probe is ProbeId.LIVEKIT_ROOM_JOIN
        assert row.phi_path is True and row.self_hostable is True
        # the synthetic host is not a PHI deployment: the row stays planned
        assert row.self_hosted_now is False
        assert row.licence_note and "turn-detector" in row.licence_note

    def test_the_runtime_row_carries_the_synthetic_turn_probe(self) -> None:
        row = next(entry for entry in load_registry(REGISTRY) if entry.component == "voice-runtime")
        assert row.probe is ProbeId.VOICE_SYNTHETIC_TURN
        assert row.self_hosted_now is False
        assert "infra/staging/compose.yaml" in row.host


def test_the_template_carries_the_two_livekit_keys_and_lib_generates_them(tmp_path: Path) -> None:
    from test_staging_compose import _generate_env_file, _read_env_file

    env_file = tmp_path / ".env"
    env_file.write_text("STAGING_HOSTNAME=203-0-113-7.sslip.io\n", encoding="utf-8")
    result = _generate_env_file(env_file)
    assert result.returncode == 0, result.stderr
    values = _read_env_file(env_file)
    for key in ("LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        assert re.fullmatch(r"[0-9a-f]{64}", values[key]), key
    assert values["LIVEKIT_API_KEY"] != values["LIVEKIT_API_SECRET"]


def test_lib_names_the_runtime_image_repository() -> None:
    assert _bash('printf "%s" "$VOICE_RUNTIME_IMAGE_REPO"').stdout == "intake-staging/voice-runtime"
