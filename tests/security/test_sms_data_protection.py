"""INT-581 — SMS data protection (owner order, 28 Oct 2026; GitHub #976).

Acceptance, verbatim: "Invariant 6 scan test: no phone number or OTP code in
logs, metrics, traces or error reports on the send and verify paths (seeded
canary values); numbers tokenised at rest; Netgsm credentials only from
OpenBao; egress only through the dedicated sms-egress proxy (ADR-042); every
send and verify appended to the hash-chained audit log (ids only)."

The audit (docs/evidence/INT-577.md, rows 34-41) found the per-module tests
sound and these gaps, each pinned here with a near miss:

- **no canary followed end to end.** One seeded number and the codes it is
  sent are now pushed through every path (sent, withheld, wrong, right,
  refresh, a vendor refusal, a vendor that crashes with the number in its
  message, a 500 in verify) and searched for in every sink: log records with
  their tracebacks, the metrics exposition, spans, error-report events after
  the scrubber, HTTP answers, the audit chain, every Redis key and value and
  every database row;
- **the redactor missed the canonical form.** ``redact_text`` masked
  ``05321234567`` and ``5321234567`` but not ``+905321234567`` — the E.164
  form the OTP tier normalises every number to — nor a grouped one; the
  collector's patterns had the same hole;
- **a crashing vendor reached the logs.** A delivery that raised anything but
  the typed error left the task with its exception, and asyncio logs that
  exception's text;
- **the synthetic host could wire Netgsm with no proxy** (``proxy is None``
  was admitted), which ADR-042 makes the only route out;
- **a failed verify left no audit row** (and nor did a refused send).
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import sys
import traceback
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.audit import verify_entries
from intake_platform.errors import scrub_event
from intake_platform.otel import JsonLogFormatter
from intake_platform.redaction import redact_text
from prometheus_client import REGISTRY, generate_latest
from sqlalchemy import create_engine, inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import netgsm_testkit as kit  # noqa: E402
from intake_api.app import _auth_from_settings  # noqa: E402
from intake_api.auth_store import OTP_MAX_ATTEMPTS, RESEND_COOLDOWN_S  # noqa: E402
from intake_api.otp import (  # noqa: E402
    AuthWiring,
    DeliveryReceipt,
    OtpDeliveryError,
    OtpDeliveryFailure,
)
from intake_api.settings import ApiSettings  # noqa: E402
from test_otp_abuse import DpopClient, OtpHarness, _build  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
COLLECTOR = REPO / "infra" / "observability" / "otel-collector.yaml"

#: The seeded canary: a number nothing else in the suite uses, and every way
#: it could be written down.
CANARY = "+905329871234"
CANARY_FORMS = (
    CANARY,
    "905329871234",
    "05329871234",
    "5329871234",
    "+90 532 987 12 34",
    "0532 987 12 34",
    "532 987 12 34",
)


def find(blob: str, secrets: tuple[str, ...]) -> list[str]:
    """Every canary form or code found in ``blob``. Codes are matched as whole
    digit runs, so a timestamp that happens to contain the six digits is not a
    leak and a stored code is."""
    found = [form for form in CANARY_FORMS if form in blob]
    found += [code for code in secrets if re.search(rf"(?<![0-9]){re.escape(code)}(?![0-9])", blob)]
    return found


@contextlib.contextmanager
def harness(tmp_path: Path, **knobs: Any) -> Iterator[OtpHarness]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    built = _build(tmp_path, **knobs)
    try:
        yield next(built)
    finally:
        next(built, None)


class Crashing:
    """A vendor client with a bug: it raises with the number and the code in
    the message — the shape of exception that ends up in a log or a tracker."""

    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
        raise RuntimeError(f"vendor client crashed sending {code} to {phone_e164}")


class Refusing:
    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
        del phone_e164, code
        raise OtpDeliveryError(OtpDeliveryFailure.REJECTED, vendor_code=50)


def _records_text(records: list[logging.LogRecord]) -> str:
    """Every log record as a raw message, its arguments, its traceback, and as
    the JSON line the API would write."""
    out = []
    formatter = JsonLogFormatter()
    for record in records:
        if record.name.startswith(("httpx", "httpcore")):
            # the TEST's HTTP client logging the URLs it calls — the dev-only
            # peek route takes the number as a query parameter — is not the
            # API's output (docs/evidence/INT-581.md, "What this does not stop")
            continue
        out.append(record.getMessage())
        out.append(repr(record.args))
        if record.exc_info:
            out.append("".join(traceback.format_exception(*record.exc_info)))
        out.append(formatter.format(record))
    return "\n".join(out)


def _redis_text(otp: OtpHarness) -> str:
    out = []
    for name in otp.redis_client.scan_iter("*"):
        key = name.decode()
        if ":otp:peek:" in key:
            continue  # the dev tier's peek slot is the one place a code may sit
        out.append(key)
        kind = otp.redis_client.type(name)
        if kind == b"string":
            out.append(otp.redis_client.get(name).decode())
        elif kind == b"zset":
            out.extend(m.decode() for m in otp.redis_client.zrange(name, 0, -1))
        elif kind == b"set":
            out.extend(m.decode() for m in otp.redis_client.smembers(name))
    return "\n".join(out)


def _database_text(otp: OtpHarness) -> str:
    url = str(otp.engine.url).replace("+aiosqlite", "+pysqlite")
    engine = create_engine(url)
    out = []
    try:
        with engine.connect() as connection:
            for table in inspect(engine).get_table_names():
                for row in connection.execute(text(f'SELECT * FROM "{table}"')):  # noqa: S608
                    out.append(repr(tuple(row)))
    finally:
        engine.dispose()
    return "\n".join(out)


# --- the canary, end to end -----------------------------------------------------------------


def test_the_canary_reaches_no_log_metric_trace_report_answer_audit_or_store(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    spans = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.add_span_processor(SimpleSpanProcessor(spans))
    caplog.set_level(logging.DEBUG)
    answers: list[str] = []
    codes: list[str] = []
    dpop = DpopClient()
    with harness(tmp_path / "flow") as otp:
        # sent, withheld, a wrong code, the right code, a refresh
        first = otp.request_otp(CANARY)
        codes.append(otp.peek(CANARY))
        withheld = otp.request_otp(CANARY, device_id="device-b")
        wrong = otp.verify(dpop, phone=CANARY, code="000000" if codes[0] != "000000" else "1" * 6)
        signed_in = otp.verify(dpop, phone=CANARY)
        assert signed_in.status_code == 200, signed_in.text
        refreshed = otp.refresh(dpop, signed_in.json()["refresh_token"])
        answers += [r.text + repr(dict(r.headers)) for r in (first, withheld, wrong, refreshed)]
        # a 500 inside verify
        otp.clock.advance(RESEND_COOLDOWN_S * 4)
        otp.request_otp(CANARY, device_id="device-c")
        codes.append(otp.peek(CANARY))

        async def down(self: Any, pseudonym: str) -> Any:
            raise RuntimeError("database unavailable")

        monkeypatch.setattr("intake_api.otp.OtpAuthService._get_or_create_patient", down)
        failed = otp.verify(dpop, phone=CANARY, device_id="device-c")
        assert failed.status_code == 500
        answers.append(failed.text)
        store = "\n".join(
            [_redis_text(otp), _database_text(otp)]
            + [repr(entry) for entry in otp.audit_store.entries()]
        )
    with harness(tmp_path / "refusing", delivery=Refusing()) as otp:
        answers.append(otp.request_otp(CANARY).text)
        codes.append(otp.peek(CANARY))
    with harness(tmp_path / "crashing", delivery=Crashing()) as otp:
        answers.append(otp.request_otp(CANARY).text)
        codes.append(otp.peek(CANARY))
        crashes = [e.action for e in otp.audit_store.entries()]
    secrets = tuple(codes)
    sinks = {
        "logs": _records_text(caplog.records),
        "metrics": generate_latest(REGISTRY).decode(),
        "traces": "\n".join(span.to_json() for span in spans.get_finished_spans()),
        "answers": "\n".join(answers),
        "store, audit and database": store,
    }
    for sink, blob in sinks.items():
        assert find(blob, secrets) == [], f"the canary reached the {sink}"
    assert crashes[-1] == "auth.otp.delivery_failed", "a crashing vendor is recorded, not lost"
    # the error report the tracker would get for that crash, after the scrubber
    try:
        raise RuntimeError(f"vendor client crashed sending {codes[-1]} to {CANARY}")
    except RuntimeError as crash:
        event = {
            "message": str(crash),
            "exception": {"values": [{"value": str(crash), "stacktrace": {"frames": []}}]},
        }
    assert find(json.dumps(scrub_event(event, None)), ()) == []


def test_the_scan_finds_a_canary_when_one_is_there(caplog: pytest.LogCaptureFixture) -> None:
    """Near miss: the scanner is not blind. A log line carrying the number, a
    code inside a word boundary, and a code inside a longer digit run."""
    caplog.set_level(logging.INFO)
    logging.getLogger("intake.test.leak").info("sent to %s", CANARY)
    assert find(_records_text(caplog.records), ()) != []
    assert find("code 482915 sent", ("482915",)) == ["482915"]
    assert find("at 1793152482915.0", ("482915",)) == [], "a timestamp is not a code"


# --- the redactor knows the canonical form ------------------------------------------------


@pytest.mark.parametrize("form", CANARY_FORMS + ("00905329871234", "+90-532-987-12-34"))
def test_every_form_of_a_turkish_mobile_is_redacted(form: str) -> None:
    out = redact_text(f"otp for {form} queued")
    assert find(out, ()) == [], out
    assert "[PHONE]" in out


@pytest.mark.parametrize(
    "text",
    [
        "BP 120/80, pulse 72",
        "+90 212 123 45 67",  # a landline is not a mobile
        "order 4329871234",  # ten digits, not a 5XX range
        "dose 5 mg twice, 532 ml",
        "2026-10-28 12:00:05",
    ],
)
def test_a_near_miss_is_not_redacted(text: str) -> None:
    assert redact_text(text) == text


def _collector_phone_patterns() -> list[str]:
    statements: list[str] = []
    cfg = yaml.safe_load(COLLECTOR.read_text(encoding="utf-8"))
    for proc in cfg["processors"].values():
        for key in ("log_statements", "trace_statements", "metric_statements"):
            for section in proc.get(key, []):
                statements.extend(section.get("statements", []))
    found = re.findall(r'"value",\s*"(.+?)",\s*"\[PHONE\]"', "\n".join(statements))
    assert found, "the collector carries no phone pattern"
    return [pattern.replace("\\\\", "\\") for pattern in found]


@pytest.mark.parametrize("form", (CANARY, "905329871234", "05329871234", "5329871234"))
def test_the_collector_redacts_the_canonical_form_too(form: str) -> None:
    for pattern in _collector_phone_patterns():
        assert re.sub(pattern, "[PHONE]", f"to {form} ok") == "to [PHONE] ok", pattern


# --- a crashing vendor is contained ------------------------------------------------------


def test_a_crashing_vendor_is_recorded_and_its_text_never_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    with harness(tmp_path, delivery=Crashing()) as otp:
        response = otp.request_otp(CANARY)
        code = otp.peek(CANARY)
        assert response.status_code == 202
        assert otp.audit_store.entries()[-1].action == "auth.otp.delivery_failed"
    assert find(_records_text(caplog.records), (code,)) == []
    assert any("RuntimeError" in record.getMessage() for record in caplog.records), (
        "the failure is still visible, by its type"
    )


# --- every send and verify on the chain, ids only ----------------------------------------


_ACTOR = re.compile(r"phone:[0-9a-f]{8}|patient:[0-9a-f-]{36}|system:[a-z-]+")
_RESOURCE = re.compile(
    r"request:[0-9a-f]{32}|delivery:[0-9a-f]+|phone:[0-9a-f]{8}|patient:[0-9a-f-]{36}"
    r"|otp_verify:[a-z]+|token_family:[0-9a-f]{32}"
)


def test_every_send_and_verify_is_on_the_chain_with_ids_only(tmp_path: Path) -> None:
    dpop = DpopClient()
    with harness(tmp_path) as otp:
        assert otp.sent(CANARY)
        real = otp.peek(CANARY)
        assert not otp.sent(CANARY, device_id="device-b")
        for _ in range(OTP_MAX_ATTEMPTS - 1):
            otp.verify(dpop, phone=CANARY, code="000000" if real != "000000" else "111111")
        assert otp.verify(dpop, phone=CANARY).status_code == 200
        never = otp.verify(dpop, phone="+905320000001", code="123456", request_id="0" * 32)
        assert never.status_code == 401  # a number that was never sent a code
        entries = otp.audit_store.entries()
    actions = [entry.action for entry in entries]
    for action in (
        "auth.otp.requested",
        "auth.otp.withheld",
        "auth.otp.sent",
        "auth.otp.verify_refused",
        "auth.otp.verified",
    ):
        assert action in actions, action
    refused = [e for e in entries if e.action == "auth.otp.verify_refused"]
    assert len(refused) == OTP_MAX_ATTEMPTS, "four wrong codes and one for a number with none"
    assert {e.resource_ref for e in refused} == {"otp_verify:invalid", "otp_verify:missing"}
    for entry in entries:
        if entry.action.startswith("auth."):
            assert _ACTOR.fullmatch(entry.actor), entry
            assert _RESOURCE.fullmatch(entry.resource_ref), entry
    assert verify_entries(entries).ok


# --- egress only through the dedicated proxy (ADR-042) -----------------------------------


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _settings(environment: str, proxy: str | None, allowlist: Path) -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode="transit",
        tokenization_key="k",
        environment=environment,
        egress_allowlist_path=allowlist,
        sms_egress_proxy_url=proxy,
    )


def test_the_synthetic_host_without_its_sms_proxy_wires_nothing_and_reads_no_secret(
    phi_egress: None, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    vault = kit.complete_vault()
    settings = _settings("staging", None, kit.allowlist_with_the_row(tmp_path))
    assert _auth_from_settings(settings, secrets=vault) is None
    assert vault.paths == []
    assert any("ADR-042" in record.getMessage() for record in caplog.records)


def test_the_synthetic_host_with_its_sms_proxy_wires_netgsm(
    phi_egress: None, tmp_path: Path
) -> None:
    """Near miss: the dedicated proxy, and nothing else, is what makes it wire."""
    settings = _settings("staging", "http://sms-egress:3128", kit.allowlist_with_the_row(tmp_path))
    wiring = _auth_from_settings(settings, secrets=kit.complete_vault())
    assert isinstance(wiring, AuthWiring)
    assert wiring.delivery.proxy == "http://sms-egress:3128"


def test_production_keeps_its_own_route(phi_egress: None, tmp_path: Path) -> None:
    """ADR-042 is the synthetic host's decision; production's SMS route is its
    own (in-country, in-process resolve-and-pin) and is not required to name
    the synthetic host's proxy."""
    settings = _settings("prod", None, kit.allowlist_with_the_row(tmp_path))
    assert isinstance(_auth_from_settings(settings, secrets=kit.complete_vault()), AuthWiring)


# --- credentials only from OpenBao (pinned elsewhere, named here) --------------------------


def test_the_netgsm_credentials_have_one_source() -> None:
    """The proof lives with INT-528 (an environment full of NETGSM_* values
    configures nothing); this pins that the proof still exists."""
    wiring_tests = (REPO / "tests" / "api" / "test_otp_netgsm_wiring.py").read_text("utf-8")
    assert "def test_the_environment_is_not_a_secrets_path(" in wiring_tests
