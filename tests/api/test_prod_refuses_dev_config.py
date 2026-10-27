"""INT-325 — outside dev, the API refuses dev bypasses and dev default credentials.

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

A public staging host must be exactly as strict as prod, so the refusal
applies to every environment that is not dev. Dev is ``INTAKE_ENV`` unset,
empty or ``dev`` (stripped, lower-cased), which is the only non-prod value any
test, CI job or compose file in this repository sets; ``staging`` (PR #549's
infra/staging) and anything else are strict.

Every refusal names the offending variable and never echoes its value
(invariant 6: a dev bearer token in an error report is still a credential).
The dev tier is the control: the same flags and absent credentials still
boot, unchanged.
"""

from __future__ import annotations

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

# the environments this repository actually deploys outside dev
STRICT_ENVIRONMENTS = ("prod", "staging")

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


def _complete_env(monkeypatch: pytest.MonkeyPatch, environment: str) -> pytest.MonkeyPatch:
    """A COMPLETE non-dev environment: no dev flag, durable KEK mode, every
    credential supplied. Each refusal test breaks exactly one thing in it."""
    for name in list(os.environ):
        if name.startswith(DEV_FLAG_PREFIX):
            monkeypatch.delenv(name)
    monkeypatch.delenv("INTAKE_API_KEK_MODE", raising=False)
    for name, value in CREDENTIAL_VARS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("INTAKE_ENV", environment)
    return monkeypatch


@pytest.fixture(params=STRICT_ENVIRONMENTS)
def strict_env(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> pytest.MonkeyPatch:
    return _complete_env(monkeypatch, str(request.param))


def _refused_error() -> type[Exception]:
    # resolved at call time so a missing class fails each case, not collection
    error: type[Exception] = api_settings.DevConfigRefusedError
    return error


def _settings(*, environment: str) -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url=CREDENTIAL_VARS["INTAKE_API_DB_URL"],
        audit_db_url=CREDENTIAL_VARS["INTAKE_API_AUDIT_DB_URL"],
        bootstrap_db_url=CREDENTIAL_VARS["INTAKE_API_BOOTSTRAP_DB_URL"],
        kek_mode="transit",
        tokenization_key="int325-tokenization-key",
        environment=environment,
    )


# --- the positive control: a complete non-dev config boots ---------------------------


def test_complete_non_dev_config_is_accepted(strict_env: pytest.MonkeyPatch) -> None:
    """Without this the refusals below could all pass by refusing outright."""
    settings = ApiSettings.from_env()
    assert settings.dev_tier_expected is False
    assert settings.kek_mode == "transit"
    assert settings.token_patient is None and settings.token_admin is None
    assert settings.dev_otp_peek is False and settings.dev_allow_unattested is False
    assert settings.app_db_url == CREDENTIAL_VARS["INTAKE_API_DB_URL"]
    assert settings.audit_db_url == CREDENTIAL_VARS["INTAKE_API_AUDIT_DB_URL"]
    assert settings.bootstrap_db_url == CREDENTIAL_VARS["INTAKE_API_BOOTSTRAP_DB_URL"]


# --- F04: every dev bypass flag is refused -----------------------------------------------


@pytest.mark.parametrize("flag", sorted(DEV_FLAGS))
def test_refuses_each_dev_flag(strict_env: pytest.MonkeyPatch, flag: str) -> None:
    value = DEV_FLAGS[flag]
    strict_env.setenv(flag, value)
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    message = str(refused.value)
    assert flag in message
    assert value not in message  # invariant 6: names only, never values


def test_refuses_a_dev_flag_that_is_not_the_opt_in_phrase(
    strict_env: pytest.MonkeyPatch,
) -> None:
    """In dev only the exact phrase turns a gate on; outside dev the flag
    being present at all is the misconfiguration, whatever it says."""
    strict_env.setenv("INTAKE_DEV_OTP_PEEK", "yes")
    with pytest.raises(_refused_error()):
        ApiSettings.from_env()


