"""INT-529 — the synthetic legal texts load only on a synthetic deployment, and a
grant there binds the synthetic text's hash.

The owner's yes (16 Oct 2026) is for synthetic tenants only. Three boundaries
make that true at boot rather than by convention:

- ``INTAKE_DEPLOYMENT_DATA_CLASS=synthetic`` is the only declaration that loads
  the synthetic index, and the synthetic image bakes it (infra/staging/
  Dockerfile.api); the compose file never sets it, so an operator cannot;
- that declaration is honoured only in an explicit ``dev`` or on the synthetic
  ``staging`` host — anywhere else the API refuses to boot;
- a real-tenant boot that points its legal root at the synthetic tree refuses
  to boot, whether it came from the environment or from a settings object.

Then the grant itself: on a synthetic deployment ``POST /v1/consents/grant``
records the SHA-256 of the committed synthetic file, which is the same digest
the synthetic index signs.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness, run  # noqa: E402
from intake_api.dev_fixture import DEV_PATIENT_ID, DEV_TENANT_ID  # noqa: E402
from intake_api.settings import (  # noqa: E402
    ApiSettings,
    SyntheticDataClassRefusedError,
)
from intake_platform.consent import text_filename  # noqa: E402
from intake_platform.consent.texts import synthetic_marker_is_visible  # noqa: E402
from intake_platform.db.models import Consent  # noqa: E402
from intake_platform.legal.synthetic import (  # noqa: E402
    DATA_CLASS_ENV,
    SYNTHETIC_CONSENTS_ROOT,
    SYNTHETIC_LEGAL_ROOT,
    DeploymentDataClass,
    SyntheticLegalTreeRefusedError,
)
from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SYNTHETIC_CONSENTS = REPO / SYNTHETIC_CONSENTS_ROOT
SYNTHETIC_INDEX = REPO / SYNTHETIC_LEGAL_ROOT / "documents.yaml"
DOCKERFILE = REPO / "infra" / "staging" / "Dockerfile.api"
COMPOSE = REPO / "infra" / "staging" / "compose.yaml"

CREDENTIALS = {
    "INTAKE_API_DB_URL": "postgresql+psycopg://app_rw@db.internal:5432/intake",
    "INTAKE_API_AUDIT_DB_URL": "postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
    "INTAKE_API_BOOTSTRAP_DB_URL": "postgresql+psycopg://intake@db.internal:5432/intake",
    "MINIO_ROOT_USER": "int529-object-store-user",
    "MINIO_ROOT_PASSWORD": "int529-object-store-secret",
}

#: The purposes INT-529 built a synthetic text for (tests/legal pins the split).
BUILT_PURPOSES = ("core", "voice", "wellbeing", "lane:affect", "documents", "satisfaction", "share")


def _env(
    monkeypatch: pytest.MonkeyPatch,
    *,
    environment: str | None,
    data_class: str | None,
    legal_root: str | None = None,
) -> None:
    for name in [*CREDENTIALS, "INTAKE_ENV", DATA_CLASS_ENV, "INTAKE_LEGAL_ROOT"]:
        monkeypatch.delenv(name, raising=False)
    # a staging boot is strict (INT-325): give it the credentials it requires
    for name, value in CREDENTIALS.items():
        monkeypatch.setenv(name, value)
    if environment is not None:
        monkeypatch.setenv("INTAKE_ENV", environment)
    if data_class is not None:
        monkeypatch.setenv(DATA_CLASS_ENV, data_class)
    if legal_root is not None:
        monkeypatch.setenv("INTAKE_LEGAL_ROOT", legal_root)


def _settings(**overrides: object) -> ApiSettings:
    base: dict[str, object] = {
        "token_patient": None,
        "token_admin": None,
        "app_db_url": "sqlite+aiosqlite:///unused.db",
        "audit_db_url": "sqlite+pysqlite:///unused-audit.db",
        "bootstrap_db_url": "sqlite+aiosqlite:///unused.db",
        "kek_mode": "file-dev",
    }
    base.update(overrides)
    return ApiSettings(**base)  # type: ignore[arg-type]


# --- boot: the environment --------------------------------------------------------------


@pytest.mark.parametrize("environment", ["dev", "staging", " Staging "])
def test_the_synthetic_host_boots_on_the_synthetic_tree_by_default(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    _env(monkeypatch, environment=environment, data_class="synthetic")
    settings = ApiSettings.from_env()
    assert settings.deployment_data_class is DeploymentDataClass.SYNTHETIC
    assert settings.legal_root == SYNTHETIC_CONSENTS_ROOT


@pytest.mark.parametrize("environment", [None, "", "prod", "production", "pilot", "staging-tr"])
def test_a_synthetic_declaration_anywhere_else_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch, environment: str | None
) -> None:
    """Unset INTAKE_ENV reads as dev elsewhere; here it is refused, so a
    deployment that forgot to name itself never loads the synthetic texts."""
    _env(monkeypatch, environment=environment, data_class="synthetic")
    with pytest.raises(SyntheticDataClassRefusedError) as caught:
        ApiSettings.from_env()
    assert DATA_CLASS_ENV in str(caught.value)


@pytest.mark.parametrize("value", [None, "", "real_phi", "Synthetic", "synthetic ", "test"])
def test_anything_but_the_exact_literal_boots_as_a_real_tenant(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """Near miss for the two cases above: a real tenant keeps the real legal
    root in every environment, and boots."""
    _env(monkeypatch, environment="prod", data_class=value)
    settings = ApiSettings.from_env()
    assert settings.deployment_data_class is DeploymentDataClass.REAL_PHI
    assert settings.legal_root == Path("docs/legal/consents")


@pytest.mark.parametrize(
    "legal_root",
    [
        "docs/legal/synthetic/consents",
        str(SYNTHETIC_CONSENTS),
        "docs/legal/synthetic/consents/../consents",
    ],
)
def test_a_real_tenant_boot_pointed_at_the_synthetic_index_refuses(
    monkeypatch: pytest.MonkeyPatch, legal_root: str
) -> None:
    _env(monkeypatch, environment="prod", data_class=None, legal_root=legal_root)
    with pytest.raises(SyntheticLegalTreeRefusedError):
        ApiSettings.from_env()


def test_a_synthetic_boot_pointed_at_the_real_tree_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other direction: a synthetic host binds synthetic texts only."""
    _env(
        monkeypatch, environment="staging", data_class="synthetic", legal_root="docs/legal/consents"
    )
    with pytest.raises(SyntheticLegalTreeRefusedError):
        ApiSettings.from_env()


