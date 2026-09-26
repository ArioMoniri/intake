"""INT-325 — production refuses dev bypasses and dev default credentials.

Production audit 2026-09-26, findings F04, F14 and the F13 silent fallback.
Before this issue nothing refused any of the following under ``INTAKE_ENV=prod``:

- the dev gates (``INTAKE_DEV_OTP_PEEK`` lets anyone read any phone's pending
  code, i.e. account takeover; ``INTAKE_DEV_ALLOW_UNATTESTED``;
  ``INTAKE_DEV_TOKEN_PATIENT``/``_ADMIN`` static bearers onto the synthetic
  accounts; ``INTAKE_DEV_GEORGE_TTS``; ``INTAKE_DEV_ALLOW_UNSCANNED``);
- ``INTAKE_API_KEK_MODE=file-dev`` (process-local KEKs: every note becomes
  unreadable on restart);
- a missing DB/MinIO credential variable, which silently fell back to the
  compose dev roles' in-code values;
- the OTP tier wired to the dev event logger, which answers "sent" and
  sends nothing.

Prod is detected the way the other prod gates in the platform detect it
(``intake_platform.documents`` DevNullScanner, ``room_tokens``): ``INTAKE_ENV``
lower-cased starts with ``prod``. That is a superset of ``secrets.py``'s exact
``prod`` match, so every environment the OpenBao gate treats as prod is
refused here too.

Every refusal names the offending variable and never echoes its value
(invariant 6: a dev bearer token in an error report is still a credential).
The dev tier is the control: the same flags and absent credentials still
boot, unchanged.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Sequence

import intake_api.settings as api_settings
import pytest
from api_harness import ApiHarness
from fastapi import FastAPI
from fastapi.testclient import TestClient
from intake_api.app import ApiWiring, _auth_from_settings, create_app
from intake_api.otp import AuthWiring, DevLogDeliveryAdapter
from intake_api.settings import ApiSettings
from intake_platform.audit import AuditEntry, AuditStore

DEV_FLAG_PREFIX = "INTAKE_DEV_"

# flag -> a value that turns the dev behaviour on. The bearer tokens carry a
# credential-shaped value so the "never echo the value" assertion bites.
DEV_FLAGS: dict[str, str] = {
    "INTAKE_DEV_OTP_PEEK": "explicit-yes",
    "INTAKE_DEV_ALLOW_UNATTESTED": "explicit-yes",
    "INTAKE_DEV_TOKEN_PATIENT": "int325-patient-bearer-value",
    "INTAKE_DEV_TOKEN_ADMIN": "int325-admin-bearer-value",
    "INTAKE_DEV_GEORGE_TTS": "explicit-yes",
    "INTAKE_DEV_ALLOW_UNSCANNED": "explicit-yes",
}

# every variable that, when absent, used to fall back to an in-code dev
# credential (settings.py DB URLs; app.py MinIO root pair)
CREDENTIAL_VARS: dict[str, str] = {
    "INTAKE_API_DB_URL": "postgresql+psycopg://app_rw@db.prod.internal:5432/intake",
    "INTAKE_API_AUDIT_DB_URL": "postgresql+psycopg://svc_audit_writer@db.prod.internal:5432/intake",
    "INTAKE_API_BOOTSTRAP_DB_URL": "postgresql+psycopg://intake_owner@db.prod.internal:5432/intake",
    "MINIO_ROOT_USER": "int325-object-store-user",
    "MINIO_ROOT_PASSWORD": "int325-object-store-secret",
}


@pytest.fixture()
def prod_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A COMPLETE production environment: no dev flag, durable KEK mode, every
    credential supplied. Each refusal test breaks exactly one thing in it."""
    for name in list(os.environ):
        if name.startswith(DEV_FLAG_PREFIX):
            monkeypatch.delenv(name)
    monkeypatch.delenv("INTAKE_API_KEK_MODE", raising=False)
    for name, value in CREDENTIAL_VARS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("INTAKE_ENV", "prod")
    return monkeypatch


def _refused_error() -> type[Exception]:
    # resolved at call time so a missing class fails each case, not collection
    error: type[Exception] = api_settings.ProdConfigRefusedError
    return error


def _settings(*, production: bool) -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url=CREDENTIAL_VARS["INTAKE_API_DB_URL"],
        audit_db_url=CREDENTIAL_VARS["INTAKE_API_AUDIT_DB_URL"],
        bootstrap_db_url=CREDENTIAL_VARS["INTAKE_API_BOOTSTRAP_DB_URL"],
        kek_mode="transit",
        tokenization_key="int325-tokenization-key",
        production=production,
    )


