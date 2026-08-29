"""INT-023 — feature-flag facade contract (CLAUDE.md inv. 12/18/19; files/10 §5).

Pinned here:
- the in-memory provider is the DEFAULT and needs no environment at all;
- the five safety flags (``device_functions``, ``s2s``, ``learning_apply``,
  ``satisfaction_prompts``, ``guardian_link``) exist with False defaults, cannot be defaulted
  open by a careless caller, and cannot be flipped by the Unleash provider
  unless the payload explicitly carries ``enabled: true``;
- the Unleash provider is constructed only when ``INTAKE_UNLEASH_URL`` is
  set, talks the client API within a 200 ms budget, and falls CLOSED to the
  in-memory defaults on every failure mode — a flag backend outage must
  never take a service down or open a gate;
- flag reads are logged as name/value/provider and never echo caller
  context (inv. 6 — no PHI in logs).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
import pytest
from intake_platform.flags import (
    SAFETY_FLAG_DEFAULTS,
    UNLEASH_TIMEOUT_SECONDS,
    InMemoryProvider,
    UnleashProvider,
    default_provider,
)

SAFETY_FLAGS = (
    "device_functions",
    "s2s",
    "learning_apply",
    "satisfaction_prompts",
    "guardian_link",
)
CTX_SENTINEL = "Ahmet Yilmaz 05321234567"  # must never appear in a log line
FLAGS_LOGGER = "intake_platform.flags"


def _unleash(handler: Callable[[httpx.Request], httpx.Response]) -> UnleashProvider:
    return UnleashProvider("http://unleash.internal:4242", transport=httpx.MockTransport(handler))


def _feature(name: str, enabled: object) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"name": name, "enabled": enabled})

    return handler


class TestDefaultProvider:
    def test_in_memory_is_default_without_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("INTAKE_UNLEASH_URL", raising=False)
        provider = default_provider()
        assert isinstance(provider, InMemoryProvider)
        assert provider.get_bool("greeting_v2", True) is True
        assert provider.get_bool("greeting_v2", False) is False

    def test_unleash_constructed_only_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INTAKE_UNLEASH_URL", "http://127.0.0.1:4242")
        provider = default_provider()
        assert isinstance(provider, UnleashProvider)
        provider.close()

    def test_in_memory_seed_wins_over_default_arg(self) -> None:
        provider = InMemoryProvider({"error_reporting": True})
        assert provider.get_bool("error_reporting", False) is True


class TestSafetyFlags:
    def test_all_four_declared_false(self) -> None:
        assert set(SAFETY_FLAGS) == set(SAFETY_FLAG_DEFAULTS)
        for name in SAFETY_FLAGS:
            assert SAFETY_FLAG_DEFAULTS[name] is False

    @pytest.mark.parametrize("name", SAFETY_FLAGS)
    def test_caller_cannot_default_a_safety_flag_open(self, name: str) -> None:
        # even a caller passing default=True gets False: the pre-declared
        # safe default outranks the call-site default.
        assert InMemoryProvider().get_bool(name, True) is False

    @pytest.mark.parametrize("name", SAFETY_FLAGS)
    def test_unleash_error_cannot_open_a_safety_flag(self, name: str) -> None:
        provider = _unleash(lambda request: httpx.Response(500, text="boom"))
        assert provider.get_bool(name, True) is False

    @pytest.mark.parametrize("enabled", ["yes", 1, "true", None])
    def test_non_boolean_payload_cannot_flip_safety_flag(self, enabled: object) -> None:
        provider = _unleash(_feature("device_functions", enabled))
        assert provider.get_bool("device_functions", False) is False

    def test_missing_enabled_field_falls_closed(self) -> None:
        provider = _unleash(lambda request: httpx.Response(200, json={"name": "device_functions"}))
        assert provider.get_bool("device_functions", False) is False

    def test_explicit_enable_in_payload_is_honoured(self) -> None:
        # the ONE path that may open a safety flag: an explicit boolean true.
        provider = _unleash(_feature("device_functions", True))
        assert provider.get_bool("device_functions", False) is True


class TestUnleashContract:
    def test_enabled_true(self) -> None:
        provider = _unleash(_feature("greeting_v2", True))
        assert provider.get_bool("greeting_v2", False) is True

    def test_enabled_false(self) -> None:
        provider = _unleash(_feature("greeting_v2", False))
        assert provider.get_bool("greeting_v2", True) is False

    def test_http_error_returns_default(self) -> None:
        provider = _unleash(lambda request: httpx.Response(503, text="unavailable"))
        assert provider.get_bool("greeting_v2", True) is True
        assert provider.get_bool("greeting_v2", False) is False

    def test_timeout_returns_default(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("deadline exceeded", request=request)

        provider = _unleash(handler)
        assert provider.get_bool("greeting_v2", True) is True

    def test_malformed_json_returns_default(self) -> None:
        provider = _unleash(lambda request: httpx.Response(200, text="<html>"))
        assert provider.get_bool("greeting_v2", True) is True

    def test_non_object_payload_returns_default(self) -> None:
        provider = _unleash(lambda request: httpx.Response(200, json=["greeting_v2"]))
        assert provider.get_bool("greeting_v2", True) is True

    def test_client_api_path_and_token_header(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["auth"] = request.headers.get("Authorization", "")
            return httpx.Response(200, json={"name": "greeting_v2", "enabled": True})

        provider = UnleashProvider(
            "http://unleash.internal:4242",
            token="default:development.unleash-insecure-client-token",
            transport=httpx.MockTransport(handler),
        )
        assert provider.get_bool("greeting_v2", False) is True
        assert seen["path"] == "/api/client/features/greeting_v2"
        assert seen["auth"] == "default:development.unleash-insecure-client-token"

    def test_provider_is_a_context_manager(self) -> None:
        with _unleash(_feature("greeting_v2", True)) as provider:
            assert provider.get_bool("greeting_v2", False) is True

    def test_timeout_budget_is_200ms(self) -> None:
        assert UNLEASH_TIMEOUT_SECONDS == 0.2
        provider = _unleash(_feature("greeting_v2", True))
        assert provider.timeout_seconds == UNLEASH_TIMEOUT_SECONDS


class TestFlagReadLogging:
    def test_read_is_logged_without_ctx_echo(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger=FLAGS_LOGGER):
            InMemoryProvider().get_bool("device_functions", False, ctx={"free_text": CTX_SENTINEL})
        messages = [record.getMessage() for record in caplog.records]
        assert any("device_functions" in m and "in_memory" in m and "False" in m for m in messages)
        assert all(CTX_SENTINEL not in m for m in messages)
        assert all("free_text" not in m for m in messages)

    def test_unleash_read_logs_provider_and_never_ctx(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = _unleash(_feature("greeting_v2", True))
        with caplog.at_level(logging.INFO, logger=FLAGS_LOGGER):
            provider.get_bool("greeting_v2", False, ctx={"free_text": CTX_SENTINEL})
        messages = [record.getMessage() for record in caplog.records]
        assert any("greeting_v2" in m and "unleash" in m for m in messages)
        assert all(CTX_SENTINEL not in m for m in messages)

    def test_ctx_is_never_transmitted_to_unleash(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = request.content.decode("utf-8", errors="replace")
            return httpx.Response(200, json={"name": "greeting_v2", "enabled": True})

        _unleash(handler).get_bool("greeting_v2", False, ctx={"tckn": "10000000146"})
        assert "10000000146" not in seen["url"]
        assert "10000000146" not in seen["body"]
