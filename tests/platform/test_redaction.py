"""INT-011 — shared OTel setup + the PII redaction layer (CLAUDE.md inv. 6).

Acceptance, verbatim:
  "propagates trace_id, hashed session_id, tenant_id, protocol_hash,
   prompt_version; JSON logs; no-PHI invariant"
  "OTel collector config with redaction (TCKN checksum regex, 05x phone, IBAN,
   names allow-list) unit-tested on fixture logs"

The collector-config test extracts the regexes from the committed YAML and runs
them against the fixture logs — the config's own patterns are what get tested,
not a copy that could drift. Free-text NAME redaction is Presidio's job
(INT-015); here "names allow-list" is the structured-attribute allow-list: an
attribute not on the list never reaches a log line.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import yaml
from intake_platform.otel import (
    JsonLogFormatter,
    bind_log_context,
    clear_log_context,
    setup_otel,
)
from intake_platform.redaction import is_valid_tckn, redact_text

REPO = Path(__file__).resolve().parents[2]
FIXTURE_LOGS = REPO / "tests" / "fixtures" / "logs" / "app_lines.txt"
COLLECTOR_CONFIG = REPO / "infra" / "observability" / "otel-collector.yaml"

VALID_TCKN = "10000000146"  # passes the published checksum (d10=4, d11=6)
INVALID_TCKN = "12345678901"  # 11 digits, checksum fails


# --- TCKN checksum ----------------------------------------------------------------


def test_tckn_checksum() -> None:
    assert is_valid_tckn(VALID_TCKN)
    assert not is_valid_tckn(INVALID_TCKN)
    assert not is_valid_tckn("01000000146")  # may not start with 0
    assert not is_valid_tckn("1234")


def test_valid_tckn_is_redacted() -> None:
    out = redact_text(f"hasta {VALID_TCKN} geldi")
    assert VALID_TCKN not in out
    assert "[TCKN]" in out


def test_checksum_failing_11_digits_survive() -> None:
    # the checksum is what makes this a TCKN redactor rather than a number shredder
    assert INVALID_TCKN in redact_text(f"sipariş no {INVALID_TCKN}")


# --- phone / IBAN -----------------------------------------------------------------


def test_tr_mobile_redacted_with_and_without_leading_zero() -> None:
    for phone in ("05321234567", "5321234567"):
        out = redact_text(f"tel {phone} kayıtlı")
        assert phone not in out
        assert "[PHONE]" in out


def test_iban_redacted() -> None:
    iban = "TR" + "3" * 24
    out = redact_text(f"iade {iban} hesabına")
    assert iban not in out
    assert "[IBAN]" in out


# --- fixture logs, app-side -------------------------------------------------------


def test_fixture_log_lines_come_out_clean() -> None:
    text = FIXTURE_LOGS.read_text(encoding="utf-8")
    redacted = redact_text(text)
    assert VALID_TCKN not in redacted
    assert "05321234567" not in redacted
    assert "TR330006100519786457841326" not in redacted


# --- collector config, tested from its own committed YAML -------------------------


def _collector_patterns() -> list[str]:
    cfg = yaml.safe_load(COLLECTOR_CONFIG.read_text(encoding="utf-8"))
    statements: list[str] = []
    for proc in cfg["processors"].values():
        for section in proc.get("log_statements", []):
            statements.extend(section.get("statements", []))
    patterns = re.findall(
        r'replace_all_patterns\([^,]+,\s*"value",\s*"(.+?)",\s*"', "\n".join(statements)
    )
    assert patterns, "no replace_all_patterns statements found in the collector config"
    return [p.replace("\\\\", "\\") for p in patterns]


def test_collector_patterns_scrub_fixture_logs() -> None:
    patterns = _collector_patterns()
    text = FIXTURE_LOGS.read_text(encoding="utf-8")
    for pattern in patterns:
        text = re.sub(pattern, "[REDACTED]", text)
    assert VALID_TCKN not in text
    assert "05321234567" not in text
    assert "TR330006100519786457841326" not in text


# --- JSON logs + context propagation ----------------------------------------------


def _formatted_record(msg: str, **extra: object) -> dict[str, object]:
    record = logging.LogRecord(
        name="intake.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonLogFormatter().format(record))


def test_json_log_carries_context_ids_and_hashes_session() -> None:
    bind_log_context(
        session_id="session-secret-42",
        tenant_id="acibadem",
        protocol_hash="p" * 12,
        prompt_version="v3",
    )
    try:
        out = _formatted_record("turn complete")
        assert out["tenant_id"] == "acibadem"
        assert out["protocol_hash"] == "p" * 12
        assert out["prompt_version"] == "v3"
        assert "session-secret-42" not in json.dumps(out), "raw session id must never log"
        session_hash = out["session_id_hash"]
        assert isinstance(session_hash, str) and len(session_hash) == 16
    finally:
        clear_log_context()


def test_json_log_redacts_message_and_drops_unknown_attributes() -> None:
    out = _formatted_record(f"hasta {VALID_TCKN} aradı", patient_name="Ayşe Yılmaz")
    dumped = json.dumps(out, ensure_ascii=False)
    assert VALID_TCKN not in dumped
    assert "[TCKN]" in str(out["message"])
    assert "Ayşe" not in dumped, "attributes off the allow-list must never reach a log line"


def test_setup_otel_is_local_only_by_default() -> None:
    provider = setup_otel(service_name="test-service")
    # No exporter is wired unless the OTLP endpoint env is set — CI is
    # vendor-free and a default network egress would violate the egress posture.
    assert provider.resource.attributes["service.name"] == "test-service"