# --- the positive control: a complete prod config boots -----------------------------


def test_complete_prod_config_is_accepted(prod_env: pytest.MonkeyPatch) -> None:
    """Without this the refusals below could all pass by refusing prod outright."""
    settings = ApiSettings.from_env()
    assert settings.production is True
    assert settings.kek_mode == "transit"
    assert settings.token_patient is None and settings.token_admin is None
    assert settings.dev_otp_peek is False and settings.dev_allow_unattested is False
    assert settings.app_db_url == CREDENTIAL_VARS["INTAKE_API_DB_URL"]
    assert settings.audit_db_url == CREDENTIAL_VARS["INTAKE_API_AUDIT_DB_URL"]
    assert settings.bootstrap_db_url == CREDENTIAL_VARS["INTAKE_API_BOOTSTRAP_DB_URL"]


# --- F04: every dev bypass flag is refused -----------------------------------------------


@pytest.mark.parametrize("flag", sorted(DEV_FLAGS))
def test_prod_refuses_each_dev_flag(prod_env: pytest.MonkeyPatch, flag: str) -> None:
    value = DEV_FLAGS[flag]
    prod_env.setenv(flag, value)
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    message = str(refused.value)
    assert flag in message
    assert value not in message  # invariant 6: names only, never values


def test_prod_refuses_a_dev_flag_that_is_not_the_opt_in_phrase(
    prod_env: pytest.MonkeyPatch,
) -> None:
    """In dev only the exact phrase turns a gate on; in prod the flag being
    present at all is the misconfiguration, whatever it says."""
    prod_env.setenv("INTAKE_DEV_OTP_PEEK", "yes")
    with pytest.raises(_refused_error()):
        ApiSettings.from_env()


def test_prod_refuses_any_future_dev_flag_by_prefix(prod_env: pytest.MonkeyPatch) -> None:
    """The refusal is by the ``INTAKE_DEV_`` prefix, so a dev gate added
    after this issue is refused in prod without anyone remembering to list it."""
    future_flag = DEV_FLAG_PREFIX + "INT325_NOT_YET_INVENTED"
    prod_env.setenv(future_flag, "explicit-yes")
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    assert future_flag in str(refused.value)


def test_prod_refuses_file_dev_kek(prod_env: pytest.MonkeyPatch) -> None:
    prod_env.setenv("INTAKE_API_KEK_MODE", "file-dev")
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    assert "INTAKE_API_KEK_MODE" in str(refused.value)


# --- F14: no in-code dev credential is ever used in prod ------------------------------


@pytest.mark.parametrize("state", ["unset", "empty"])
@pytest.mark.parametrize("variable", sorted(CREDENTIAL_VARS))
def test_prod_refuses_each_missing_credential(
    prod_env: pytest.MonkeyPatch, variable: str, state: str
) -> None:
    if state == "unset":
        prod_env.delenv(variable)
    else:
        prod_env.setenv(variable, "")
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    assert variable in str(refused.value)


def test_prod_refusal_names_every_offence_at_once(prod_env: pytest.MonkeyPatch) -> None:
    """One boot, one list: an operator fixes the deployment in one pass."""
    prod_env.setenv("INTAKE_DEV_OTP_PEEK", "explicit-yes")
    prod_env.setenv("INTAKE_API_KEK_MODE", "file-dev")
    prod_env.delenv("MINIO_ROOT_PASSWORD")
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    message = str(refused.value)
    for name in ("INTAKE_DEV_OTP_PEEK", "INTAKE_API_KEK_MODE", "MINIO_ROOT_PASSWORD"):
        assert name in message


@pytest.mark.parametrize("env_value", ["PROD", "production", "prod-tr"])
def test_prod_detection_is_case_insensitive_and_by_prefix(
    prod_env: pytest.MonkeyPatch, env_value: str
) -> None:
    prod_env.setenv("INTAKE_ENV", env_value)
    prod_env.setenv("INTAKE_DEV_OTP_PEEK", "explicit-yes")
    with pytest.raises(_refused_error()):
        ApiSettings.from_env()


def test_the_boot_path_refuses_before_wiring_anything(prod_env: pytest.MonkeyPatch) -> None:
    """``create_app()`` with no wiring is how the service boots; the refusal
    must reach it, not only a direct ``from_env`` call."""
    prod_env.setenv("INTAKE_DEV_TOKEN_ADMIN", DEV_FLAGS["INTAKE_DEV_TOKEN_ADMIN"])
    with pytest.raises(_refused_error()):
        create_app()