def test_a_real_settings_object_on_the_synthetic_tree_refuses_too(tmp_path: Path) -> None:
    """The gate is on the settings object, not only on from_env: the test
    harness, a script or a future entry point cannot build around it."""
    with pytest.raises(SyntheticLegalTreeRefusedError):
        _settings(legal_root=SYNTHETIC_CONSENTS)
    with pytest.raises(SyntheticLegalTreeRefusedError):
        _settings(legal_strings_path=REPO / SYNTHETIC_LEGAL_ROOT / "strings.yaml")
    # near miss: an ordinary tmp tree boots
    assert _settings(legal_root=tmp_path / "legal" / "consents").legal_root.name == "consents"


# --- boot: the image ----------------------------------------------------------------------


def test_the_synthetic_image_bakes_the_data_class() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "INTAKE_DEPLOYMENT_DATA_CLASS=synthetic" in dockerfile


def test_the_compose_file_never_declares_the_data_class() -> None:
    """Baked, not configured: the class comes from the image alone."""
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    for name, service in compose["services"].items():
        environment = service.get("environment") or {}
        assert DATA_CLASS_ENV not in environment, name


# --- the grant on the synthetic host ------------------------------------------------------


@pytest.fixture()
def synthetic_harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        legal_root=SYNTHETIC_CONSENTS,
        deployment_data_class="synthetic",
    )


