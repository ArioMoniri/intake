"""INT-320 — the tenant embed registry (ADR-028).

A partner embed tenant is a REGISTERED row addressed only by ``tenant_id`` —
the same "second list, out-of-band, fail-closed, zero rows" shape ADR-026 gave
connector destinations. Branding is constrained data: six-digit hex colours, a
bounded display name and id-shaped references to an asset and a consent
document set. Partner-supplied markup, URLs and schemes are refused at load, so
the embed cannot become an injection or SSRF surface.

``device_functions`` may not be enabled here (ADR-020: no CE certificate). A
``prod`` row is refused unless its recorded human facts — the executed DPA and
the brand-use permission — are present, so the committed file ships with dev
tenants only and every real partner is a reviewed commit that a human, not an
engineer, fills in.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

__all__ = [
    "EmbedConfigError",
    "EmbedRegistryError",
    "EmbedTheme",
    "EmbedThemeError",
    "TenantEmbedConfig",
    "TenantEmbedRegistry",
    "UnknownTenantError",
    "load_shipped_registry",
    "shipped_registry_path",
]

Tier = Literal["dev", "prod"]

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_ID_REF = re.compile(r"^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")
_VAULT_REF = re.compile(r"^[a-z0-9]([a-z0-9._/-]*[a-z0-9])?$")
_DISPLAY_MAX = 80


class EmbedRegistryError(Exception):
    """Base for every embed-registry load failure."""


class EmbedThemeError(EmbedRegistryError):
    """A theme field is not the constrained shape the schema allows."""


class EmbedConfigError(EmbedRegistryError):
    """A tenant row is structurally invalid or fails a fail-closed rule."""


class UnknownTenantError(EmbedRegistryError, KeyError):
    """No registered embed tenant matches the requested id (fail closed)."""


def _require_hex(name: str, value: object) -> str:
    if not isinstance(value, str) or not _HEX_COLOR.match(value):
        raise EmbedThemeError(f"{name} must be a #RRGGBB hex colour")
    return value


def _require_id_ref(name: str, value: object) -> str:
    if not isinstance(value, str) or ".." in value or not _ID_REF.match(value):
        raise EmbedThemeError(f"{name} must be an id-shaped reference (no url, scheme or path)")
    return value


def _require_display_name(value: object) -> str:
    if not isinstance(value, str):
        raise EmbedThemeError("display_name must be a string")
    if not value.strip() or len(value) > _DISPLAY_MAX:
        raise EmbedThemeError(f"display_name must be 1..{_DISPLAY_MAX} non-blank characters")
    if any(ch in value for ch in "<>{}") or any(ord(ch) < 0x20 for ch in value):
        raise EmbedThemeError("display_name must not contain markup or control characters")
    return value


def _require_locale(value: object) -> str:
    if not isinstance(value, str) or not re.match(r"^[a-z]{2}(-[A-Z]{2})?$", value):
        raise EmbedThemeError("locale must be a BCP-47 language (e.g. 'tr' or 'tr-TR')")
    return value


@dataclass(frozen=True)
class EmbedTheme:
    """A tenant's constrained white-label branding — data, never markup."""

    display_name: str
    locale: str
    primary_color: str
    accent_color: str
    logo_asset_id: str
    consent_doc_set_id: str

    @classmethod
    def from_mapping(cls, raw: object) -> EmbedTheme:
        if not isinstance(raw, dict):
            raise EmbedThemeError("theme must be a mapping")
        allowed = {
            "display_name",
            "locale",
            "primary_color",
            "accent_color",
            "logo_asset_id",
            "consent_doc_set_id",
        }
        extra = set(raw) - allowed
        if extra:
            raise EmbedThemeError(f"theme carries unknown keys: {sorted(extra)}")
        return cls(
            display_name=_require_display_name(raw.get("display_name")),
            locale=_require_locale(raw.get("locale")),
            primary_color=_require_hex("primary_color", raw.get("primary_color")),
            accent_color=_require_hex("accent_color", raw.get("accent_color")),
            logo_asset_id=_require_id_ref("logo_asset_id", raw.get("logo_asset_id")),
            consent_doc_set_id=_require_id_ref("consent_doc_set_id", raw.get("consent_doc_set_id")),
        )


