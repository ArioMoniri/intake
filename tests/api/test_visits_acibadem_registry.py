"""INT-318 — the registry half of ``POST /v1/visits/sync`` (audit F06, §6 item 8).

On int-demo the route built its source row in code: binding refs that named no
signed agreement and no recorded approval, a plaintext approval granted
whenever the base URL said ``http``, and ``core`` standing in for the purpose a
hospital-record read needs. That made the route live whenever two environment
variables were set, whatever ``infra/connectors/sources.yaml`` said.

Rebuilt, the row comes from the registry file and nowhere else:

* the shipped registry has zero rows, so nothing is wired — even with the
  int-demo environment set — and the route answers ``unavailable`` without a
  byte reaching the feed;
* no module under ``intake_api`` builds a row or names a binding ref (derived
  from the schema, never spelled here — a guard must not name what it forbids);
* the read clears the purpose the ROW names, so ``core`` alone unlocks nothing;
* a row serves only the tenant it is registered for;
* the runtime gate and the plaintext decision stay the connector's, and an
  unconfigured OpenBao, an invalid file or two rows for one adapter wire
  nothing.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from acibadem_sync_harness import (
    BEFORE_THE_VISITS,
    FATMA_PHONE,
    CountingFeed,
    DpopClient,
    SyncHarness,
    build_sync_harness,
    consumer_source,
)
from intake_api import visits_acibadem
from intake_api.app import wiring_from_env
from intake_connectors.acibadem import ADAPTER_ID
from intake_connectors.sources import ClinicalSource, load_sources
from intake_platform.consent.registry import CORE, PURPOSES, LegalBasis
from intake_platform.secrets import SecretsBootError, SecretsProvider

REPO = Path(__file__).resolve().parents[2]
SHIPPED_REGISTRY = REPO / "infra" / "connectors" / "sources.yaml"
API_SRC = REPO / "services" / "api" / "src" / "intake_api"
ROUTE_MODULE = API_SRC / "visits_acibadem.py"

#: A registered purpose that is not core, so a pass proves the row's purpose —
#: not the door's — is what the read clears. Picked from the closed registry by
#: rule rather than by name: any explicit-consent, unparameterised purpose works.
OTHER_PURPOSE = next(
    p.id
    for p in PURPOSES
    if p.id != CORE and not p.parameterised and p.legal_basis is LegalBasis.EXPLICIT_CONSENT
)


def _binding_fields() -> tuple[str, ...]:
    """The row fields that bind a source to a human decision, read off the
    schema's own validator so this test tracks the schema, not a copy of it."""
    validators = ClinicalSource.__pydantic_decorators__.field_validators
    fields = validators["_binding_refs"].info.fields
    assert len(fields) >= 2, "derivation found no binding fields; the guard would prove nothing"
    return tuple(fields)


def _credential_field() -> str:
    (name,) = ClinicalSource.__pydantic_decorators__.field_validators[
        "_credential_path"
    ].info.fields
    return name


def _demo_refs() -> set[str]:
    """The int-demo stand-ins, rebuilt from the adapter id and the binding
    field names — the shape the audit recorded — so no forbidden value is
    spelled in this file."""
    vendor = ADAPTER_ID.split("-")[0]
    refs = {f"dev-{vendor}-{name.split('_')[0]}" for name in _binding_fields()}
    refs.add(f"{vendor}-demo")
    assert len(refs) == len(_binding_fields()) + 1
    return refs


def _api_modules() -> list[Path]:
    modules = sorted(API_SRC.rglob("*.py"))
    assert ROUTE_MODULE in modules, "the route module moved; the guard would scan nothing"
    return modules


def _write_registry(path: Path, *rows: ClinicalSource | dict[str, object]) -> Path:
    body = [row.model_dump() if isinstance(row, ClinicalSource) else row for row in rows]
    path.write_text(yaml.safe_dump({"version": 1, "sources": body}), encoding="utf-8")
    return path


