"""INT-528 — where the Netgsm adapter is wired, and the OTP route's answer.

The owner's SMS vendor is Netgsm (INT-358, 16 Oct 2026). Outside dev (INT-325:
every environment but ``dev``, staging included) the OTP tier is configured only
when ALL of these hold, and then delivery is Netgsm:

1. the phone-tokenization key is set (INT-131, unchanged);
2. the egress policy admits the SMS purpose to ``api.netgsm.com.tr`` on the PHI
   tier, with ``INTAKE_ALLOW_PHI_EGRESS=explicit-yes`` at runtime — the shipped
   allow-list does not, because that row is the owner's patch;
3. OpenBao holds ``secret/api/netgsm`` with ``usercode``, ``password`` and
   ``msgheader`` (invariant 14). No environment variable configures anything.

Anything missing leaves the tier unconfigured (every /v1/auth route answers 503)
and the dev event logger is never the fallback (INT-325). Twilio, the INT-329
adapter, is no longer wired anywhere. Dev is unchanged.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import pytest
from api_harness import run, sqlite_ddl_clone
from fastapi.testclient import TestClient
from intake_api.app import ApiWiring, _auth_from_settings, create_app
from intake_api.attestation import DevStructuralAttestationVerifier
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter, ensure_consumer_tenant
from intake_api.settings import ApiSettings
from intake_platform.egress import AllowlistEntry, EgressPurpose
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.secrets import SecretsBootError
from intake_platform.tokenization import Tokenizer
from netgsm_testkit import (
    JOBID,
    MSGHEADER,
    PASSWORD,
    PHONE,
    SHIPPED_ALLOWLIST,
    STRICT_ENVIRONMENTS,
    UNREADABLE,
    USERCODE,
    VAULT_DOC,
    Vault,
    Vendor,
    accepted,
    adapter,
    allowlist_with,
    allowlist_with_the_row,
    assert_clean,
    complete_vault,
    empty_policy,
    netgsm,
    record_text,
    replay,
)
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _settings(
    environment: str, allowlist: Path = SHIPPED_ALLOWLIST, tokenization_key: str | None = "k"
) -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode="transit",
        tokenization_key=tokenization_key,
        environment=environment,
        egress_allowlist_path=allowlist,
        # INT-581: on the synthetic host the dedicated SMS proxy is the only
        # route out (ADR-042), so a staging wiring names it
        sms_egress_proxy_url="http://sms-egress:3128" if environment == "staging" else None,
    )


# --- the matrix -----------------------------------------------------------------------


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_non_dev_wires_netgsm_when_every_piece_is_present(
    phi_egress: None, tmp_path: Path, environment: str
) -> None:
    vault = complete_vault()
    settings = _settings(environment, allowlist_with_the_row(tmp_path))
    wiring = _auth_from_settings(settings, secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert isinstance(wiring.delivery, netgsm().NetgsmSmsDeliveryAdapter)
    # INT-578: the OTP pepper is read after the vendor document, never before;
    # INT-488: the App Review document after the pepper, outside dev only
    assert vault.paths == ["api/netgsm", "api/otp", "api/review_signin"]


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
@pytest.mark.parametrize("field", ["usercode", "password", "msgheader"])
def test_missing_any_vendor_value_leaves_the_tier_unconfigured(
    phi_egress: None,
    tmp_path: Path,
    environment: str,
    field: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    doc = {key: value for key, value in VAULT_DOC.items() if key != field}
    caplog.set_level(logging.DEBUG)
    settings = _settings(environment, allowlist_with_the_row(tmp_path))
    assert _auth_from_settings(settings, secrets=Vault({"api/netgsm": doc})) is None
    assert any(field in record.getMessage() for record in caplog.records), (
        "the refusal names the missing field"
    )
    for record in caplog.records:
        assert_clean(record_text(record), "a wiring log line")


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
@pytest.mark.parametrize(
    "error",
    [None, SecretsBootError("OpenBao address/token missing"), httpx.ConnectError("unreachable")],
    ids=["document-absent", "vault-not-configured", "vault-unreachable"],
)
def test_no_vault_document_leaves_the_tier_unconfigured(
    phi_egress: None, tmp_path: Path, environment: str, error: Exception | None
) -> None:
    settings = _settings(environment, allowlist_with_the_row(tmp_path))
    assert _auth_from_settings(settings, secrets=Vault(error=error)) is None


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_the_environment_is_not_a_secrets_path(
    phi_egress: None, tmp_path: Path, environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariant 14: the password is a secret, and secrets come from OpenBao."""
    for name, value in (
        ("NETGSM_USERCODE", USERCODE),
        ("NETGSM_PASSWORD", PASSWORD),
        ("NETGSM_MSGHEADER", MSGHEADER),
    ):
        monkeypatch.setenv(name, value)
    settings = _settings(environment, allowlist_with_the_row(tmp_path))
    assert _auth_from_settings(settings, secrets=Vault()) is None


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_the_shipped_allowlist_and_the_vault_wire_netgsm(
    phi_egress: None, environment: str
) -> None:
    """With the owner's row on main, the shipped list plus OpenBao is enough."""
    vault = complete_vault()
    wiring = _auth_from_settings(_settings(environment), secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert isinstance(wiring.delivery, netgsm().NetgsmSmsDeliveryAdapter)
    # INT-578: the OTP pepper is read after the vendor document, never before;
    # INT-488: the App Review document after the pepper, outside dev only
    assert vault.paths == ["api/netgsm", "api/otp", "api/review_signin"]


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_the_shipped_allowlist_without_the_runtime_gate_reads_no_secret(
    environment: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The row alone is not enough: without INTAKE_ALLOW_PHI_EGRESS the tier
    stays at 503 and the vendor's secret is never pulled."""
    monkeypatch.delenv("INTAKE_ALLOW_PHI_EGRESS", raising=False)
    caplog.set_level(logging.WARNING)
    vault = complete_vault()
    assert _auth_from_settings(_settings(environment), secrets=vault) is None
    assert any("egress" in record.getMessage() for record in caplog.records)
    assert vault.paths == []


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_the_runtime_phi_gate_unset_keeps_the_tier_at_503(
    tmp_path: Path, environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INTAKE_ALLOW_PHI_EGRESS", raising=False)
    settings = _settings(environment, allowlist_with_the_row(tmp_path))
    assert _auth_from_settings(settings, secrets=complete_vault()) is None


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_an_unreadable_allowlist_keeps_the_tier_at_503(
    phi_egress: None, tmp_path: Path, environment: str
) -> None:
    settings = _settings(environment, tmp_path / "absent.yaml")
    assert _auth_from_settings(settings, secrets=complete_vault()) is None


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_no_tokenization_key_means_no_tier_and_no_vault_read(environment: str) -> None:
    vault = complete_vault()
    assert _auth_from_settings(_settings(environment, tokenization_key=None), secrets=vault) is None
    assert vault.paths == []


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_twilio_is_never_wired_even_when_fully_configured(
    phi_egress: None, tmp_path: Path, environment: str
) -> None:
    """The owner chose Netgsm: a Twilio row and a Twilio vault document
    configure nothing, and the vault is never asked for Twilio's secret."""
    twilio_row = AllowlistEntry(
        name="twilio-sms-test-row",
        host="api.twilio.com",
        port=443,
        protocol="https",
        purpose_id=EgressPurpose("sms_otp_delivery"),
        purpose="unit fixture",
        basis="unit fixture only",
        phi_allowed=True,
        phi_exception_approval="unit-fixture-not-a-decision",
    )
    twilio_doc = {"account_sid": "AC" + "0" * 32, "auth_token": "t" * 32, "from": "+15005550006"}
    vault = Vault({"api/twilio": twilio_doc})
    settings = _settings(environment, allowlist_with(tmp_path, twilio_row))
    assert _auth_from_settings(settings, secrets=vault) is None
    assert "api/twilio" not in vault.paths


def test_dev_keeps_the_dev_logger_whatever_the_vault_holds(
    phi_egress: None, tmp_path: Path
) -> None:
    vault = complete_vault()
    wiring = _auth_from_settings(_settings("dev", allowlist_with_the_row(tmp_path)), secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert isinstance(wiring.delivery, DevLogDeliveryAdapter)
    # the vendor's document is never read in dev; the OTP pepper is (INT-578:
    # dev on the OpenBao dev server reads it there, like every environment)
    assert vault.paths == ["api/otp"]


# --- the route: 202 with the job id, or a generic 503 -------------------------------


def _harness(tmp_path: Path, auth: AuthWiring | None) -> Iterator[TestClient]:
    from intake_platform.db.audit_store import SqlAlchemyAuditStore
    from sqlalchemy import create_engine

    app_db, audit_db = tmp_path / "otp.db", tmp_path / "otp-audit.db"
    for path in (app_db, audit_db):
        ddl = create_engine(f"sqlite+pysqlite:///{path}")
        sqlite_ddl_clone().create_all(ddl)
        ddl.dispose()
    audit_engine = create_engine(f"sqlite+pysqlite:///{audit_db}")
    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}", poolclass=NullPool)
    wiring = ApiWiring(
        settings=ApiSettings(
            token_patient=None,
            token_admin=None,
            app_db_url=f"sqlite+aiosqlite:///{app_db}",
            audit_db_url=f"sqlite+pysqlite:///{audit_db}",
            bootstrap_db_url=f"sqlite+aiosqlite:///{app_db}",
            kek_mode="file-dev",
        ),
        engine=engine,
        audit_store=SqlAlchemyAuditStore(audit_engine),
        cipher=EnvelopeCipher(FileKekProvider()),
        bootstrap=False,
        documents=None,
        auth=auth,
    )
    run(ensure_consumer_tenant(engine))
    with TestClient(create_app(wiring), raise_server_exceptions=False) as client:
        yield client
    run(engine.dispose())
    audit_engine.dispose()


def _auth(delivery: Any) -> AuthWiring:
    return AuthWiring(
        redis_client=fakeredis.FakeStrictRedis(),
        tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
        delivery=delivery,
        attestation=DevStructuralAttestationVerifier(),
    )


def _request_otp(client: TestClient) -> httpx.Response:
    challenge = client.post("/v1/auth/attest/challenge").json()["challenge"]
    attestation = {
        "platform": "ios",
        "mode": "dev-unattested",
        "token": base64.urlsafe_b64encode(b"intake-dev-attest").rstrip(b"=").decode("ascii"),
        "device_id": "device-a",
        "nonce": challenge,
    }
    return client.post(
        "/v1/auth/otp/request",
        json={"phone": PHONE},
        headers={"X-Intake-Attestation": json.dumps(attestation)},
    )


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_absent_credentials_answer_503_on_the_route(
    phi_egress: None, tmp_path: Path, environment: str
) -> None:
    """The acceptance's fail-closed 503, end to end: the wiring the API would
    build outside dev with no Netgsm document in OpenBao is no wiring at all,
    and the route says so rather than claiming a code was sent."""
    settings = _settings(environment, allowlist_with_the_row(tmp_path))
    auth = _auth_from_settings(settings, secrets=Vault())
    assert auth is None
    for client in _harness(tmp_path, auth):
        response = client.post("/v1/auth/otp/request", json={"phone": PHONE})
        assert response.status_code == 503, response.text
        assert response.json() == {"error": "otp_auth_unconfigured"}


def _audited(client: TestClient) -> list[str]:
    """The audit actions, once the deliveries in flight have ended (INT-579:
    the vendor is called after the response)."""
    client.portal.call(client.app.state.api.auth.settle)
    store = client.app.state.api.audit
    return [entry.action for entry in client.portal.call(store.entries)]


def test_the_route_answers_202_and_the_job_id_is_audited(phi_egress: None, tmp_path: Path) -> None:
    """INT-579: the 202 carries no vendor job id — the vendor answers after the
    response — and the job id goes to the hash chain."""
    for client in _harness(tmp_path, _auth(adapter(Vendor(accepted)))):
        response = _request_otp(client)
        assert response.status_code == 202, response.text
        assert set(response.json()) == {"request_id", "resend_after_s"}
        assert _audited(client)[-2:] == ["auth.otp.requested", "auth.otp.sent"]
        store = client.app.state.api.audit
        assert client.portal.call(store.entries)[-1].resource_ref == f"delivery:{JOBID}"


@pytest.mark.parametrize("code", ["20", "30", "50", "60", "100"])
def test_a_refused_delivery_answers_like_a_sent_one_and_is_audited(
    phi_egress: None, tmp_path: Path, code: str
) -> None:
    """INT-579: a vendor refusal is no longer read off the route. Code 50 is
    Netgsm refusing a number: a 503 there told a stranger which numbers are
    live. Never a claimed send: the chain records the failure."""
    for client in _harness(tmp_path, _auth(adapter(Vendor(replay("error", code=code))))):
        response = _request_otp(client)
        assert response.status_code == 202, response.text
        assert set(response.json()) == {"request_id", "resend_after_s"}
        assert_clean(response.text, "the response body")
        assert _audited(client)[-2:] == ["auth.otp.requested", "auth.otp.delivery_failed"]


def test_an_egress_refusal_answers_alike_and_never_reaches_the_vendor(
    phi_egress: None, tmp_path: Path
) -> None:
    vendor = Vendor(accepted)
    for client in _harness(tmp_path, _auth(adapter(vendor, empty_policy()))):
        response = _request_otp(client)
        assert response.status_code == 202
        assert _audited(client)[-1] == "auth.otp.delivery_failed"
    assert vendor.requests == []


@pytest.mark.parametrize("scenario", ["plain-text-00-jobid", "00-without-jobid"])
def test_an_unreadable_200_is_sent_once_and_the_cooldown_holds_the_resend(
    phi_egress: None, tmp_path: Path, scenario: str
) -> None:
    """INT-576: Netgsm may have sent the code, so nothing sends it again: one
    vendor call, and a resend straight after is held by the wait the first
    request started. INT-579: the vendor answers after the response, so the
    route says 202 to both and the chain records the unreadable answer; the
    held resend is withheld, never sent."""
    vendor = Vendor(UNREADABLE[scenario][0])
    for client in _harness(tmp_path, _auth(adapter(vendor))):
        first = _request_otp(client)
        assert first.status_code == 202, first.text
        assert _audited(client)[-1] == "auth.otp.delivery_failed"
        again = _request_otp(client)
        assert again.status_code == 202, again.text
        assert _audited(client)[-1] == "auth.otp.withheld"
    assert len(vendor.requests) == 1


# --- ADR-042: the SMS-only proxy ----------------------------------------------------------


def _with_proxy(environment: str, allowlist: Path, proxy: str) -> ApiSettings:
    return dataclasses.replace(_settings(environment, allowlist), sms_egress_proxy_url=proxy)


def test_the_dedicated_proxy_is_the_one_the_adapter_rides(phi_egress: None, tmp_path: Path) -> None:
    settings = _with_proxy("staging", allowlist_with_the_row(tmp_path), "http://sms-egress:3128")
    wiring = _auth_from_settings(settings, secrets=complete_vault())
    assert isinstance(wiring, AuthWiring)
    assert wiring.delivery.proxy == "http://sms-egress:3128"


@pytest.mark.parametrize(
    "proxy", ["http://egress-proxy:3128", "http://sms-egress:3129", "https://sms-egress:3128"]
)
def test_any_other_proxy_leaves_the_tier_unconfigured_and_reads_no_secret(
    phi_egress: None, tmp_path: Path, proxy: str
) -> None:
    vault = complete_vault()
    settings = _with_proxy("staging", allowlist_with_the_row(tmp_path), proxy)
    assert _auth_from_settings(settings, secrets=vault) is None
    assert vault.paths == []


def test_settings_read_the_proxy_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    monkeypatch.setenv("INTAKE_SMS_EGRESS_PROXY_URL", "http://sms-egress:3128")
    assert ApiSettings.from_env().sms_egress_proxy_url == "http://sms-egress:3128"
    monkeypatch.delenv("INTAKE_SMS_EGRESS_PROXY_URL")
    assert ApiSettings.from_env().sms_egress_proxy_url is None
