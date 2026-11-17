"""INT-320 — the tenant embed registry (ADR-029).

A partner embed tenant is a REGISTERED row, addressed only by ``tenant_id`` —
the connector-destination pattern (ADR-026) in a second list. What this pins:
- branding is constrained DATA (hex colours, id-shaped asset/consent refs, a
  bounded display name), never partner-supplied markup — no injection surface;
- ``device_functions`` cannot be on (ADR-020: no CE certificate here);
- a ``prod`` row is refused without its recorded human facts (DPA + brand
  permission) — the mechanism ships fail-closed with ZERO prod rows;
- an unknown tenant fails closed;
- the committed ``infra/tenants/embed_registry.yaml`` holds exactly one dev-tier
  synthetic tenant and no real partner.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from intake_platform.embed.registry import (
    EmbedConfigError,
    EmbedRegistryError,
    EmbedThemeError,
    TenantEmbedRegistry,
    UnknownTenantError,
    load_shipped_registry,
    shipped_registry_path,
)

REPO = Path(__file__).resolve().parents[2]

_DEV = {
    "tenant_id": "0b6f9d2e-1111-5aaa-8bbb-000000000001",
    "tier": "dev",
    "signing_key_ref": "embed/dev-partner-alpha/signing-key",
    "legal_root": "docs/legal/embed/dev-partner-alpha",
    "device_functions": False,
    "theme": {
        "display_name": "Önvizit Dev Partner",
        "locale": "tr",
        "primary_color": "#0B5FFF",
        "accent_color": "#00303C",
        "logo_asset_id": "embed.dev-partner-alpha.logo",
        "consent_doc_set_id": "embed.dev-partner-alpha",
    },
}


def _write(path: Path, rows: list[dict[str, object]], *, version: str = "v0-dev") -> Path:
    path.write_text(
        yaml.safe_dump({"registry_version": version, "tenants": rows}), encoding="utf-8"
    )
    return path


def test_dev_row_loads_and_resolves(tmp_path: Path) -> None:
    reg = TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [dict(_DEV)]))
    cfg = reg.resolve(_DEV["tenant_id"])  # type: ignore[arg-type]
    assert cfg.tier == "dev"
    assert cfg.device_functions is False
    assert cfg.theme.display_name == "Önvizit Dev Partner"
    assert cfg.theme.primary_color == "#0B5FFF"


def test_unknown_tenant_fails_closed(tmp_path: Path) -> None:
    reg = TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [dict(_DEV)]))
    with pytest.raises(UnknownTenantError):
        reg.resolve("99999999-9999-5999-8999-999999999999")


def test_empty_registry_is_valid_and_resolves_nothing(tmp_path: Path) -> None:
    reg = TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", []))
    assert reg.tenant_ids() == ()
    with pytest.raises(UnknownTenantError):
        reg.resolve(_DEV["tenant_id"])  # type: ignore[arg-type]


def test_duplicate_tenant_is_refused(tmp_path: Path) -> None:
    with pytest.raises(EmbedConfigError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [dict(_DEV), dict(_DEV)]))


@pytest.mark.parametrize(
    "bad_color",
    ["red", "#fff", "#12345", "#1234567", "rgb(0,0,0)", "#GGGGGG", "javascript:alert(1)"],
)
def test_theme_colours_must_be_six_digit_hex(tmp_path: Path, bad_color: str) -> None:
    row = dict(_DEV)
    row["theme"] = {**_DEV["theme"], "primary_color": bad_color}  # type: ignore[dict-item]
    with pytest.raises(EmbedThemeError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


@pytest.mark.parametrize(
    "bad_name",
    ["<script>alert(1)</script>", "a" * 200, "", "  ", 123],
)
def test_display_name_is_bounded_and_markup_free(tmp_path: Path, bad_name: object) -> None:
    row = dict(_DEV)
    row["theme"] = {**_DEV["theme"], "display_name": bad_name}  # type: ignore[dict-item]
    with pytest.raises(EmbedThemeError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


@pytest.mark.parametrize(
    "bad_ref",
    ["https://evil.example/logo.svg", "../secrets", "a b", "<b>", "javascript:x"],
)
def test_asset_and_consent_refs_are_id_shaped(tmp_path: Path, bad_ref: str) -> None:
    row = dict(_DEV)
    row["theme"] = {**_DEV["theme"], "logo_asset_id": bad_ref}  # type: ignore[dict-item]
    with pytest.raises(EmbedThemeError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


def test_device_functions_cannot_be_enabled(tmp_path: Path) -> None:
    row = dict(_DEV)
    row["device_functions"] = True
    with pytest.raises(EmbedConfigError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


def test_prod_row_without_recorded_human_facts_is_refused(tmp_path: Path) -> None:
    row = dict(_DEV)
    row["tier"] = "prod"  # no dpa_ref, no brand_permission_ref → fail closed
    with pytest.raises(EmbedConfigError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


def test_prod_row_with_the_facts_loads(tmp_path: Path) -> None:
    row = dict(_DEV)
    row.update(
        tier="prod",
        dpa_ref="dpa:2026-000-example",
        brand_permission_ref="brand:2026-000-example",
    )
    reg = TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))
    assert reg.resolve(_DEV["tenant_id"]).tier == "prod"  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_locale", ["tr_TR", "TR", "turkish", "t", "tr-tr"])
def test_locale_must_be_bcp47(tmp_path: Path, bad_locale: str) -> None:
    row = dict(_DEV)
    row["theme"] = {**_DEV["theme"], "locale": bad_locale}  # type: ignore[dict-item]
    with pytest.raises(EmbedThemeError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


def test_theme_must_be_a_mapping(tmp_path: Path) -> None:
    row = dict(_DEV)
    row["theme"] = "not-a-theme"
    with pytest.raises(EmbedThemeError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


def test_theme_rejects_unknown_keys(tmp_path: Path) -> None:
    row = dict(_DEV)
    row["theme"] = {**_DEV["theme"], "custom_css": "body{}"}  # type: ignore[dict-item]
    with pytest.raises(EmbedThemeError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


@pytest.mark.parametrize(
    "mutate",
    [
        {"tenant_id": "not-a-uuid"},
        {"tenant_id": 12345},
        {"tier": "staging"},
        {"signing_key_ref": "Not A Ref"},
        {"legal_root": "../etc/passwd"},
        {"legal_root": 7},
    ],
)
def test_config_field_validation(tmp_path: Path, mutate: dict[str, object]) -> None:
    row = dict(_DEV)
    row.update(mutate)
    with pytest.raises(EmbedConfigError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


def test_tenant_row_must_be_a_mapping(tmp_path: Path) -> None:
    with pytest.raises(EmbedConfigError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", ["just a string"]))  # type: ignore[list-item]


def test_partner_backend_origin_must_be_https_origin(tmp_path: Path) -> None:
    row = dict(_DEV)
    row["partner_backend_origin"] = "https://host.example/path?q=1"
    with pytest.raises(EmbedConfigError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


def test_optional_ref_present_but_blank_is_refused(tmp_path: Path) -> None:
    row = dict(_DEV)
    row.update(tier="prod", dpa_ref="   ", brand_permission_ref="brand:x")
    with pytest.raises(EmbedConfigError):
        TenantEmbedRegistry.from_yaml(_write(tmp_path / "r.yaml", [row]))


def test_missing_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(EmbedRegistryError):
        TenantEmbedRegistry.from_yaml(tmp_path / "absent.yaml")


def test_registry_must_be_a_mapping(tmp_path: Path) -> None:
    p = tmp_path / "r.yaml"
    p.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(EmbedRegistryError):
        TenantEmbedRegistry.from_yaml(p)


def test_tenants_must_be_a_list(tmp_path: Path) -> None:
    p = tmp_path / "r.yaml"
    p.write_text("registry_version: v0\ntenants: {}\n", encoding="utf-8")
    with pytest.raises(EmbedRegistryError):
        TenantEmbedRegistry.from_yaml(p)


def test_shipped_registry_is_dev_only_and_holds_no_real_partner() -> None:
    reg = load_shipped_registry()
    assert shipped_registry_path() == REPO / "infra" / "tenants" / "embed_registry.yaml"
    ids = reg.tenant_ids()
    assert len(ids) >= 1
    for tid in ids:
        cfg = reg.resolve(tid)
        assert cfg.tier == "dev", "the committed registry ships dev-tier tenants only"
        assert cfg.device_functions is False
        assert cfg.dpa_ref is None and cfg.brand_permission_ref is None
