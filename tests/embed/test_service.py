"""INT-320 — the embed service seams that the router tests do not reach
(ADR-029): the OpenBao signing-key resolver, the assembly helper, and the
fail-closed launch branches for an absent key and a ticket naming an unhosted
tenant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import yaml
from fastapi import HTTPException
from intake_api.embed.service import (
    EmbedWiring,
    MappingSigningKeys,
    OpenBaoSigningKeys,
    build_embed_service,
)
from intake_platform.embed import (
    InMemoryNonceStore,
    TenantEmbedRegistry,
    mint_launch_ticket,
)

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)
DEV = "0b6f9d2e-1111-5aaa-8bbb-000000000001"
KEY_REF = "embed/dev/signing-key"
KEY = b"a-signing-key-for-the-dev-tenant"


class _FakeSecrets:
    def __init__(self, doc: dict[str, Any] | Exception) -> None:
        self._doc = doc

    def get_kv(self, path: str) -> dict[str, Any]:
        if isinstance(self._doc, Exception):
            raise self._doc
        return self._doc


class _FakeAudit:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    async def record(
        self, *, actor: str, action: str, resource_ref: str, consent_scope: str
    ) -> None:
        self.calls.append(
            {
                "actor": actor,
                "action": action,
                "resource_ref": resource_ref,
                "consent_scope": consent_scope,
            }
        )


def _registry(tmp_path: Any) -> TenantEmbedRegistry:
    rows = [
        {
            "tenant_id": DEV,
            "tier": "dev",
            "signing_key_ref": KEY_REF,
            "legal_root": "docs/legal/embed/dev",
            "device_functions": False,
            "theme": {
                "display_name": "Önvizit Dev Partner",
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
    return TenantEmbedRegistry.from_yaml(p)


def test_openbao_resolver_reads_a_hex_key() -> None:
    resolver = OpenBaoSigningKeys(_FakeSecrets({"signing_key": KEY.hex()}))  # type: ignore[arg-type]
    assert resolver.signing_key(KEY_REF) == KEY


@pytest.mark.parametrize(
    "doc",
    [
        {"other": "field"},  # no signing_key
        {"signing_key": 123},  # not a string
        {"signing_key": "zznothex"},  # not hex
        KeyError("secret/data/embed absent"),  # path missing
    ],
)
def test_openbao_resolver_fails_closed(doc: Any) -> None:
    resolver = OpenBaoSigningKeys(_FakeSecrets(doc))  # type: ignore[arg-type]
    assert resolver.signing_key(KEY_REF) is None


def test_build_embed_service_defaults_a_nonce_store(tmp_path: Any) -> None:
    service = build_embed_service(
        _registry(tmp_path),
        MappingSigningKeys({KEY_REF: KEY}),
        launch_base_url="https://intake.app/embed/launch",
        audit=_FakeAudit(),  # type: ignore[arg-type]
    )
    result = run(service.mint(DEV, actor="dev-clinic-admin"))
    assert result.ticket
    assert result.launch_url.startswith("https://intake.app/embed/launch#ticket=")


def _service(tmp_path: Any, keys: dict[str, bytes]):  # type: ignore[no-untyped-def]
    wiring = EmbedWiring(
        registry=_registry(tmp_path),
        signing_keys=MappingSigningKeys(keys),
        launch_base_url="https://intake.app/embed/launch",
        nonce_store=InMemoryNonceStore(),
    )
    from intake_api.embed.service import EmbedService

    return EmbedService(wiring, _FakeAudit(), now_fn=lambda: NOW)  # type: ignore[arg-type]


def test_launch_without_a_key_is_service_unavailable(tmp_path: Any) -> None:
    token, _ = mint_launch_ticket(tenant_id=DEV, signing_key=KEY, now=NOW)
    service = _service(tmp_path, keys={})  # registered, but no key
    with pytest.raises(HTTPException) as exc:
        run(service.launch(token))
    assert exc.value.status_code == 503
    assert exc.value.detail == {"error": "embed_signing_key_unavailable"}


def test_launch_ticket_for_an_unhosted_tenant_is_refused(tmp_path: Any) -> None:
    token, _ = mint_launch_ticket(
        tenant_id="ffffffff-ffff-5fff-8fff-ffffffffffff", signing_key=KEY, now=NOW
    )
    service = _service(tmp_path, keys={KEY_REF: KEY})
    with pytest.raises(HTTPException) as exc:
        run(service.launch(token))
    assert exc.value.status_code == 400
    assert exc.value.detail == {"error": "embed_ticket_refused", "reason": "tenant"}


def run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)