def _sqlite_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("INTAKE_API_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/app.db")
    monkeypatch.setenv("INTAKE_API_AUDIT_DB_URL", f"sqlite+pysqlite:///{tmp_path}/audit.db")
    monkeypatch.setenv("INTAKE_API_BOOTSTRAP_DB_URL", f"sqlite+aiosqlite:///{tmp_path}/app.db")
    monkeypatch.setenv("INTAKE_API_KEK_MODE", "file-dev")


def _no_openbao(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unconfigured() -> SecretsProvider:
        raise SecretsBootError("unit lane: OpenBao is not configured")

    monkeypatch.setattr(SecretsProvider, "from_env", staticmethod(_unconfigured))


def _openbao_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    # constructing the provider opens no connection; nothing here reads a secret
    monkeypatch.setattr(
        SecretsProvider,
        "from_env",
        staticmethod(lambda: SecretsProvider("http://127.0.0.1:9", "unit-lane")),
    )


# --- zero rows: the shipped state ---------------------------------------------------------


def test_the_shipped_registry_holds_no_row() -> None:
    assert load_sources(SHIPPED_REGISTRY).rows == ()


def test_zero_rows_wire_no_client_even_with_the_demo_environment_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _sqlite_env(monkeypatch, tmp_path)
    # exactly what made the int-demo route live: a base URL, a key, the gate
    monkeypatch.setenv("ACIBADEM_BASE_URL", "http://10.150.0.42:8091")
    monkeypatch.setenv("ACIBADEM_API_KEY", "unit-lane-key-material")
    monkeypatch.setenv("INTAKE_ALLOW_LAN_SOURCE", "explicit-yes")
    monkeypatch.delenv("INTAKE_CLINICAL_SOURCES", raising=False)
    monkeypatch.chdir(REPO)  # the default path is the committed registry
    _no_openbao(monkeypatch)  # zero rows must not even ask for a credential

    assert wiring_from_env().acibadem is None


def test_zero_rows_answer_unavailable_and_never_touch_the_feed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_LAN_SOURCE", "explicit-yes")
    for harness in build_sync_harness(tmp_path, registered=False):
        dpop = DpopClient()
        bundle = harness.sign_up(FATMA_PHONE, dpop)
        harness.grant_core(bundle["patient_id"])

        response = harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
        assert response.status_code == 200, response.text
        assert response.json() == {"outcome": "unavailable", "patient_name": None, "visits": []}
        assert harness.feed.calls == []


# --- the row is read, never built ---------------------------------------------------------


def test_no_api_module_builds_a_row_or_names_a_binding_ref() -> None:
    demo_refs = _demo_refs()
    banned_keys = {*_binding_fields(), _credential_field()}
    offences: list[str] = []
    for module in _api_modules():
        source = module.read_text(encoding="utf-8")
        name = module.relative_to(REPO)
        offences += [f"{name}: names {ref!r}" for ref in sorted(demo_refs) if ref in source]
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call):
                callee = ast.unparse(node.func)
                if callee.split(".")[0] == ClinicalSource.__name__:
                    offences.append(f"{name}:{node.lineno}: builds a row ({callee})")
                offences += [
                    f"{name}:{node.lineno}: passes {kw.arg}="
                    for kw in node.keywords
                    if kw.arg in banned_keys
                ]
            if isinstance(node, ast.Dict):
                offences += [
                    f"{name}:{node.lineno}: dict key {key.value!r}"
                    for key in node.keys
                    if isinstance(key, ast.Constant) and key.value in banned_keys
                ]
    assert offences == []


def test_the_route_clears_the_rows_purpose_and_defines_no_scope_of_its_own() -> None:
    tree = ast.parse(ROUTE_MODULE.read_text(encoding="utf-8"))
    # no module-level scope constant: the read's purpose is the row's
    local_scopes = [
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name) and "SCOPE" in target.id.upper()
    ]
    assert local_scopes == []
    scope_args = [
        kw.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("ensure_consent")
        for kw in node.keywords
        if kw.arg == "scope"
    ]
    assert scope_args, "the route never calls ensure_consent for the read"
    assert all(
        isinstance(arg, ast.Attribute) and arg.attr == "consent_scope" for arg in scope_args
    ), [ast.unparse(arg) for arg in scope_args]


