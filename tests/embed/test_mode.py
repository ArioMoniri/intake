"""INT-322 — the intake mode bound inside the embed launch ticket (ADR-029).

The white-label handshake (INT-320) gains an intake DEPTH: the mobile app's two
intakes, ``hastanede`` (detailed / "Detaylı") and ``brief`` (quick / "Hızlı").
The partner chooses it at mint; it is bound INSIDE the signed ticket so it can
neither be tampered nor re-supplied at launch; and the tenant gates which modes
it may offer. The mode is a UI-depth flag, never personal data (invariant 6).

What this pins:
- mint with each mode round-trips through the SIGNED ticket to the launch;
- the default mode is ``brief`` when the partner omits it;
- a mode a tenant does not allow is refused at mint, fail closed;
- the mode comes ONLY from the signed claims — it cannot be injected at launch;
- an unknown mode string is refused by the schema (enum) and by the ticket core.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import yaml
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from fastapi import HTTPException
from intake_api.embed.schemas import LaunchResponse, MintRequest, ThemeOut
from intake_api.embed.service import EmbedService, EmbedWiring, MappingSigningKeys
from intake_platform.embed import (
    DEFAULT_INTAKE_MODE,
    INTAKE_MODES,
    PURPOSE,
    InMemoryNonceStore,
    TenantEmbedRegistry,
    TicketMalformed,
    TicketModeInvalid,
    load_shipped_registry,
    mint_launch_ticket,
    resolve_launch_context,
    verify_launch_ticket,
)
from intake_platform.embed.registry import EmbedConfigError
from pydantic import ValidationError

NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=UTC)
DEV_TENANT = "0b6f9d2e-1111-5aaa-8bbb-000000000001"
DEV_KEY_REF = "embed/dev-partner-alpha/signing-key"
TEST_KEY = b"unit-lane-embed-signing-key-32byte"
LAUNCH_BASE = "https://intake.app/embed/launch"

_UNSET = object()


# --- the closed enum -------------------------------------------------------------


def test_the_closed_enum_is_exactly_the_two_modes() -> None:
    assert INTAKE_MODES == frozenset({"hastanede", "brief"})
    assert DEFAULT_INTAKE_MODE == "brief"


# --- schema (MintRequest / LaunchResponse) ---------------------------------------


def test_mint_request_defaults_to_brief() -> None:
    assert MintRequest(tenant_id=DEV_TENANT).mode == "brief"


@pytest.mark.parametrize("mode", ["hastanede", "brief"])
def test_mint_request_accepts_each_mode(mode: str) -> None:
    assert MintRequest(tenant_id=DEV_TENANT, mode=mode).mode == mode  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["detayli", "hizli", "detailed", "quick", "", "HASTANEDE", 123])
def test_mint_request_rejects_an_unknown_mode(bad: object) -> None:
    with pytest.raises(ValidationError):
        MintRequest(tenant_id=DEV_TENANT, mode=bad)  # type: ignore[arg-type]


def test_mint_request_still_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MintRequest(tenant_id=DEV_TENANT, mode="brief", surprise="x")  # type: ignore[call-arg]


def test_launch_response_carries_mode() -> None:
    resp = LaunchResponse(
        tenant_id=DEV_TENANT,
        theme=ThemeOut(
            display_name="Önvizit Dev Partner",
            locale="tr",
            primary_color="#0B5FFF",
            accent_color="#00303C",
            logo_asset_id="embed.dev.logo",
        ),
        consent_doc_set_id="embed.dev",
        device_functions=False,
        mode="hastanede",
    )
    assert resp.mode == "hastanede"


# --- ticket core -----------------------------------------------------------------


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _hand_signed(*, mode: object, exp: int = 9) -> str:
    """A token signed under the dev key but carrying an arbitrary ``mode`` — to
    reach the post-signature validation a genuine mint would never emit."""
    head = _b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64u(
        json.dumps(
            {
                "tid": DEV_TENANT,
                "nonce": "n",
                "iat": 0,
                "exp": exp,
                "purpose": PURPOSE,
                "mode": mode,
            }
        ).encode()
    )
    sig = _b64u(hmac.new(TEST_KEY, f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


@pytest.mark.parametrize("mode", ["hastanede", "brief"])
def test_ticket_binds_and_round_trips_mode(mode: str) -> None:
    token, claims = mint_launch_ticket(
        tenant_id=DEV_TENANT, signing_key=TEST_KEY, now=NOW, mode=mode
    )
    assert claims.mode == mode
    verified = verify_launch_ticket(
        token,
        expected_tenant_id=DEV_TENANT,
        signing_key=TEST_KEY,
        now=NOW,
        nonce_store=InMemoryNonceStore(),
    )
    assert verified.mode == mode


def test_default_mode_is_brief_when_omitted() -> None:
    _token, claims = mint_launch_ticket(tenant_id=DEV_TENANT, signing_key=TEST_KEY, now=NOW)
    assert claims.mode == "brief"


def test_mode_rides_inside_the_signed_payload() -> None:
    token, _ = mint_launch_ticket(
        tenant_id=DEV_TENANT, signing_key=TEST_KEY, now=NOW, mode="hastanede"
    )
    _head, payload_b64, _sig = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    assert payload["mode"] == "hastanede"
    # the closed claim set grows by exactly one — still no PHI, only ids/flags
    assert set(payload) == {"tid", "nonce", "iat", "exp", "purpose", "mode"}


def test_mint_refuses_an_unknown_mode() -> None:
    with pytest.raises(TicketModeInvalid):
        mint_launch_ticket(tenant_id=DEV_TENANT, signing_key=TEST_KEY, now=NOW, mode="detayli")


def test_forged_unknown_mode_is_refused_at_verify() -> None:
    # a token signed under the key but carrying a mode outside the closed set (a
    # leaked-key forgery) is still refused — defence in depth past the schema
    with pytest.raises(TicketModeInvalid):
        verify_launch_ticket(
            _hand_signed(mode="evil"),
            expected_tenant_id=DEV_TENANT,
            signing_key=TEST_KEY,
            now=NOW,
            nonce_store=InMemoryNonceStore(),
        )


def test_mode_that_is_not_a_string_fails_closed() -> None:
    with pytest.raises(TicketMalformed):
        verify_launch_ticket(
            _hand_signed(mode=7),
            expected_tenant_id=DEV_TENANT,
            signing_key=TEST_KEY,
            now=NOW,
            nonce_store=InMemoryNonceStore(),
        )


# --- registry allowed_modes ------------------------------------------------------


def _registry(tmp_path: Any, *, allowed_modes: object = _UNSET) -> TenantEmbedRegistry:
    row: dict[str, object] = {
        "tenant_id": DEV_TENANT,
        "tier": "dev",
        "signing_key_ref": DEV_KEY_REF,
        "legal_root": "docs/legal/embed/dev-partner-alpha",
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
    if allowed_modes is not _UNSET:
        row["allowed_modes"] = allowed_modes
    p = tmp_path / "r.yaml"
    p.write_text(yaml.safe_dump({"registry_version": "v0-dev", "tenants": [row]}), encoding="utf-8")
    return TenantEmbedRegistry.from_yaml(p)


def test_allowed_modes_defaults_to_both_when_absent(tmp_path: Any) -> None:
    cfg = _registry(tmp_path).resolve(DEV_TENANT)
    assert cfg.allowed_modes == INTAKE_MODES


def test_allowed_modes_explicit_subset(tmp_path: Any) -> None:
    cfg = _registry(tmp_path, allowed_modes=["brief"]).resolve(DEV_TENANT)
    assert cfg.allowed_modes == frozenset({"brief"})


@pytest.mark.parametrize("bad", [["detayli"], ["brief", "unknown"], "brief", 5, [1]])
def test_allowed_modes_rejects_bad_values(tmp_path: Any, bad: object) -> None:
    with pytest.raises(EmbedConfigError):
        _registry(tmp_path, allowed_modes=bad)


def test_allowed_modes_rejects_empty_list(tmp_path: Any) -> None:
    with pytest.raises(EmbedConfigError):
        _registry(tmp_path, allowed_modes=[])


# --- launch resolution -----------------------------------------------------------


@pytest.mark.parametrize("mode", ["hastanede", "brief"])
def test_resolve_launch_context_carries_mode(tmp_path: Any, mode: str) -> None:
    cfg = _registry(tmp_path).resolve(DEV_TENANT)
    _token, claims = mint_launch_ticket(
        tenant_id=DEV_TENANT, signing_key=TEST_KEY, now=NOW, mode=mode
    )
    ctx = resolve_launch_context(claims, cfg)
    assert ctx.mode == mode


# --- service (gating + forged-mode mapping) --------------------------------------


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


def _service(registry: TenantEmbedRegistry, keys: dict[str, bytes]) -> EmbedService:
    wiring = EmbedWiring(
        registry=registry,
        signing_keys=MappingSigningKeys(keys),
        launch_base_url=LAUNCH_BASE,
        nonce_store=InMemoryNonceStore(),
    )
    return EmbedService(wiring, _FakeAudit(), now_fn=lambda: NOW)  # type: ignore[arg-type]


def run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


def test_service_mint_rejects_a_disallowed_mode(tmp_path: Any) -> None:
    service = _service(_registry(tmp_path, allowed_modes=["brief"]), {DEV_KEY_REF: TEST_KEY})
    with pytest.raises(HTTPException) as exc:
        run(service.mint(DEV_TENANT, actor="dev-clinic-admin", mode="hastanede"))
    assert exc.value.status_code == 400
    assert exc.value.detail == {"error": "embed_mode_not_allowed"}


def test_service_mint_allows_a_permitted_mode(tmp_path: Any) -> None:
    service = _service(_registry(tmp_path, allowed_modes=["brief"]), {DEV_KEY_REF: TEST_KEY})
    result = run(service.mint(DEV_TENANT, actor="dev-clinic-admin", mode="brief"))
    assert result.ticket


def test_service_launch_refuses_a_forged_mode(tmp_path: Any) -> None:
    service = _service(_registry(tmp_path), {DEV_KEY_REF: TEST_KEY})
    with pytest.raises(HTTPException) as exc:
        run(service.launch(_hand_signed(mode="evil")))
    assert exc.value.status_code == 400
    assert exc.value.detail == {"error": "embed_ticket_refused", "reason": "mode"}


# --- router (over the real app) --------------------------------------------------


def _wiring() -> EmbedWiring:
    return EmbedWiring(
        registry=load_shipped_registry(),
        signing_keys=MappingSigningKeys({DEV_KEY_REF: TEST_KEY}),
        launch_base_url=LAUNCH_BASE,
        nonce_store=InMemoryNonceStore(),
    )


@pytest.fixture()
def embed_harness(tmp_path: Any) -> Iterator[ApiHarness]:
    yield from build_harness(
        tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN, embed=_wiring()
    )


@pytest.mark.parametrize("mode", ["hastanede", "brief"])
def test_mint_then_launch_round_trips_the_mode(embed_harness: ApiHarness, mode: str) -> None:
    minted = embed_harness.client.post(
        "/embed/v1/launch-tickets",
        json={"tenant_id": DEV_TENANT, "mode": mode},
        headers=embed_harness.admin(),
    )
    assert minted.status_code == 200, minted.text
    launched = embed_harness.client.post(
        "/embed/v1/launch", json={"ticket": minted.json()["ticket"]}
    )
    assert launched.status_code == 200, launched.text
    assert launched.json()["mode"] == mode


def test_mint_defaults_to_brief_over_the_app(embed_harness: ApiHarness) -> None:
    minted = embed_harness.client.post(
        "/embed/v1/launch-tickets", json={"tenant_id": DEV_TENANT}, headers=embed_harness.admin()
    )
    assert minted.status_code == 200, minted.text
    launched = embed_harness.client.post(
        "/embed/v1/launch", json={"ticket": minted.json()["ticket"]}
    )
    assert launched.json()["mode"] == "brief"


def test_mode_cannot_be_injected_at_launch(embed_harness: ApiHarness) -> None:
    # minted as brief; the launch body cannot carry a mode (extra=forbid) and the
    # resolved mode is whatever was SIGNED, never re-supplied at the door
    minted = embed_harness.client.post(
        "/embed/v1/launch-tickets",
        json={"tenant_id": DEV_TENANT, "mode": "brief"},
        headers=embed_harness.admin(),
    )
    ticket = minted.json()["ticket"]
    injected = embed_harness.client.post(
        "/embed/v1/launch", json={"ticket": ticket, "mode": "hastanede"}
    )
    assert injected.status_code == 422  # LaunchRequest forbids the extra field
    # the rejected request never consumed the single-use nonce; the honest
    # launch still works and resolves the SIGNED mode
    launched = embed_harness.client.post("/embed/v1/launch", json={"ticket": ticket})
    assert launched.status_code == 200, launched.text
    assert launched.json()["mode"] == "brief"


def test_router_rejects_an_unknown_mode_at_mint(embed_harness: ApiHarness) -> None:
    resp = embed_harness.client.post(
        "/embed/v1/launch-tickets",
        json={"tenant_id": DEV_TENANT, "mode": "detayli"},
        headers=embed_harness.admin(),
    )
    assert resp.status_code == 422  # the schema's closed enum
