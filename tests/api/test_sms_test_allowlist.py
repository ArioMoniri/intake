"""INT-528 — the synthetic host's SMS test allow-list (owner order, 16 Oct 2026).

SMS is real on the synthetic host, so there the API sends a code, and starts an
OTP login, only for a number on the owner's list: SSM SecureString
``/intake/staging/sms_test_allowlist``, synced into OpenBao ``secret/api/netgsm``
as ``test_allowlist``. An empty, unreadable or malformed list admits nobody.

Every number here is synthetic. The near miss differs from the listed number by
one digit. No number reaches a log line, an error, a metric label or the route's
answer (invariant 6).
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
from intake_api.otp import AuthWiring, ensure_consumer_tenant
from intake_api.settings import ApiSettings
from intake_api.sms_recipients import ADMIT_ALL, SmsTestAllowlist
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.tokenization import Tokenizer
from netgsm_testkit import (
    VAULT_DOC,
    Vault,
    Vendor,
    accepted,
    adapter,
    allowlist_with_the_row,
    netgsm,
    otp_module,
    policy,
    record_text,
    send,
)
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

LISTED = "+905550000001"
NEAR_MISS = "+905550000002"  # one digit away from LISTED
OTHER = "+905559999999"
NUMBERS = (LISTED, NEAR_MISS, OTHER, LISTED[3:], NEAR_MISS[3:])


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


def _clean(text: str, where: str) -> None:
    for number in NUMBERS:
        assert number not in text, f"{where} carries a phone number"


# --- the list -----------------------------------------------------------------------------


def test_the_listed_number_is_admitted_and_its_near_miss_is_not() -> None:
    gate = SmsTestAllowlist.parse(LISTED)
    assert gate.admits(LISTED)
    assert not gate.admits(NEAR_MISS)
    assert not gate.admits(OTHER)


@pytest.mark.parametrize(
    "raw",
    [f"{LISTED},{OTHER}", f"{LISTED}\n{OTHER}\n", f" {LISTED} ; {OTHER}\t"],
    ids=["comma", "newline", "spaces-and-semicolon"],
)
def test_several_numbers_may_be_listed(raw: str) -> None:
    gate = SmsTestAllowlist.parse(raw)
    assert gate.admits(LISTED) and gate.admits(OTHER)
    assert not gate.admits(NEAR_MISS)
    assert gate.count == 2


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        905550000001,
        ["+905550000001"],
        "05550000001",
        "+4915112345678",
        f"{LISTED},not-a-number",
        f"{LISTED},+90555000000",
    ],
    ids=[
        "absent",
        "empty",
        "blank",
        "number-type",
        "list-type",
        "national-form",
        "abroad",
        "one-malformed-entry",
        "one-short-entry",
    ],
)
def test_an_empty_unreadable_or_malformed_list_admits_nobody(raw: object) -> None:
    """Fail closed: one bad entry voids the whole list, so a typo never
    quietly narrows it to something nobody checked."""
    gate = SmsTestAllowlist.parse(raw)
    assert gate.count == 0
    assert not gate.admits(LISTED)


def test_the_list_never_shows_its_numbers() -> None:
    gate = SmsTestAllowlist.parse(f"{LISTED},{OTHER}")
    _clean(repr(gate), "the allow-list's repr")
    _clean(str(gate), "the allow-list's str")


# --- the adapter refuses before the wire ---------------------------------------------------


def test_the_adapter_sends_to_the_listed_number(phi_egress: None) -> None:
    vendor = Vendor(accepted)
    delivery = netgsm().NetgsmSmsDeliveryAdapter(
        netgsm().NetgsmCredentials.parse(VAULT_DOC),
        egress=policy(),
        inner=httpx.MockTransport(vendor),
        recipients=SmsTestAllowlist.parse(LISTED),
    )
    assert send(delivery, phone=LISTED).delivery_id
    assert vendor.requests


@pytest.mark.parametrize("phone", [NEAR_MISS, OTHER])
def test_the_adapter_refuses_an_unlisted_number_before_the_wire(
    phi_egress: None, phone: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    vendor = Vendor(accepted)
    delivery = netgsm().NetgsmSmsDeliveryAdapter(
        netgsm().NetgsmCredentials.parse(VAULT_DOC),
        egress=policy(),
        inner=httpx.MockTransport(vendor),
        recipients=SmsTestAllowlist.parse(LISTED),
    )
    with pytest.raises(otp_module().OtpDeliveryError) as caught:
        send(delivery, phone=phone)
    assert caught.value.refusal == netgsm().NetgsmRefusal.NOT_ON_TEST_ALLOWLIST
    assert vendor.requests == []
    _clean(f"{caught.value} {vars(caught.value)!r}", "the error")
    for record in caplog.records:
        _clean(record_text(record), "a log record")


# --- the wiring: the synthetic host reads the list, and fails closed without it -------------


def _settings(environment: str, allowlist: Path) -> ApiSettings:
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
        # INT-581: on the synthetic host the dedicated SMS proxy is the only
        # route out (ADR-042), so a staging wiring names it
        sms_egress_proxy_url="http://sms-egress:3128" if environment == "staging" else None,
    )


def test_the_synthetic_host_wires_the_list_from_the_vault(phi_egress: None, tmp_path: Path) -> None:
    vault = Vault({"api/netgsm": {**VAULT_DOC, "test_allowlist": LISTED}})
    wiring = _auth_from_settings(_settings("staging", allowlist_with_the_row(tmp_path)), vault)
    assert isinstance(wiring, AuthWiring)
    assert wiring.recipients.admits(LISTED)
    assert not wiring.recipients.admits(NEAR_MISS)
    assert wiring.delivery.recipients is wiring.recipients


def test_the_synthetic_host_without_a_list_admits_nobody(
    phi_egress: None, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    vault = Vault({"api/netgsm": VAULT_DOC})
    wiring = _auth_from_settings(_settings("staging", allowlist_with_the_row(tmp_path)), vault)
    assert isinstance(wiring, AuthWiring)
    assert not wiring.recipients.admits(LISTED)
    assert any("test allow-list" in record.getMessage() for record in caplog.records)


def test_production_has_no_test_list(phi_egress: None, tmp_path: Path) -> None:
    vault = Vault({"api/netgsm": {**VAULT_DOC, "test_allowlist": LISTED}})
    wiring = _auth_from_settings(_settings("prod", allowlist_with_the_row(tmp_path)), vault)
    assert isinstance(wiring, AuthWiring)
    assert wiring.recipients is ADMIT_ALL


# --- the route: an unlisted number starts no login -------------------------------------------


def _harness(tmp_path: Path, auth: AuthWiring) -> Iterator[TestClient]:
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


def _request_otp(client: TestClient, phone: str) -> Any:
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
        json={"phone": phone},
        headers={"X-Intake-Attestation": json.dumps(attestation)},
    )


@pytest.mark.parametrize(("phone", "sent"), [(LISTED, True), (NEAR_MISS, False)])
def test_an_unlisted_number_starts_no_login_and_sends_nothing(
    phi_egress: None, tmp_path: Path, phone: str, sent: bool
) -> None:
    """INT-579: the unlisted number gets the same 202 as the listed one, so a
    stranger cannot read the owner's test list off the route; only the vendor
    tells them apart."""
    vendor = Vendor(accepted)
    gate = SmsTestAllowlist.parse(LISTED)
    auth = AuthWiring(
        redis_client=fakeredis.FakeStrictRedis(),
        tokenizer=Tokenizer(keys={"v1": b"unit-lane-tokenization-key"}, active_key_id="v1"),
        delivery=adapter(vendor),
        attestation=DevStructuralAttestationVerifier(),
        recipients=gate,
    )
    for client in _harness(tmp_path, auth):
        response = _request_otp(client, phone)
        assert response.status_code == 202, response.text
        assert set(response.json()) == {"request_id", "resend_after_s"}
        _clean(response.text, "the route's answer")
    # the harness closed the app, and shutdown settles every delivery in flight
    assert bool(vendor.requests) is sent
