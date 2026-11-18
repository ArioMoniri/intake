"""INT-613: the App Review sign-in harness (D39) against main's real API, in process.

scripts/release/review_signin_harness.py walks the app's sign-in calls. Here it
runs against main's own FastAPI app, wired the way the dev tier wires it:

* the dev attestation tier (``dev-unattested``) and the dev peek route;
* a counting delivery adapter as the SMS probe;
* synthetic numbers only, and no Apple credential.

What this file proves:

* a synthetic patient signs in end to end (request, verify with DPoP,
  refresh, an authenticated read), and exactly one delivery is recorded;
* the report carries no number, code or token;
* near misses: a wrong code fails at verify; a host without the dev tier
  refuses the unattested payload, which is what ``--probe-unattested``
  expects of a public host;
* the D39 check fails closed: main's API does not reserve any number yet,
  because INT-488 is not merged. So the harness's no-SMS check reports
  ``sms_sent`` against it. Once INT-488 lands, the same check runs against
  the reserved number and must pass. That test belongs with INT-488.
* the CLI refuses a full sign-in against a host, refuses to probe with the
  reviewer number, and takes no code on its command line.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import fakeredis
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "api"))

from api_harness import run, sqlite_ddl_clone  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from intake_api.app import ApiWiring, create_app  # noqa: E402
from intake_api.attestation import (  # noqa: E402
    AttestationReason,
    DevStructuralAttestationVerifier,
    FailClosedAttestationVerifier,
    PlatformAttestationVerifier,
)
from intake_api.otp import (  # noqa: E402
    AuthWiring,
    DeliveryReceipt,
    DevLogDeliveryAdapter,
    ensure_consumer_tenant,
)
from intake_api.settings import ApiSettings  # noqa: E402
from intake_platform.envelope import EnvelopeCipher, FileKekProvider  # noqa: E402
from intake_platform.tokenization import Tokenizer  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

BASE = "http://testserver"
#: Synthetic numbers in the shape the other OTP suites use; nobody's.
PATIENT = "+905321114455"
OTHER = "+905321114466"


def _load() -> ModuleType:
    path = REPO / "scripts" / "release" / "review_signin_harness.py"
    spec = importlib.util.spec_from_file_location("review_signin_harness", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


H = _load()


class CountingDelivery:
    """The SMS seam, counted. It wraps the dev adapter and sends nothing."""

    def __init__(self) -> None:
        self.sent = 0
        self._inner = DevLogDeliveryAdapter()

    async def send(self, *, phone_e164: str, code: str) -> DeliveryReceipt:
        self.sent += 1
        return await self._inner.send(phone_e164=phone_e164, code=code)


@dataclass
class Api:
    client: TestClient
    delivery: CountingDelivery


def _build(tmp_path: Path, *, dev_tier: bool) -> Iterator[Api]:
    from intake_platform.db.audit_store import SqlAlchemyAuditStore
    from sqlalchemy import create_engine

    app_db = tmp_path / "signin.db"
    audit_db = tmp_path / "signin-audit.db"
    for path in (app_db, audit_db):
        ddl = create_engine(f"sqlite+pysqlite:///{path}")
        sqlite_ddl_clone().create_all(ddl)
        ddl.dispose()
    audit_engine = create_engine(f"sqlite+pysqlite:///{audit_db}")
    engine = create_async_engine(f"sqlite+aiosqlite:///{app_db}", poolclass=NullPool)
    delivery = CountingDelivery()
    refused = FailClosedAttestationVerifier(AttestationReason.APP_ATTEST_NOT_CONFIGURED)
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
            tokenizer=Tokenizer(keys={"v1": b"int613-harness-tokenization"}, active_key_id="v1"),
            delivery=delivery,
            attestation=PlatformAttestationVerifier(
                app_attest=refused,
                play_integrity=FailClosedAttestationVerifier(
                    AttestationReason.PLAY_INTEGRITY_NOT_CONFIGURED
                ),
                dev=DevStructuralAttestationVerifier() if dev_tier else None,
            ),
            dev_otp_peek=dev_tier,
        ),
    )
    run(ensure_consumer_tenant(engine))
    with TestClient(create_app(wiring), raise_server_exceptions=False) as client:
        yield Api(client=client, delivery=delivery)
    run(engine.dispose())
    audit_engine.dispose()


@pytest.fixture()
def dev_api(tmp_path: Path) -> Iterator[Api]:
    yield from _build(tmp_path, dev_tier=True)


@pytest.fixture()
def public_api(tmp_path: Path) -> Iterator[Api]:
    """No dev tier: what a public host runs (INT-348)."""
    yield from _build(tmp_path, dev_tier=False)


def _harness(api: Api, **knobs: object) -> object:
    return H.SignInHarness(
        client=api.client,
        base_url=BASE,
        attestor=H.dev_unattested(),
        codes=knobs.pop("codes", H.DevPeek()),
        sms_probe=lambda: api.delivery.sent,
        **knobs,
    )


def test_a_synthetic_patient_signs_in_end_to_end(dev_api: Api) -> None:
    report = _harness(dev_api).run(PATIENT)  # type: ignore[attr-defined]
    assert report.ok, report.render()
    assert [s.name for s in report.steps] == [
        "otp.request",
        "sms.sent_once",
        "code.obtained",
        "otp.verify",
        "token.refresh",
        "session.read",
    ]
    assert dev_api.delivery.sent == 1
    read = report.steps[-1]
    # authenticated: the profile answers, or asks for the core consent; never 401
    assert read.status == 200 or (read.status == 403 and read.error == "consent_required")


def test_the_report_carries_no_number_code_or_token(dev_api: Api) -> None:
    seen: dict[str, str] = {}

    class Spy:
        def code(self, client: object, phone: str) -> str | None:
            value = H.DevPeek().code(client, phone)
            seen["code"] = value or ""
            return value

    report = _harness(dev_api, codes=Spy()).run(PATIENT)  # type: ignore[attr-defined]
    rendered = report.render()
    assert report.ok, rendered
    assert seen["code"] and seen["code"] not in rendered
    for fragment in (PATIENT, PATIENT[1:], PATIENT[-7:], "eyJ", "Bearer", "DPoP "):
        assert fragment not in rendered


def test_near_miss_a_wrong_code_fails_at_verify(dev_api: Api) -> None:
    class Wrong:
        def code(self, client: object, phone: str) -> str | None:
            real = H.DevPeek().code(client, phone) or "000000"
            return "".join(str((int(ch) + 1) % 10) for ch in real)

    report = _harness(dev_api, codes=Wrong()).run(OTHER)  # type: ignore[attr-defined]
    assert not report.ok
    failed = report.steps[-1]
    assert failed.name == "otp.verify" and failed.status in {400, 401, 403}


def test_near_miss_a_public_host_refuses_the_unattested_payload(public_api: Api) -> None:
    report = _harness(public_api).probe_unattested(PATIENT)  # type: ignore[attr-defined]
    assert report.ok, report.render()
    assert public_api.delivery.sent == 0
    # and the full sign-in stops at the request, before any SMS
    full = _harness(public_api).run(PATIENT)  # type: ignore[attr-defined]
    assert not full.ok and full.steps[0].name == "otp.request"
    assert public_api.delivery.sent == 0


def test_the_d39_no_sms_check_fails_closed_until_int_488_reserves_the_number(
    dev_api: Api,
) -> None:
    """main reserves no number, so 'never sends an SMS' cannot pass against it.
    The check reports sms_sent, and nothing pretends otherwise."""
    report = _harness(dev_api, expect_no_sms=True).run(PATIENT)  # type: ignore[attr-defined]
    sms = next(step for step in report.steps if step.name == "sms.not_sent")
    assert not sms.ok and sms.error == "sms_sent"
    assert not report.ok


def test_the_review_code_is_read_from_the_environment_only() -> None:
    source = H.EnvCode({H.ENV_REVIEW_CODE: "fixture-value"})
    assert source.code(None, PATIENT) == "fixture-value"
    assert H.EnvCode({}).code(None, PATIENT) is None


def test_cli_refuses_a_full_sign_in_against_a_host(capsys: pytest.CaptureFixture[str]) -> None:
    assert H.main(["--base-url", "https://synthetic.invalid"], environ={}) == 3
    assert "INT-348" in capsys.readouterr().out


def test_cli_never_probes_with_the_reviewer_number(capsys: pytest.CaptureFixture[str]) -> None:
    env = {H.ENV_PROBE_NUMBER: OTHER, H.ENV_REVIEW_NUMBER: OTHER}
    assert (
        H.main(["--base-url", "https://synthetic.invalid", "--probe-unattested"], environ=env) == 3
    )
    assert "reviewer number" in capsys.readouterr().out
    assert (
        H.main(["--base-url", "https://synthetic.invalid", "--probe-unattested"], environ={}) == 3
    )


def test_cli_takes_no_code_argument() -> None:
    with pytest.raises(SystemExit):
        H.main(["--base-url", "https://synthetic.invalid", "--code", "123456"], environ={})
