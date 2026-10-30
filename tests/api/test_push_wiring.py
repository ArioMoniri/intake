"""INT-583 — wiring the APNs push gateway: fail closed with a typed reason.

``intake_api.push_wiring.push_gateway_from_settings`` wires the gateway only
with HTTP/2, a route (on the synthetic host, exactly the dedicated push-egress
proxy), the owner's egress row with the runtime gate open, and the key in
OpenBao, in that order, so a refused host never has its key read. Each missing
piece is its own typed reason; near misses throughout.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

import apns_testkit as kit
import pytest
from intake_api.settings import ApiSettings


def apns() -> Any:
    return importlib.import_module("intake_api.push_apns")


def port() -> Any:
    return importlib.import_module("intake_api.push_port")


def wiring() -> Any:
    """Resolved per call, so each test fails on its own line before the module exists."""
    return importlib.import_module("intake_api.push_wiring")


@pytest.fixture()
def phi_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


# --- wiring: fail closed with a typed reason ---------------------------------------------------


class Vault:
    """The OpenBao reader, recording which paths were read."""

    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents
        self.reads: list[str] = []

    def get_kv(self, path: str) -> dict[str, Any]:
        self.reads.append(path)
        return self.documents[path]


def _settings(
    allowlist: Path,
    environment: str | None = None,
    *,
    deployment: str = "production",
    proxy: str | None = None,
) -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode="transit",
        environment=deployment,
        egress_allowlist_path=allowlist,
        app_attest_environment=environment,
        push_egress_proxy_url=proxy,
    )


def test_the_shipped_allowlist_refuses_apns_so_no_key_is_read() -> None:
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    result = wiring().push_gateway_from_settings(_settings(kit.SHIPPED_ALLOWLIST), vault)
    assert result is port().PushUnconfigured.EGRESS_REFUSED
    assert vault.reads == []


def test_with_the_row_the_gate_and_the_key_the_gateway_is_wired(
    tmp_path: Path, phi_gate: None
) -> None:
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    result = wiring().push_gateway_from_settings(
        _settings(kit.allowlist_with_the_row(tmp_path)), vault
    )
    assert isinstance(result, apns().ApnsPushGateway)
    assert result.host == kit.HOST
    assert vault.reads == ["api/apns"]


def test_a_development_build_pushes_to_the_sandbox(tmp_path: Path, phi_gate: None) -> None:
    """The APNs host follows App Attest's environment (one provisioning
    profile carries both). Near miss: the production row does not admit it."""
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    sandbox = _settings(kit.allowlist_with_the_row(tmp_path, kit.SANDBOX_HOST), "development")
    result = wiring().push_gateway_from_settings(sandbox, vault)
    assert isinstance(result, apns().ApnsPushGateway) and result.host == kit.SANDBOX_HOST
    production_row_only = _settings(kit.allowlist_with_the_row(tmp_path), "development")
    assert (
        wiring().push_gateway_from_settings(production_row_only, vault)
        is port().PushUnconfigured.EGRESS_REFUSED
    )
    assert apns().apns_environment("Development") == "production"


def test_no_key_in_openbao_is_no_channel(tmp_path: Path, phi_gate: None) -> None:
    result = wiring().push_gateway_from_settings(
        _settings(kit.allowlist_with_the_row(tmp_path)), Vault({})
    )
    assert result is port().PushUnconfigured.NO_CREDENTIALS


def test_a_malformed_key_is_no_channel_and_names_no_value(
    tmp_path: Path, phi_gate: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    document = kit.vault_doc(kit.signing_key())
    document["team_id"] = "not-a-team"
    result = wiring().push_gateway_from_settings(
        _settings(kit.allowlist_with_the_row(tmp_path)), Vault({"api/apns": document})
    )
    assert result is port().PushUnconfigured.MALFORMED_CREDENTIALS
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "team_id" in text and "not-a-team" not in text and "PRIVATE KEY" not in text


def test_without_http2_there_is_no_channel(
    tmp_path: Path, phi_gate: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = wiring()
    real = module.importlib.util.find_spec
    monkeypatch.setattr(
        module.importlib.util, "find_spec", lambda name: None if name == "h2" else real(name)
    )
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    result = module.push_gateway_from_settings(
        _settings(kit.allowlist_with_the_row(tmp_path)), vault
    )
    assert result is port().PushUnconfigured.HTTP2_UNAVAILABLE
    assert vault.reads == []


# --- the route: the dedicated push proxy, exactly, or none outside the synthetic host -------

PUSH_PROXY = "http://push-egress:3128"


def test_the_synthetic_host_rides_the_dedicated_push_proxy(tmp_path: Path, phi_gate: None) -> None:
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    allowlist = kit.allowlist_with_the_row(tmp_path)
    settings = _settings(allowlist, deployment="staging", proxy=PUSH_PROXY)
    result = wiring().push_gateway_from_settings(settings, vault)
    assert isinstance(result, apns().ApnsPushGateway)
    assert result.proxy == PUSH_PROXY == wiring().PUSH_PROXY


def test_the_synthetic_host_without_its_proxy_has_no_route_and_reads_no_key(
    tmp_path: Path, phi_gate: None, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    settings = _settings(kit.allowlist_with_the_row(tmp_path), deployment="staging")
    assert wiring().push_gateway_from_settings(settings, vault) is port().PushUnconfigured.NO_ROUTE
    assert vault.reads == []
    assert any("no push egress proxy" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "proxy",
    [
        "http://sms-egress:3128",  # the SMS proxy carries no push
        "http://egress-proxy:3128",  # the hosted lanes' proxy neither
        "http://push-egress:3129",
        "https://push-egress:3128",
        "http://push-egress.attacker.example:3128",
    ],
)
def test_any_other_proxy_is_no_route(tmp_path: Path, phi_gate: None, proxy: str) -> None:
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    allowlist = kit.allowlist_with_the_row(tmp_path)
    for deployment in ("staging", "production"):
        settings = _settings(allowlist, deployment=deployment, proxy=proxy)
        result = wiring().push_gateway_from_settings(settings, vault)
        assert result is port().PushUnconfigured.NO_ROUTE
    assert vault.reads == []


def test_outside_the_synthetic_host_no_proxy_means_resolve_and_pin_here(
    tmp_path: Path, phi_gate: None
) -> None:
    """Near miss of the synthetic case: a production host with its own route
    out needs no proxy and gets none."""
    vault = Vault({"api/apns": kit.vault_doc(kit.signing_key())})
    result = wiring().push_gateway_from_settings(
        _settings(kit.allowlist_with_the_row(tmp_path)), vault
    )
    assert isinstance(result, apns().ApnsPushGateway) and result.proxy is None
