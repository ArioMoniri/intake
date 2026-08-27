"""INT-023 — GlitchTip wiring is flag-gated and every event is scrubbed
(files/10 §3: the crash reporter is "the leak nobody mentioned"; CLAUDE.md
inv. 6/14).

Pinned here:
- ``setup_error_reporting`` activates ONLY when ``INTAKE_GLITCHTIP_DSN`` is
  set AND the ``error_reporting`` flag is on, and stays a logged no-op when
  sentry-sdk (the protocol GlitchTip speaks) is not installed — the SDK is
  an optional import, never a hard dependency;
- the scrub hook is a pure function: request bodies are dropped entirely,
  message/exception strings pass ``redact_text``, frame locals are dropped,
  and extra/tags keep only the same attribute keys as the log layer.

sentry-sdk is exercised through an injected module object, so these tests
run identically whether or not the real SDK is installed (no skips —
inv. 17). ``include_local_variables=False`` is asserted because files/10 §3
names it as a live defect class: a local ``pcm`` buffer is patient voice.
"""

from __future__ import annotations

import logging
import sys
import types
from typing import Any

import pytest
from intake_platform.errors import (
    ERROR_REPORTING_FLAG,
    scrub_event,
    setup_error_reporting,
)
from intake_platform.flags import InMemoryProvider
from intake_platform.otel import ALLOWED_LOG_ATTRIBUTES

VALID_TCKN = "10000000146"  # checksum-valid synthetic TC Kimlik test number
PHONE = "05321234567"
DSN = "http://f00d@127.0.0.1:8010/1"
ERRORS_LOGGER = "intake_platform.errors"


def _flags_on() -> InMemoryProvider:
    return InMemoryProvider({ERROR_REPORTING_FLAG: True})


class TestScrubHookPureFunction:
    def test_tckn_and_phone_in_exception_message_are_redacted(self) -> None:
        event: dict[str, Any] = {
            "exception": {
                "values": [
                    {
                        "type": "ValueError",
                        "value": f"bad slot value for {VALID_TCKN} call {PHONE}",
                        "stacktrace": {
                            "frames": [{"filename": "worker.py", "vars": {"pcm": "0" * 64}}]
                        },
                    }
                ]
            }
        }
        out = scrub_event(event, None)
        value = out["exception"]["values"][0]["value"]
        assert VALID_TCKN not in value
        assert PHONE not in value
        assert "[TCKN]" in value
        assert "[PHONE]" in value

    def test_frame_locals_are_dropped(self) -> None:
        event: dict[str, Any] = {
            "exception": {
                "values": [
                    {
                        "type": "RuntimeError",
                        "value": "boom",
                        "stacktrace": {
                            "frames": [{"filename": "audio.py", "vars": {"pcm": "raw"}}]
                        },
                    }
                ]
            }
        }
        out = scrub_event(event, None)
        frame = out["exception"]["values"][0]["stacktrace"]["frames"][0]
        assert "vars" not in frame
        assert frame["filename"] == "audio.py"

    def test_message_and_logentry_are_redacted(self) -> None:
        event: dict[str, Any] = {
            "message": f"retry for {PHONE}",
            "logentry": {"message": f"retry for {PHONE} (%s)", "params": [VALID_TCKN]},
        }
        out = scrub_event(event, None)
        assert PHONE not in out["message"]
        assert PHONE not in out["logentry"]["message"]
        assert out["logentry"]["params"] == ["[TCKN]"]

    def test_request_section_is_dropped_entirely(self) -> None:
        event: dict[str, Any] = {
            "message": "err",
            "request": {
                "url": "http://api.internal/intake",
                "data": {"transcript": "hastanin anlattigi her sey"},
                "headers": {"Cookie": "session=abc"},
            },
        }
        out = scrub_event(event, None)
        assert "request" not in out

    def test_user_section_is_dropped(self) -> None:
        out = scrub_event({"user": {"ip_address": "10.0.0.1", "id": "p-1"}}, None)
        assert "user" not in out

    def test_extra_and_tags_keep_only_log_layer_whitelist(self) -> None:
        event: dict[str, Any] = {
            "extra": {
                "tenant_id": "t-izmir-1",
                "note_text": f"hasta {VALID_TCKN} aradi",
                "duration_ms": 42,
            },
            "tags": {"protocol_hash": "abc123", "patient_name": "Ayse"},
        }
        out = scrub_event(event, None)
        assert set(out["extra"]) == {"tenant_id", "duration_ms"}
        assert set(out["tags"]) == {"protocol_hash"}

    def test_whitelist_is_exactly_the_log_layers(self) -> None:
        event: dict[str, Any] = {"extra": {key: "v" for key in ALLOWED_LOG_ATTRIBUTES}}
        out = scrub_event(event, None)
        assert set(out["extra"]) == set(ALLOWED_LOG_ATTRIBUTES)

    def test_malformed_event_shapes_never_raise(self) -> None:
        # the hook runs inside the SDK's send path: a scrub crash would drop
        # the event AND raise in the reporter, so every section tolerates
        # whatever shape arrives and PHI-bearing sections degrade to dropped.
        event: dict[str, Any] = {
            "message": 5,
            "logentry": "not-a-mapping",
            "exception": "boom",
            "breadcrumbs": ["not-a-mapping"],
            "extra": "not-a-mapping",
            "tags": ["not-a-mapping"],
        }
        out = scrub_event(event, None)
        assert out["extra"] == {}
        assert out["tags"] == {}
        assert out["message"] == 5

    def test_partial_exception_and_breadcrumb_entries_are_tolerated(self) -> None:
        event: dict[str, Any] = {
            "exception": {
                "values": [
                    "not-a-mapping",
                    {"type": "OSError", "value": 7, "stacktrace": "not-a-mapping"},
                    {"type": "KeyError"},
                ]
            },
            "breadcrumbs": {
                "values": ["not-a-mapping", {"category": "http"}, {"data": "not-a-mapping"}]
            },
        }
        out = scrub_event(event, None)
        assert out["exception"]["values"][1]["value"] == 7
        assert out["breadcrumbs"]["values"][2]["data"] == {}

    def test_exception_without_values_is_tolerated(self) -> None:
        out = scrub_event({"exception": {}, "breadcrumbs": {}}, None)
        assert out["exception"] == {}

    def test_breadcrumbs_are_redacted_and_data_whitelisted(self) -> None:
        event: dict[str, Any] = {
            "breadcrumbs": {
                "values": [
                    {
                        "message": f"dialing {PHONE}",
                        "data": {"event": "call", "raw_utterance": "sesli metin"},
                    }
                ]
            }
        }
        out = scrub_event(event, None)
        crumb = out["breadcrumbs"]["values"][0]
        assert PHONE not in crumb["message"]
        assert set(crumb["data"]) == {"event"}


