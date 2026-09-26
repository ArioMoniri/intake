"""INT-329 — where the Twilio adapter is wired, and the OTP route's answer.

Outside dev (INT-325: every environment but ``dev``, staging included) the OTP
tier is configured only when ALL of these hold, and then delivery is Twilio:

1. the phone-tokenization key is set (INT-131, unchanged);
2. OpenBao holds ``secret/api/twilio`` with ``account_sid``, ``auth_token`` and
   ``from`` — invariant 14, the auth token is a secret and secrets come from
   OpenBao; the ``TWILIO_*`` environment variables configure nothing;
3. the egress policy admits the SMS purpose to ``api.twilio.com`` — which the
   shipped allow-list does not, because that row is the owner's DPA and
   cross-border decision.

Anything missing leaves the tier unconfigured (every /v1/auth route 503) and
the dev event logger is never the fallback (#521 / INT-325). Dev is unchanged.

The route maps every delivery failure to one generic ``503
otp_delivery_unavailable``: never a fake "sent", never a vendor body.
"""

from __future__ import annotations

import base64
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
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.secrets import SecretsBootError
from intake_platform.tokenization import Tokenizer
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from twilio_testkit import (
    ACCOUNT_SID,
    AUTH_TOKEN,
    FAILURES,
    MESSAGE_SID,
    PHONE,
    SENDER,
    SHIPPED_ALLOWLIST,
    STRICT_ENVIRONMENTS,
    VAULT_DOC,
    Vault,
    Vendor,
    adapter,
    allowlist_with_the_row,
    assert_clean,
    complete_vault,
    created,
    empty_policy,
    record_text,
    twilio,
)


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
    )


# --- the matrix -----------------------------------------------------------------------


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_non_dev_wires_twilio_when_every_piece_is_present(
    phi_egress: None, tmp_path: Path, environment: str
) -> None:
    vault = complete_vault()
    settings = _settings(environment, allowlist_with_the_row(tmp_path))
    wiring = _auth_from_settings(settings, secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert isinstance(wiring.delivery, twilio().TwilioSmsDeliveryAdapter)
    assert vault.paths == ["api/twilio"]


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
@pytest.mark.parametrize("field", ["account_sid", "auth_token", "from"])
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
    assert _auth_from_settings(settings, secrets=Vault({"api/twilio": doc})) is None
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
    """Invariant 14: TWILIO_* in the environment configure nothing — the auth
    token is a secret, and secrets come from OpenBao."""
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", ACCOUNT_SID)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("TWILIO_FROM", SENDER)
    settings = _settings(environment, allowlist_with_the_row(tmp_path))
    assert _auth_from_settings(settings, secrets=Vault()) is None


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_the_shipped_allowlist_keeps_the_tier_at_503(
    phi_egress: None, environment: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Today's state: credentials alone do not configure the tier, because the
    SMS row does not exist until the owner records the DPA and the
    cross-border decision."""
    caplog.set_level(logging.WARNING)
    assert _auth_from_settings(_settings(environment), secrets=complete_vault()) is None
    assert any("egress" in record.getMessage() for record in caplog.records)


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


def test_dev_keeps_the_dev_logger_whatever_the_vault_holds(
    phi_egress: None, tmp_path: Path
) -> None:
    vault = complete_vault()
    wiring = _auth_from_settings(_settings("dev", allowlist_with_the_row(tmp_path)), secrets=vault)
    assert isinstance(wiring, AuthWiring)
    assert isinstance(wiring.delivery, DevLogDeliveryAdapter)
    assert vault.paths == []


def test_settings_read_the_allowlist_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """One variable points both readers of the allow-list (this wiring and the
    compliance register) at the same file."""
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    monkeypatch.setenv("INTAKE_EGRESS_ALLOWLIST_PATH", "/etc/intake/egress-allowlist.yaml")
    assert ApiSettings.from_env().egress_allowlist_path == Path("/etc/intake/egress-allowlist.yaml")
    monkeypatch.delenv("INTAKE_EGRESS_ALLOWLIST_PATH")
    assert ApiSettings.from_env().egress_allowlist_path == Path(
        "infra/security/egress-allowlist.yaml"
    )


# --- the route: 202 with the vendor id, or a generic 503 ---------------------------


def _harness(tmp_path: Path, delivery: Any) -> Iterator[TestClient]:
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
        auth=AuthWiring(
            redis_client=fakeredis.FakeStrictRedis(),
            tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
            delivery=delivery,
            attestation=DevStructuralAttestationVerifier(),
        ),
    )
    run(ensure_consumer_tenant(engine))
    with TestClient(create_app(wiring), raise_server_exceptions=False) as client:
        yield client
    run(engine.dispose())
    audit_engine.dispose()


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


def test_the_route_answers_202_with_the_vendor_message_id(phi_egress: None, tmp_path: Path) -> None:
    for client in _harness(tmp_path, adapter(Vendor(created))):
        response = _request_otp(client)
        assert response.status_code == 202, response.text
        assert response.json()["delivery_id"] == MESSAGE_SID


@pytest.mark.parametrize(
    "scenario", ["invalid-number-400", "auth-failure-401", "vendor-500", "timeout"]
)
def test_a_failed_delivery_is_a_generic_503_never_a_fake_sent(
    phi_egress: None, tmp_path: Path, scenario: str
) -> None:
    for client in _harness(tmp_path, adapter(Vendor(FAILURES[scenario][0]))):
        response = _request_otp(client)
        assert response.status_code == 503, response.text
        assert response.json() == {"error": "otp_delivery_unavailable"}
        assert_clean(response.text, "the response body")


def test_an_egress_refusal_reaches_the_route_as_the_same_503(
    phi_egress: None, tmp_path: Path
) -> None:
    vendor = Vendor(created)
    for client in _harness(tmp_path, adapter(vendor, empty_policy())):
        response = _request_otp(client)
        assert response.status_code == 503
        assert response.json() == {"error": "otp_delivery_unavailable"}
    assert vendor.requests == []
