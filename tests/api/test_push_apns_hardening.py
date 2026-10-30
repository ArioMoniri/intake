"""INT-583 review fixes for the APNs adapter (security review, 30 Oct 2026).

- **hpack never logs a header.** h2's header compressor logs every header it
  adds to its table at DEBUG, the ``:path`` that carries the device token and
  the ``authorization`` bearer included. Importing the adapter pins the
  ``hpack`` logger to INFO, and a real h2 encode under a DEBUG root logger
  leaves neither in any record. Near miss: with the pin lifted, the same
  encode does log them, so this test can see a leak.
- **A key in a format cryptography cannot load** is malformed credentials (a
  typed reason), never a crash at boot.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

import apns_testkit as kit
import h2.config
import h2.connection
import pytest
from cryptography.exceptions import UnsupportedAlgorithm

BEARER = "bearer eyJhbGciOiJFUzI1NiJ9.unit.signature"  # a shape, signed by nobody


def apns() -> Any:
    return importlib.import_module("intake_api.push_apns")


def _encode_through_h2() -> None:
    connection = h2.connection.H2Connection(h2.config.H2Configuration(client_side=True))
    connection.initiate_connection()
    connection.send_headers(
        1,
        [
            (":method", "POST"),
            (":scheme", "https"),
            (":authority", kit.HOST),
            (":path", f"/3/device/{kit.TOKEN_A}"),
            ("authorization", BEARER),
            ("apns-topic", kit.TOPIC),
        ],
    )
    connection.data_to_send()


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


def test_hpack_never_logs_a_header_value(caplog: pytest.LogCaptureFixture) -> None:
    apns()  # importing the adapter pins the logger
    caplog.set_level(logging.DEBUG)
    _encode_through_h2()
    logged = _logged(caplog)
    assert kit.TOKEN_A not in logged and "unit.signature" not in logged
    assert logging.getLogger("hpack").getEffectiveLevel() >= logging.INFO


def test_without_the_pin_the_same_encode_would_leak(caplog: pytest.LogCaptureFixture) -> None:
    """Near miss: the test above can see a leak."""
    apns()
    hpack_logger = logging.getLogger("hpack")
    pinned = hpack_logger.level
    caplog.set_level(logging.DEBUG)
    hpack_logger.setLevel(logging.DEBUG)
    try:
        _encode_through_h2()
    finally:
        hpack_logger.setLevel(pinned)
    assert kit.TOKEN_A in _logged(caplog)


def test_a_key_cryptography_cannot_load_is_malformed_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = apns()

    def unsupported(data: bytes, password: object = None, **_: object) -> object:
        raise UnsupportedAlgorithm("this key type is not supported")

    monkeypatch.setattr(module.serialization, "load_pem_private_key", unsupported)
    with pytest.raises(module.ApnsConfigError) as refused:
        module.ApnsCredentials.parse(kit.vault_doc(kit.signing_key()))
    assert "key_p8" in str(refused.value)


def test_the_wiring_reports_it_as_malformed_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = apns()
    wiring = importlib.import_module("intake_api.push_wiring")
    port = importlib.import_module("intake_api.push_port")
    settings = importlib.import_module("intake_api.settings").ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode="transit",
        environment="production",
        egress_allowlist_path=kit.allowlist_with_the_row(tmp_path),
    )

    class Vault:
        def get_kv(self, path: str) -> dict[str, Any]:
            return kit.vault_doc(kit.signing_key())

    def unsupported(data: bytes, password: object = None, **_: object) -> object:
        raise UnsupportedAlgorithm("this key type is not supported")

    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")
    monkeypatch.setattr(module.serialization, "load_pem_private_key", unsupported)
    result = wiring.push_gateway_from_settings(settings, Vault())
    assert result is port.PushUnconfigured.MALFORMED_CREDENTIALS
