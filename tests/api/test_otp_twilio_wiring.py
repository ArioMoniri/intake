"""INT-329 — the Twilio adapter through the OTP route, and the allow-list override.

Twilio was the INT-329 adapter. Since INT-528 the owner's SMS vendor is Netgsm
(INT-358, 16 Oct 2026) and nothing wires Twilio outside tests: the wiring
matrix now lives in test_otp_netgsm_wiring.py, which also pins that a Twilio
row and a Twilio vault document configure nothing.

What stays here is vendor-independent: the route maps every delivery failure
to one generic ``503 otp_delivery_unavailable`` — never a fake "sent", never a
vendor body — and one variable points both readers of the allow-list at the
same file.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import pytest
from api_harness import run, sqlite_ddl_clone
from fastapi.testclient import TestClient
from intake_api.app import ApiWiring, create_app
from intake_api.attestation import DevStructuralAttestationVerifier
from intake_api.otp import AuthWiring, ensure_consumer_tenant
from intake_api.settings import ApiSettings
from intake_platform.envelope import EnvelopeCipher, FileKekProvider
from intake_platform.tokenization import Tokenizer
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from twilio_testkit import (
    FAILURES,
    MESSAGE_SID,
    PHONE,
    Vendor,
    adapter,
    assert_clean,
    created,
    empty_policy,
)


@pytest.fixture()
def phi_egress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_PHI_EGRESS", "explicit-yes")


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


def test_the_route_answers_202_and_the_message_id_is_audited(
    phi_egress: None, tmp_path: Path
) -> None:
    """INT-579: the vendor answers after the response, so its id is on the
    hash chain, not in the 202."""
    for client in _harness(tmp_path, adapter(Vendor(created))):
        response = _request_otp(client)
        assert response.status_code == 202, response.text
        assert set(response.json()) == {"request_id", "resend_after_s"}
        client.portal.call(client.app.state.api.auth.settle)
        entries = client.portal.call(client.app.state.api.audit.entries)
        assert entries[-1].resource_ref == f"delivery:{MESSAGE_SID}"


@pytest.mark.parametrize(
    "scenario", ["invalid-number-400", "auth-failure-401", "vendor-500", "timeout"]
)
def test_a_failed_delivery_answers_like_a_sent_one_and_is_audited(
    phi_egress: None, tmp_path: Path, scenario: str
) -> None:
    """INT-579: the vendor answers after the response, so its refusal (an
    invalid number among them) cannot be read off the route; never a claimed
    send: the chain records the failure."""
    for client in _harness(tmp_path, adapter(Vendor(FAILURES[scenario][0]))):
        response = _request_otp(client)
        assert response.status_code == 202, response.text
        assert set(response.json()) == {"request_id", "resend_after_s"}
        assert_clean(response.text, "the response body")
        client.portal.call(client.app.state.api.auth.settle)
        entries = client.portal.call(client.app.state.api.audit.entries)
        assert entries[-1].action == "auth.otp.delivery_failed"


def test_an_egress_refusal_answers_alike_and_never_reaches_the_vendor(
    phi_egress: None, tmp_path: Path
) -> None:
    vendor = Vendor(created)
    for client in _harness(tmp_path, adapter(vendor, empty_policy())):
        response = _request_otp(client)
        assert response.status_code == 202
    assert vendor.requests == []