@dataclass(frozen=True)
class TenantEmbedConfig:
    """One registered embed tenant."""

    tenant_id: str
    tier: Tier
    theme: EmbedTheme
    signing_key_ref: str
    legal_root: str
    device_functions: bool
    dpa_ref: str | None
    brand_permission_ref: str | None
    partner_backend_origin: str | None

    @classmethod
    def from_mapping(cls, raw: object) -> TenantEmbedConfig:
        if not isinstance(raw, dict):
            raise EmbedConfigError("a tenant row must be a mapping")
        tenant_id = raw.get("tenant_id")
        if not isinstance(tenant_id, str):
            raise EmbedConfigError("tenant_id must be a string")
        try:
            uuid.UUID(tenant_id)
        except ValueError as exc:
            raise EmbedConfigError("tenant_id must be a uuid") from exc

        tier = raw.get("tier")
        if tier not in ("dev", "prod"):
            raise EmbedConfigError("tier must be 'dev' or 'prod'")

        device_functions = raw.get("device_functions", False)
        if device_functions is not False:
            # ADR-020: no embed tenant has a CE certificate here, and this
            # registry has no field that could record one, so the only lawful
            # value is off. A row asking for it on is refused, not honoured.
            raise EmbedConfigError("device_functions cannot be enabled for an embed tenant")

        signing_key_ref = raw.get("signing_key_ref")
        if not isinstance(signing_key_ref, str) or not _VAULT_REF.match(signing_key_ref):
            raise EmbedConfigError("signing_key_ref must be an OpenBao-path-shaped reference")

        legal_root = raw.get("legal_root")
        if (
            not isinstance(legal_root, str)
            or ".." in legal_root
            or not _VAULT_REF.match(legal_root)
        ):
            raise EmbedConfigError("legal_root must be a repo-relative path (no '..')")

        dpa_ref = _optional_ref("dpa_ref", raw.get("dpa_ref"))
        brand_permission_ref = _optional_ref(
            "brand_permission_ref", raw.get("brand_permission_ref")
        )
        partner_backend_origin = _optional_origin(raw.get("partner_backend_origin"))

        if tier == "prod" and not (dpa_ref and brand_permission_ref):
            # fail closed: a live partner tenant costs recorded human facts,
            # exactly like a connector destination (ADR-026).
            raise EmbedConfigError(
                "a prod embed tenant requires both dpa_ref and brand_permission_ref"
            )

        return cls(
            tenant_id=tenant_id,
            tier=tier,
            theme=EmbedTheme.from_mapping(raw.get("theme")),
            signing_key_ref=signing_key_ref,
            legal_root=legal_root,
            device_functions=False,
            dpa_ref=dpa_ref,
            brand_permission_ref=brand_permission_ref,
            partner_backend_origin=partner_backend_origin,
        )


def _optional_ref(name: str, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise EmbedConfigError(f"{name}, when present, must be a non-empty reference")
    return value


def _optional_origin(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.match(r"^https://[a-z0-9.-]+(:[0-9]{1,5})?$", value):
        raise EmbedConfigError("partner_backend_origin must be an https origin (scheme+host only)")
    return value


class TenantEmbedRegistry:
    """The loaded, validated set of embed tenants — a lookup by id, fail closed."""

    def __init__(self, tenants: dict[str, TenantEmbedConfig]) -> None:
        self._tenants = tenants

    @classmethod
    def from_yaml(cls, path: Path) -> TenantEmbedRegistry:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise EmbedRegistryError(f"embed registry not found: {path}") from exc
        if not isinstance(document, dict):
            raise EmbedRegistryError("embed registry must be a mapping")
        rows = document.get("tenants", [])
        if not isinstance(rows, list):
            raise EmbedRegistryError("'tenants' must be a list")
        tenants: dict[str, TenantEmbedConfig] = {}
        for row in rows:
            config = TenantEmbedConfig.from_mapping(row)
            if config.tenant_id in tenants:
                raise EmbedConfigError(f"duplicate tenant id {config.tenant_id}")
            tenants[config.tenant_id] = config
        return cls(tenants)

    def resolve(self, tenant_id: str) -> TenantEmbedConfig:
        try:
            return self._tenants[tenant_id]
        except KeyError as exc:
            raise UnknownTenantError(tenant_id) from exc

    def tenant_ids(self) -> tuple[str, ...]:
        return tuple(self._tenants)


def shipped_registry_path() -> Path:
    """The committed registry file (INT-320)."""
    return Path(__file__).resolve().parents[5] / "infra" / "tenants" / "embed_registry.yaml"


def load_shipped_registry() -> TenantEmbedRegistry:
    """Load the committed ``infra/tenants/embed_registry.yaml`` (dev tenants only)."""
    return TenantEmbedRegistry.from_yaml(shipped_registry_path())