def test_refuses_any_future_dev_flag_by_prefix(strict_env: pytest.MonkeyPatch) -> None:
    """The refusal is by the ``INTAKE_DEV_`` prefix, so a dev gate added after
    this issue is refused outside dev without anyone remembering to list it."""
    future_flag = DEV_FLAG_PREFIX + "INT325_NOT_YET_INVENTED"
    strict_env.setenv(future_flag, "explicit-yes")
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    assert future_flag in str(refused.value)


def test_refuses_file_dev_kek(strict_env: pytest.MonkeyPatch) -> None:
    strict_env.setenv("INTAKE_API_KEK_MODE", "file-dev")
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    assert "INTAKE_API_KEK_MODE" in str(refused.value)


# --- F14: no in-code dev credential is ever used outside dev -------------------------


@pytest.mark.parametrize("state", ["unset", "empty"])
@pytest.mark.parametrize("variable", sorted(CREDENTIAL_VARS))
def test_refuses_each_missing_credential(
    strict_env: pytest.MonkeyPatch, variable: str, state: str
) -> None:
    if state == "unset":
        strict_env.delenv(variable)
    else:
        strict_env.setenv(variable, "")
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    assert variable in str(refused.value)


def test_refusal_names_every_offence_at_once(strict_env: pytest.MonkeyPatch) -> None:
    """One boot, one list: an operator fixes the deployment in one pass."""
    strict_env.setenv("INTAKE_DEV_OTP_PEEK", "explicit-yes")
    strict_env.setenv("INTAKE_API_KEK_MODE", "file-dev")
    strict_env.delenv("MINIO_ROOT_PASSWORD")
    with pytest.raises(_refused_error()) as refused:
        ApiSettings.from_env()
    message = str(refused.value)
    for name in ("INTAKE_DEV_OTP_PEEK", "INTAKE_API_KEK_MODE", "MINIO_ROOT_PASSWORD"):
        assert name in message


@pytest.mark.parametrize(
    "env_value", ["PROD", "production", "prod-tr", "STAGING", " staging ", "test"]
)
def test_every_non_dev_spelling_is_strict(monkeypatch: pytest.MonkeyPatch, env_value: str) -> None:
    """Strict is everything that is not dev. ``test`` is listed on purpose:
    nothing in this repository sets it, so it gets no dev exemption."""
    _complete_env(monkeypatch, env_value)
    monkeypatch.setenv("INTAKE_DEV_OTP_PEEK", "explicit-yes")
    with pytest.raises(_refused_error()):
        ApiSettings.from_env()


def test_the_boot_path_refuses_before_wiring_anything(strict_env: pytest.MonkeyPatch) -> None:
    """``create_app()`` with no wiring is how the service boots; the refusal
    must reach it, not only a direct ``from_env`` call."""
    strict_env.setenv("INTAKE_DEV_TOKEN_ADMIN", DEV_FLAGS["INTAKE_DEV_TOKEN_ADMIN"])
    with pytest.raises(_refused_error()):
        create_app()


# --- F13: the OTP tier never claims a delivery it did not make -------------------------


class _EmptyVault:
    """OpenBao with no SMS vendor document (INT-329 reads it from there)."""

    def get_kv(self, path: str) -> dict[str, object]:
        raise KeyError(path)


@pytest.mark.parametrize("environment", STRICT_ENVIRONMENTS)
def test_non_dev_never_wires_the_dev_log_delivery_adapter(environment: str) -> None:
    """With no SMS vendor configured, a non-dev API leaves the OTP tier
    unconfigured (every /v1/auth route answers 503 otp_auth_unconfigured)
    rather than answering 202 for a code that never leaves the building.
    INT-528 wires Netgsm when it IS configured (tests/api/test_otp_netgsm_wiring.py);
    the dev logger is never the fallback."""
    assert _auth_from_settings(_settings(environment=environment), secrets=_EmptyVault()) is None


# --- the dev control: dev behaviour is unchanged ---------------------------------------


def test_dev_tier_still_wires_the_dev_log_delivery_adapter() -> None:
    wiring = _auth_from_settings(_settings(environment="dev"))
    assert isinstance(wiring, AuthWiring)
    assert isinstance(wiring.delivery, DevLogDeliveryAdapter)


