"""INT-474 — the deployment-role gate on the other-subject data categories.

The INT-471 legal lane (LD-03, LD-04; still in legal review, owner decision
D25 scope: synthetic and test use only) reads KVKK m.6(3)(e) as the ground for
the relatives', household members' and partner's own data. That ground is the
health service provider's, so it holds where the hospital is the data
controller and is not decided for the consumer deployment, where the company
is. The INT-349 register row cannot carry that split: a filled row would open
both deployments. This gate refuses ``household``, ``relatives_health`` and
``partner_fertility`` in every compile that is not for the hospital-controller
deployment, whatever the register says, and refuses them when no role is
declared at all.

Everything here is synthetic (files/04 §7). The "complete" register rows are
test values standing for counsel's answers and carry no legal meaning.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from protocols.bindings import OperationalTemplate
from protocols.cli import load_registry, main
from protocols.compile import CompileError, LifeThreatSet, RefusalCode, compile_bundle
from protocols.data_register import (
    DATA_REGISTER_PATH,
    OTHER_SUBJECT_CATEGORIES,
    DataCategoryRegister,
    DataCategoryRow,
)
from protocols.deployment_role import (
    HOSPITAL_CONTROLLER_ONLY,
    DeploymentRole,
    DeploymentRoleRefused,
    admits,
    require_admitted,
)
from protocols.loader import PackRegistry
from protocols.pack import ProtocolPack
from protocols.types import DataCategory

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "protocols" / "compile"
FIXTURE_PACK = FIXTURES / "tree" / "base" / "intake.yaml"
SIGNED_LIFE_THREAT = FIXTURES / "life_threat_signed.yaml"
PACK_ID = "base.derlenebilir"
VOICE = "sentetik-ses"
SECTION, KEY = "tarama", "sessiz_soru"
LINK_ID = f"{SECTION}.{KEY}"

OTHER_SUBJECT = ("household", "relatives_health", "partner_fertility")
PATIENT_ONLY = tuple(
    c for c in DataCategory if c is not DataCategory.GENERAL_HEALTH and c.value not in OTHER_SUBJECT
)


def _row(category: DataCategory) -> DataCategoryRow:
    """A synthetic row with every counsel field filled."""
    return DataCategoryRow.model_validate(
        {
            "category": category,
            "purpose": "SENTETİK amaç — test verisi",
            "basis": "SENTETİK dayanak — test verisi",
            "retention": "SENTETİK saklama süresi — test verisi",
            "recipients": "SENTETİK alıcılar — test verisi",
            "consent_scope": "sentetik_kapsam",
            "other_subject_basis_and_notice": "SENTETİK üçüncü kişi aydınlatması — test verisi",
            "counsel_reviewed_at": date(2026, 10, 4),
        }
    )


def _filled_register() -> DataCategoryRegister:
    """Every row complete: the state the day counsel fills the register."""
    rows: dict[DataCategory, DataCategoryRow] = {
        c: _row(c) for c in DataCategory if c is not DataCategory.GENERAL_HEALTH
    }
    return DataCategoryRegister(version="sentetik-dolu", rows=rows)


def _tree(tmp_path: Path, category: str | None) -> Path:
    """The committed fixture tree with the screening slot tagged ``category``."""
    raw: dict[str, Any] = yaml.safe_load(FIXTURE_PACK.read_text(encoding="utf-8"))
    if category is not None:
        raw["sections"][SECTION]["slots"][KEY]["data_category"] = category
    base = tmp_path / "tree" / "base"
    base.mkdir(parents=True)
    (base / "intake.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return tmp_path / "tree"


def _compile(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    role: DeploymentRole | None,
    *,
    register: DataCategoryRegister | None = None,
    pack_id: str = PACK_ID,
) -> Any:
    return compile_bundle(
        pack_id=pack_id,
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        data_register=_filled_register() if register is None else register,
        deployment_role=role,
    )


def _role_refusals(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    role: DeploymentRole | None,
    *,
    register: DataCategoryRegister | None = None,
    pack_id: str = PACK_ID,
) -> tuple[Any, ...]:
    with pytest.raises(CompileError) as excinfo:
        _compile(registry, life_threat, template, role, register=register, pack_id=pack_id)
    return excinfo.value.refusals


def _by_code(refusals: tuple[Any, ...], code: RefusalCode) -> list[Any]:
    return [r for r in refusals if r.code is code]


# --------------------------------------------------------------------------
# The vocabulary: two roles, three gated categories, no default.
# --------------------------------------------------------------------------


def test_the_gated_categories_are_exactly_the_three_other_subject_ids() -> None:
    """The register's own ids, not a second spelling of them."""
    assert frozenset(c.value for c in HOSPITAL_CONTROLLER_ONLY) == set(OTHER_SUBJECT)
    assert HOSPITAL_CONTROLLER_ONLY == OTHER_SUBJECT_CATEGORIES