def _wipe_consents(harness: ApiHarness) -> None:
    async def _wipe() -> None:
        async with AsyncSession(harness.engine) as session, session.begin():
            await session.execute(
                delete(Consent).where(
                    Consent.tenant_id == DEV_TENANT_ID, Consent.patient_id == DEV_PATIENT_ID
                )
            )

    run(_wipe())


def _rows(harness: ApiHarness, scope: str) -> list[Consent]:
    async def _read() -> list[Consent]:
        async with AsyncSession(harness.engine) as session:
            result = await session.scalars(
                select(Consent).where(
                    Consent.tenant_id == DEV_TENANT_ID,
                    Consent.patient_id == DEV_PATIENT_ID,
                    Consent.scope == scope,
                )
            )
            return list(result.all())

    rows: list[Consent] = run(_read())
    return rows


def _index_sha(purpose: str) -> str:
    index = yaml.safe_load(SYNTHETIC_INDEX.read_text(encoding="utf-8"))
    document_id = "acik_riza." + purpose.replace(":", ".")
    (row,) = [r for r in index["documents"] if r["id"] == document_id]
    digest: str = row["sha256"]
    return digest


def test_the_synthetic_host_serves_exactly_the_built_marked_texts(
    synthetic_harness: ApiHarness,
) -> None:
    response = synthetic_harness.client.get("/v1/consents", headers=synthetic_harness.patient())
    assert response.status_code == 200, response.text
    texts = {row["purpose"]: row for row in response.json()["texts"]}
    assert set(texts) == set(BUILT_PURPOSES)
    for purpose, row in texts.items():
        assert synthetic_marker_is_visible(row["body"]), purpose
        assert row["text_hash"] == _index_sha(purpose)


@pytest.mark.parametrize("scope", ["core", "documents", "share:previsit_note"])
def test_a_grant_on_the_synthetic_host_binds_the_synthetic_texts_hash(
    synthetic_harness: ApiHarness, scope: str
) -> None:
    _wipe_consents(synthetic_harness)
    purpose = "share" if scope.startswith("share:") else scope
    raw = (SYNTHETIC_CONSENTS / text_filename(purpose)).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = synthetic_harness.client.get(
        "/v1/consents", headers=synthetic_harness.patient()
    ).json()
    (text,) = [row for row in snapshot["texts"] if row["purpose"] == purpose]
    response = synthetic_harness.client.post(
        "/v1/consents/grant",
        json={"scope": scope, "version": text["version"], "text_hash": text["text_hash"]},
        headers=synthetic_harness.patient(),
    )
    assert response.status_code == 201, response.text
    (row,) = _rows(synthetic_harness, scope)
    assert row.text_hash == digest == _index_sha(purpose)
    assert row.version == text["version"]
    assert row.channel == "app"


@pytest.mark.parametrize("scope", ["research", "lane:linguistic"])
def test_an_unbuilt_purpose_still_refuses_the_grant(
    synthetic_harness: ApiHarness, scope: str
) -> None:
    """Near miss: the synthetic index does not make every purpose grantable.
    A text left awaiting-human is absent, so the grant is 409 text_missing."""
    response = synthetic_harness.client.post(
        "/v1/consents/grant",
        json={"scope": scope, "version": "2026-10-16.syn1", "text_hash": "0" * 64},
        headers=synthetic_harness.patient(),
    )
    assert response.status_code == 409
    assert response.json() == {"error": "text_missing", "scope": scope}
    assert _rows(synthetic_harness, scope) == []


def test_a_real_tenant_harness_on_the_synthetic_tree_refuses_to_build(tmp_path: Path) -> None:
    """A real-tenant boot with the synthetic index is refused before the app
    exists — the harness builds the same settings object the API runs on."""
    with pytest.raises(SyntheticLegalTreeRefusedError):
        next(
            build_harness(
                tmp_path,
                token_patient=PATIENT_TOKEN,
                token_admin=ADMIN_TOKEN,
                legal_root=SYNTHETIC_CONSENTS,
            )
        )
