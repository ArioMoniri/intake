"""INT-320 — resolving a verified ticket to a launch context (ADR-028).

The launch context is what the branded intake needs to start: the tenant's
theme and the id of the consent document set the patient must be shown. It
carries NO clinical or personal data, and ``device_functions`` is always off.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from intake_platform.embed.launch import LaunchContext, resolve_launch_context
from intake_platform.embed.registry import TenantEmbedConfig, TenantEmbedRegistry
from intake_platform.embed.tickets import mint_launch_ticket

TENANT = "0b6f9d2e-1111-5aaa-8bbb-000000000001"
NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)


def _config(tmp_path: Path) -> TenantEmbedConfig:
    rows = [
        {
            "tenant_id": TENANT,
            "tier": "dev",
            "signing_key_ref": "embed/dev/signing-key",
            "legal_root": "docs/legal/embed/dev-partner-alpha",
            "device_functions": False,
            "theme": {
                "display_name": "Vizite Dev Partner",
                "locale": "tr",
                "primary_color": "#0B5FFF",
                "accent_color": "#00303C",
                "logo_asset_id": "embed.dev.logo",
                "consent_doc_set_id": "embed.dev",
            },
        }
    ]
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump({"registry_version": "v0-dev", "tenants": rows}), encoding="utf-8")
    return TenantEmbedRegistry.from_yaml(p).resolve(TENANT)


def test_resolve_returns_theme_and_consent_reference(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    _token, claims = mint_launch_ticket(tenant_id=TENANT, signing_key=b"k" * 32, now=NOW)
    ctx = resolve_launch_context(claims, cfg)
    assert isinstance(ctx, LaunchContext)
    assert ctx.tenant_id == TENANT
    assert ctx.display_name == "Vizite Dev Partner"
    assert ctx.locale == "tr"
    assert ctx.primary_color == "#0B5FFF"
    assert ctx.consent_doc_set_id == "embed.dev"
    assert ctx.device_functions is False


def test_claims_tenant_must_match_the_config(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    _token, claims = mint_launch_ticket(
        tenant_id="ffffffff-ffff-5fff-8fff-ffffffffffff", signing_key=b"k" * 32, now=NOW
    )
    with pytest.raises(ValueError):
        resolve_launch_context(claims, cfg)