def test_the_deployment_roles_are_the_two_files_06_roles() -> None:
    """files/06 §0.1(1): the consumer app (the company is controller) and the
    hospital deployment (the hospital is controller, INTAKE its processor)."""
    assert {r.value for r in DeploymentRole} == {"hospital_controller", "consumer_controller"}


@pytest.mark.parametrize("category", OTHER_SUBJECT)
def test_only_the_hospital_controller_role_admits_a_gated_category(category: str) -> None:
    gated = DataCategory(category)
    assert admits(gated, DeploymentRole.HOSPITAL_CONTROLLER)
    assert not admits(gated, DeploymentRole.CONSUMER_CONTROLLER)
    assert not admits(gated, None)


def test_a_role_spelled_as_a_bare_string_does_not_admit() -> None:
    """Only the parsed enum member opens the gate. A raw value that skipped
    parsing (from a config read nobody validated) is refused, fail closed."""
    forged = cast(DeploymentRole, "hospital_controller")
    assert not admits(DataCategory.RELATIVES_HEALTH, forged)


@pytest.mark.parametrize("category", [c.value for c in PATIENT_ONLY] + ["general_health"])
def test_control_the_gate_leaves_every_other_category_to_the_register(category: str) -> None:
    for role in (*DeploymentRole, None):
        assert admits(DataCategory(category), role)


def test_require_admitted_raises_with_ids_only() -> None:
    with pytest.raises(DeploymentRoleRefused) as excinfo:
        require_admitted(DataCategory.PARTNER_FERTILITY, DeploymentRole.CONSUMER_CONTROLLER)
    refused = excinfo.value
    assert refused.category is DataCategory.PARTNER_FERTILITY
    assert refused.role is DeploymentRole.CONSUMER_CONTROLLER
    message = str(refused)
    assert "INT-474" in message
    assert "partner_fertility" in message
    assert "consumer_controller" in message


def test_require_admitted_names_a_missing_role_as_missing() -> None:
    with pytest.raises(DeploymentRoleRefused, match="no deployment role"):
        require_admitted(DataCategory.HOUSEHOLD, None)


def test_require_admitted_returns_quietly_for_the_hospital_controller() -> None:
    require_admitted(DataCategory.HOUSEHOLD, DeploymentRole.HOSPITAL_CONTROLLER)
    require_admitted(DataCategory.LITERACY, None)


# --------------------------------------------------------------------------
# The compiler: a filled register row does not open a gated category.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("category", OTHER_SUBJECT)
def test_a_consumer_deployment_is_refused_even_with_a_filled_register_row(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate, category: str
) -> None:
    registry = load_registry(_tree(tmp_path, category))
    refusals = _role_refusals(registry, life_threat, template, DeploymentRole.CONSUMER_CONTROLLER)
    gate = _by_code(refusals, RefusalCode.DATA_CATEGORY_DEPLOYMENT_ROLE)
    assert [r.subject for r in gate] == [LINK_ID]
    assert "INT-474" in gate[0].message
    assert category in gate[0].message
    assert "consumer_controller" in gate[0].message
    assert "m.6(3)(e)" in gate[0].message
    # the row is complete, so this is the role gate alone and not the register
    assert not _by_code(refusals, RefusalCode.DATA_CATEGORY_REGISTER_INCOMPLETE)


@pytest.mark.parametrize("category", OTHER_SUBJECT)
def test_a_compile_with_no_deployment_role_is_refused_even_with_a_filled_row(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate, category: str
) -> None:
    registry = load_registry(_tree(tmp_path, category))
    refusals = _role_refusals(registry, life_threat, template, None)
    gate = _by_code(refusals, RefusalCode.DATA_CATEGORY_DEPLOYMENT_ROLE)
    assert [r.subject for r in gate] == [LINK_ID]
    assert "no deployment role" in gate[0].message


@pytest.mark.parametrize("category", OTHER_SUBJECT)
def test_near_miss_the_hospital_controller_deployment_with_a_filled_row_compiles(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate, category: str
) -> None:
    registry = load_registry(_tree(tmp_path, category))
    bundle = _compile(registry, life_threat, template, DeploymentRole.HOSPITAL_CONTROLLER)
    assert bundle.resolved_protocol_hash
    manifest = json.loads(bundle.artifacts["manifest.json"])
    assert manifest["deployment_role"] == "hospital_controller"


@pytest.mark.parametrize("category", OTHER_SUBJECT)
def test_the_hospital_role_does_not_open_an_incomplete_register_row(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate, category: str
) -> None:
    """The two gates are independent both ways: the role is necessary, never
    sufficient. Counsel's row still has to be complete."""
    registry = load_registry(_tree(tmp_path, category))
    empty = DataCategoryRegister(version="sentetik-bos", rows={})
    refusals = _role_refusals(
        registry, life_threat, template, DeploymentRole.HOSPITAL_CONTROLLER, register=empty
    )
    assert [
        r.subject for r in _by_code(refusals, RefusalCode.DATA_CATEGORY_REGISTER_INCOMPLETE)
    ] == [LINK_ID]
    assert not _by_code(refusals, RefusalCode.DATA_CATEGORY_DEPLOYMENT_ROLE)


