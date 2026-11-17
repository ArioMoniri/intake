"""INT-536 F8 — the synthetic legal loader reads ADR-035's bound data class.

ADR-035 binds the deployment's data class into the model-lane control record
on the first control write. From then on a declaration that disagrees reads as
``real_phi`` (``model_lanes.guard.effective_data_class``). The synthetic legal
loader used to read only the declaration (``INTAKE_DEPLOYMENT_DATA_CLASS``).
So a deployment bound ``real_phi`` that later declared ``synthetic`` would have
refused its hosted lanes but still served the synthetic texts (INT-529 F8).

The loader now reads the bound class fresh on every lookup, as it reads the
bytes:
- bound ``real_phi`` with a ``synthetic`` declaration is refused;
- an unreadable record is refused, because the class cannot be known;
- unbound or bound ``synthetic`` serves;
- with no control store configured, nothing can be bound, so the declaration
  governs.

The consent catalog turns a refusal into an invalid text, which raises, so no
grant can bind a synthetic text there. The API wires the deployment's store
(``INTAKE_MODEL_LANES_REDIS_URL``) into the catalog.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from intake_api.settings import ApiSettings
from intake_api.state import consent_catalog_for
from intake_platform.consent import ConsentTextInvalidError
from intake_platform.legal.synthetic import (
    SYNTHETIC_CONSENTS_ROOT,
    SYNTHETIC_LEGAL_ROOT,
    DeploymentDataClass,
    SyntheticConsentTextCatalog,
    SyntheticLegalIndex,
    SyntheticLegalTreeRefusedError,
)
from intake_platform.model_lanes.model import ModelLanesControl
from intake_platform.model_lanes.store import (
    InMemoryModelLanesStore,
    ModelLanesReader,
    ModelLanesUnavailable,
)

REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / SYNTHETIC_LEGAL_ROOT
SYN = DeploymentDataClass.SYNTHETIC
REAL = DeploymentDataClass.REAL_PHI
DOCUMENT = "acik_riza.core"


def _bound(data_class: DeploymentDataClass | None) -> InMemoryModelLanesStore:
    return InMemoryModelLanesStore(ModelLanesControl(data_class=data_class))


def _settings(**overrides: object) -> ApiSettings:
    """A settings object as the harness builds one, on the synthetic tree."""
    base: dict[str, object] = {
        "token_patient": None,
        "token_admin": None,
        "app_db_url": "sqlite+aiosqlite:///int536.db",
        "audit_db_url": "sqlite+pysqlite:///int536-audit.db",
        "bootstrap_db_url": "sqlite+aiosqlite:///int536.db",
        "kek_mode": "file-dev",
        "legal_root": REPO / SYNTHETIC_CONSENTS_ROOT,
        "deployment_data_class": SYN,
    }
    base.update(overrides)
    return ApiSettings(**base)  # type: ignore[arg-type]


class _Unreadable:
    def read(self) -> ModelLanesControl:
        raise ModelLanesUnavailable("model_lanes_unreachable")


@pytest.mark.parametrize(
    "bound",
    [None, _bound(None), _bound(SYN)],
    ids=["no-store", "unbound", "bound-synthetic"],
)
def test_the_synthetic_texts_serve_while_the_bound_class_agrees(
    bound: ModelLanesReader | None,
) -> None:
    index = SyntheticLegalIndex(ROOT, data_class=SYN, bound=bound)
    assert index.entry(DOCUMENT).id == DOCUMENT


def test_a_deployment_bound_real_phi_refuses_the_synthetic_texts() -> None:
    index = SyntheticLegalIndex(ROOT, data_class=SYN, bound=_bound(REAL))
    with pytest.raises(SyntheticLegalTreeRefusedError, match="bound"):
        index.entry(DOCUMENT)
    assert index.available() == ()


def test_an_unreadable_bound_class_refuses() -> None:
    index = SyntheticLegalIndex(ROOT, data_class=SYN, bound=_Unreadable())
    with pytest.raises(SyntheticLegalTreeRefusedError, match="model_lanes_unreachable"):
        index.entry(DOCUMENT)


def test_the_bound_class_is_read_on_every_lookup() -> None:
    """Fresh, like the bytes: a class bound after the loader was built still
    refuses the next lookup."""
    store = _bound(None)
    index = SyntheticLegalIndex(ROOT, data_class=SYN, bound=store)
    assert index.entry(DOCUMENT).id == DOCUMENT
    store.write(ModelLanesControl(data_class=REAL, revision=1), expected_revision=0)
    with pytest.raises(SyntheticLegalTreeRefusedError):
        index.entry(DOCUMENT)


def test_the_consent_catalog_refuses_a_grant_on_a_mismatch() -> None:
    catalog = SyntheticConsentTextCatalog(
        REPO / SYNTHETIC_CONSENTS_ROOT, data_class=SYN, bound=_bound(REAL)
    )
    with pytest.raises(ConsentTextInvalidError):
        catalog.entry("core")
    with pytest.raises(ConsentTextInvalidError):
        catalog.try_entry("core")
    # near miss: the same catalog, bound synthetic, serves
    serving = SyntheticConsentTextCatalog(
        REPO / SYNTHETIC_CONSENTS_ROOT, data_class=SYN, bound=_bound(SYN)
    )
    assert serving.entry("core").purpose == "core"


def test_settings_read_the_control_store_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTAKE_ENV", "dev")
    monkeypatch.setenv("INTAKE_DEPLOYMENT_DATA_CLASS", "synthetic")
    monkeypatch.delenv("INTAKE_LEGAL_ROOT", raising=False)
    monkeypatch.setenv("INTAKE_MODEL_LANES_REDIS_URL", "redis://lanes.internal:6379/0")
    assert ApiSettings.from_env().model_lanes_redis_url == "redis://lanes.internal:6379/0"
    monkeypatch.delenv("INTAKE_MODEL_LANES_REDIS_URL")
    assert ApiSettings.from_env().model_lanes_redis_url is None


def test_the_api_catalog_reads_the_deployment_s_bound_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wiring: the catalog the API builds consults the store its settings
    name. The store is swapped for an in-memory one bound ``real_phi``."""
    seen: list[str] = []

    def _store(env: dict[str, str]) -> InMemoryModelLanesStore:
        seen.extend(env.values())
        return _bound(REAL)

    monkeypatch.setattr("intake_api.state.model_lanes_store_from_env", _store)
    settings = _settings(model_lanes_redis_url="redis://lanes.internal:6379/0")
    catalog = consent_catalog_for(settings)
    assert seen == ["redis://lanes.internal:6379/0"]
    with pytest.raises(ConsentTextInvalidError):
        catalog.entry("core")


def test_with_no_control_store_the_declaration_governs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _never(env: dict[str, str]) -> None:
        raise AssertionError("no store address, so no store is built")

    monkeypatch.setattr("intake_api.state.model_lanes_store_from_env", _never)
    settings = _settings()
    assert consent_catalog_for(settings).entry("core").purpose == "core"