class TestSetupGating:
    def test_no_dsn_means_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("INTAKE_GLITCHTIP_DSN", raising=False)
        assert setup_error_reporting(_flags_on()) is False

    def test_flag_off_means_off_even_with_dsn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INTAKE_GLITCHTIP_DSN", DSN)
        # InMemoryProvider with no seed: error_reporting defaults to False.
        assert setup_error_reporting(InMemoryProvider()) is False

    def test_missing_sdk_is_a_logged_noop(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("INTAKE_GLITCHTIP_DSN", DSN)
        monkeypatch.setitem(sys.modules, "sentry_sdk", None)  # forces ImportError
        with caplog.at_level(logging.INFO, logger=ERRORS_LOGGER):
            assert setup_error_reporting(_flags_on()) is False
        assert any("sentry-sdk" in record.getMessage() for record in caplog.records)

    def test_activation_wires_scrub_and_disables_locals(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INTAKE_GLITCHTIP_DSN", DSN)
        recorded: dict[str, Any] = {}
        fake_sdk = types.SimpleNamespace(init=lambda **options: recorded.update(options))
        monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)
        assert setup_error_reporting(_flags_on()) is True
        assert recorded["dsn"] == DSN
        assert recorded["before_send"] is scrub_event
        assert recorded["include_local_variables"] is False  # files/10 §3
        assert recorded["send_default_pii"] is False
        assert recorded["max_request_body_size"] == "never"
        assert recorded["traces_sample_rate"] == 0.0

    def test_default_provider_is_used_when_none_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INTAKE_GLITCHTIP_DSN", DSN)
        monkeypatch.delenv("INTAKE_UNLEASH_URL", raising=False)
        # default provider = in-memory, error_reporting off by default.
        assert setup_error_reporting() is False