def test_a_consumer_compile_with_an_empty_row_reports_both_reasons(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """One compile names every reason (files/12 §3.4), so the author learns
    that filling the row will not be enough in this deployment."""
    registry = load_registry(_tree(tmp_path, "relatives_health"))
    empty = DataCategoryRegister(version="sentetik-bos", rows={})
    refusals = _role_refusals(
        registry, life_threat, template, DeploymentRole.CONSUMER_CONTROLLER, register=empty
    )
    codes = {r.code for r in refusals}
    assert RefusalCode.DATA_CATEGORY_DEPLOYMENT_ROLE in codes
    assert RefusalCode.DATA_CATEGORY_REGISTER_INCOMPLETE in codes


@pytest.mark.parametrize("category", [c.value for c in PATIENT_ONLY])
def test_control_a_patient_only_category_compiles_in_the_consumer_deployment(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate, category: str
) -> None:
    registry = load_registry(_tree(tmp_path, category))
    bundle = _compile(registry, life_threat, template, DeploymentRole.CONSUMER_CONTROLLER)
    assert bundle.resolved_protocol_hash


def test_control_an_untagged_pack_compiles_with_no_role_and_records_none(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    bundle = _compile(load_registry(_tree(tmp_path, None)), life_threat, template, None)
    assert json.loads(bundle.artifacts["manifest.json"])["deployment_role"] is None


def test_a_child_pack_that_adds_a_gated_category_is_refused_for_the_consumer(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The gate reads the resolved slot, so a category a later layer adds is
    refused exactly like one the base declared."""
    registry = load_registry(_tree(tmp_path, None))
    raw: dict[str, Any] = yaml.safe_load(FIXTURE_PACK.read_text(encoding="utf-8"))
    slot = {**raw["sections"][SECTION]["slots"][KEY], "data_category": "household"}
    registry.add(
        ProtocolPack.model_validate(
            {
                "kind": "pack",
                "id": "specialty.sentetik_cocuk",
                "layer": "specialty",
                "version": "1.0.0",
                "schema_version": 2,
                "maturity": "L1",
                "status": "clinically-reviewed-synthetic",
                "language": "tr",
                "extends": PACK_ID,
                "sections": {SECTION: {"delivery": "text_only", "slots": {KEY: slot}}},
            }
        )
    )
    refusals = _role_refusals(
        registry,
        life_threat,
        template,
        DeploymentRole.CONSUMER_CONTROLLER,
        pack_id="specialty.sentetik_cocuk",
    )
    assert [r.subject for r in _by_code(refusals, RefusalCode.DATA_CATEGORY_DEPLOYMENT_ROLE)] == [
        LINK_ID
    ]


# --------------------------------------------------------------------------
# The CLI: the role is operator configuration, parsed to the enum.
# --------------------------------------------------------------------------


def _filled_register_file(tmp_path: Path) -> Path:
    raw: dict[str, Any] = yaml.safe_load((REPO_ROOT / DATA_REGISTER_PATH).read_text("utf-8"))
    for row in raw["categories"]:
        row.update(
            {
                "basis": "SENTETİK dayanak — test verisi",
                "retention": "SENTETİK saklama süresi — test verisi",
                "recipients": "SENTETİK alıcılar — test verisi",
                "consent_scope": "sentetik_kapsam",
                "other_subject_basis_and_notice": "SENTETİK aydınlatma — test verisi",
                "counsel_reviewed_at": "2026-10-04",
            }
        )
    path = tmp_path / "data-categories.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _cli(tmp_path: Path, *role: str) -> int:
    return main(
        [
            "compile",
            "--pack",
            PACK_ID,
            "--packs",
            str(_tree(tmp_path, "relatives_health")),
            "--life-threat",
            str(SIGNED_LIFE_THREAT),
            "--data-register",
            str(_filled_register_file(tmp_path)),
            "--voice",
            VOICE,
            "--out",
            str(tmp_path / "dist"),
            *role,
        ]
    )


@pytest.mark.parametrize(
    "role", [(), ("--deployment-role", "consumer_controller")], ids=["absent", "consumer"]
)
def test_cli_refuses_a_gated_category_outside_the_hospital_deployment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], role: tuple[str, ...]
) -> None:
    assert _cli(tmp_path, *role) == 1
    assert not (tmp_path / "dist").exists()
    assert RefusalCode.DATA_CATEGORY_DEPLOYMENT_ROLE.value in capsys.readouterr().out


def test_cli_near_miss_the_hospital_deployment_writes_a_bundle_that_says_so(
    tmp_path: Path,
) -> None:
    assert _cli(tmp_path, "--deployment-role", "hospital_controller") == 0
    manifest = json.loads((tmp_path / "dist" / PACK_ID / "manifest.json").read_text("utf-8"))
    assert manifest["deployment_role"] == "hospital_controller"


def test_cli_rejects_a_role_outside_the_closed_set(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _cli(tmp_path, "--deployment-role", "hospital")
