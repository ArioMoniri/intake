"""INT-320 — the embed handshake service (ADR-028).

Wires the DB-free core (``intake_platform.embed``) to a per-tenant signing key
from OpenBao, a single-use nonce store and the hash-chained audit log. Every
refusal is fail-closed and id-shaped; nothing clinical or personal is logged,
audited or returned (invariant 6). Secrets come only from OpenBao (invariant 14):
the signing key is resolved from the tenant's registry ``signing_key_ref`` and,
when it is not present, the surface answers 503 rather than minting a ticket
nobody could verify.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from intake_platform.consent.texts import ConsentTextCatalog
from intake_platform.embed import (
    DEFAULT_TTL_S,
    EmbedConsentDocumentSet,
    InMemoryNonceStore,
    LaunchContext,
    LaunchTicketError,
    NonceStore,
    TenantEmbedRegistry,
    TicketExpired,
    TicketMalformed,
    TicketPurposeInvalid,
    TicketReplayed,
    TicketSignatureInvalid,
    TicketTenantMismatch,
    TicketTtlTooLong,
    UnknownTenantError,
    embed_disclosure_root,
    mint_launch_ticket,
    resolve_embed_consent_documents,
    resolve_launch_context,
    unverified_tenant,
    verify_launch_ticket,
)
from intake_platform.secrets import SecretsProvider

from intake_api.audit import AuditWriter
from intake_api.errors import (
    embed_consent_unavailable,
    embed_signing_key_unavailable,
    embed_ticket_refused,
    unknown_embed_tenant,
)

__all__ = [
    "EmbedService",
    "EmbedWiring",
    "MappingSigningKeys",
    "MintResult",
    "OpenBaoSigningKeys",
    "SigningKeyResolver",
    "build_embed_service",
]

logger = logging.getLogger("intake_api.embed")

#: The audit basis for a handshake step: there is no patient consent scope at
#: this layer (the patient grants consent inside Vizite's own flow afterwards),
#: so the entry is discharged under the handshake basis, id-shaped.
_AUDIT_BASIS = "basis:embed-handshake"

_REFUSAL_CODES: dict[type[LaunchTicketError], str] = {
    TicketExpired: "expired",
    TicketReplayed: "replayed",
    TicketSignatureInvalid: "signature",
    TicketTenantMismatch: "tenant",
    TicketPurposeInvalid: "purpose",
    TicketTtlTooLong: "ttl",
    TicketMalformed: "malformed",
}


@runtime_checkable
class SigningKeyResolver(Protocol):
    """Resolve a tenant's HMAC signing key from its registry ``signing_key_ref``.
    Returns ``None`` when the key is not available, so the surface fails closed
    rather than inventing one."""

    def signing_key(self, ref: str) -> bytes | None: ...


class MappingSigningKeys:
    """A fixed ref→key map — the unit lane and any purely in-memory dev run."""

    def __init__(self, keys: dict[str, bytes]) -> None:
        self._keys = dict(keys)

    def signing_key(self, ref: str) -> bytes | None:
        return self._keys.get(ref)


class OpenBaoSigningKeys:
    """Read the tenant's signing key from OpenBao KV (invariant 14: secrets
    only from OpenBao). The ref is the registry ``signing_key_ref``; the KV
    document carries a hex ``signing_key`` field. Any failure — path absent,
    field missing or malformed — returns ``None`` (fail closed), never a
    default, and logs an id-shaped line only."""

    def __init__(self, secrets: SecretsProvider) -> None:
        self._secrets = secrets

    def signing_key(self, ref: str) -> bytes | None:
        try:
            document = self._secrets.get_kv(ref)
            material = document["signing_key"]
            if not isinstance(material, str):
                raise ValueError("signing_key is not a hex string")
            return bytes.fromhex(material)
        except Exception:  # noqa: BLE001 — fail closed; never leak the ref content
            logger.warning("embed signing key unavailable for a registered tenant")
            return None


@dataclass(frozen=True)
class EmbedWiring:
    """Everything the embed service needs, injectable for tests."""

    registry: TenantEmbedRegistry
    signing_keys: SigningKeyResolver
    launch_base_url: str
    nonce_store: NonceStore
    ttl_s: int = DEFAULT_TTL_S
    # INT-320 (follow-up): the consent catalogue the embed launch renders its
    # ``core`` service consent from — the SAME global tree a later grant binds
    # against, so what the patient reads and what is recorded cannot drift. The
    # per-tenant partner-processor disclosure lives under ``legal_base`` +
    # the tenant's ``legal_root``. Both absent → the consent step fails closed
    # (503), exactly like an unauthored legal tree elsewhere (invariant 18).
    consent_catalog: ConsentTextCatalog | None = None
    legal_base: Path | None = None


@dataclass(frozen=True)
class MintResult:
    ticket: str
    launch_url: str
    expires_at: int


class EmbedService:
    """The mint/launch handshake. Both steps audit; neither touches clinical
    data."""

    def __init__(
        self,
        wiring: EmbedWiring,
        audit: AuditWriter,
        *,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._wiring = wiring
        self._audit = audit
        self._now_fn: Callable[[], datetime] = now_fn or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        return self._now_fn()

    async def mint(self, tenant_id: str, *, actor: str) -> MintResult:
        try:
            config = self._wiring.registry.resolve(tenant_id)
        except UnknownTenantError as exc:
            raise unknown_embed_tenant() from exc
        key = self._wiring.signing_keys.signing_key(config.signing_key_ref)
        if key is None:
            raise embed_signing_key_unavailable()
        token, claims = mint_launch_ticket(
            tenant_id=tenant_id,
            signing_key=key,
            now=self._now(),
            ttl_s=self._wiring.ttl_s,
        )
        await self._audit.record(
            actor=actor,
            action="embed.ticket_minted",
            resource_ref=f"tenant:{tenant_id}",
            consent_scope=_AUDIT_BASIS,
        )
        # the ticket carries no personal data; it rides in the URL fragment, so
        # it never reaches a server access log or the browser's Referer header
        launch_url = f"{self._wiring.launch_base_url}#ticket={token}"
        return MintResult(ticket=token, launch_url=launch_url, expires_at=claims.expires_at)

    async def launch(self, ticket: str) -> LaunchContext:
        try:
            claimed_tenant = unverified_tenant(ticket)
        except LaunchTicketError as exc:
            raise embed_ticket_refused(_REFUSAL_CODES.get(type(exc), "refused")) from exc
        try:
            config = self._wiring.registry.resolve(claimed_tenant)
        except UnknownTenantError as exc:
            # a ticket naming a tenant we do not host is a refused ticket, not a
            # 404 that would confirm which tenants exist
            raise embed_ticket_refused("tenant") from exc
        key = self._wiring.signing_keys.signing_key(config.signing_key_ref)
        if key is None:
            raise embed_signing_key_unavailable()
        try:
            claims = verify_launch_ticket(
                ticket,
                expected_tenant_id=claimed_tenant,
                signing_key=key,
                now=self._now(),
                nonce_store=self._wiring.nonce_store,
            )
        except LaunchTicketError as exc:
            raise embed_ticket_refused(_REFUSAL_CODES.get(type(exc), "refused")) from exc
        context = resolve_launch_context(claims, config)
        await self._audit.record(
            actor=f"embed:{claimed_tenant}",
            action="embed.launched",
            resource_ref=f"embed_launch:{claims.nonce}",
            consent_scope=_AUDIT_BASIS,
        )
        return context

    async def consent_documents(
        self, tenant_id: str, consent_doc_set_id: str
    ) -> EmbedConsentDocumentSet:
        """Render the branded intake's consent document set (the launch step
        after the handshake). ``tenant_id`` and ``consent_doc_set_id`` are the
        public ids the launch returned; they must name the same registered
        tenant, and the set fails closed (503) when its texts are unauthored —
        never an empty consent shown to a patient (invariant 18). No ticket is
        needed and none is consumed: the doc set carries only public consent
        copy, and the patient still grants through Vizite's own hash-bound flow.
        """
        try:
            config = self._wiring.registry.resolve(tenant_id)
        except UnknownTenantError as exc:
            raise unknown_embed_tenant() from exc
        # the doc set id must match the one bound to this tenant's row — a
        # mismatch is a refused request, not a peek at another tenant's set
        if config.theme.consent_doc_set_id != consent_doc_set_id:
            raise embed_consent_unavailable()
        catalog = self._wiring.consent_catalog
        legal_base = self._wiring.legal_base
        if catalog is None or legal_base is None:
            # the render is unconfigured (no consent catalogue wired) — fail
            # closed rather than answer with no documents
            raise embed_consent_unavailable()
        doc_set = resolve_embed_consent_documents(
            doc_set_id=consent_doc_set_id,
            consent_catalog=catalog,
            disclosure_root=embed_disclosure_root(config.legal_root, legal_base),
        )
        if not doc_set.documents:
            raise embed_consent_unavailable()
        await self._audit.record(
            actor=f"embed:{tenant_id}",
            action="embed.consent_rendered",
            resource_ref=f"tenant:{tenant_id}",
            consent_scope=_AUDIT_BASIS,
        )
        return doc_set


def build_embed_service(
    registry: TenantEmbedRegistry,
    signing_keys: SigningKeyResolver,
    *,
    launch_base_url: str,
    audit: AuditWriter,
    nonce_store: NonceStore | None = None,
    ttl_s: int = DEFAULT_TTL_S,
    consent_catalog: ConsentTextCatalog | None = None,
    legal_base: Path | None = None,
) -> EmbedService:
    """Assemble an :class:`EmbedService`. The default nonce store is the
    process-local one — a production deployment needs a SHARED store so
    single-use holds across API replicas (flagged awaiting-human, not stubbed).
    ``consent_catalog``/``legal_base`` wire the consent render; without them the
    consent step fails closed (503).
    """
    wiring = EmbedWiring(
        registry=registry,
        signing_keys=signing_keys,
        launch_base_url=launch_base_url,
        nonce_store=nonce_store if nonce_store is not None else InMemoryNonceStore(),
        ttl_s=ttl_s,
        consent_catalog=consent_catalog,
        legal_base=legal_base,
    )
    return EmbedService(wiring, audit)