# --- F13: the OTP tier never claims a delivery it did not make -------------------------


def test_prod_never_wires_the_dev_log_delivery_adapter() -> None:
    """With no contracted SMS vendor wired, prod leaves the OTP tier
    unconfigured (every /v1/auth route answers 503 otp_auth_unconfigured)
    rather than answering 202 for a code that never leaves the building."""
    assert _auth_from_settings(_settings(production=True)) is None


# --- the dev control: dev behaviour is unchanged ---------------------------------------


def test_dev_tier_still_wires_the_dev_log_delivery_adapter() -> None:
    wiring = _auth_from_settings(_settings(production=False))
    assert isinstance(wiring, AuthWiring)
    assert isinstance(wiring.delivery, DevLogDeliveryAdapter)


@pytest.mark.parametrize("env_value", [None, "dev"])
def test_dev_tier_still_boots_with_every_dev_flag_and_no_credentials(
    monkeypatch: pytest.MonkeyPatch, env_value: str | None
) -> None:
    if env_value is None:
        monkeypatch.delenv("INTAKE_ENV", raising=False)
    else:
        monkeypatch.setenv("INTAKE_ENV", env_value)
    for name, value in DEV_FLAGS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("INTAKE_API_KEK_MODE", "file-dev")
    for name in CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)

    settings = ApiSettings.from_env()
    assert settings.production is False
    assert settings.kek_mode == "file-dev"
    assert settings.dev_otp_peek is True and settings.dev_allow_unattested is True
    assert settings.dev_auth_configured
    # the compose dev roles, exactly as before INT-325
    assert settings.app_db_url.startswith("postgresql+psycopg://app_rw:")
    assert settings.audit_db_url.startswith("postgresql+psycopg://svc_audit_writer:")


# --- readiness: prod does not wait on the dev bearers it refuses -----------------------


class _BrokenAuditStore:
    """An audit backend that is gone: readiness must report it in prod too."""

    def append(self, entry: AuditEntry) -> None:
        raise ConnectionError("audit backend unavailable")

    def last(self) -> AuditEntry | None:
        raise ConnectionError("audit backend unavailable")

    def entries(self) -> Sequence[AuditEntry]:
        raise ConnectionError("audit backend unavailable")


def _app_without_dev_bearers(
    harness: ApiHarness, *, production: bool, audit_store: AuditStore | None = None
) -> FastAPI:
    """The harness's healthy sqlite db and audit store, with neither dev
    bearer set: exactly what a prod boot looks like once INT-325 refuses them."""
    settings = dataclasses.replace(
        harness.settings, production=production, token_patient=None, token_admin=None
    )
    return create_app(
        ApiWiring(
            settings=settings,
            engine=harness.engine,
            audit_store=audit_store if audit_store is not None else harness.audit_store,
            cipher=harness.cipher,
            bootstrap=False,
        )
    )


def test_prod_is_ready_with_every_real_dependency_healthy(harness: ApiHarness) -> None:
    """Prod refuses INTAKE_DEV_TOKEN_* at boot, so a readiness check that
    requires them would hold every prod API not-ready forever."""
    app = _app_without_dev_bearers(harness, production=True)
    with TestClient(app, raise_server_exceptions=False) as client:
        ready = client.get("/readyz")
    assert ready.status_code == 200, ready.text
    assert ready.json()["checks"] == {"db": "ok", "audit_store": "ok"}


def test_prod_readiness_still_fails_on_a_real_dependency(harness: ApiHarness) -> None:
    """Near-miss control: dropping the dev-bearer check must not make prod
    readiness vacuous. A dead audit store still holds it not-ready."""
    app = _app_without_dev_bearers(harness, production=True, audit_store=_BrokenAuditStore())
    with TestClient(app, raise_server_exceptions=False) as client:
        ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json()["checks"]["audit_store"] == "error"


def test_dev_readiness_still_requires_the_dev_bearers(harness: ApiHarness) -> None:
    """Dev is unchanged (INT-197): without both bearers the dev tier is not ready."""
    app = _app_without_dev_bearers(harness, production=False)
    with TestClient(app, raise_server_exceptions=False) as client:
        ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json()["checks"] == {"db": "ok", "audit_store": "ok", "dev_auth": "error"}