# --- the row's purpose, the row's tenant, the operator's gate -----------------------------


@pytest.fixture()
def other_purpose_harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SyncHarness]:
    monkeypatch.setenv("INTAKE_ALLOW_LAN_SOURCE", "explicit-yes")
    monkeypatch.setattr(visits_acibadem, "_today", lambda: BEFORE_THE_VISITS)
    yield from build_sync_harness(tmp_path, source=consumer_source(consent_scope=OTHER_PURPOSE))


def test_core_alone_does_not_unlock_a_row_registered_for_another_purpose(
    other_purpose_harness: SyncHarness,
) -> None:
    harness = other_purpose_harness
    dpop = DpopClient()
    bundle = harness.sign_up(FATMA_PHONE, dpop)
    harness.grant_core(bundle["patient_id"])

    refused = harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
    assert refused.status_code == 403
    assert refused.json() == {"error": "consent_required", "scope": OTHER_PURPOSE}
    assert harness.feed.calls == []

    harness.grant(bundle["patient_id"], OTHER_PURPOSE)
    allowed = harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["outcome"] == "matched"
    synced = [e for e in harness.audit_store.entries() if e.action == "api.visit.acibadem.sync"]
    assert [e.consent_scope_ref for e in synced] == [f"scope:{OTHER_PURPOSE}"]


def test_a_row_registered_for_another_tenant_serves_no_patient_here(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTAKE_ALLOW_LAN_SOURCE", "explicit-yes")
    elsewhere = consumer_source(tenant_id="tenant-registered-elsewhere")
    for harness in build_sync_harness(tmp_path, source=elsewhere):
        dpop = DpopClient()
        bundle = harness.sign_up(FATMA_PHONE, dpop)
        harness.grant_core(bundle["patient_id"])

        response = harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == "unavailable"
        assert harness.feed.calls == []


def test_the_runtime_gate_off_answers_unavailable_and_sends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INTAKE_ALLOW_LAN_SOURCE", raising=False)
    for harness in build_sync_harness(tmp_path, feed=CountingFeed()):
        dpop = DpopClient()
        bundle = harness.sign_up(FATMA_PHONE, dpop)
        harness.grant_core(bundle["patient_id"])

        response = harness.sync(FATMA_PHONE, bundle["access_token"], dpop)
        assert response.status_code == 200, response.text
        assert response.json() == {"outcome": "unavailable", "patient_name": None, "visits": []}
        # the LanSourcePolicy refused before the inner transport saw a request
        assert harness.feed.calls == []


# --- wiring: the registry file is the only way in -----------------------------------------


def test_one_registered_row_is_the_client_the_app_wires(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    row = consumer_source()
    _sqlite_env(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "INTAKE_CLINICAL_SOURCES", str(_write_registry(tmp_path / "sources.yaml", row))
    )
    _openbao_stub(monkeypatch)

    client = wiring_from_env().acibadem
    assert client is not None
    assert client.source == row


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param(
            [{**consumer_source().model_dump(), "plaintext_approval": None}],
            id="plaintext-without-a-recorded-decision",
        ),
        pytest.param(
            [consumer_source(), consumer_source(source_id="acibadem-appointments-second")],
            id="two-rows-for-one-adapter",
        ),
        pytest.param("not a registry", id="malformed-file"),
    ],
)
def test_a_registry_that_does_not_name_exactly_one_valid_row_wires_nothing(
    rows: list[ClinicalSource | dict[str, object]] | str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "sources.yaml"
    if isinstance(rows, str):
        path.write_text(rows, encoding="utf-8")
    else:
        _write_registry(path, *rows)
    _openbao_stub(monkeypatch)

    assert visits_acibadem.acibadem_client_from_registry(path) is None


def test_an_unconfigured_openbao_wires_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = _write_registry(tmp_path / "sources.yaml", consumer_source())
    _no_openbao(monkeypatch)

    assert visits_acibadem.acibadem_client_from_registry(path) is None
