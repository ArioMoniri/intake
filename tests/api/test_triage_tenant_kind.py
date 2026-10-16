"""INT-465: only the synthetic host may declare a synthetic triage tenant.

A synthetic tenant is the only tenant that admits the test-key signature (see
tests/protocols/test_red_signature.py). The setting that declares one is therefore
guarded at boot, as well as at the signature:
- It is honoured only in ``dev`` and on the synthetic ``staging`` host. That host is
  infra/staging: SYNTHETIC PATIENTS ONLY, X-Intake-Environment: staging-synthetic-only.
- Any other environment that declares it refuses to boot. A misconfigured
  production deployment cannot quietly trust a test key.
- Anything but the exact value ``synthetic`` reads as a real tenant, which is the
  fail-closed direction.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from intake_api.settings import (
    ENV_TRIAGE_DEPLOYMENT,
    ENV_TRIAGE_SIGNATURE,
    ENV_TRIAGE_TENANT_KIND,
    ApiSettings,
    TriageTenantRefusedError,
)
from intake_platform.red_tenant import TenantKind

CREDENTIALS = {
    "INTAKE_API_DB_URL": "postgresql+psycopg://app_rw@db.internal:5432/intake",
    "INTAKE_API_AUDIT_DB_URL": "postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
    "INTAKE_API_BOOTSTRAP_DB_URL": "postgresql+psycopg://intake@db.internal:5432/intake",
    "MINIO_ROOT_USER": "int465-object-store-user",
    "MINIO_ROOT_PASSWORD": "int465-object-store-secret",
}


HOST = "i-0e489e48739f5de98"


def _env(
    monkeypatch: pytest.MonkeyPatch,
    environment: str | None,
    kind: str | None,
    deployment: str | None = HOST,
) -> None:
    for name in [
        *CREDENTIALS,
        "INTAKE_ENV",
        ENV_TRIAGE_TENANT_KIND,
        ENV_TRIAGE_SIGNATURE,
        ENV_TRIAGE_DEPLOYMENT,
    ]:
        monkeypatch.delenv(name, raising=False)
    if deployment is not None:
        monkeypatch.setenv(ENV_TRIAGE_DEPLOYMENT, deployment)
    for name, value in CREDENTIALS.items():
        monkeypatch.setenv(name, value)
    if environment is not None:
        monkeypatch.setenv("INTAKE_ENV", environment)
    if kind is not None:
        monkeypatch.setenv(ENV_TRIAGE_TENANT_KIND, kind)


@pytest.mark.parametrize("environment", ["dev", "staging", " Staging "])
def test_dev_and_the_synthetic_staging_host_may_declare_a_synthetic_tenant(
    monkeypatch: pytest.MonkeyPatch, environment: str | None
) -> None:
    _env(monkeypatch, environment, "synthetic")
    assert ApiSettings.from_env().triage_tenant_kind is TenantKind.SYNTHETIC


@pytest.mark.parametrize("environment", [None, "", "prod", "production", "pilot", "staging-tr"])
def test_any_other_environment_declaring_a_synthetic_tenant_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch, environment: str | None
) -> None:
    """Unset INTAKE_ENV reads as dev elsewhere; here it is refused, so a deployment
    that forgot to name itself never trusts the test key."""
    _env(monkeypatch, environment, "synthetic")
    with pytest.raises(TriageTenantRefusedError) as caught:
        ApiSettings.from_env()
    assert ENV_TRIAGE_TENANT_KIND in str(caught.value)


@pytest.mark.parametrize("kind", [None, "", "real", "Synthetic", "synthetic ", "test"])
def test_anything_but_the_exact_value_is_a_real_tenant(
    monkeypatch: pytest.MonkeyPatch, kind: str | None
) -> None:
    """Near miss for the two cases above: a real tenant boots in every environment."""
    _env(monkeypatch, "prod", kind)
    assert ApiSettings.from_env().triage_tenant_kind is TenantKind.REAL


@pytest.mark.parametrize("deployment", [None, "", "   "])
def test_a_synthetic_tenant_that_names_no_host_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch, deployment: str | None
) -> None:
    """The test signature is bound to one host. A synthetic tenant that does not
    say which host it is cannot be checked against it, so it refuses at boot.
    Near miss: the same environment naming the host boots."""
    _env(monkeypatch, "staging", "synthetic", deployment=deployment)
    with pytest.raises(TriageTenantRefusedError) as caught:
        ApiSettings.from_env()
    assert ENV_TRIAGE_DEPLOYMENT in str(caught.value)
    _env(monkeypatch, "staging", "synthetic")
    assert ApiSettings.from_env().triage_deployment == HOST


def test_the_signature_path_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, "staging", "synthetic")
    assert ApiSettings.from_env().triage_signature_path is None
    monkeypatch.setenv(
        ENV_TRIAGE_SIGNATURE, "packages/protocols/signing/red_rule_set.synthetic.json"
    )
    assert ApiSettings.from_env().triage_signature_path == Path(
        "packages/protocols/signing/red_rule_set.synthetic.json"
    )