@pytest.mark.parametrize("env_value", [None, "", "dev", "DEV", " dev "])
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
    assert settings.dev_tier_expected is True
    assert settings.kek_mode == "file-dev"
    assert settings.dev_otp_peek is True and settings.dev_allow_unattested is True
    assert settings.dev_auth_configured
    # the compose dev roles, exactly as before INT-325
    assert settings.app_db_url.startswith("postgresql+psycopg://app_rw:")
    assert settings.audit_db_url.startswith("postgresql+psycopg://svc_audit_writer:")


# --- readiness: only the dev environment waits on the dev bearers ---------------------


class _BrokenAuditStore:
    """An audit backend that is gone: readiness must report it outside dev too."""

    def append(self, entry: AuditEntry) -> None:
        raise ConnectionError("audit backend unavailable")

    def last(self) -> AuditEntry | None:
        raise ConnectionError("audit backend unavailable")

    def entries(self) -> Sequence[AuditEntry]:
        raise ConnectionError("audit backend unavailable")


def _app_for_environment(
    harness: ApiHarness,
    monkeypatch: pytest.MonkeyPatch,
    environment: str | None,
    audit_store: AuditStore | None = None,
) -> FastAPI:
    """Settings built the way the service builds them (``ApiSettings.from_env``)
    for one ``INTAKE_ENV``, with no ``INTAKE_DEV_*`` variable at all, over the
    harness's healthy sqlite db and audit store."""
    for name in list(os.environ):
        if name.startswith(DEV_FLAG_PREFIX):
            monkeypatch.delenv(name)
    monkeypatch.delenv("INTAKE_API_KEK_MODE", raising=False)
    for name, value in CREDENTIAL_VARS.items():
        monkeypatch.setenv(name, value)
    if environment is None:
        monkeypatch.delenv("INTAKE_ENV", raising=False)
    else:
        monkeypatch.setenv("INTAKE_ENV", environment)
    return create_app(
        ApiWiring(
            settings=ApiSettings.from_env(),
            engine=harness.engine,
            audit_store=audit_store if audit_store is not None else harness.audit_store,
            cipher=harness.cipher,
            bootstrap=False,
        )
    )


@pytest.mark.parametrize("environment", ["prod", "staging"])
def test_non_dev_environment_is_ready_with_every_real_dependency_healthy(
    harness: ApiHarness, monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    """Dev bearers are expected only in dev. Prod and staging (infra/staging)
    refuse them at boot, so a readiness check that requires them would hold
    either API not-ready forever."""
    app = _app_for_environment(harness, monkeypatch, environment)
    with TestClient(app, raise_server_exceptions=False) as client:
        ready = client.get("/readyz")
    assert ready.status_code == 200, ready.text
    assert ready.json()["checks"] == {"db": "ok", "audit_store": "ok"}


@pytest.mark.parametrize("environment", ["prod", "staging"])
def test_non_dev_readiness_still_fails_on_a_real_dependency(
    harness: ApiHarness, monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    """Near-miss control: dropping the dev-bearer check must not make
    readiness vacuous. A dead audit store still holds the API not-ready."""
    app = _app_for_environment(harness, monkeypatch, environment, _BrokenAuditStore())
    with TestClient(app, raise_server_exceptions=False) as client:
        ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json()["checks"]["audit_store"] == "error"


@pytest.mark.parametrize("environment", [None, "dev"])
def test_dev_readiness_still_requires_the_dev_bearers(
    harness: ApiHarness, monkeypatch: pytest.MonkeyPatch, environment: str | None
) -> None:
    """Dev is unchanged (INT-197): without both bearers the dev tier is not
    ready, whether INTAKE_ENV says dev or is unset (dev is the default)."""
    app = _app_for_environment(harness, monkeypatch, environment)
    with TestClient(app, raise_server_exceptions=False) as client:
        ready = client.get("/readyz")
    assert ready.status_code == 503
    assert ready.json()["checks"] == {"db": "ok", "audit_store": "ok", "dev_auth": "error"}
